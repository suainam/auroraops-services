import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import requests

try:
    import ddddocr
    HAS_DDDDOCR = True
except ImportError:
    HAS_DDDDOCR = False

# ── captcha task types that text OCR cannot solve ──
# https://github.com/suainam/ip2free + API reverse engineering
SKIP_CAPTCHA_CODES = {
    "client_click",      # 点选验证码 – 需要点击坐标序列
    "manual_review",     # 人工审核 – 需站点管理员后台操作
    "register",           # 邀请注册任务 – 需新用户注册
    "register_one_three", # 邀请1人送3天
    "register_three",     # 邀请3人送30天
}

CONFIG_DIR = Path("/opt/ip2free")
CONFIG_FILE = CONFIG_DIR / "config.json"
NODES_FILE = CONFIG_DIR / "nodes.json"
LOCK_FILE = CONFIG_DIR / ".agent.lock"
MAX_API_ATTEMPTS = 3
RETRY_DELAYS = (2, 4)

HEADERS = {
    "webname": "IP2FREE",
    "domain": "www.ip2free.com",
    "lang": "cn",
    "referer": "https://www.ip2free.com/",
    "origin": "https://www.ip2free.com",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "content-type": "text/plain;charset=UTF-8",
}


class AuthError(Exception):
    pass


class SchemaError(Exception):
    pass


class TransientExhausted(Exception):
    pass


def load_config(config_file=CONFIG_FILE):
    config_file = Path(config_file)
    if not config_file.exists():
        print(f"Config not found: {config_file}")
        return {}
    try:
        with config_file.open() as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        raise SchemaError("config contains invalid JSON") from exc
    if not isinstance(config, dict):
        raise SchemaError("config must be a JSON object")
    return config


def acquire_lock():
    if LOCK_FILE.exists():
        pid = LOCK_FILE.read_text().strip()
        if pid and os.path.exists(f"/proc/{pid}"):
            print(f"Lock held by PID {pid}, skipping")
            return False
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock():
    LOCK_FILE.unlink(missing_ok=True)


class IP2FreeClient:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.token = None
        self.ocr = None

    def login(self):
        result = self._post("/account/login", {"email": self.email, "password": self.password})
        self.token = result.get("data", {}).get("token") or self.session.cookies.get("Mall-Token")
        if not self.token:
            raise AuthError("Login failed: no token")
        self.session.headers["x-token"] = self.token
        self.session.cookies.set("Mall-Token", self.token, domain="www.ip2free.com", path="/")
        print(f"Logged in: {self.email}")

    def _post(self, endpoint, data=None, allow_error=False, timeout=30):
        url = f"https://api.ip2free.com/api{endpoint}"
        for attempt in range(MAX_API_ATTEMPTS):
            try:
                resp = self.session.post(url, json=data or {}, timeout=timeout)
                if resp.status_code in (401, 403):
                    raise AuthError(f"Authentication rejected by {endpoint}")
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt == MAX_API_ATTEMPTS - 1:
                        raise TransientExhausted(
                            f"{endpoint} unavailable after {MAX_API_ATTEMPTS} attempts"
                        )
                    retry_after = resp.headers.get("Retry-After", "")
                    delay = RETRY_DELAYS[attempt]
                    if retry_after.isdigit():
                        delay = max(delay, int(retry_after))
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                try:
                    result = resp.json()
                except (ValueError, requests.exceptions.JSONDecodeError) as exc:
                    raise SchemaError(f"Invalid JSON from {endpoint}") from exc
                if not isinstance(result, dict):
                    raise SchemaError(f"Invalid response schema from {endpoint}")
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                if attempt == MAX_API_ATTEMPTS - 1:
                    raise TransientExhausted(
                        f"{endpoint} unavailable after {MAX_API_ATTEMPTS} attempts"
                    ) from exc
                time.sleep(RETRY_DELAYS[attempt])
        if result.get("code") != 0 and not allow_error:
            message = result.get("msg", f"API error: {endpoint}")
            if endpoint == "/account/login":
                raise AuthError(message)
            raise SchemaError(message)
        return result

    def _get_captcha_image(self):
        for attempt in range(3):
            resp = self.session.get(
                f"https://api.ip2free.com/api/account/captcha",
                timeout=30,
            )
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "image" in ctype or ctype.startswith("application/octet"):
                return resp.content
            if attempt < 2:
                print(f"  captcha response content-type={ctype}, retrying...")
                time.sleep(1)
        raise ValueError("captcha endpoint did not return an image after 3 attempts")

    def _solve_captcha(self, image_bytes):
        from PIL import Image, ImageEnhance, ImageFilter

        img = Image.open(BytesIO(image_bytes)).convert("L")
        img = img.filter(ImageFilter.SHARPEN)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        buf = BytesIO()
        img.save(buf, format="PNG")
        if self.ocr is None:
            self.ocr = ddddocr.DdddOcr(show_ad=False)
        return self.ocr.classification(buf.getvalue())

    def _submit_captcha(self, code):
        result = self._post("/account/checkCaptcha", {"code": code}, allow_error=True)
        return result.get("code") == 0

    def claim_rewards(self):
        task_data = self._post("/account/taskList")
        tasks = task_data.get("data", {}).get("list", []) or []
        claimed = 0
        for t in tasks:
            if t.get("is_finished") == 1:
                continue
            code = t.get("task_code", "")
            name = t.get("task_name", "unknown")
            tid = t.get("id")
            if not tid:
                continue
            r = self._post("/account/finishTask", {"id": tid}, allow_error=True)
            resp_code = r.get("code", -999)
            resp_msg = r.get("msg", "")
            if resp_code == 0:
                print(f"  Claimed: {name} (code={code})")
                claimed += 1
            elif resp_code == -1 and "invalid" in resp_msg:
                print(f"  Captcha needed: {name} (code={code})")
                if code in SKIP_CAPTCHA_CODES:
                    print(f"  SKIP - {code} requires manual action (click/review/referral)")
                    continue
                if not HAS_DDDDOCR:
                    print(f"  SKIP - ddddocr not installed, install with: pip install ddddocr")
                    continue
                try:
                    img = self._get_captcha_image()
                    captcha_text = self._solve_captcha(img)
                    print(f"  OCR result: [{captcha_text}]")
                    if not captcha_text:
                        print(f"  OCR returned empty, skipping")
                        continue
                    if self._submit_captcha(captcha_text):
                        print(f"  Captcha accepted, task should auto-complete")
                        r2 = self._post("/account/finishTask", {"id": tid}, allow_error=True)
                        if r2.get("code") == 0:
                            print(f"  Claimed after captcha: {name}")
                            claimed += 1
                        else:
                            print(f"  finishTask after captcha: {r2.get('msg','')}")
                    else:
                        print(f"  Captcha rejected (OCR wrong), tried: {captcha_text}")
                        time.sleep(2)
                except Exception as e:
                    print(f"  Captcha flow failed: {e}")
            else:
                print(f"  Claim failed: {name} (code={code}) - {resp_msg}")
        print(f"Claimed {claimed} rewards")
        return claimed

    def fetch_free_proxies(self):
        proxies = []
        page = 1
        while True:
            result = self._post("/ip/freeList", {
                "keyword": "", "country": "", "city": "",
                "page": page, "page_size": 100,
            })
            items = result.get("data", {}).get("free_ip_list", []) or []
            if not items:
                break
            proxies.extend(self._normalize(items, "free"))
            if len(items) < 100:
                break
            page += 1
        return proxies

    def fetch_activity_proxies(self):
        proxies = []
        page = 1
        while True:
            result = self._post("/ip/taskIpList", {
                "keyword": "", "country": "", "city": "",
                "page": page, "page_size": 100,
            }, allow_error=True)
            if result.get("code") not in (0, None):
                break
            items = result.get("data", {}).get("page", {}).get("list", []) or []
            if not items:
                break
            proxies.extend(self._normalize(items, "activity"))
            if len(items) < 100:
                break
            page += 1
        return proxies

    def _normalize(self, items, source):
        out = []
        for p in items:
            node = {
                "source": source,
                "protocol": (p.get("protocol") or "socks5").lower(),
                "server": p.get("ip") or p.get("host") or "",
                "port": int(p.get("port", 0)),
                "username": p.get("username") or "",
                "password": p.get("password") or "",
                "country": p.get("country_code") or p.get("country") or "XX",
                "id": p.get("id") or p.get("task_id") or 0,
                "fetched_at": datetime.utcnow().isoformat(),
            }
            if node["server"] and node["port"]:
                out.append(node)
        return out


