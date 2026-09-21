"""Run the configured mature probe adapter over Sub-Store sing-box nodes."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from probe_runner import run_isolated_probe
from registry import CapabilityRegistry, normalize_node


class ProbeSystemError(RuntimeError):
    """No scheduled node produced a valid probe observation in this profiler run."""


SUPPORTED_PROTOCOLS = {"vless", "vmess", "trojan", "hysteria2", "shadowsocks", "anytls", "tuic"}
METADATA_NAME_RE = re.compile(
    r"(?:剩余流量|流量剩余|到期|过期|官网|网址|公告|套餐|重置|客服|群组|频道|traffic|expire|expiry|reset|website)",
    re.IGNORECASE,
)
PURE_HINT_RE = re.compile(
    r"(?:家宽|加宽|家庭宽带|住宅|原生(?:\s*ip)?|residential|\bisp\b|native(?:\s*ip)?)",
    re.IGNORECASE,
)
LINE_QUALITY_HINT_RE = re.compile(r"(?:iepl|iplc|专线|精品线路|中转)", re.IGNORECASE)
PURE_REVIEW_POLICY_VERSION = 3


def _raw_node_name(raw: dict[str, Any]) -> str:
    for key in ("display_name", "name", "remark", "tag"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _has_required_auth(raw: dict[str, Any], protocol: str) -> bool:
    if protocol in {"vless", "vmess"}:
        return isinstance(raw.get("uuid"), str) and bool(raw["uuid"])
    if protocol in {"trojan", "hysteria2", "shadowsocks", "anytls"}:
        return isinstance(raw.get("password"), str) and bool(raw["password"])
    if protocol == "tuic":
        return all(isinstance(raw.get(key), str) and bool(raw[key]) for key in ("uuid", "password"))
    return False


def node_is_probeable(raw: dict[str, Any]) -> bool:
    """Cheap admission gate before any sing-box process or network probe."""
    protocol = raw.get("protocol") or raw.get("type")
    name = _raw_node_name(raw)
    server = raw.get("server") or raw.get("address") or raw.get("host")
    port = raw.get("port") or raw.get("server_port")
    if not isinstance(protocol, str) or protocol.lower() not in SUPPORTED_PROTOCOLS:
        return False
    protocol = protocol.lower()
    try:
        port_number = int(port)
    except (TypeError, ValueError):
        return False
    if isinstance(port, bool) or not 1 <= port_number <= 65535:
        return False
    if not isinstance(server, str) or not server.strip() or not _has_required_auth(raw, protocol):
        return False
    if not name or len(name) > 160 or METADATA_NAME_RE.search(name):
        return False
    if name == server or name == f"{server}:{raw.get('port', raw.get('server_port', ''))}":
        return False
    return bool(re.search(r"[A-Za-z0-9\u3400-\u9fff]", name))


def pure_candidate(raw: dict[str, Any]) -> bool:
    """Names only prioritize expensive Pure review; they never grant Pure status."""
    if raw.get("owned") is True:
        return True
    name = _raw_node_name(raw)
    return bool(PURE_HINT_RE.search(name))


def _probe_revision(identity: Any, provider_display_names: dict[str, str], candidate: bool) -> str:
    payload = {
        "node_id": identity.node_id,
        "provider_names": provider_display_names,
        "pure_candidate": candidate,
        "policy": 2,
    }
    if candidate:
        payload["pure_review_policy"] = PURE_REVIEW_POLICY_VERSION
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _periodic_due(node_id: str, last_checked: float, now: float, period_seconds: int, buckets: int) -> bool:
    """Spread one reconciliation per period across deterministic time buckets."""
    if period_seconds <= 0 or buckets <= 0:
        raise ValueError("probe schedule period and buckets must be positive")
    bucket_seconds = period_seconds / buckets
    cycle_start = now - (now % period_seconds)
    if last_checked > 0 and last_checked >= cycle_start:
        return False
    bucket = int(node_id[:8], 16) % buckets
    target = cycle_start + bucket * bucket_seconds
    return now >= target


def singbox_nodes(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [node for node in payload if isinstance(node, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("outbounds"), list):
        ignored = {"direct", "block", "dns", "selector", "urltest", "tailscale"}
        return [
            node
            for node in payload["outbounds"]
            if isinstance(node, dict) and node.get("type") not in ignored and node.get("server")
        ]
    raise ValueError("Sub-Store sing-box output must contain outbounds")

def load_provider_catalog_nodes(
    catalog_path: Path,
    sub_store_base_url: str,
    template: str,
    *,
    timeout: float = 60.0,
) -> list[dict[str, Any]]:
    """Convert every enabled provider through one Sub-Store template."""
    catalog = json.loads(catalog_path.read_text())
    if not isinstance(catalog, list):
        raise ValueError("provider catalog must be a list")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    nodes: list[dict[str, Any]] = []
    for item in catalog:
        if not isinstance(item, dict) or item.get("enabled", True) is not True:
            continue
        name = item.get("name")
        provider_url = item.get("url")
        prefix = item.get("additional-prefix", f"[{name}]")
        if not isinstance(name, str) or not name or not isinstance(provider_url, str) or not provider_url:
            raise ValueError("provider catalog entry requires name and url")
        if not isinstance(prefix, str) or not prefix or len(prefix) > 64:
            raise ValueError("provider catalog additional-prefix must be a non-empty string up to 64 characters")
        query = urllib.parse.urlencode({"target": "sing-box", "url": provider_url})
        download_url = (
            f"{sub_store_base_url.rstrip('/')}/download/"
            f"{urllib.parse.quote(template, safe='')}?{query}"
        )
        with opener.open(download_url, timeout=timeout) as response:
            payload = json.load(response)
        for node in singbox_nodes(payload):
            enriched = dict(node)
            enriched["provider"] = name
            enriched["provider_prefix"] = prefix
            enriched["owned"] = item.get("owned") is True
            nodes.append(enriched)
    return nodes


def load_nodes(
    source_url: str | None = None,
    input_path: Path | None = None,
    source_url_path: Path | None = None,
    timeout: float = 60.0,
) -> list[dict[str, Any]]:
    if source_url_path:
        source_url = source_url_path.read_text().strip()
    if source_url:
        req = urllib.request.Request(
            source_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SubStore/2.0)"}
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as response:
            payload = json.load(response)
    elif input_path:
        payload = json.loads(input_path.read_text())
    else:
        payload = json.load(sys.stdin)
    return singbox_nodes(payload)


def profile_nodes(
    raw_nodes: Sequence[dict[str, Any]],
    command: Sequence[str],
    state_path: Path,
    *,
    provider: str = "unknown",
    ttl_seconds: int = 86400,
    probe_timeout: float = 60.0,
    geo_ttl_seconds: float = 86400.0,
    risk_ttl_seconds: float = 86400.0,
    probe_period_seconds: int = 86400,
    probe_buckets: int = 24,
    now: float | None = None,
) -> CapabilityRegistry:
    """Incrementally probe changed nodes plus one deterministic daily bucket."""
    now = time.time() if now is None else now
    registry = CapabilityRegistry(state_path, ttl_seconds=ttl_seconds)
    normalized: dict[str, tuple[Any, dict[str, Any], dict[str, str]]] = {}
    for raw in raw_nodes:
        if not node_is_probeable(raw):
            continue
        identity, _ = normalize_node(raw, provider=raw.get("provider", provider))
        existing = normalized.get(identity.node_id)
        if existing:
            existing[2][identity.provider] = identity.display_name
        else:
            normalized[identity.node_id] = (
                identity,
                raw,
                {identity.provider: identity.display_name},
            )
    if not normalized:
        raise ValueError("no probeable nodes")
    valid_observations = 0
    scheduled = 0
    for identity, raw, provider_display_names in normalized.values():
        existing = registry.nodes.get(identity.node_id)
        candidate = pure_candidate(raw)
        revision = _probe_revision(identity, provider_display_names, candidate)
        previous_revision = ""
        last_checked = 0.0
        if existing:
            previous_details = existing.last_observation.get("details", {})
            if isinstance(previous_details, dict):
                previous_revision = str(previous_details.get("probe_revision", ""))
            last_checked = float(existing.last_observation.get("checked_at", 0) or 0)
        changed = existing is None or previous_revision != revision
        due = changed or _periodic_due(identity.node_id, last_checked, now, probe_period_seconds, probe_buckets)
        if not due:
            continue
        scheduled += 1
        context = existing.probe_context() if existing else {}
        context.update(
            {
                "geo_ttl_seconds": geo_ttl_seconds,
                "risk_ttl_seconds": risk_ttl_seconds,
                "pure_candidate": candidate,
            }
        )
        runtime_outbound = {
            key: value
            for key, value in raw.items()
            if key not in {"provider", "provider_prefix", "owned", "fixed_ip"}
        }
        observation = run_isolated_probe(
            command,
            identity,
            timeout=probe_timeout,
            context=context,
            outbound=runtime_outbound,
        )
        if observation.probe_status == "infrastructure_error":
            continue
        observation.details["probe_revision"] = revision
        observation.details["pure_candidate"] = candidate
        valid_observations += 1
        node = registry.observe(
            identity,
            observation,
            owned=raw.get("owned") is True,
            fixed_ip=raw.get("fixed_ip") is True,
        )
        if node is not None:
            node.providers = sorted(set(node.providers) | set(provider_display_names))
            node.provider_display_names.update(provider_display_names)
    if scheduled > 0 and valid_observations == 0:
        raise ProbeSystemError("all scheduled node probes failed at the probe infrastructure boundary")
    if valid_observations > 0:
        registry.save()
    return registry


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--provider", default="unknown")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--source-url", default=None)
    parser.add_argument("--source-url-file", type=Path, default=None)
    parser.add_argument("--provider-catalog", type=Path, default=None)
    parser.add_argument("--sub-store-base-url", default=None)
    parser.add_argument("--template", default=None)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--geo-ttl", type=float, default=86400.0)
    parser.add_argument("--risk-ttl", type=float, default=86400.0)
    parser.add_argument("--probe-period", type=int, default=86400)
    parser.add_argument("--probe-buckets", type=int, default=24)
    parser.add_argument("command", nargs="+", help="mature probe adapter command")
    args = parser.parse_args()
    selected_sources = sum(bool(value) for value in (args.input, args.source_url, args.source_url_file, args.provider_catalog))
    if selected_sources > 1:
        parser.error("choose one node source")
    if args.provider_catalog:
        if not args.sub_store_base_url or not args.template:
            parser.error("provider catalog requires --sub-store-base-url and --template")
        raw_nodes = load_provider_catalog_nodes(
            args.provider_catalog,
            args.sub_store_base_url,
            args.template,
            timeout=args.timeout,
        )
    else:
        raw_nodes = load_nodes(args.source_url, args.input, args.source_url_file, timeout=args.timeout)
    profile_nodes(
        raw_nodes,
        args.command,
        args.state,
        provider=args.provider,
        probe_timeout=args.timeout,
        geo_ttl_seconds=args.geo_ttl,
        risk_ttl_seconds=args.risk_ttl,
        probe_period_seconds=args.probe_period,
        probe_buckets=args.probe_buckets,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
