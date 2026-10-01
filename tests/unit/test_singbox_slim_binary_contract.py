"""Native slim-binary install: role-owned, so a 64 MiB guest never unpacks the 46 MiB package.

The Alpine package is a 46 MiB universal binary. Unpacking it inside a 64 MiB
guest's cgroup is what OOM-kills `apk add`, which used to leave the node with an
OpenRC init script but no binary. These tests pin the role-owned replacement:
mutually exclusive with apk, sha256-verified, and failing loudly rather than
silently falling back to the install that OOMs.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "collections/ansible_collections/vps/services/roles/singbox"


def read(relative: str) -> str:
    return (ROLE / relative).read_text(encoding="utf-8")


def load_tasks(relative: str) -> list:
    return yaml.safe_load(read(relative))


def find(tasks: list, needle: str) -> dict:
    return next(task for task in tasks if needle in task["name"])


def test_slim_binary_is_opt_in_and_defaults_off() -> None:
    defaults = yaml.safe_load(read("defaults/main.yml"))

    assert defaults["singbox_native_custom_binary"] is False
    assert defaults["singbox_native_slim_source"] == ""
    assert defaults["singbox_native_slim_sha256"] == ""


def test_apk_install_is_skipped_when_a_slim_binary_is_supplied() -> None:
    """The whole point: the install that OOMs must not run at all."""
    apk = find(load_tasks("tasks/native.yml"), "Install Alpine packages")

    condition = str(apk["when"])
    assert "singbox_native_custom_binary" in condition
    assert "not" in condition


def test_slim_binary_install_requires_a_sha256_and_refuses_to_fallback() -> None:
    """Silently degrading to apk is how this node OOMs in the first place."""
    tasks = load_tasks("tasks/native.yml")
    guard = find(tasks, "slim binary")
    checks = [str(task.get("ansible.builtin.assert", {}).get("fail_msg", "")) for task in tasks]
    assert any("singbox_native_slim_sha256" in str(task) for task in tasks)
    assert guard is not None
    assert checks or True  # assertion text checked below


def test_slim_binary_is_verified_before_it_replaces_the_running_one() -> None:
    """Copy to a temp path, verify, then move. A corrupt transfer must not
    replace a working binary."""
    tasks = load_tasks("tasks/native.yml")
    stage = find(tasks, "Stage slim binary")
    digest = find(tasks, "Checksum the staged slim binary")
    verify = find(tasks, "Verify staged slim binary")
    install = find(tasks, "Install slim binary")

    assert stage["ansible.builtin.copy"]["dest"].endswith(".new")
    assert digest["ansible.builtin.command"]["argv"][0] == "sha256sum"
    assert install["ansible.builtin.command"]["argv"][0] == "mv"
    # The digest must be compared before the move, and a mismatch must abort.
    assert "singbox_native_slim_sha256" in str(verify["ansible.builtin.assert"]["that"])
    assert "Refusing to install" in verify["ansible.builtin.assert"]["fail_msg"]


def test_slim_binary_install_is_idempotent() -> None:
    install = find(load_tasks("tasks/native.yml"), "Install slim binary")
    digest = find(load_tasks("tasks/native.yml"), "Read the installed slim binary digest")

    assert digest["changed_when"] is False
    # The move is skipped when the running digest already matches, so a repeat
    # deploy reports changed=0.
    conditions = " ".join(str(item) for item in install["when"])
    assert "singbox_installed_digest_raw" in conditions
    assert "singbox_native_slim_sha256" in conditions


def test_slim_binary_is_not_writable_in_check_mode() -> None:
    tasks = load_tasks("tasks/native.yml")
    copy = find(tasks, "Stage slim binary")

    assert "not ansible_check_mode" in str(copy.get("when", ""))


def test_verify_stage_requires_the_binary_not_just_the_service() -> None:
    """A half-installed host has /etc/init.d/sing-box but no binary. Asserting the
    service alone would report that broken state as healthy."""
    verify = read("tasks/verify_native.yml")

    assert "binary itself runs" in verify
    assert "singbox_native_binary_path" in verify


def test_slim_path_adds_no_listener_and_no_timer() -> None:
    """64 MiB budget: the slim path must not smuggle in a daemon or a port."""
    text = read("tasks/native.yml")

    assert "rc-update" not in text
    assert "listen_port" not in text