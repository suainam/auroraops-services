"""The memory-envelope guard must not misfire in check mode.

`nat-deploy` runs `nat-check` first, and `makefiles/ops.mk` executes the check
action with `--check`. Under `--check`, Ansible skips `command` tasks, so the
memory probe produced empty stdout, the derived fact became 0, and the
fail-closed assertion below reported a memory fault on a host whose memory was
fine (measured on nat-jp3: 196608 kB, cgroup limit 201326592).

That aborted `nat-deploy` at ok=26/failed=1 for every NAT node. The fix skips the
assertion in check mode only.

What is asserted here, and why each part:

  * the guard exists, so the regression cannot come back silently;
  * the probe is still a `command` with no check-mode skip, which is the
    upstream cause -- asserted so that "fixing" it by skipping the probe is not
    mistaken for the same thing;
  * real runs are untouched, so the fail-closed guarantee survives;
  * and behaviourally: the exact task pair runs under `--check` without failing,
    and still fails under a real run when the probe returns nothing. The last one
    is what stops this from being satisfied by deleting the assertion.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "collections/ansible_collections/vps/services/roles/singbox"


def tasks() -> list:
    return yaml.safe_load((ROLE / "tasks/native.yml").read_text(encoding="utf-8"))


def find(name_fragment: str) -> dict:
    return next(t for t in tasks() if name_fragment in t["name"])


def test_the_memory_assert_is_skipped_in_check_mode() -> None:
    # `.get` rather than indexing: without the guard this task has no `when` key at
    # all, and a KeyError would report the regression as a crash in the test rather
    # than as the missing condition it actually is.
    guard = find("Assert effective memory is sane").get("when", "")

    assert "not ansible_check_mode" in str(guard), (
        "the memory assertion carries no check-mode guard, so --check reports a "
        "memory fault on every host whose memory is fine"
    )


def test_the_probe_itself_is_not_skipped_in_check_mode() -> None:
    """The cause, pinned so it is not "fixed" in the wrong direction.

    Skipping the probe would also silence the failure, and would additionally make
    the recorded fact wrong in check mode. The probe is harmless to run -- it only
    reads /proc and /sys -- so the narrow fix is the right one.
    """
    probe = find("Resolve effective memory envelope")

    assert "not ansible_check_mode" not in str(probe.get("when", ""))
    assert probe["ansible.builtin.command"]["argv"][0] == "/bin/sh"


def test_real_runs_keep_the_fail_closed_guard() -> None:
    """A dry run has nothing to write; a real deploy must still refuse.

    This is the half that must not be relaxed. Dropping the assertion outright, or
    widening its condition to something that also matches real runs, would let a
    genuinely non-positive envelope through and write a GOMEMLIMIT derived from
    nothing.
    """
    guard = find("Assert effective memory is sane")

    assert guard["ansible.builtin.assert"]["that"] == [
        "singbox_effective_memtotal_mb | int > 0"
    ]
    assert "refusing to write GOMEMLIMIT" in guard["ansible.builtin.assert"]["fail_msg"]


def _playbook(tmp_path: Path, probe_body: str) -> Path:
    """The probe/record/assert trio exactly as the role orders it."""
    path = tmp_path / "check-mode.yml"
    path.write_text(
        f"""---
- hosts: localhost
  connection: local
  gather_facts: false
  become: false
  tasks:
    - name: Resolve effective memory envelope
      ansible.builtin.command:
        argv:
          - /bin/sh
          - -c
          - |
{probe_body}
      register: singbox_effective_mem
      changed_when: false
      failed_when: false
    - name: Record effective memory fact
      ansible.builtin.set_fact:
        singbox_effective_memtotal_mb: "{{{{ singbox_effective_mem.stdout | trim | int }}}}"
    - name: Assert effective memory is sane
      when: not ansible_check_mode
      ansible.builtin.assert:
        that:
          - singbox_effective_memtotal_mb | int > 0
        fail_msg: "Effective memory probe returned a non-positive value; refusing to write GOMEMLIMIT."
