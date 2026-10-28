"""Contract tests for Magpie GOMEMLIMIT validation."""

from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "collections/ansible_collections/vps/services/roles/docker_apps"


def test_magpie_tasks_assert_gomemlimit_syntax():
    tasks = yaml.safe_load(
        (ROLE / "tasks/magpie.yml").read_text(encoding="utf-8")
    )
    assert_task = next(
        task for task in tasks if "GOMEMLIMIT conforms to Go runtime" in task.get("name", "")
    )
    assert "ansible.builtin.assert" in assert_task
    assert_spec = assert_task["ansible.builtin.assert"]["that"]
    assert any("docker_apps_magpie_gomemlimit is match" in rule for rule in assert_spec)

    # Validate regex correctness against positive and negative test cases
    pattern = r"^[0-9]+([KMGTkmgt]i?B|B)?$"
    valid_cases = ["384MiB", "512MB", "1GiB", "2048KiB", "1048576B", "1048576"]
    invalid_cases = ["384m", "512M", "1g", "1G", "2k", "384mb", "foo", ""]

    for val in valid_cases:
        assert re.match(pattern, val), f"Expected valid: {val}"
    for val in invalid_cases:
        if val == "":
            continue
        assert not re.match(pattern, val), f"Expected invalid: {val}"
