"""Built-in sing-box capability probe adapter.

Runs one transient sing-box instance for one normalized node, exposes only a
loopback mixed inbound, and emits a safe Observation-compatible JSON object.
No response body or proxy credential is written to stdout.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from statistics import median
from typing import Any

CAPABILITIES = ("pure", "ai", "media", "low_rtt", "bilibili")
BASE_TARGET = "https://www.gstatic.com/generate_204"
EXIT_IP_TARGET = "https://api.ipify.org"
IPQUALITY_DEMO_TARGET = "https://ipinfo.io/widget/demo/"
IPQUALITY_CHECK_PLACE_TARGET = "https://ipinfo.check.place/"
IP_ENRICHMENT_TARGET = IPQUALITY_DEMO_TARGET
BILIBILI_HK_TW_TARGET = "https://api.bilibili.com/pgc/player/web/playurl?avid=18281381&cid=29892777&qn=0&type=&otype=json&ep_id=183799&fourk=1&fnver=0&fnval=16&module=bangumi"
NETFLIX_TARGETS = (
    "https://www.netflix.com/title/81280792",
    "https://www.netflix.com/title/70143836",
)
TARGETS = {
    "openai": "https://api.openai.com/v1/models",
    "claude": "https://api.anthropic.com/",
    "gemini": "https://generativelanguage.googleapis.com/",
}
BASE_SAMPLES = 3
LOW_RTT_P95_MS = 250.0
GEO_TTL_SECONDS = 86400.0
RISK_TTL_SECONDS = 86400.0


def exit_ip_fingerprint(value: str) -> str:
    """Persist only a stable one-way fingerprint of a valid public exit IP."""
    address = ipaddress.ip_address(value.strip())
    if not address.is_global:
        raise ValueError("exit IP must be globally routable")
    return hashlib.sha256(address.compressed.encode("ascii")).hexdigest()


def enrichment_due(
    previous: dict[str, Any],
    fingerprint: str,
    *,
    now: float,
    geo_ttl_seconds: float = GEO_TTL_SECONDS,
    risk_ttl_seconds: float = RISK_TTL_SECONDS,
) -> tuple[bool, bool]:
    """Refresh geo/risk when the exit changes or each fact's TTL expires."""
    if previous.get("exit_ip_fingerprint") != fingerprint:
        return True, True

    def expired(key: str, ttl: float) -> bool:
        value = previous.get(key)
        return (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value <= 0
            or now - float(value) >= ttl
        )

    return expired("geo_checked_at", geo_ttl_seconds), expired("risk_checked_at", risk_ttl_seconds)


def _abuser_percent(payload: dict[str, Any]) -> float | None:
    for section_name in ("company", "asn"):
        section = payload.get(section_name)
        if not isinstance(section, dict):
            continue
        raw = section.get("abuser_score")
        if not isinstance(raw, str):
            continue
        match = re.match(r"\s*(0(?:\.\d+)?|1(?:\.0+)?)", raw)
        if match:
            return float(match.group(1)) * 100.0
    return None