""",
        encoding="utf-8",
    )
    return path


def _ansible() -> str | None:
    """Locate ansible-playbook without assuming this repo owns a venv.

    The behavioural tests are the ones that matter here -- a text assertion on the
    `when` key would pass on a comment -- so they must actually run. Resolution
    order is PATH, then the nearest ancestor .venv, which is where the parent
    control repo keeps it when the subrepo is checked out as a submodule.
    """
    found = shutil.which("ansible-playbook")
    if found:
        return found
    for parent in ROOT.parents:
        for relative in (".venv/bin/ansible-playbook", ".local/bin/ansible-playbook"):
            candidate = parent / relative
            if candidate.is_file():
                return str(candidate)
    return None


def _run(playbook: Path, *extra: str) -> subprocess.CompletedProcess:
    # The parent control repo's ansible.cfg sets `strategy = mitogen_linear` with a
    # plugin path that does not exist inside this subrepo checkout, so an
    # unisolated run fails before it reaches any task. Pointing ANSIBLE_CONFIG at a
    # written-out empty config keeps these tests about the role rather than about
    # whichever repo happens to contain them -- and matters for the check-mode
    # question specifically, because a strategy plugin could change what runs.
    config = playbook.parent / "ansible.cfg"
    config.write_text("[defaults]\n", encoding="utf-8")
    return subprocess.run(
        [_ansible(), "-i", "localhost,", "-c", "local", str(playbook), *extra],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "ANSIBLE_CONFIG": str(config),
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_LOCALHOST_WARNING": "0",
            "ANSIBLE_INVENTORY_UNPARSED_WARNING": "0",
            "ANSIBLE_DEPRECATION_WARNINGS": "0",
        },
    )


@pytest.mark.skipif(_ansible() is None, reason="ansible-playbook is unavailable")
def test_check_mode_does_not_report_a_memory_fault(tmp_path: Path) -> None:
    """The regression itself: `--check` must not fail on a healthy host.

    A `command` task is skipped under `--check`, which is exactly the condition
    that produced empty stdout and a spurious failure on every NAT node.
    """
    playbook = _playbook(tmp_path, "            echo $((196608 / 1024))")
    result = _run(playbook, "--check")

    assert result.returncode == 0, result.stdout[-800:] + result.stderr[-400:]


@pytest.mark.skipif(_ansible() is None, reason="ansible-playbook is unavailable")
def test_a_real_run_still_refuses_an_empty_probe(tmp_path: Path) -> None:
    """The other half: the guard is not simply gone.

    Without this, deleting the assertion would satisfy the test above.
    """
    playbook = _playbook(tmp_path, "            true  # probe yields no output")
    result = _run(playbook)

    assert result.returncode != 0, (
        "a real run must still fail when the probe returns nothing"
    )
    assert "refusing to write GOMEMLIMIT" in result.stdout


@pytest.mark.skipif(_ansible() is None, reason="ansible-playbook is unavailable")
def test_a_real_run_accepts_a_healthy_probe(tmp_path: Path) -> None:
    playbook = _playbook(tmp_path, "            echo $((196608 / 1024))")
    result = _run(playbook)

    assert result.returncode == 0, result.stdout[-800:] + result.stderr[-400:]


@pytest.mark.skipif(_ansible() is None, reason="ansible-playbook is unavailable")
def test_check_mode_still_reports_a_real_assertion_failure(tmp_path: Path) -> None:
    """Check mode is not a blanket mute.

    Without this, "fixing" the bug by disabling check mode for the whole role would
    satisfy the regression test above while turning the check stage into a stage
    that always passes -- worse than the failure it replaced. An assertion runs
    normally under `--check`, so it is the right probe here; a `command` task would
    be skipped and prove nothing.
    """
    path = tmp_path / "genuine-failure.yml"
    path.write_text(
        """---
- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: An assertion that genuinely cannot hold
      ansible.builtin.assert:
        that:
          - 1 == 2
        fail_msg: "deliberate failure"
""",
        encoding="utf-8",
    )
    result = _run(path, "--check")

    assert result.returncode != 0, "check mode must still surface a real failure"
    assert "deliberate failure" in result.stdout


def test_the_workaround_is_not_leaking_into_other_roles() -> None:
    """Scope check: the fix belongs to this one assertion.

    Guards against a future 'fix' that disables command tasks or check mode more
    broadly in this role, which would silence genuine dry-run failures.
    """
    native = (ROLE / "tasks/native.yml").read_text(encoding="utf-8")

    assert "ignore_check_mode" not in native
    assert "check_mode: no" not in native
