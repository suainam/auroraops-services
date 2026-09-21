"""Synchronize #221 capability pool filters into one Mihomo profile.

Sub-Store remains the only subscription aggregator and protocol converter. This
module reads the safe #220 Registry, selects node names for five capability
pools, and atomically substitutes exact-name filters into a static Mihomo
profile template. Provider-scoped filters use stable provider IDs rather than
catalog ordering. No proxy credentials or raw node payloads are copied here.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from registry import CapabilityRegistry, NodeState

POOL_CAPABILITIES = {
    "ai": "ai",
    "server-low-rtt": "low_rtt",
    "hk-tw-media": "bilibili",
    "international-media": "media",
}

REGION_COUNTRIES = {
    "region-hk-mo": frozenset({"HK", "MO"}),
    "region-tw": frozenset({"TW"}),
    "region-jp": frozenset({"JP"}),
    "region-sg": frozenset({"SG"}),
    "region-us": frozenset({"US"}),
    "region-europe": frozenset(
        {
            "AD", "AL", "AT", "BA", "BE", "BG", "BY", "CH", "CY", "CZ",
            "DE", "DK", "EE", "ES", "FI", "FR", "GB", "GR", "HR", "HU",
            "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MC", "MD", "ME",
            "MK", "MT", "NL", "NO", "PL", "PT", "RO", "RS", "SE", "SI",
            "SK", "SM", "UA", "VA",
        }
    ),
}
REGION_NAME_PATTERNS = {
    "region-hk-mo": re.compile(r"🇭🇰|🇲🇴|\b(HK|Hong\s*Kong|MO|Macau)\b|香港|澳門|澳门", re.IGNORECASE),
    "region-tw": re.compile(r"🇹🇼|\b(TW|Taiwan)\b|台湾|臺灣", re.IGNORECASE),
    "region-jp": re.compile(r"🇯🇵|\b(JP|Japan)\b|日本", re.IGNORECASE),
    "region-sg": re.compile(r"🇸🇬|\b(SG|Singapore)\b|狮城|新加坡", re.IGNORECASE),
    "region-us": re.compile(r"🇺🇸|\b(US|USA|United\s*States)\b|美国", re.IGNORECASE),
    "region-europe": re.compile(
        r"🇬🇧|🇩🇪|🇫🇷|🇳🇱|\b(UK|GB|DE|FR|NL|EU|Europe|Britain|England|Germany|France|Netherlands)\b|英国|德国|法国|荷兰",
        re.IGNORECASE,
    ),
}
REGION_POOL_ORDER = tuple(REGION_COUNTRIES) + ("region-other",)
REGION_MARKERS = {
    "region-hk-mo": "__FILTER_REGION_HK_MO__",
    "region-tw": "__FILTER_REGION_TW__",
    "region-jp": "__FILTER_REGION_JP__",
    "region-sg": "__FILTER_REGION_SG__",
    "region-us": "__FILTER_REGION_US__",
    "region-europe": "__FILTER_REGION_EUROPE__",
    "region-other": "__FILTER_REGION_OTHER__",
}

POOL_MARKERS = {
    "baseline": "__FILTER_BASELINE__",
    **{pool: f"__FILTER_{pool.upper().replace('-', '_')}__" for pool in POOL_CAPABILITIES},
    "pure-low-risk": "__FILTER_PURE_LOW_RISK__",
    **REGION_MARKERS,
}
FAIL_CLOSED_EMPTY_POOLS = {"baseline", "pure-low-risk", *REGION_POOL_ORDER}

GROUP_KEYS = {
    "ai": ("AI · ",),
    "server-low-rtt": ("快速 · ", "低延迟 · ", "_cap_rtt_"),
    "pure-low-risk": ("纯净 · ", "_cap_pure_"),
    "hk-tw-media": ("B站港澳台 · ", "港台媒体 · ", "_cap_hktw_"),
    "international-media": ("国际媒体 · ", "_cap_media_"),
}

PROVIDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _provider_catalog(catalog_path: Path) -> list[dict[str, str]]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("provider catalog must be a list")
    catalog: list[dict[str, str]] = []
    names: set[str] = set()
    provider_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or item.get("enabled", True) is not True:
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("provider catalog entry requires name")
        provider_id = item.get("provider-id", name)
        if not isinstance(provider_id, str) or not PROVIDER_ID_PATTERN.fullmatch(provider_id):
            raise ValueError(f"invalid provider-id for {name}")
        prefix = item.get("additional-prefix", f"[{name}]")
        if not isinstance(prefix, str) or not prefix:
            raise ValueError("provider prefix must be a non-empty string")
        if name in names:
            raise ValueError(f"duplicate provider name: {name}")
        if provider_id in provider_ids:
            raise ValueError(f"duplicate provider-id: {provider_id}")
        names.add(name)
        provider_ids.add(provider_id)
        catalog.append({"name": name, "provider_id": provider_id, "prefix": prefix})
    return catalog


def _provider_prefixes(catalog_path: Path) -> dict[str, str]:
    return {entry["name"]: entry["prefix"] for entry in _provider_catalog(catalog_path)}


def _provider_ids(catalog_path: Path) -> dict[str, str]:
    return {entry["name"]: entry["provider_id"] for entry in _provider_catalog(catalog_path)}


def provider_pool_marker(pool: str, provider_id: str) -> str:
    return f"__FILTER_{pool.upper().replace('-', '_')}_{provider_id}__"


def _raw_name(display_name: str, provider: str, prefixes: dict[str, str]) -> str:
    prefix = prefixes.get(provider, f"[{provider}]")
    for marker in (f"{prefix} ", f"[{provider}] "):
        if display_name.startswith(marker):
            return display_name[len(marker) :]
    if display_name in {prefix, f"[{provider}]"}:
        raise ValueError("provider-prefixed node name is empty")
    return display_name


def _pure_allowed(node: NodeState, max_abuse_score: float = 0.85) -> bool:
    capabilities = node.last_observation.get("capabilities", {})
    if not isinstance(capabilities, dict) or capabilities.get("pure") != "pass":
        return False
    details = node.last_observation.get("details", {})
    if not isinstance(details, dict):
        return False
    abuse_score = details.get("abuse_score")
    if abuse_score is not None and isinstance(abuse_score, (int, float)) and not isinstance(abuse_score, bool):
        if not (0 <= float(abuse_score) <= max_abuse_score):
            return False
    return details.get("threat") in ("low", None)


def _region_pool(node: NodeState) -> str:
    details = node.last_observation.get("details", {})
    country = details.get("country") if isinstance(details, dict) else None
    country = country.upper() if isinstance(country, str) else ""
    for pool, countries in REGION_COUNTRIES.items():
        if country in countries:
            return pool
    name = node.identity.display_name or node.identity.name or ""
    for pool, pattern in REGION_NAME_PATTERNS.items():
        if pattern.search(name):
            return pool
    return "region-other"


def _projected_names(node: NodeState, prefixes: dict[str, str]) -> list[str]:
    names: list[str] = []
    for provider in node.providers or [node.identity.provider]:
        if provider not in prefixes:
            continue
        display_name = node.provider_display_names.get(provider)
        if display_name is None and provider == node.identity.provider:
            display_name = node.identity.display_name
        if display_name is None:
            continue
        prefix = prefixes.get(provider, f"[{provider}]")
        names.append(f"{prefix} {_raw_name(display_name, provider, prefixes)}")
    return sorted(set(names))


def pool_member_names(
    registry: CapabilityRegistry,
    prefixes: dict[str, str],
    *,
    max_abuse_score: float = 0.85,
    now: float | None = None,
) -> dict[str, list[str]]:
    """Return deterministic provider-prefixed Mihomo node names for capability and region pools."""
    now = time.time() if now is None else now
    fresh_alive = [
        node
        for node in registry.nodes.values()
        if node.last_seen > 0
        and now - node.last_seen < registry.ttl_seconds
        and node.last_observation.get("alive") is True
    ]
    selected: dict[str, list[NodeState]] = {
        "baseline": list(fresh_alive),
        **{
            pool: [
                node
                for node in fresh_alive
                if node.last_observation.get("capabilities", {}).get(capability) == "pass"
            ]
            for pool, capability in POOL_CAPABILITIES.items()
        },
        **{
            pool: [node for node in fresh_alive if _region_pool(node) == pool]
            for pool in REGION_POOL_ORDER
        },
    }
    selected["pure-low-risk"] = [
        node for node in fresh_alive if _pure_allowed(node, max_abuse_score)
    ]

    all_name_to_nodes: dict[str, list[NodeState]] = {}
    for node in registry.nodes.values():
        for name in _projected_names(node, prefixes):
            all_name_to_nodes.setdefault(name, []).append(node)

    selected_ids = {
        pool: {node.identity.node_id for node in nodes}
        for pool, nodes in selected.items()
    }
    result: dict[str, list[str]] = {}
    for pool in POOL_MARKERS:
        names: list[str] = []
        for node in selected.get(pool, []):
            for name in _projected_names(node, prefixes):
                candidates = all_name_to_nodes.get(name, [])
                ids = {candidate.identity.node_id for candidate in candidates}
                if len(ids) > 1:
                    latest_seen = max(candidate.last_seen for candidate in candidates)
                    latest_ids = {
                        candidate.identity.node_id
                        for candidate in candidates
                        if candidate.last_seen == latest_seen
                    }
                    if (
                        pool != "pure-low-risk"
                        or not latest_ids <= selected_ids["pure-low-risk"]
                    ):
                        # Historical endpoint identities can retain the same
                        # display name after a provider rotates a node. For
                        # Pure, accept the newest identity only when every
                        # newest twin independently passes the Pure contract;
                        # current non-Pure twins remain fail-closed.
                        continue
                names.append(name)
        result[pool] = sorted(set(names))
    for provider, prefix in prefixes.items():
        for pool in POOL_MARKERS:
            result[f"{pool}-{provider}"] = [
                name for name in result[pool] if name.startswith(f"{prefix} ")
            ]
    return result


def exact_name_filter(names: list[str]) -> str:
    if not names:
        raise ValueError("capability pool contains no nodes")
    return "^(?:" + "|".join(re.escape(name) for name in sorted(set(names))) + ")$"


def _existing_filters(profile_path: Path) -> dict[str, str]:
    if not profile_path.exists():
        return {}
    payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    groups = payload.get("proxy-groups", [])
    if not isinstance(groups, list):
        return {}
    by_name = {
        group.get("name"): group
        for group in groups
        if isinstance(group, dict) and isinstance(group.get("name"), str)
    }
    result: dict[str, str] = {}
    for pool, name_prefixes in GROUP_KEYS.items():
        for group_name, group in by_name.items():
            if not any(group_name.startswith(prefix) for prefix in name_prefixes):
                continue
            if isinstance(group, dict) and isinstance(group.get("filter"), str) and group["filter"]:
                result[pool] = group["filter"]
                break
    return result


def render_profile(
    template_text: str,
    member_names: dict[str, list[str]],
    *,
    existing_filters: dict[str, str] | None = None,
    provider_names: list[str] | None = None,
    provider_ids: dict[str, str] | None = None,
) -> tuple[str, list[str]]:
    """Replace global/provider filter markers; empty global pools retain LKG."""
    existing_filters = existing_filters or {}
    provider_names = provider_names or []
    provider_ids = provider_ids or {}
    rendered = template_text
    reused_lkg: list[str] = []
    for provider in provider_names:
        provider_id = provider_ids.get(provider, provider)
        for pool in POOL_MARKERS:
            marker = provider_pool_marker(pool, provider_id)
            names = member_names.get(f"{pool}-{provider}", [])
            value = exact_name_filter(names) if names else "^$"
            rendered = rendered.replace(marker, json.dumps(value, ensure_ascii=False))
    for pool, marker in POOL_MARKERS.items():
        names = member_names.get(pool, [])
        if names:
            value = exact_name_filter(names)
        elif pool in FAIL_CLOSED_EMPTY_POOLS:
            # A stricter Pure policy must never resurrect a previously accepted
            # datacenter/unknown node through LKG. An empty strict pool is safer
            # than serving stale membership that no longer satisfies the contract.
            value = "^$"
        else:
            value = existing_filters.get(pool, "")
            # If LKG is stale or mismatched, gracefully fall back to baseline members to prevent emptyFallback: COMPATIBLE
            if not value or "CC" in value:
                baseline_names = member_names.get("baseline", [])
                if baseline_names:
                    value = exact_name_filter(baseline_names)
                else:
                    raise ValueError(f"capability pool {pool} is empty and has no LKG or baseline filter")
            reused_lkg.append(pool)
        rendered = rendered.replace(marker, json.dumps(value, ensure_ascii=False))
    if any(marker in rendered for marker in POOL_MARKERS.values()) or re.search(
        r"__FILTER_[A-Za-z0-9_-]+__", rendered
    ):
        raise ValueError("capability profile contains unresolved filter markers")
    payload = yaml.safe_load(rendered)
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("proxy-providers"), dict)
        or not isinstance(payload.get("proxy-groups"), list)
    ):
        raise ValueError("capability profile is not a valid Mihomo profile")
    return rendered, reused_lkg


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--provider-catalog", type=Path, required=True)
    parser.add_argument("--template-path", type=Path, required=True)
    parser.add_argument("--profile-path", type=Path, required=True)
    parser.add_argument("--pure-max-abuse-score", type=float, default=0.85)
    args = parser.parse_args()
    if not 0 <= args.pure_max_abuse_score <= 100:
        parser.error("--pure-max-abuse-score must be between 0 and 100")

    registry = CapabilityRegistry(args.state)
    prefixes = _provider_prefixes(args.provider_catalog)
    provider_ids = _provider_ids(args.provider_catalog)
    names = pool_member_names(
        registry,
        prefixes,
        max_abuse_score=args.pure_max_abuse_score,
    )
    rendered, reused_lkg = render_profile(
        args.template_path.read_text(encoding="utf-8"),
        names,
        existing_filters=_existing_filters(args.profile_path),
        provider_names=list(prefixes),
        provider_ids=provider_ids,
    )
    atomic_write(args.profile_path, rendered)
    print(
        json.dumps(
            {
                "counts": {pool: len(values) for pool, values in names.items()},
                "lkg": sorted(reused_lkg),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