def ipquality_enrichment_contract(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Map xykt/IPQuality multi-database facts into safe Registry facts and pure status."""
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return "unknown", {"threat": "unknown"}

    safe: dict[str, Any] = {}
    # Country extraction
    country = data.get("country")
    if not country and isinstance(data.get("Country"), dict):
        country = data["Country"].get("IsoCode")
    if not country and isinstance(data.get("location"), dict):
        country = data["location"].get("country_code")
    if isinstance(country, str) and re.fullmatch(r"[A-Za-z]{2}", country):
        safe["country"] = country.upper()

    # Region/City extraction
    region = data.get("region") or data.get("city")
    if not region and isinstance(data.get("City"), dict):
        region = data["City"].get("Name")
    if isinstance(region, str) and region:
        safe["region"] = region[:32]

    # ASN extraction
    asn_val = data.get("asn") or {}
    asn_upper = data.get("ASN") or {}
    asn_number = None
    asn_type = ""
    if isinstance(asn_val, dict):
        raw_asn = asn_val.get("asn") or asn_val.get("AutonomousSystemNumber") or (asn_upper.get("AutonomousSystemNumber") if isinstance(asn_upper, dict) else None)
        if isinstance(raw_asn, int) and raw_asn > 0:
            asn_number = raw_asn
        elif isinstance(raw_asn, str) and raw_asn.upper().startswith("AS"):
            try:
                asn_number = int(raw_asn[2:])
            except ValueError:
                pass
        asn_type = (asn_val.get("type") or "").lower()
    elif isinstance(asn_upper, dict):
        raw_asn = asn_upper.get("AutonomousSystemNumber")
        if isinstance(raw_asn, int) and raw_asn > 0:
            asn_number = raw_asn
    if asn_number is not None:
        safe["asn"] = asn_number
    # Company & usage extraction
    company = data.get("company") if isinstance(data.get("company"), dict) else {}
    company_type = (company.get("type") or "").lower()

    privacy = data.get("privacy") if isinstance(data.get("privacy"), dict) else {}
    is_hosting = privacy.get("hosting") is True or asn_type == "hosting"
    is_isp = asn_type == "isp" or company_type == "isp"
    is_proxy = privacy.get("proxy") is True or privacy.get("tor") is True

    if is_isp:
        safe["ip_type"] = "isp"
    elif is_hosting:
        safe["ip_type"] = "hosting"
    elif asn_type:
        safe["ip_type"] = asn_type[:32]
    elif company_type:
        safe["ip_type"] = company_type[:32]

    # Threat and Pure classification (xykt/IPQuality model)
    if is_proxy:
        safe["threat"] = "high"
        return "fail", safe
    if is_hosting:
        safe["threat"] = "medium"
        return "fail", safe
    if is_isp and not is_hosting:
        safe["threat"] = "low"
        return "pass", safe

    safe["threat"] = "unknown"
    return "unknown", safe

def bilibili_hk_tw_contract(status: int | None, body: str) -> str:
    if status is None or status >= 500:
        return "unknown"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return "unknown"
    if not isinstance(payload, dict):
        return "unknown"
    code = payload.get("code")
    if code == 0:
        return "pass"
    if code == -10403:
        return "fail"
    return "unknown"


def netflix_full_unlock_contract(responses: list[tuple[int | None, str]]) -> str:
    if len(responses) < 2 or any(status is None or status >= 500 or not body for status, body in responses):
        return "unknown"
    blocked = ["Oh no!" in body for _, body in responses]
    return "fail" if all(blocked) else "pass"


def classify_http_status(status: int | None) -> str:
    """Public reachability contract: success/redirect pass; explicit blocks fail."""
    if status is None or status >= 500:
        return "unknown"
    if 200 <= status < 400:
        return "pass"
    if status in {403, 451}:
        return "fail"
    return "unknown"


def classify_api_reachability(status: int | None) -> str:
    """API auth errors prove network reachability; explicit regional block fails."""
    if status is None or status >= 500:
        return "unknown"
    if 200 <= status < 400 or status in {401, 403, 404, 405}:
        return "pass"
    if status == 451:
        return "fail"
    return "unknown"


def ai_service_contract(http_statuses: dict[str, int | None]) -> tuple[str, dict[str, str]]:
    services = {
        name: classify_api_reachability(http_statuses.get(name))
        for name in ("openai", "claude", "gemini")
    }
    passes = sum(status == "pass" for status in services.values())
    failures = sum(status == "fail" for status in services.values())
    if passes >= 2:
        return "pass", services
    if failures >= 2:
        return "fail", services
    return "unknown", services


def classify_low_rtt(samples_ms: list[float], attempts: int = BASE_SAMPLES) -> tuple[str, dict[str, float]]:
    """Require >=2/3 successful base probes; classify by p95 latency threshold."""
    valid = [value for value in samples_ms if math.isfinite(value) and value >= 0]
    success_rate = len(valid) / attempts if attempts > 0 else 0.0
    metrics: dict[str, float] = {"success_rate": success_rate}
    if not valid:
        return "unknown", metrics
    ordered = sorted(valid)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    metrics.update(
        {
            "rtt_p50": float(median(ordered)),
            "rtt_p95": float(ordered[p95_index]),
            "jitter": float(max(ordered) - min(ordered)),
        }
    )
    if len(valid) < 2 or success_rate < (2 / 3):
        return "unknown", metrics
    return ("pass" if metrics["rtt_p95"] <= LOW_RTT_P95_MS else "fail"), metrics


def capability_contract(
    *,
    alive: bool,
    http_statuses: dict[str, int | None],
    base_samples_ms: list[float],
) -> tuple[dict[str, str], dict[str, float]]:
    """Evaluate the five stable registry dimensions from non-sensitive facts."""
    low_rtt, metrics = classify_low_rtt(base_samples_ms)
    ai, _ = ai_service_contract(http_statuses)
    capabilities = {
        # No trustworthy IP-reputation source is owned by AuroraOps yet.
        "pure": "unknown",
        "ai": ai if alive else "unknown",
        "media": classify_http_status(http_statuses.get("media")) if alive else "unknown",
        "low_rtt": low_rtt if alive else "unknown",
        "bilibili": classify_http_status(http_statuses.get("bilibili")) if alive else "unknown",
    }
    return capabilities, metrics


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _required_auth(auth: Any, key: str) -> str:
    if isinstance(auth, str) and auth:
        return auth
    if isinstance(auth, dict) and isinstance(auth.get(key), str) and auth[key]:
        return auth[key]
    raise ValueError(f"missing {key} authentication")


def build_outbound(payload: dict[str, Any]) -> dict[str, Any]:
    protocol = payload.get("protocol")
    server = payload.get("server")
    port = payload.get("port")
    if not isinstance(protocol, str) or not isinstance(server, str) or not isinstance(port, int):
        raise ValueError("invalid normalized node")
    outbound: dict[str, Any] = {
        "type": protocol,
        "tag": "probe-out",
        "server": server,
        "server_port": port,
    }
    transport = payload.get("transport", {})
    if isinstance(transport, dict):
        outbound.update(transport)
    auth = payload.get("auth", "")
    if protocol in {"vless", "vmess"}:
        outbound["uuid"] = _required_auth(auth, "uuid")
    elif protocol in {"trojan", "hysteria2", "shadowsocks", "anytls"}:
        outbound["password"] = _required_auth(auth, "password")
        if protocol == "hysteria2" and isinstance(outbound.get("obfs"), dict):
            outbound["obfs"]["password"] = _required_auth(auth, "obfs_password")
    elif protocol == "tuic":
        outbound["uuid"] = _required_auth(auth, "uuid")
        outbound["password"] = _required_auth(auth, "password")
    else:
        raise ValueError("unsupported sing-box outbound protocol")
    return outbound


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))


def _probe_engine(config: dict[str, Any]) -> tuple[Path, list[str], str | None]:
    """Write one private config and return an isolated sing-box command."""
    image = os.environ.get("SINGBOX_PROBE_IMAGE", "").strip()
    config_path = (Path(os.environ.get("TMPDIR", ".")) / "sing-box-probe.json").resolve()
    _write_private_json(config_path, config)
    if image:
        requested_name = os.environ.get("SUB_STORE_PROBE_CONTAINER_NAME", "").strip()
        if requested_name and re.fullmatch(r"sub-store-capability-probe-[0-9]+-[0-9]+", requested_name):
            container_name = requested_name
        else:
            container_name = f"sub-store-capability-probe-{os.getpid()}-{int(time.time_ns() % 1_000_000_000)}"
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "host",
            "--volume",
            f"{config_path}:/tmp/sing-box-probe.json:ro",
            "--entrypoint",
            "sing-box",
            image,
            "run",
            "-c",
            "/tmp/sing-box-probe.json",
        ]
        return config_path, command, container_name
    return config_path, ["sing-box", "run", "-c", str(config_path)], None


def _wait_ready(process: subprocess.Popen[str], port: int, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _curl_text(port: int, url: str, timeout: float = 10.0) -> tuple[int | None, str]:
    completed = subprocess.run(
        [
            "curl",
            "--silent",
            "--show-error",
            "--write-out",
            "\n%{http_code}",
            "--connect-timeout",
            "5",
            "--max-time",
            str(timeout),
            "--socks5-hostname",
            f"127.0.0.1:{port}",
            url,
        ],
        text=True,
        capture_output=True,
        timeout=timeout + 2,
        check=False,
    )
    if completed.returncode != 0 or "\n" not in completed.stdout:
        return None, ""
    body, raw_status = completed.stdout.rsplit("\n", 1)
    try:
        status = int(raw_status.strip())
    except ValueError:
        return None, ""
    return (status if status > 0 else None), body[:65536]

def _curl_ipquality_text(port: int, raw_ip: str, timeout: float = 10.0) -> tuple[int | None, str]:
    """Query IP quality information through the proxy port using xykt/IPQuality multi-source endpoints."""
    endpoints = [
        (
            f"{IPQUALITY_DEMO_TARGET}{raw_ip}",
            ["-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
             "-H", "Referer: https://ipinfo.io/"]
        ),
        (
            f"{IPQUALITY_CHECK_PLACE_TARGET}{raw_ip}?lang=en",
            ["-H", "User-Agent: curl/7.88.1"]
        ),
    ]
    for url, extra_headers in endpoints:
        cmd = [
            "curl",
            "--silent",
            "--show-error",
            "--write-out",
            "\n%{http_code}",
            "--connect-timeout",
            "5",
            "--max-time",
            str(timeout),
            "--socks5-hostname",
            f"127.0.0.1:{port}",
            *extra_headers,
            url,
        ]
        completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        output = completed.stdout
        if "\n" not in output:
            continue
        body, status_str = output.rsplit("\n", 1)
        try:
            status = int(status_str.strip())
        except ValueError:
            continue
        if 200 <= status < 300 and body.strip():
            return status, body[:65536]
    return None, ""
def _curl_probe(port: int, url: str, timeout: float = 10.0) -> tuple[int | None, float | None]:
    completed = subprocess.run(
        [
            "curl",
            "--silent",
            "--show-error",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code} %{time_total}",
            "--connect-timeout",
            "5",
            "--max-time",
            str(timeout),
            "--socks5-hostname",
            f"127.0.0.1:{port}",
            url,
        ],
        text=True,
        capture_output=True,
        timeout=timeout + 2,
        check=False,
    )
    if completed.returncode != 0:
        return None, None
    try:
        raw_status, raw_seconds = completed.stdout.strip().split()
        status = int(raw_status)
        seconds = float(raw_seconds)
    except (TypeError, ValueError):
        return None, None
    if status <= 0 or not math.isfinite(seconds) or seconds < 0:
        return None, None
    return status, seconds * 1000


def run(payload: dict[str, Any]) -> dict[str, Any]:
    port = _free_port()
    raw_outbound = payload.get("outbound")
    if not isinstance(raw_outbound, dict):
        raise ValueError("probe payload requires raw sing-box outbound")
    outbound = json.loads(json.dumps(raw_outbound))
    outbound["tag"] = "probe-out"
    config = {
        "log": {"disabled": True},
        "inbounds": [
            {"type": "mixed", "tag": "probe-in", "listen": "127.0.0.1", "listen_port": port}
        ],
        "outbounds": [outbound],
        "route": {"final": "probe-out", "auto_detect_interface": True},
    }
    config_path, engine_command, probe_container = _probe_engine(config)
    process = subprocess.Popen(
        engine_command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    try:
        if not _wait_ready(process, port):
            raise RuntimeError("sing-box probe engine failed to start")
        base_results = [_curl_probe(port, BASE_TARGET) for _ in range(BASE_SAMPLES)]
        base_samples_ms = [latency for status, latency in base_results if status is not None and latency is not None]
        alive = len(base_samples_ms) >= 2
        http_statuses = {
            name: _curl_probe(port, url)[0] if alive else None
            for name, url in TARGETS.items()
        }
        capabilities, metrics = capability_contract(
            alive=alive,
            http_statuses=http_statuses,
            base_samples_ms=base_samples_ms,
        )
        _, ai_services = ai_service_contract(http_statuses)
        media_services = {"hk_tw_media": "unknown", "international_media": "unknown"}
        if alive:
            bili_status, bili_body = _curl_text(port, BILIBILI_HK_TW_TARGET)
            media_services["hk_tw_media"] = bilibili_hk_tw_contract(bili_status, bili_body)
            netflix_responses = [_curl_text(port, url) for url in NETFLIX_TARGETS]
            media_services["international_media"] = netflix_full_unlock_contract(netflix_responses)
            capabilities["bilibili"] = media_services["hk_tw_media"]
            capabilities["media"] = media_services["international_media"]
        now = time.time()
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        previous_details = context.get("details") if isinstance(context.get("details"), dict) else {}
        previous_capabilities = context.get("capabilities") if isinstance(context.get("capabilities"), dict) else {}
        details = dict(previous_details)
        details.update(ai_services)
        details.update(media_services)

        pure_candidate = context.get("pure_candidate", True) is True
        if alive and pure_candidate:
            exit_status, raw_exit_ip = _curl_text(port, EXIT_IP_TARGET)
            try:
                fingerprint = exit_ip_fingerprint(raw_exit_ip) if exit_status and 200 <= exit_status < 300 else ""
            except ValueError:
                fingerprint = ""
            if fingerprint:
                previous_fingerprint = previous_details.get("exit_ip_fingerprint")
                changed = previous_fingerprint not in {None, fingerprint}
                geo_ttl_seconds = context.get("geo_ttl_seconds", GEO_TTL_SECONDS)
                risk_ttl_seconds = context.get("risk_ttl_seconds", RISK_TTL_SECONDS)
                if not isinstance(geo_ttl_seconds, (int, float)) or isinstance(geo_ttl_seconds, bool) or geo_ttl_seconds <= 0:
                    geo_ttl_seconds = GEO_TTL_SECONDS
                if not isinstance(risk_ttl_seconds, (int, float)) or isinstance(risk_ttl_seconds, bool) or risk_ttl_seconds <= 0:
                    risk_ttl_seconds = RISK_TTL_SECONDS
                geo_due, risk_due = enrichment_due(
                    previous_details,
                    fingerprint,
                    now=now,
                    geo_ttl_seconds=float(geo_ttl_seconds),
                    risk_ttl_seconds=float(risk_ttl_seconds),
                )
                if changed:
                    details = {**ai_services, **media_services}
                details["exit_ip_fingerprint"] = fingerprint
                if geo_due or risk_due:
                    enrich_status, enrich_body = _curl_ipquality_text(port, raw_exit_ip)
                    try:
                        enrichment_payload = json.loads(enrich_body) if enrich_status and 200 <= enrich_status < 300 else {}
                    except json.JSONDecodeError:
                        enrichment_payload = {}
                    if (
                        isinstance(enrichment_payload, dict)
                        and enrichment_payload
                        and "error" not in enrichment_payload
                    ):
                        pure, enrichment = ipquality_enrichment_contract(enrichment_payload)
                        details.update(enrichment)
                        if geo_due:
                            details["geo_checked_at"] = now
                        if risk_due:
                            details["risk_checked_at"] = now
                            capabilities["pure"] = pure
                    else:
                        capabilities["pure"] = "unknown"
                elif previous_capabilities.get("pure") in {"pass", "fail"}:
                    capabilities["pure"] = previous_capabilities["pure"]
        elif alive:
            # Name/ownership hints only decide whether Pure review is worth the
            # expensive exit-IP/reputation path. They never grant Pure status.
            capabilities["pure"] = "unknown"

        return {
            "alive": alive,
            "capabilities": capabilities,
            "metrics": metrics,
            "details": details,
            "checked_at": now,
        }
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if probe_container:
            subprocess.run(
                ["docker", "rm", "-f", probe_container],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        try:
            config_path.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("probe payload must be an object")
        result = run(payload)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError):
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
