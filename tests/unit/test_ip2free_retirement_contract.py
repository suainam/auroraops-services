"""The residential proxy must actually be able to leave.

Issue #40 was closed with its acceptance list unticked, and the capability was
still running afterwards: `ip2free_gateway` was true on cc15, sing-box still
held UDP 30059, and `ip2free-health.timer` was rewriting
`06_ip2free.json` every 30 minutes. Declaring a capability retired and leaving it
installed is only safe if something converges the host to match, and nothing
did. The playbook gated the whole include on the flag, so switching the flag off
skipped the role entirely -- units, working directory and generated fragment all
stayed exactly where they were.

The generated fragment is the part that made this cost more than tidiness. No
Ansible role manages it: the sing-box role ships a `06_ip2free.json.j2` template
that nothing deploys, and the file on disk is written by `update_outbounds.py` on
a timer. So a capability that was supposed to be off kept changing part of the
sing-box configuration, which is a plausible enough cause for other roles'
verify stages to fail for reasons that had nothing to do with them.

These tests hold the retirement path in place. They read role and playbook text
only, so they cannot prove a host was cleaned -- `make verify` on a real host is
what does that -- but they do fail if the path is deleted or made unreachable
again, which is the failure that let #40 close early.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "collections/ansible_collections/vps/services/roles/ip2free_gateway"
MAIN = ROLE / "tasks/main.yml"
VERIFY = ROLE / "tasks/verify.yml"
DEFAULTS = ROLE / "defaults/main.yml"
DEPLOY_PB = REPO / "playbooks/services/deploy.yml"
VERIFY_PB = REPO / "playbooks/services/verify.yml"

UNIT_PATHS = (
    "/etc/systemd/system/ip2free-agent.timer",
    "/etc/systemd/system/ip2free-health.timer",
    "/etc/systemd/system/ip2free-agent.service",
    "/etc/systemd/system/ip2free-health.service",
)


def _tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def _play_tasks(path: Path) -> list[dict]:
    """Task list of a services playbook.

    These files are a single play, so the tasks are nested one level down. The
    first version of this test read the top level, found no `ip2free_gateway`
    task, and reported the role as never having been included -- a false
    negative that would have passed on a genuinely broken playbook.
    """
    document = _tasks(path)
    tasks: list[dict] = []
    for play in document:
        if isinstance(play, dict) and isinstance(play.get("tasks"), list):
            tasks.extend(play["tasks"])
        elif isinstance(play, dict):
            tasks.append(play)
    return tasks


def _flag(task: dict) -> str:
    return str(task.get("when", ""))


def test_the_playbooks_do_not_gate_the_include_on_the_capability() -> None:
    """The flag selects an outcome inside the role; it must not skip the role.

    The old gate was `default(true)`, so it was fail-open as well: deleting the
    key from host_vars left the capability on. Keeping the include ungated means
    the role's own `default(false)` is the only thing that decides, and it fails
    closed.
    """
    for path in (DEPLOY_PB, VERIFY_PB):
        includes = [
            task
            for task in _play_tasks(path)
            if "ip2free_gateway" in str(task.get("name", ""))
        ]
        assert includes, (
            f"{path.name} no longer includes the ip2free_gateway role, so the "
            "retirement path can never run"
        )
        for task in includes:
            assert "when" not in task, (
                f"{path.name} gates the ip2free_gateway include on "
                f"{_flag(task)!r}, which makes retirement unreachable: the role "
                "would not run at all with the capability off"
            )


def test_the_role_has_a_retirement_path_gated_on_the_capability_being_off() -> None:
    retirement = [
        task
        for task in _tasks(MAIN)
        if "Retire IP2Free" in str(task.get("name", ""))
    ]
    assert retirement, (
        "the role has no retirement path, so switching the capability off skips "
        "the role and leaves everything it installed in place"
    )
    assert "block" in retirement[0], "retirement must be a block of removals"
    gate = _flag(retirement[0])
    assert "ip2free_gateway" in gate and "not" in gate, (
        f"retirement must run when the capability is off, gate is {gate!r}"
    )


def test_retirement_removes_the_units_the_directory_and_the_fragment() -> None:
    """All three, because each was observed still present after #40 closed."""
    retirement = next(
        task for task in _tasks(MAIN) if "Retire IP2Free" in str(task.get("name", ""))
    )
    steps = retirement["block"]
    text = yaml.safe_dump(steps, allow_unicode=True)

    for unit in UNIT_PATHS:
        assert unit in text, f"retirement does not remove {unit}"
    assert "ip2free_gateway_ip2free_dir" in text, (
        "retirement does not remove the working directory"
    )
    assert "ip2free_gateway_ip2free_singbox_fragment" in text, (
        "retirement does not remove the generated sing-box fragment, which is "
        "the artifact a timer keeps rewriting"
    )
    # Removal has to be idempotent and safe on a host that never had the role.
    # `systemd: state=stopped` on a unit that does not exist is an error, and
    # most hosts in the inventory never had this capability, so an unconditional
    # stop would turn the retirement path into a failure on ten of them.
    #
    # The check has to be per-loop, not per-block: `item.stat.exists` appears in
    # both the timer and the service loops, so counting occurrences only proves
    # one of them was guarded. An earlier version asserted the string was
    # present, and a control that removed the guard from exactly one loop still
    # passed.
    for step in steps:
        if "ansible.builtin.systemd" not in step:
            continue
        if "loop" not in step:
            # A systemd step that names a single unit by name is a genuine
            # failure if the unit is absent, so it has to be guarded. The
            # daemon-reload is the exception: it names no unit and is already
            # conditional on whether any unit file was there.
            #
            # The unit name lives in the *module arguments*, not in a key. The
            # first version tested `"name:" in step`, which looks for a dict key
            # spelled `name:` -- never present, because YAML gives `name`. The
            # branch was dead: injecting an unguarded, loop-less, named systemd
            # stop, exactly the shape this exists to reject, left all eight tests
            # green.
            module_args = step.get("ansible.builtin.systemd") or {}
            if "name" in module_args:
                assert "when" in step, (
                    f"retirement step {step.get('name')!r} stops the named unit "
                    f"{module_args['name']!r} with no condition, so a host that "
                    "never had this capability fails on a unit that was never "
                    "installed"
                )
            continue
        guards = str(step.get("when", ""))
        assert "item.stat.exists" in guards, (
            f"retirement step {step.get('name')!r} acts on systemd units without "
            "checking the unit file exists, so a host that never had this "
            "capability fails on a unit that was never installed"
        )


