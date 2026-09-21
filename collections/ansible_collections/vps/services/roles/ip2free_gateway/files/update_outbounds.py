#!/usr/bin/env python3
"""
Generate 06_ip2free.json with IP2Free SOCKS5 outbounds + urltest group.
Singbox loads this file from its config directory and hot-reloads via SIGHUP.
"""
import json, subprocess, sys
from pathlib import Path

ALIVE_FILE = Path("/opt/ip2free/nodes_alive.json")
OUTPUT_FILE = Path("/opt/dockers/singbox/config/06_ip2free.json")

COUNTRY_FLAGS = {
    "US": "\U0001f1fa\U0001f1f8", "HK": "\U0001f1ed\U0001f1f0", "JP": "\U0001f1ef\U0001f1f5", "KR": "\U0001f1f0\U0001f1f7", "GB": "\U0001f1ec\U0001f1e7",
    "DE": "\U0001f1e9\U0001f1ea", "FR": "\U0001f1eb\U0001f1f7", "NL": "\U0001f1f3\U0001f1f1", "CA": "\U0001f1e8\U0001f1e6", "AU": "\U0001f1e6\U0001f1fa",
    "SG": "\U0001f1f8\U0001f1ec", "IN": "\U0001f1ee\U0001f1f3", "BR": "\U0001f1e7\U0001f1f7", "ES": "\U0001f1ea\U0001f1f8", "IT": "\U0001f1ee\U0001f1f9",
}

FALLBACK_OUTBOUNDS = {
    "outbounds": [
        {"type": "selector", "tag": "\U0001f3e0 \u4f4f\u5b85\u4ee3\u7406", "outbounds": ["direct-out"]}
    ]
}

def main():
    if not ALIVE_FILE.exists():
        print("No alive nodes, using fallback")
        OUTPUT_FILE.write_text(json.dumps(FALLBACK_OUTBOUNDS, indent=2))
        reload_singbox()
        return

    alive = json.loads(ALIVE_FILE.read_text())
    if not alive:
        print("Empty alive list, using fallback")
        OUTPUT_FILE.write_text(json.dumps(FALLBACK_OUTBOUNDS, indent=2))
        reload_singbox()
        return

    socks_obs = []
    tags = []
    for i, node in enumerate(alive, 1):
        country = node.get("country", "XX").upper()
        flag = COUNTRY_FLAGS.get(country, "\U0001f30d")
        tag = f"{flag} IP2FREE_{country}_{i}"
        tags.append(tag)
        ob = {
            "type": "socks",
            "tag": tag,
            "server": node["server"],
            "server_port": int(node["port"]),
            "version": "5",
        }
        if node.get("username") and node.get("password"):
            ob["username"] = node["username"]
            ob["password"] = node["password"]
        socks_obs.append(ob)

    urltest = {
        "type": "urltest",
        "tag": "\U0001f3e0 \u4f4f\u5b85\u4ee3\u7406",
        "outbounds": tags,
        "url": "https://www.gstatic.com/generate_204",
        "interval": "5m",
    }

    config = {"outbounds": [urltest] + socks_obs}
    output = json.dumps(config, indent=2, ensure_ascii=False)
    OUTPUT_FILE.write_text(output)
    print(f"Wrote {len(socks_obs)} IP2Free outbounds to {OUTPUT_FILE}")
    reload_singbox()

def reload_singbox():
    result = subprocess.run(
        ["docker", "kill", "-s", "HUP", "singbox"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        print("Singbox hot-reloaded (SIGHUP)")
    else:
        print(f"Singbox SIGHUP failed: {result.stderr.strip()}")

if __name__ == "__main__":
    main()
