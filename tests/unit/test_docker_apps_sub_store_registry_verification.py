import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


VERIFY_TASKS = (
    Path(__file__).resolve().parents[2]
    / "collections/ansible_collections/vps/services/roles/docker_apps/tasks/verify.yml"
)


@pytest.mark.parametrize(
    ("registry", "nonempty", "forbidden"),
    [
        ({"nodes": [{"name": "example", "observations": [1]}]}, True, False),
        ({"nodes": [{"TOKEN": "secret-value"}]}, True, True),
        ({}, False, False),
        ([], False, False),
    ],
)
def test_registry_verification_keeps_large_state_remote_and_reports_only_safety_flags(
    tmp_path: Path, registry: object, nonempty: bool, forbidden: bool
) -> None:
    tasks = yaml.safe_load(VERIFY_TASKS.read_text())
    summary = next(
        task
        for task in tasks
        if task.get("name") == "Summarize Sub-Store capability registry on the remote host"
    )
    script = summary["ansible.builtin.command"]["argv"][2]
    state_file = tmp_path / "registry.json"
    _ = state_file.write_text(json.dumps(registry))

    result = subprocess.run(
        [sys.executable, "-c", script, str(state_file)],
        capture_output=True,
        check=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "nonempty_mapping": nonempty,
        "forbidden_keys": forbidden,
    }
    assert "secret-value" not in result.stdout