def test_the_fragment_path_is_declared_and_names_the_singbox_config_dir() -> None:
    """The fragment has no Ansible-managed counterpart, so the path is stated here."""
    defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    fragment = defaults.get("ip2free_gateway_ip2free_singbox_fragment", "")
    assert "06_ip2free.json" in fragment
    assert "singbox_config_dir" in fragment, (
        "the fragment lives in the sing-box config directory; hardcoding the "
        "path would leave it behind on any host that configures it elsewhere"
    )


def test_verify_asserts_absence_when_the_capability_is_off() -> None:
    """Asserting absence is what tells "retired" apart from "never installed"."""
    blocks = [task for task in _tasks(VERIFY) if isinstance(task.get("block"), list)]
    assert len(blocks) >= 2, (
        "verify must assert both directions: a host with the capability off and "
        "nothing installed is indistinguishable from a host that never had it, "
        "unless the retired state is asserted too"
    )
    off = [
        task
        for task in blocks
        if "ip2free_gateway" in _flag(task) and "not" in _flag(task)
    ]
    assert off, "verify has no block gated on the capability being off"
    text = yaml.safe_dump(off[0]["block"], allow_unicode=True)
    assert "state: absent" not in text, (
        "the retired-state block asserts, it does not remove; removal belongs to "
        "the deploy path"
    )
    assert "selectattr('stat.exists')" in text and "== 0" in text, (
        "the retired-state assertion must require that nothing is left, and say "
        "which paths, so nobody has to go and look"
    )


def test_the_singbox_inbound_and_route_are_still_gated_on_the_capability() -> None:
    """Turning the flag off must actually remove the data plane, not just files.

    The inbound, its route rule and the subscription entries are all conditioned
    on the flag, so a host with the flag off stops rendering them. If that
    gating is ever dropped, the port comes back open with nothing managing it.
    """
    singbox = REPO / "collections/ansible_collections/vps/services/roles/singbox/templates"
    for name in ("inbounds_direct.json.j2", "route_direct.json.j2"):
        text = (singbox / name).read_text(encoding="utf-8")
        assert "ip2free_gateway" in text, (
            f"{name} references the residential proxy without gating it on the "
            "capability flag"
        )


@pytest.mark.parametrize("template", ["inbounds_direct.json.j2", "route_direct.json.j2"])
def test_no_residential_port_literal_survives_in_the_singbox_templates(
    template: str,
) -> None:
    """A default naming the retired port would keep the endpoint alive.

    30059 is being given up. A `default(30059)` in a template renders the old
    number after the allocation moves, reports nothing, and reinstates a port
    that was supposed to be closed.
    """
    text = (
        REPO
        / "collections/ansible_collections/vps/services/roles/singbox/templates"
        / template
    ).read_text(encoding="utf-8")
    assert "default(30059)" not in text, (
        f"{template} still falls back to the retired residential port; the "
        "variable must be required so a missing one fails loudly"
    )
