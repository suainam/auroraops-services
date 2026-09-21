"""Run a configured isolated probe adapter without touching production Clash.

The adapter is intentionally external: proxykit/sing-box can evolve without
embedding protocol clients in the Sub-Store role. The adapter receives one
normalized node as JSON and returns one observation as JSON.
"""
from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Iterator, Sequence
from typing import Any

from registry import CAPABILITIES, NodeIdentity, Observation


class ProbeError(RuntimeError):
    """The probe adapter is not configured."""


def _failed_observation() -> Observation:
    return Observation(
        alive=False,
        capabilities={name: "unknown" for name in CAPABILITIES},
        probe_status="infrastructure_error",
    )


def _force_remove_probe_container(container_name: str) -> None:
    if not container_name:
        return
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


@contextlib.contextmanager
def _probe_container_lifecycle(env: dict[str, str]) -> Iterator[None]:
    """Best-effort cleanup for every Docker-backed probe exit path.

    docker run --rm handles the normal case, but the parent owns the unique
    container name and always issues a final rm -f so timeout, adapter crash,
    cancellation, and partial startup cannot leak probe containers.
    """
    container_name = env.get("SUB_STORE_PROBE_CONTAINER_NAME", "")
    try:
        yield
    finally:
        _force_remove_probe_container(container_name)


def _run_adapter(
    command: Sequence[str],
    payload: str,
    cwd: str,
    env: dict[str, str],
    timeout: float,
) -> subprocess.CompletedProcess[str] | None:
    process = subprocess.Popen(
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        return None
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def run_isolated_probe(
    command: Sequence[str],
    identity: NodeIdentity,
    timeout: float = 60.0,
    auth: str = "",
    context: dict[str, Any] | None = None,
    outbound: dict[str, Any] | None = None,
) -> Observation:
    """Run a configured adapter in a scrubbed, temporary process context."""
    if not command:
        raise ProbeError("probe adapter command is not configured")
    payload = {
        "node_id": identity.node_id,
        "provider": identity.provider,
        "server": identity.server,
        "port": identity.port,
        "protocol": identity.protocol,
        "transport": identity.transport,
        "display_name": identity.display_name,
    }
    if auth:
        payload["auth"] = auth
    if outbound is not None:
        payload["outbound"] = outbound
    if context:
        payload["context"] = context
    env = {
        key: os.environ[key]
        for key in (
            "PATH",
            "LANG",
            "LC_ALL",
            "SINGBOX_PROBE_IMAGE",
            "IPAPI_API_KEY_FILE",
        )
        if key in os.environ
    }
    if env.get("SINGBOX_PROBE_IMAGE"):
        env["SUB_STORE_PROBE_CONTAINER_NAME"] = (
            f"sub-store-capability-probe-{os.getpid()}-{time.time_ns()}"
        )
    try:
        with tempfile.TemporaryDirectory(prefix="sub-store-probe-") as workdir:
            env.update({"HOME": workdir, "TMPDIR": workdir})
            with _probe_container_lifecycle(env):
                completed = _run_adapter(
                    command,
                    json.dumps(payload),
                    workdir,
                    env,
                    timeout,
                )
    except OSError:
        return _failed_observation()
    if completed is None or completed.returncode != 0:
        return _failed_observation()
    try:
        result: dict[str, Any] = json.loads(completed.stdout)
        if not isinstance(result, dict):
            raise TypeError("adapter response must be an object")
        capabilities = result.get("capabilities", {})
        metrics = result.get("metrics", {})
        details = result.get("details", {})
        alive = result.get("alive")
        if not isinstance(capabilities, dict) or not isinstance(metrics, dict) or not isinstance(details, dict):
            raise TypeError("adapter response fields must be objects")
        if not isinstance(alive, bool):
            raise TypeError("alive must be a boolean")
        if set(capabilities) - set(CAPABILITIES):
            raise ValueError("unsupported capability")
        if set(capabilities.values()) - {"pass", "fail", "unknown"}:
            raise ValueError("unsupported status")
        return Observation(
            alive=alive,
            capabilities=capabilities,
            metrics=metrics,
            details=details,
            checked_at=float(result["checked_at"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, AttributeError):
        return _failed_observation()
