"""Contract tests for Magpie GOMEMLIMIT validation."""

from pathlib import Path
import re
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "collections/ansible_collections/vps/services/roles/docker_apps"


def test_magpie_tasks_assert_gomemlimit_syntax() -> None:
    raw_tasks = yaml.safe_load(
        (ROLE / "tasks/magpie.yml").read_text(encoding="utf-8")
    )
    tasks = cast(list[dict[str, Any]], raw_tasks)
    assert_task = next(
        task for task in tasks if "GOMEMLIMIT conforms to Go runtime" in str(task.get("name", ""))
    )
    assert "ansible.builtin.assert" in assert_task
    assert_dict = cast(dict[str, Any], assert_task["ansible.builtin.assert"])
    assert_spec = cast(list[str], assert_dict["that"])
    assert any("docker_apps_magpie_gomemlimit is match" in rule for rule in assert_spec)

    pattern = r"^[0-9]+([KMGTkmgt]i?B|B)?$"
    valid_cases = ["384MiB", "512MB", "1GiB", "2048KiB", "1048576B", "1048576"]
    invalid_cases = ["384m", "512M", "1g", "1G", "2k", "384mb", "foo"]

    for val in valid_cases:
        assert re.match(pattern, val), f"Expected valid: {val}"
    for val in invalid_cases:
        assert not re.match(pattern, val), f"Expected invalid: {val}"
