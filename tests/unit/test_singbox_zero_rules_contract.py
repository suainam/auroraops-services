"""Zero-rule NAT mode: no remote rule_set, no FakeIP DNS, dynamic Go memory.

32 MiB NAT guests OOM because full rule-set parsing expands a 30-50 MiB
trie. This contract pins the opt-in zero-rule rendering (default off), the
fallback compatibility of the full mode, and the OpenRC Go runtime env that
proves GOMEMLIMIT/GOGC reach the process.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
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


def _probe_script() -> str:
    tasks = yaml.safe_load((ROLE / "tasks/native.yml").read_text(encoding="utf-8"))
    task = next(t for t in tasks if t["name"].startswith("Sing-box Native - Resolve effective memory"))
    return task["ansible.builtin.command"]["argv"][2]


def _run_probe(root: Path, mounts: str, cgroup_lines: list[str], meminfo_kb: int = 4 * 1024 * 1024) -> int:
    proc = root / "proc"
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "meminfo").write_text(f"MemTotal:       {meminfo_kb} kB\n", encoding="utf-8")
    (proc / "1").mkdir(exist_ok=True)
    (proc / "self").mkdir(exist_ok=True)
    (proc / "1" / "cgroup").write_text("\n".join(cgroup_lines) + "\n", encoding="utf-8")
    (proc / "self" / "cgroup").write_text("\n".join(cgroup_lines) + "\n", encoding="utf-8")
    (proc / "mounts").write_text(mounts, encoding="utf-8")
    env = dict(os.environ, SB_PROC_ROOT=str(proc), SB_MOUNTS=str(proc / "mounts"))
    out = subprocess.run(["/bin/sh", "-c", _probe_script()], capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    return int(out.stdout.strip())


def test_probe_takes_v2_leaf_and_ancestor_limits(tmp_path: Path) -> None:
    root = tmp_path / "cg2"
    sys2 = root / "sys/fs/cgroup"
    (sys2 / "openrc" / "sing-box").mkdir(parents=True)
    (sys2 / "memory.max").write_text("max\n", encoding="utf-8")
    (sys2 / "openrc" / "memory.max").write_text("134217728\n", encoding="utf-8")  # 128 MiB
    (sys2 / "openrc" / "sing-box" / "memory.max").write_text("max\n", encoding="utf-8")
    mounts = f"cgroup2 {sys2} cgroup2 rw,0\n"
    assert _run_probe(root, mounts, ["0::/openrc/sing-box"]) == 128


def test_probe_takes_v1_controller_limit_with_mount_point_first(tmp_path: Path) -> None:
    root = tmp_path / "cg1"
    memmount = root / "sys/fs/cgroup/memory"
    (memmount / "docker" / "abc").mkdir(parents=True)
    (memmount / "memory.limit_in_bytes").write_text("9223372036854771712\n", encoding="utf-8")  # kernel default
    (memmount / "docker" / "memory.limit_in_bytes").write_text("268435456\n", encoding="utf-8")  # 256 MiB
    (memmount / "docker" / "abc" / "memory.limit_in_bytes").write_text("max\n", encoding="utf-8")
    mounts = f"memory {memmount} cgroup rw,memory\n"
    assert _run_probe(root, mounts, ["5:memory:/docker/abc"]) == 256


def test_probe_falls_back_to_physical_when_unbounded(tmp_path: Path) -> None:
    root = tmp_path / "cgmax"
    sys2 = root / "sys/fs/cgroup"
    sys2.mkdir(parents=True)
    (sys2 / "memory.max").write_text("max\n", encoding="utf-8")
    mounts = f"cgroup2 {sys2} cgroup2 rw,0\n"
    assert _run_probe(root, mounts, ["0::/"], meminfo_kb=1_048_576) == 1024


def test_probe_caps_by_physical_when_cgroup_is_larger(tmp_path: Path) -> None:
    root = tmp_path / "cgbig"
    sys2 = root / "sys/fs/cgroup"
    sys2.mkdir(parents=True)
    (sys2 / "memory.max").write_text(f"{16 * 1024 * 1024 * 1024}\n", encoding="utf-8")  # 16 GiB
    mounts = f"cgroup2 {sys2} cgroup2 rw,0\n"
    assert _run_probe(root, mounts, ["0::/"], meminfo_kb=65_536) == 64


def test_probe_writes_no_temporary_files(tmp_path: Path) -> None:
    root = tmp_path / "cgclean"
    sys2 = root / "sys/fs/cgroup"
    sys2.mkdir(parents=True)
    (sys2 / "memory.max").write_text("max\n", encoding="utf-8")
    mounts = f"cgroup2 {sys2} cgroup2 rw,0\n"
    _run_probe(root, mounts, ["0::/"], meminfo_kb=1_048_576)
    assert [p.name for p in root.iterdir()] == ["proc", "sys"]


def test_conf_d_renders_19MiB_for_32_mib_effective_memory() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/native.yml").read_text(encoding="utf-8"))
    env_task = next(t for t in tasks if t.get("ansible.builtin.copy", {}).get("dest") == "/etc/conf.d/sing-box")
    jinja2 = Environment()
    jinja2.filters["bool"] = bool
    rendered = jinja2.from_string(env_task["ansible.builtin.copy"]["content"]).render(
        singbox_native_config_dir="/etc/sing-box",
        singbox_native_workdir="/var/lib/sing-box",
        docker_apps_singbox_zero_rules=True,
        singbox_effective_memtotal_mb=32,
        ansible_memtotal_mb=32,
    )
    assert "export GOMEMLIMIT=19MiB" in rendered
    assert "export GOGC=30" in rendered
