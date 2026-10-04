"""Zero-rule NAT mode: no remote rule_set, no FakeIP DNS, dynamic Go memory.

32 MiB NAT guests OOM because full rule-set parsing expands a 30-50 MiB
trie. This contract pins the opt-in zero-rule rendering (default off), the
fallback compatibility of the full mode, and the OpenRC Go runtime env that
proves GOMEMLIMIT/GOGC reach the process.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "collections/ansible_collections/vps/services/roles/singbox"
TEMPLATES = ROLE / "templates"

ENV = Environment(loader=FileSystemLoader(str(TEMPLATES)), undefined=ChainableUndefined)
ENV.filters.update(
    bool=bool,
    to_json=json.dumps,
    regex_replace=lambda value, pattern, replacement: re.sub(pattern, replacement, value),
)


def render(name: str, **overrides) -> str:
    values = dict(
        inventory_hostname="nat-test",
        auroraops_roles={"services": {}},
        singbox_wireguard_enabled=True,
        singbox_extra_nodes=[],
        docker_apps_singbox_warp_enabled=False,
        docker_apps_singbox_block_ads=True,
        docker_apps_singbox_processed_nodes=[],
        singbox_nodes=[],
    )
    values.update(overrides)
    return ENV.get_template(name).render(**values)


def render_route(name: str, **overrides) -> dict:
    return json.loads(render(name, **overrides))["route"]


def test_zero_rules_defaults_to_false() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text(encoding="utf-8"))
    assert defaults["docker_apps_singbox_zero_rules"] is False


def test_zero_rule_route_has_no_remote_rule_set_and_defaults_direct() -> None:
    route = render_route("route_direct.json.j2", docker_apps_singbox_zero_rules=True)
    assert route["rule_set"] == []
    assert route["final"] == "direct-out"
    outbounds = [r.get("outbound") for r in route["rules"]]
    assert outbounds[-1] == "direct-out"
    assert not any("rule_set" in r for r in route["rules"])
    rendered = render("route_direct.json.j2", docker_apps_singbox_zero_rules=True)
    assert ".srs" not in rendered


def test_zero_rule_route_keeps_mesh_private_and_relay_protection() -> None:
    route = render_route(
        "route_direct.json.j2",
        docker_apps_singbox_zero_rules=True,
        singbox_extra_nodes=[{"name": "jp", "relay_outbound": "out-jp"}],
    )
    mesh = next(r for r in route["rules"] if r.get("outbound", "").startswith("wg-"))
    assert mesh["ip_cidr"] == ["10.144.10.0/24"]
    reject = next(r for r in route["rules"] if r.get("action") == "reject")
    assert "10.0.0.0/8" in reject["ip_cidr"]
    relay = next(r for r in route["rules"] if r.get("outbound") == "out-jp")
    assert relay["inbound"] == ["in-jp"]
    # Mesh must win over the private-range reject (10.144.10.0/24 is in 10/8).
    assert route["rules"].index(mesh) < route["rules"].index(reject)


def test_zero_rule_relay_route_keeps_failover_cluster_without_rule_set() -> None:
    route = render_route(
        "route_relay.json.j2",
        docker_apps_singbox_zero_rules=True,
        singbox_role="relay",
    )
    assert route["rule_set"] == []
    assert not any("rule_set" in r for r in route["rules"])
    cluster = next(r for r in route["rules"] if r.get("outbound") == "relay-failover-cluster")
    assert "inbound" in cluster
    assert route["final"] == "direct-out"


def test_zero_rule_dns_has_no_fakeip_or_ruleset_rules() -> None:
    dns = json.loads(render("dns.json.j2", docker_apps_singbox_zero_rules=True))["dns"]
    tags = [s["tag"] for s in dns["servers"]]
    assert "block-dns" not in tags
    assert not any(s.get("type") == "fakeip" for s in dns["servers"])
    assert not any("rule_set" in r for r in dns["rules"])
    assert "block-dns" not in json.dumps(dns)
    # Plain domain-suffix routing still works in zero mode.
    assert any("domain_suffix" in r for r in dns["rules"])


def test_default_mode_keeps_full_rules_and_fakeip() -> None:
    route = render_route("route_direct.json.j2")
    assert len(route["rule_set"]) == 3
    assert all(rs["type"] == "remote" for rs in route["rule_set"])
    assert any("rule_set" in r for r in route["rules"])
    dns = json.loads(render("dns.json.j2"))["dns"]
    assert any(s["tag"] == "block-dns" for s in dns["servers"])
    assert any("rule_set" in r for r in dns["rules"])
    relay = render_route("route_relay.json.j2", singbox_role="relay")
    assert len(relay["rule_set"]) == 2


def test_openrc_conf_declares_dynamic_go_memory() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/native.yml").read_text(encoding="utf-8"))
    env_task = next(t for t in tasks if "/etc/conf.d/sing-box" in str(t.get("ansible.builtin.copy", {}).get("dest", "")))
    content = env_task["ansible.builtin.copy"]["content"]
    assert "GOGC=30" in content
    assert re.search(r"GOMEMLIMIT=\{\{.*0\.6.*\}\}MiB", content)
    assert "ansible_memtotal_mb" in content or "singbox_effective_memtotal_mb" in content


def test_effective_memory_fact_considers_cgroup_limit() -> None:
    native = (ROLE / "tasks" / "native.yml").read_text(encoding="utf-8")
    assert "/sys/fs/cgroup/memory.max" in native
    assert "memory.limit_in_bytes" in native
    assert "singbox_effective_memtotal_mb" in native
