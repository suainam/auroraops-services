"""Persistent node capability registry for an isolated probe adapter."""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CAPABILITIES = ("pure", "ai", "media", "low_rtt", "bilibili")




def _safe_transport(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    blocked = ("password", "uuid", "token", "secret", "private", "psk", "authorization", "cookie", "credential", "header")

    def clean(item: Any, key: str = "") -> Any:
        lowered = key.lower()
        if any(marker in lowered for marker in blocked):
            return None
        if isinstance(item, str) and (
            "://" in item or re.search(r"\b(?:uuid|password|token|secret|key)\s*=", item, re.I)
        ):
            return None
        if isinstance(item, Mapping):
            return {str(k): cleaned for k, v in item.items() if (cleaned := clean(v, str(k))) is not None}
        if isinstance(item, list):
            return [cleaned for v in item if (cleaned := clean(v)) is not None]
        return item if item is None or isinstance(item, (str, int, float, bool)) else None

    return {key: cleaned for key, value in value.items() if (cleaned := clean(value, str(key))) is not None}


@dataclass(frozen=True)
class NodeIdentity:
    provider: str
    server: str
    port: int
    protocol: str
    auth_fingerprint: str  # caller must provide a one-way digest, never a secret
    display_name: str = field(compare=False)
    transport: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.auth_fingerprint):
            raise ValueError("auth_fingerprint must be a 64-character lowercase SHA-256 digest")
        for field_name in ("provider", "server", "protocol", "display_name"):
            value = getattr(self, field_name).lower()
            if "://" in value or "@" in value or re.search(r"\b(?:uuid|password|token|secret|key)\s*=", value):
                raise ValueError(f"{field_name} must not contain proxy credentials or URI data")
        object.__setattr__(self, "transport", _safe_transport(self.transport))
        for field_name in ("provider", "server", "protocol"):
            object.__setattr__(self, field_name, getattr(self, field_name).lower())

    @property
    def node_id(self) -> str:
        canonical = {
            "server": self.server,
            "port": self.port,
            "protocol": self.protocol,
            "auth_fingerprint": self.auth_fingerprint,
            "transport": self.transport,
        }
        payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def normalize_node(raw: Mapping[str, Any], provider: str = "unknown") -> tuple[NodeIdentity, Any]:
    """Extract a safe identity; return auth only for one-shot probe stdin."""
    if not isinstance(raw, Mapping):
        raise ValueError("node must be an object")
    server = raw.get("server") or raw.get("address") or raw.get("host")
    port = raw.get("port") or raw.get("server_port")
    protocol = raw.get("protocol") or raw.get("type")
    raw_display_name = raw.get("display_name") or raw.get("name") or raw.get("remark") or raw.get("tag") or server
    provider_prefix = raw.get("provider_prefix", f"[{provider}]")
    if not isinstance(provider_prefix, str) or not provider_prefix or len(provider_prefix) > 64:
        raise ValueError("node provider prefix is invalid")
    display_name = f"{provider_prefix} {raw_display_name}"
    if not isinstance(server, str) or not server:
        raise ValueError("node server is required")
    if isinstance(port, bool) or not isinstance(port, (int, str)):
        raise ValueError("node port is invalid")
    try:
        port_number = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError("node port is invalid") from exc
    if not 1 <= port_number <= 65535:
        raise ValueError("node port is invalid")
    if not isinstance(protocol, str) or not protocol:
        raise ValueError("node protocol is required")
    if not isinstance(display_name, str) or not display_name:
        raise ValueError("node display name is required")
    if not isinstance(provider, str) or not provider:
        raise ValueError("node provider is required")
    auth_material = {
        key: raw[key]
        for key in ("uuid", "password", "token", "auth", "private_key", "psk", "obfs_password")
        if raw.get(key)
    }
    obfs = raw.get("obfs")
    if isinstance(obfs, Mapping) and isinstance(obfs.get("password"), str) and obfs["password"]:
        auth_material["obfs_password"] = obfs["password"]
    if any(not isinstance(value, str) for value in auth_material.values()):
        raise ValueError("node auth material is invalid")
    auth = next(iter(auth_material.values()), "") if len(auth_material) == 1 else auth_material
    auth_digest = hashlib.sha256(
        json.dumps(auth_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    transport_keys = (
        "tls", "transport", "flow", "packet_encoding", "multiplex", "sni", "server_name",
        "alpn", "network", "path", "host", "service_name", "method", "obfs", "insecure",
    )
    transport = _safe_transport({key: raw[key] for key in transport_keys if key in raw})
    identity = NodeIdentity(
        provider=provider,
        server=server,
        port=port_number,
        protocol=protocol,
        auth_fingerprint=auth_digest,
        display_name=display_name,
        transport=transport,
    )
    return identity, auth


@dataclass
class Observation:
    alive: bool
    capabilities: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: float = field(default_factory=time.time)
    probe_status: str = "valid"

    def __post_init__(self) -> None:
        if not math.isfinite(self.checked_at):
            raise ValueError("checked_at must be finite")
        if self.probe_status not in {"valid", "infrastructure_error"}:
            raise ValueError("unsupported probe_status")

SAFE_DETAIL_KEYS = {
    "abuse_score", "asn", "claude", "country", "exit_ip_fingerprint", "fraud_score", "gemini",
    "geo_checked_at", "hk_tw_media", "international_media", "ip_type", "managed_egress", "openai",
    "probe_revision", "pure_candidate", "purity_score", "region", "risk_checked_at", "shared_count", "status", "threat",
}
SERVICE_DETAIL_KEYS = {"openai", "claude", "gemini", "hk_tw_media", "international_media"}


def _safe_details(details: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in details.items():
        if key not in SAFE_DETAIL_KEYS:
            continue
        if key in {"abuse_score", "fraud_score", "purity_score"} and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            if key in {"abuse_score", "fraud_score"} and 0 <= value <= 100:
                safe[key] = value
            elif key == "purity_score" and 0 <= value <= 1:
                safe[key] = value
        elif key in {"geo_checked_at", "risk_checked_at"} and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
            safe[key] = float(value)
        elif key == "asn" and isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 4294967295:
            safe[key] = value
        elif key == "shared_count" and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            safe[key] = value
        elif key == "managed_egress" and isinstance(value, bool):
            safe[key] = value
        elif key == "country" and isinstance(value, str) and re.fullmatch(r"[A-Z]{2}", value):
            safe[key] = value
        elif key in {"ip_type", "region"} and isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9 _/-]{0,31}", value):
            safe[key] = value
        elif key in {"exit_ip_fingerprint", "probe_revision"} and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
            safe[key] = value
        elif key == "pure_candidate" and isinstance(value, bool):
            safe[key] = value
        elif key in SERVICE_DETAIL_KEYS and value in {"pass", "fail", "unknown"}:
            safe[key] = value
        elif key == "threat" and value in {"low", "medium", "high", "unknown"}:
            safe[key] = value
        elif key == "status" and value in {"pass", "fail", "unknown", "partial", "available", "blocked"}:
            safe[key] = value
    return safe


def _safe_metrics(metrics: dict[str, float]) -> dict[str, float]:
    allowed = {"rtt_p50", "rtt_p95", "jitter", "success_rate"}
    return {
        key: value
        for key, value in metrics.items()
        if key in allowed
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    }


def _safe_timestamp(value: Any) -> float:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return 0.0
    return timestamp if math.isfinite(timestamp) else 0.0


def _safe_last_observation(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    capabilities = raw.get("capabilities", {})
    if not isinstance(capabilities, dict):
        capabilities = {}
    capabilities = {
        key: value
        for key, value in capabilities.items()
        if key in CAPABILITIES and value in {"pass", "fail", "unknown"}
    }
    try:
        checked_at = float(raw.get("checked_at", 0))
        observation = Observation(
            alive=raw.get("alive") if isinstance(raw.get("alive"), bool) else False,
            capabilities=capabilities,
            metrics=raw.get("metrics", {}) if isinstance(raw.get("metrics", {}), dict) else {},
            details=raw.get("details", {}) if isinstance(raw.get("details", {}), dict) else {},
            checked_at=checked_at,
            probe_status=raw.get("probe_status", "valid"),
        )
    except (TypeError, ValueError):
        return {}
    return asdict(
        Observation(
            alive=observation.alive,
            capabilities=observation.capabilities,
            metrics=_safe_metrics(observation.metrics),
            details=_safe_details(observation.details),
            checked_at=observation.checked_at,
            probe_status=observation.probe_status,
        )
    )


@dataclass
class NodeState:
    identity: NodeIdentity
    providers: list[str] = field(default_factory=list)
    provider_display_names: dict[str, str] = field(default_factory=dict)
    history: list[bool] = field(default_factory=list)
    capability_history: dict[str, list[str]] = field(default_factory=dict)
    capability_failures: dict[str, int] = field(default_factory=dict)
    consecutive_failures: int = 0
    last_seen: float = 0.0
    last_observation: dict[str, Any] = field(default_factory=dict)
    owned: bool = False
    fixed_ip: bool = False

    def probe_context(self) -> dict[str, Any]:
        return {
            "details": _safe_details(self.last_observation.get("details", {})),
            "capabilities": {
                key: value
                for key, value in self.last_observation.get("capabilities", {}).items()
                if key in CAPABILITIES and value in {"pass", "fail", "unknown"}
            },
        }

    def record(self, observation: Observation, window: int = 10) -> None:
        if observation.probe_status == "infrastructure_error":
            return
        reported = dict(observation.capabilities)
        for name in CAPABILITIES:
            reported.setdefault(name, "unknown")
        capabilities = dict(reported)
        for name, status in reported.items():
            self.capability_history.setdefault(name, []).append(status)
            del self.capability_history[name][:-window]
            if status == "pass":
                self.capability_failures[name] = 0
            elif status == "fail":
                self.capability_failures[name] = self.capability_failures.get(name, 0) + 1
        observation = Observation(
            alive=observation.alive,
            capabilities=capabilities,
            metrics=_safe_metrics(observation.metrics),
            details=_safe_details(observation.details),
            checked_at=observation.checked_at,
            probe_status=observation.probe_status,
        )
        self.history.append(observation.alive)
        del self.history[:-window]
        if observation.alive:
            self.consecutive_failures = 0
            self.last_seen = observation.checked_at
        else:
            self.consecutive_failures += 1
        self.last_observation = asdict(observation)
    def eligible(self, now: float, ttl_seconds: float, required_passes: int = 2) -> bool:
        if not math.isfinite(now) or not math.isfinite(self.last_seen) or self.last_seen <= 0 or now - self.last_seen >= ttl_seconds:
            return False
        return sum(self.history[-3:]) >= required_passes


class CapabilityRegistry:
    def __init__(self, path: Path | None = None, ttl_seconds: int = 86400) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds
        self.nodes: dict[str, NodeState] = {}
        if path and path.exists():
            self._load()

    def observe(self, identity: NodeIdentity, observation: Observation, *, owned: bool = False, fixed_ip: bool = False) -> NodeState | None:
        invalid_capabilities = set(observation.capabilities) - set(CAPABILITIES)
        invalid_statuses = set(observation.capabilities.values()) - {"pass", "fail", "unknown"}
        if invalid_capabilities or invalid_statuses:
            raise ValueError("observation contains unsupported capabilities or statuses")
        node = self.nodes.get(identity.node_id)
        if observation.probe_status == "infrastructure_error":
            return node
        if node is None:
            node = NodeState(
                identity=identity,
                providers=[identity.provider],
                provider_display_names={identity.provider: identity.display_name},
                owned=owned,
                fixed_ip=fixed_ip,
            )
            self.nodes[identity.node_id] = node
        else:
            node.owned = owned
            node.fixed_ip = fixed_ip
            node.identity = identity
            node.providers = sorted(set(node.providers) | {identity.provider})
            node.provider_display_names[identity.provider] = identity.display_name
        node.record(observation)
        return node

    def members(self, capability: str, now: float | None = None) -> list[NodeState]:
        if capability not in CAPABILITIES:
            raise ValueError(f"unsupported capability: {capability}")
        now = time.time() if now is None else now
        result = []
        for node in self.nodes.values():
            if not node.eligible(now, self.ttl_seconds):
                continue
            statuses = node.capability_history.get(capability, [])
            if sum(status == "pass" for status in statuses[-3:]) < 2:
                continue
            if node.capability_failures.get(capability, 0) >= 2:
                continue
            result.append(node)
        return result

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {key: asdict(node) for key, node in self.nodes.items()}
        fd, tmp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _load(self) -> None:
        content = self.path.read_text(encoding="utf-8").strip()
        if not content:
            return
        data = json.loads(content)
        for raw in data.values():
            identity = NodeIdentity(**raw["identity"])
            providers = raw.get("providers", [identity.provider])
            if not isinstance(providers, list):
                providers = [identity.provider]
            providers = sorted(
                {
                    value
                    for value in providers
                    if isinstance(value, str)
                    and value
                    and "://" not in value
                    and "@" not in value
                }
                | {identity.provider}
            )
            provider_display_names = raw.get(
                "provider_display_names", {identity.provider: identity.display_name}
            )
            if not isinstance(provider_display_names, dict):
                provider_display_names = {identity.provider: identity.display_name}
            provider_display_names = {
                key: value
                for key, value in provider_display_names.items()
                if isinstance(key, str)
                and key in providers
                and isinstance(value, str)
                and value
                and "://" not in value
                and "@" not in value
            }
            provider_display_names.setdefault(identity.provider, identity.display_name)
            node = NodeState(
                identity=identity,
                providers=providers,
                provider_display_names=provider_display_names,
                history=raw.get("history", []),
                capability_history=raw.get("capability_history", {}),
                capability_failures=raw.get("capability_failures", {}),
                consecutive_failures=raw.get("consecutive_failures", 0),
                last_seen=_safe_timestamp(raw.get("last_seen", 0.0)),
                last_observation=_safe_last_observation(raw.get("last_observation", {})),
                owned=raw.get("owned", False),
                fixed_ip=raw.get("fixed_ip", False),
            )
            self.nodes[identity.node_id] = node
