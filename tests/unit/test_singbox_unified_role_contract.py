from __future__ import annotations

import re
from pathlib import Path

from jinja2 import ChainableUndefined
from jinja2.nativetypes import NativeEnvironment

ROLE = Path(__file__).resolve().parents[2] / "collections/ansible_collections/vps/services/roles/singbox"


def read(relative: str) -> str:
    return (ROLE / relative).read_text(encoding="utf-8")


def test_unified_singbox_role_structure() -> None:
    assert (ROLE / "meta/main.yml").exists()
    assert (ROLE / "defaults/main.yml").exists()
    assert (ROLE / "handlers/main.yml").exists()
    assert (ROLE / "tasks/main.yml").exists()
    assert (ROLE / "tasks/resolve.yml").exists()
    assert (ROLE / "tasks/common_prep.yml").exists()
    assert (ROLE / "tasks/configure_common.yml").exists()
    assert (ROLE / "tasks/docker.yml").exists()
    assert (ROLE / "tasks/native.yml").exists()
    assert (ROLE / "tasks/verify.yml").exists()
    assert (ROLE / "tasks/verify_docker.yml").exists()
    assert (ROLE / "tasks/verify_native.yml").exists()


def test_fail_closed_mode_resolution() -> None:
    resolve = read("tasks/resolve.yml")
    assert "singbox_effective_mode" in resolve
    assert "singbox_effective_mode in ['native', 'docker']" in resolve


def test_shared_templates_coexist_in_unified_role() -> None:
    templates = ROLE / "templates"
    for expected in (
        "base.json.j2",
        "outbounds_direct.json.j2",
        "dns.json.j2",
        "inbounds_direct.json.j2",
        "route_direct.json.j2",
        "06_wireguard.json.j2",
        "singbox_provider_profile.yaml.j2",
    ):
        assert (templates / expected).exists(), f"Missing template {expected}"


def test_wireguard_endpoint_inbound_is_strictly_system_mode_guarded() -> None:
    wg_template = read("templates/06_wireguard.json.j2")
    assert "singbox_wireguard_system | default(false) | bool" in wg_template
    assert "singbox_wireguard_http_inbound | default(false) | bool" in wg_template


def test_docker_container_declares_explicit_run_command() -> None:
    """Regression: the sing-box image entrypoint is a bare `sing-box`.

    Without an explicit `run` command the container prints help, exits 0 and
    lands in a restart loop, so redeploy after rollback silently breaks the
    service. Assert the run command and the split-config directory are pinned.
    """
    docker = read("tasks/docker.yml")
    assert "community.docker.docker_container:" in docker
    assert re.search(r"^\s*command:\s*run\s+-C\s+/etc/sing-box\s*$", docker, re.M), (
        "docker.yml must pin `command: run -C /etc/sing-box`"
    )


def outbound_blocks(text: str) -> dict[str, str]:
    """Split a rendered outbound template into {tag: block} pairs.

    Slicing on tag boundaries keeps each block's Reality material paired with
    the outbound it actually belongs to.
    """
    marks = [(m.start(), m.group(1)) for m in re.finditer(r'"tag":\s*"([^"]+)"', text)]
    blocks: dict[str, str] = {}
    for index, (start, tag) in enumerate(marks):
        end = marks[index + 1][0] if index + 1 < len(marks) else len(text)
        blocks[tag] = text[start:end]
    return blocks


def test_jp3_outbound_resolves_reality_material_from_hostvars() -> None:
    """Regression: the JP3 peer key must have exactly one authority.

    The public key and short ID rotate whenever a host regenerates
    reality_key.txt. A literal copy in the template silently breaks the
    outbound, so peer material is resolved from hostvars instead.
    """
    blocks = outbound_blocks(read("templates/outbounds_direct.json.j2"))
    assert "out-nat-jp3" in blocks
    jp3_block = blocks["out-nat-jp3"]
    key = re.search(r'"public_key":\s*"([^"]*)"', jp3_block)
    short = re.search(r'"short_id":\s*"([^"]*)"', jp3_block)
    assert key and "{{" in key.group(1), "out-nat-jp3 must resolve public_key via Jinja"
    assert short and "{{" in short.group(1), "out-nat-jp3 must resolve short_id via Jinja"
    assert "hostvars['nat-jp3'].singbox_reality_public_key" in key.group(1)


# Known pre-existing debt: these peers still carry literal Reality material and
# address fallbacks. Tracked in auroraops-control issue #18. The allowlist makes
# the debt explicit and fails if a NEW hardcoded peer is introduced.
KNOWN_HARDCODED_PEER_DEBT = {
    ("outbounds_direct.json.j2", "out-cc15"),
    ("outbounds_direct.json.j2", "out-nat-hk216"),
    ("outbounds_direct.json.j2", "out-nat-hk084"),
    ("outbounds_relay.json.j2", "public-relay-fallback"),
}


