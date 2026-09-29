"""Custom filter plugins for Cloudflare DNS DR operations."""

from __future__ import annotations

from typing import Any


def cloudflare_dns_backup(
    records: list[dict[str, Any]],
    *,
    zone_id: str,
    record_name: str,
    captured_at: str,
) -> dict[str, Any]:
    return {
        "zone_id": zone_id,
        "record_name": record_name,
        "captured_at": captured_at,
        "records": records,
    }


def cloudflare_dns_switch_payload(
    source_record: dict[str, Any],
    *,
    tunnel_id: str,
) -> dict[str, Any]:
    return {
        "type": "CNAME",
        "name": source_record.get("name", ""),
        "content": f"{tunnel_id}.cfargotunnel.com",
        "ttl": 1,
        "proxied": True,
        "comment": "AuroraOps managed standby DR tunnel pointer",
    }


def cloudflare_dns_restore_payload(backup_data: dict[str, Any]) -> list[dict[str, Any]]:
    records = backup_data.get("records", [])
    restore_list = []
    for r in records:
        entry = {
            "type": r.get("type", "A"),
            "name": r.get("name", backup_data.get("record_name", "")),
            "content": r.get("content", ""),
            "ttl": r.get("ttl", 1),
            "proxied": r.get("proxied", True),
        }
        if r.get("comment"):
            entry["comment"] = r["comment"]
        restore_list.append(entry)
    return restore_list


class FilterModule:
    def filters(self) -> dict[str, Any]:
        return {
            "cloudflare_dns_backup": cloudflare_dns_backup,
            "cloudflare_dns_switch_payload": cloudflare_dns_switch_payload,
            "cloudflare_dns_restore_payload": cloudflare_dns_restore_payload,
        }
