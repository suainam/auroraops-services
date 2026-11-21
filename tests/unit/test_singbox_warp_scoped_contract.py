"""Scoped WARP outbound & service activation contract for vps.services.singbox.

Verifies:
1. Legacy callers enabling WARP without setting global_rules keep global AI
   geosite rulesets, DNS rules, and warp-out capture (backwards compatibility).
2. Opt-in scoped mode (`singbox_warp_global_rules: false`) provisions `warp-out`
   while omitting global AI rulesets/rules, routing ONLY explicit extra nodes
   with `relay_outbound: warp-out` fail-closed to `warp-out`, leaving direct
   and `relay_ai_domains` nodes unchanged.
3. WARP container lifecycle (`warp-svc`, loopback-only SOCKS5) is wired into
   the unified `vps.services.singbox` docker deploy, verify, and rollback tasks.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]
SINGBOX_ROLE = ROOT / "collections/ansible_collections/vps/services/roles/singbox"
DOCKER_APPS_ROLE = ROOT / "collections/ansible_collections/vps/services/roles/docker_apps"
TEMPLATES = SINGBOX_ROLE / "templates"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), undefined=ChainableUndefined)
    env.filters.update(
        bool=lambda v: str(v).lower() in ("true", "1", "yes", "on") if not isinstance(v, bool) else v,
        to_json=json.dumps,
        regex_replace=lambda value, pattern, replacement: re.sub(pattern, replacement, str(value)),
    )
    env.tests["search"] = lambda value, pattern: re.search(pattern, str(value)) is not None
    return env


def _render_json(template_name: str, **overrides) -> dict:
    context = {
        "inventory_hostname": "qqg1299",
        "auroraops_roles": {"services": {"ip2free_gateway": False}},
        "docker_apps_singbox_inbound_listen": "::",
        "docker_apps_singbox_certificate_domain": "suai.eu.org",
        "singbox_reality_private_key": "MOCK_PRIVATE_KEY",
        "singbox_reality_public_key": "MOCK_PUBLIC_KEY",
        "singbox_reality_short_ids": ["8b1ec27f"],
        "singbox_uuid_aws": "00000000-0000-4000-8000-000000000001",
        "singbox_domain": "uk.suai.eu.org",
        "app_port_singbox_reality_aws": 30052,
        "hostvars": {
            "cc15": {
                "ansible_host": "cc15.example.net",
                "singbox_reality_public_key": "MOCK_CC15_PK",
                "singbox_reality_short_ids": ["15d9565c"],
            },
            "nat-jp3": {
                "nat_public_ipv4": "192.0.2.10",
                "singbox_reality_public_key": "MOCK_JP3_PK",
                "singbox_reality_short_ids": ["abcdef12"],
            },
        },
        "singbox_nodes": [
            {
                "name": "🇺🇸 [VPS] QQG1299-千兆-Vless-送中",
                "type": "vless",
                "uuid": "00000000-0000-4000-8000-000000000001",
                "port": 30052,
                "sni": "aws.amazon.com",
            },
        ],
        "singbox_extra_nodes": [
            {
                "name": "🇺🇸 [VPS] QQG1299-千兆-Vless-中继-US",
                "type": "vless",
                "uuid": "00000000-0000-4000-8000-000000000002",
                "port": 30062,
                "sni": "www.cloudflare.com",
                "relay_outbound": "out-cc15",
                "relay_ai_domains": True,
            },
            {
                "name": "🇺🇸 [VPS] QQG1299-千兆-Vless-WARP",
                "type": "vless",
                "uuid": "00000000-0000-4000-8000-000000000002",
                "port": 30063,
                "sni": "www.cloudflare.com",
                "relay_outbound": "warp-out",
            },
        ],
    }
    context.update(overrides)
    return json.loads(_env().get_template(template_name).render(**context))


def test_legacy_warp_enabled_caller_preserves_global_ai_rules_by_default() -> None:
    outbounds = _render_json("outbounds_direct.json.j2", docker_apps_singbox_warp_enabled=True)["outbounds"]
    route = _render_json("route_direct.json.j2", docker_apps_singbox_warp_enabled=True)["route"]
    dns = _render_json("dns.json.j2", docker_apps_singbox_warp_enabled=True)["dns"]

    assert any(o.get("tag") == "warp-out" and o.get("server") == "127.0.0.1" and o.get("server_port") == 40000 for o in outbounds)
    rule_set_tags = {rs["tag"] for rs in route["rule_set"]}
    assert {"geosite-openai", "geosite-anthropic", "geosite-google"} <= rule_set_tags
    assert any(
        r.get("outbound") == "warp-out" and set(r.get("rule_set", [])) >= {"geosite-openai", "geosite-anthropic", "geosite-google"}
        for r in route["rules"]
    )
    assert any(
        set(r.get("rule_set", [])) >= {"geosite-openai", "geosite-anthropic", "geosite-google"}
        for r in dns["rules"]
        if isinstance(r.get("rule_set"), list)
    )


def test_scoped_warp_mode_routes_only_warp_inbound_fail_closed_and_preserves_direct_and_cc15() -> None:
    overrides = {
        "singbox_warp_enabled": True,
        "singbox_warp_global_rules": False,
    }
    inbounds = _render_json("inbounds_direct.json.j2", **overrides)["inbounds"]
    outbounds = _render_json("outbounds_direct.json.j2", **overrides)["outbounds"]
    route = _render_json("route_direct.json.j2", **overrides)["route"]
    dns = _render_json("dns.json.j2", **overrides)["dns"]

    # 1. warp-out outbound exists on loopback 127.0.0.1:40000
    warp_out = next((o for o in outbounds if o.get("tag") == "warp-out"), None)
    assert warp_out == {
        "type": "socks",
        "tag": "warp-out",
        "server": "127.0.0.1",
        "server_port": 40000,
    }

    # 2. Global WARP AI rule_sets, global warp-out capture, and DNS AI rules are absent
    declared_rs = {rs["tag"] for rs in route["rule_set"]}
    for ai_rs in ("geosite-openai", "geosite-anthropic", "geosite-google"):
        assert ai_rs not in declared_rs
    assert not any(r.get("domain_suffix") == ["daily-cloudcode-pa.googleapis.com"] for r in route["rules"])
    dns_referenced_rs = {
        tag
        for r in dns["rules"]
        for tag in (r["rule_set"] if isinstance(r.get("rule_set"), list) else ([r["rule_set"]] if "rule_set" in r else []))
    }
    assert dns_referenced_rs <= declared_rs

    # 3. ONLY the dedicated WARP inbound routes to warp-out, fail-closed (no direct-out fallback for it)
    warp_rules = [r for r in route["rules"] if r.get("outbound") == "warp-out"]
    assert warp_rules == [{"inbound": ["in-vpsqqg1299--vless-warp"], "outbound": "warp-out"}]
    assert [r for r in route["rules"] if r.get("inbound") == ["in-vpsqqg1299--vless-warp"]] == warp_rules

    # 4. Existing cc15 relay-US node stays unchanged (AI/YouTube -> out-cc15, rest -> direct-out)
    cc15_rules = [r for r in route["rules"] if r.get("inbound") == ["in-vpsqqg1299--vless--us"]]
    assert len(cc15_rules) == 2
    assert cc15_rules[0]["outbound"] == "out-cc15"
    assert cc15_rules[1] == {"inbound": ["in-vpsqqg1299--vless--us"], "outbound": "direct-out"}

    # 5. All referenced inbound/outbound tags resolve
    inbound_tags = {ib["tag"] for ib in inbounds}
    outbound_tags = {ob["tag"] for ob in outbounds}
    assert "in-vpsqqg1299--vless-warp" in inbound_tags
    for r in route["rules"]:
        if "inbound" in r:
            assert set(r["inbound"]) <= inbound_tags
        if "outbound" in r:
            assert r["outbound"] in outbound_tags

    # 6. Private IP reject precedes warp-out (SSRF guard) and catch-all stays direct-out
    private_idx = next(i for i, r in enumerate(route["rules"]) if "10.0.0.0/8" in r.get("ip_cidr", []))
    warp_idx = route["rules"].index(warp_rules[0])
    assert private_idx < warp_idx
    assert route["rules"][-1] == {"outbound": "direct-out"}
    assert route["final"] == "direct-out"


def test_explicit_docker_apps_false_overrides_singbox_warp_enabled() -> None:
    outbounds = _render_json(
        "outbounds_direct.json.j2",
        singbox_warp_enabled=True,
        docker_apps_singbox_warp_enabled=False,
    )["outbounds"]
    assert not any(o.get("tag") == "warp-out" for o in outbounds)


def test_singbox_role_wires_warp_service_lifecycle_and_removes_orphaned_copy() -> None:
    assert not (DOCKER_APPS_ROLE / "tasks/warp.yml").exists(), "orphaned docker_apps/tasks/warp.yml must not linger"
    assert (SINGBOX_ROLE / "tasks/warp.yml").exists()

    defaults = yaml.safe_load((SINGBOX_ROLE / "defaults/main.yml").read_text(encoding="utf-8"))
    assert defaults["singbox_warp_enabled"] is False
    assert defaults["singbox_warp_global_rules"] is True

    main_tasks = yaml.safe_load((SINGBOX_ROLE / "tasks/main.yml").read_text(encoding="utf-8"))
    warp_idx = next(i for i, t in enumerate(main_tasks) if t.get("ansible.builtin.include_tasks") == "warp.yml")
    render_idx = next(i for i, t in enumerate(main_tasks) if t.get("ansible.builtin.import_tasks") == "configure_common.yml")
    assert warp_idx < render_idx, "WARP readiness must pass before Sing-box writes runtime config"
    assert "singbox_manage_warp | default(false) | bool" in main_tasks[warp_idx]["when"]
    assert "singbox_effective_mode == 'docker'" in main_tasks[warp_idx]["when"]

    warp_text = (SINGBOX_ROLE / "tasks/warp.yml").read_text(encoding="utf-8")
    assert "name: singbox-warp" in warp_text
    assert "127.0.0.1:{{ singbox_warp_effective_port }}:{{ singbox_warp_effective_port }}" in warp_text
    assert "warp=(on|plus)" in warp_text

    verify_text = (SINGBOX_ROLE / "tasks/verify_docker.yml").read_text(encoding="utf-8")
    assert "name: singbox-warp" in verify_text
    assert "docker_container_info:" in verify_text

    rollback_text = (SINGBOX_ROLE / "tasks/rollback.yml").read_text(encoding="utf-8")
    rollback_verify_text = (SINGBOX_ROLE / "tasks/rollback_verify.yml").read_text(encoding="utf-8")
    assert "name: singbox-warp" in rollback_text
    assert "name: singbox-warp" in rollback_verify_text
