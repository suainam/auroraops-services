#!/usr/bin/env python3
"""
IP2Free 节点健康检查
每5分钟检测 SOCKS5 节点存活，剔除死节点
触发 update_outbounds.py 更新 Singbox outbounds
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

CONFIG_DIR = Path("/opt/ip2free")
NODES_FILE = CONFIG_DIR / "nodes.json"
ALIVE_FILE = CONFIG_DIR / "nodes_alive.json"
LOCK_FILE = CONFIG_DIR / ".health.lock"
MERGE_SCRIPT = CONFIG_DIR / "update_outbounds.py"
COOLDOWN_FILE = CONFIG_DIR / ".refresh_cooldown"
COOLDOWN_PERIOD = 1800  # 30 minutes
TIMEOUT = 5


def acquire_lock():
    if LOCK_FILE.exists():
        pid = LOCK_FILE.read_text().strip()
        if pid and os.path.exists(f"/proc/{pid}"):
            return False
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock():
    LOCK_FILE.unlink(missing_ok=True)


def check_socks5(node):
    server = node.get("server", "")
    port = node.get("port", 0)
    username = node.get("username", "")
    password = node.get("password", "")

    if not server or not port:
        return False

    try:
        import socks
        s = socks.socksocket()
        s.settimeout(TIMEOUT)
        s.set_proxy(socks.SOCKS5, server, port, username=username, password=password)
        s.connect(("8.8.8.8", 443))
        s.close()
        return True
    except ImportError:
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(TIMEOUT)
            s.connect((server, port))
            s.close()
            return True
        except Exception:
            return False
    except Exception:
        return False


def run_update():
    if MERGE_SCRIPT.exists():
        result = subprocess.run(
            [sys.executable, str(MERGE_SCRIPT)],
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.splitlines():
            print(f"  update: {line}")
        if result.stderr:
            for line in result.stderr.splitlines():
                print(f"  update err: {line}")
        return result.returncode == 0
    return False


def trigger_refresh_if_needed():
    """Start ip2free-agent when all nodes dead, with 30min cooldown."""
    now = time.time()
    if COOLDOWN_FILE.exists():
        try:
            last = float(COOLDOWN_FILE.read_text().strip())
            elapsed = now - last
            if elapsed < COOLDOWN_PERIOD:
                remaining = int(COOLDOWN_PERIOD - elapsed)
                print(f"  Refresh cooldown active ({remaining}s remaining)")
                return
        except (ValueError, OSError):
            pass

    COOLDOWN_FILE.write_text(str(now))
    print("  All nodes dead, triggering ip2free-agent refresh...")
    result = subprocess.run(
        ["systemctl", "start", "ip2free-agent.service"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0:
        print("  ip2free-agent triggered successfully")
    else:
        print(f"  Failed to trigger ip2free-agent: {result.stderr.strip()}")


def main():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not acquire_lock():
        sys.exit(0)

    try:
        if not NODES_FILE.exists():
            print(f"Nodes file not found: {NODES_FILE}")
            sys.exit(0)

        with open(NODES_FILE) as f:
            nodes = json.load(f)

        if not nodes:
            print("No nodes to check")
            sys.exit(0)

        total = len(nodes)
        alive = []
        dead = []

        for node in nodes:
            tag = f"{node.get('country','XX')}_{node.get('server','')}:{node.get('port',0)}"
            if check_socks5(node):
                alive.append(node)
            else:
                dead.append(node)
                print(f"  DEAD: {tag}")

        if alive:
            with open(ALIVE_FILE, "w") as f:
                json.dump(alive, f, indent=2, ensure_ascii=False)
            print(f"Alive: {len(alive)}/{total}")
        else:
            ALIVE_FILE.unlink(missing_ok=True)
            print(f"All {total} nodes dead")
            trigger_refresh_if_needed()

        if run_update():
            print("IP2Free outbounds updated successfully")

    finally:
        release_lock()


if __name__ == "__main__":
    main()