def validate_nodes(nodes):
    if not isinstance(nodes, list):
        raise SchemaError("nodes payload must be a list")
    if not nodes:
        raise SchemaError("nodes payload must not be empty")
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise SchemaError(f"node {index} must be an object")
        if not isinstance(node.get("server"), str) or not node["server"]:
            raise SchemaError(f"node {index} has invalid server")
        port = node.get("port")
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise SchemaError(f"node {index} has invalid port")
        if node.get("protocol") not in {"socks5", "http", "https"}:
            raise SchemaError(f"node {index} has invalid protocol")


def publish_nodes_atomic(nodes, output_file):
    validate_nodes(nodes)
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_file.parent,
            prefix=f".{output_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(nodes, temporary, indent=2, ensure_ascii=False)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())

        with temporary_path.open(encoding="utf-8") as candidate:
            validate_nodes(json.load(candidate))
        os.replace(temporary_path, output_file)
        temporary_path = None
        directory_fd = os.open(output_file.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(CONFIG_FILE))
    parser.add_argument("--output", default=str(NODES_FILE))
    args = parser.parse_args(argv)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not acquire_lock():
        return 0

    try:
        config = load_config(args.config)
        email = config.get("email") or os.environ.get("IP2FREE_EMAIL", "")
        password = config.get("password") or os.environ.get("IP2FREE_PASSWORD", "")
        if not email or not password:
            raise AuthError("IP2FREE_EMAIL and IP2FREE_PASSWORD must be set")

        client = IP2FreeClient(email, password)
        client.login()
        client.claim_rewards()

        proxies = []
        free = client.fetch_free_proxies()
        proxies.extend(free)
        print(f"Free proxies: {len(free)}")

        activity = client.fetch_activity_proxies()
        proxies.extend(activity)
        print(f"Activity proxies: {len(activity)}")

        publish_nodes_atomic(proxies, args.output)
        print(f"Total nodes written: {len(proxies)} -> {args.output}")
        return 0
    except TransientExhausted as exc:
        print(json.dumps({
            "event": "ip2free_refresh_degraded",
            "status": "degraded",
            "reason": str(exc),
            "last_good_preserved": True,
        }, sort_keys=True))
        return 0
    except (AuthError, SchemaError) as exc:
        print(f"IP2Free hard failure: {exc}", file=sys.stderr)
        return 1
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