def test_no_new_hardcoded_peer_reality_material_is_introduced() -> None:
    """Every remaining literal peer must be on the known-debt allowlist."""
    offenders: set[tuple[str, str]] = set()
    for template in sorted((ROLE / "templates").glob("*.j2")):
        for tag, block in outbound_blocks(template.read_text(encoding="utf-8")).items():
            key = re.search(r'"public_key":\s*"([^"]*)"', block)
            if key and key.group(1).strip() and "{{" not in key.group(1):
                offenders.add((template.name, tag))
    assert offenders <= KNOWN_HARDCODED_PEER_DEBT, (
        f"New hardcoded peer Reality key(s) introduced: "
        f"{sorted(offenders - KNOWN_HARDCODED_PEER_DEBT)}"
    )


def test_verify_config_contract_never_logs_raw_config_bytes() -> None:
    """Regression: the contract check slurps fragments containing the Reality
    private key and peer credentials. Any failure while decoding them would
    otherwise dump base64 key material into the task output."""
    contract = read("tasks/verify_config_contract.yml")
    assert "ansible.builtin.slurp:" in contract
    # Every task that registers or derives from slurped bytes must be no_log.
    for task_block in re.split(r"\n- name:", contract):
        if "slurp" in task_block or "b64decode" in task_block:
            assert "no_log: true" in task_block, (
                "a task handling slurped sing-box config bytes is missing no_log"
            )


def _ansible_env():
    """Jinja environment mirroring Ansible: native types, ChainableUndefined,
    an Ansible-style `flatten`, so guard expressions evaluate as they do in play."""
    env = NativeEnvironment(undefined=ChainableUndefined)

    def _flatten(value):
        out = []
        for item in value:
            out.extend(item) if isinstance(item, (list, tuple)) else out.append(item)
        return out

    env.filters["flatten"] = _flatten
    return env


def _peer(tag, public_key=...):
    reality = {"enabled": True}
    if public_key is not ...:
        reality["public_key"] = public_key
    return {"type": "vless", "tag": tag, "tls": {"reality": reality}}


KEY = "1JpJBhBeCb5N2s8gcXkVbPMYxGB6XHCjWIyeHonRoG0"


def test_auto_routing_peer_reality_assertion_flags_broken_members() -> None:
    """Regression guard for the auto-routing urltest clusters.

    A VLESS Reality peer whose public_key is absent or rendered empty still has
    a resolvable tag, so route-reference checks pass while the cluster silently
    selects a member that can never handshake. The contract check must flag it.
    """
    contract = read("tasks/verify_config_contract.yml")
    env = _ansible_env()

    collect = env.from_string(
        "{{ singbox_config_documents | map(attribute='outbounds', default=[]) | flatten"
        " | selectattr('type', 'equalto', 'vless')"
        " | selectattr('tls.reality.enabled', 'defined')"
        " | selectattr('tls.reality.enabled') | list }}"
    )
    incomplete = env.from_string(
        "{{ (peers | rejectattr('tls.reality.public_key', 'defined')"
        " | map(attribute='tag') | list)"
        " + (peers | selectattr('tls.reality.public_key', 'defined')"
        " | selectattr('tls.reality.public_key', 'equalto', '')"
        " | map(attribute='tag') | list) }}"
    )

    def audit(outbounds: list[dict]) -> list[str]:
        peers = collect.render(singbox_config_documents=[{"outbounds": outbounds}])
        return incomplete.render(peers=peers)

    # Healthy clusters produce no findings.
    assert audit([_peer("out-nat-jp3", KEY), _peer("out-cc15", KEY)]) == []
    # Non-Reality and non-VLESS outbounds are out of scope.
    assert audit([{"type": "vless", "tag": "x", "tls": {}}]) == []
    assert audit([{"type": "hysteria2", "tag": "hy", "tls": {"reality": {"enabled": True, "public_key": ""}}}]) == []

    # Both failure modes are caught: key missing entirely, and key rendered empty.
    assert audit([_peer("out-nat-jp3", KEY), _peer("out-cc15", "")]) == ["out-cc15"]
    assert audit([_peer("out-nat-jp3", KEY), _peer("out-hk084")]) == ["out-hk084"]

    # The assertion is actually wired into the role.
    assert "singbox_config_incomplete_reality_peers | length == 0" in contract
    assert "Collect peers with missing or empty Reality public key" in contract


def test_singbox_preflight_never_asserts_deploy_artifacts_exist() -> None:
    """Regression: preflight is a read-only capability probe that runs *before*
    deploy. The config directory and the binary are created by deploy, so
    asserting their presence breaks bootstrap on a fresh host."""
    preflight = read("tasks/preflight.yml")
    assert "ansible.builtin.assert:" in preflight
    assert "ansible_facts['os_family'] in ['Debian', 'Alpine']" in preflight
    assert "ansible_facts['architecture'] in ['x86_64', 'aarch64']" in preflight
    assertions = preflight.split("ansible.builtin.assert:", 1)[1].split("- name:", 1)[0]
    assert "singbox_preflight_config_dir.stat.exists" not in assertions
    assert "singbox_preflight_version.rc == 0" not in assertions
    # Nothing in preflight may mutate the host.
    for forbidden in ("state: absent", "state: present", "state: started", "copy:", "template:"):
        assert forbidden not in preflight, f"preflight must stay read-only, found {forbidden}"
