from __future__ import annotations

from pathlib import Path

ROLE = Path(__file__).resolve().parents[1] / "collections/ansible_collections/vps/services/roles/singbox"


def test_verify_contract_rejects_unresolved_route_outbounds() -> None:
    text = (ROLE / "tasks/verify_config_contract.yml").read_text(encoding="utf-8")
    assert "singbox_config_route_outbound_refs | difference(singbox_config_outbound_tags) | length == 0" in text
    assert "relay-failover-cluster" in text
    assert "verify_config_contract.yml" in (ROLE / "tasks/verify_native.yml").read_text(encoding="utf-8")
    assert "verify_config_contract.yml" in (ROLE / "tasks/verify_docker.yml").read_text(encoding="utf-8")


def test_singbox_preflight_is_read_only() -> None:
    """Preflight observes. It must not create, generate or modify anything.

    The configuration directory and the binary are deploy artifacts, so on a
    host that has not been deployed yet their absence says nothing about whether
    this host is supported. Asserting there would make preflight fail on every
    fresh machine, which is the opposite of a preflight.
    """
    text = (ROLE / "tasks/preflight.yml").read_text(encoding="utf-8")
    assert "changed_when: false" in text
    assert "failed_when: false" in text
    assert "Probes the" not in text  # keep the assertions below meaningful
    assert "sing-box version" in text


def test_singbox_preflight_reports_availability_without_asserting_it() -> None:
    """Missing artifacts are reported as diagnostics, never asserted on.

    An earlier version of this test demanded the opposite: it required
    preflight to fail closed when the binary was absent in native mode. That
    contradicted the stage's purpose, and the test was the thing that was
    wrong. Asserting the absence here is deliberate, so the contract cannot be
    quietly inverted again by someone who reads a failing test as a missing
    feature.
    """
    text = (ROLE / "tasks/preflight.yml").read_text(encoding="utf-8")
    assert "binary_available: {{ singbox_preflight_version.rc == 0 }}" in text
    assert "config_dir_present: {{ singbox_preflight_config_dir.stat.exists }}" in text
    assert "singbox_effective_mode != 'native' or singbox_preflight_version.rc == 0" not in text, (
        "preflight must not assert on binary availability; it reports it"
    )
    # Platform support is still a real precondition, and that one is asserted.
    assert "singbox_effective_mode in ['native', 'docker']" in text
    assert "ansible_facts['architecture'] in ['x86_64', 'aarch64']" in text


def test_generated_client_profile_is_idempotent() -> None:
    template = (ROLE / "templates/singbox_client_profile.yaml.j2").read_text(encoding="utf-8")
    assert "now()" not in template
    assert "生成时间" not in template


def test_native_singbox_rollback_skips_docker_container_removal() -> None:
    """Native rollback must not remove a container it never deployed.

    The previous version pinned the variable name `docker_apps_singbox_deploy_mode`
    and broke when the mode variable was split. Naming a variable is a weak way
    to express this: the property that matters is the guard around `state:
    absent`, so that is what is asserted here.
    """
    text = (ROLE.parent / "docker_apps/tasks/rollback.yml").read_text(encoding="utf-8")
    assert "rollback_docker_app_name == 'singbox'" in text
    assert "singbox_deploy_mode" in text
    # The removal is skipped when the host is native, and also when the mode is
    # unresolvable on a host too small or too unusual to run the container.
    assert "state: absent" in text
    assert "(singbox_deploy_mode | default('auto') | lower) == 'native'" in text
    assert "(singbox_deploy_mode | default('auto') | lower) not in ['native', 'docker']" in text
    assert "ansible_memtotal_mb | default(1024)) < 512" in text


def test_singbox_rollback_resolves_effective_mode() -> None:
    rollback = (ROLE / "tasks/rollback.yml").read_text(encoding="utf-8")
    verify = (ROLE / "tasks/rollback_verify.yml").read_text(encoding="utf-8")
    assert "import_tasks: resolve.yml" in rollback
    assert "import_tasks: resolve.yml" in verify
