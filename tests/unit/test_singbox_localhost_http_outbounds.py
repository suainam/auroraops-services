from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "collections/ansible_collections/vps/services/roles/singbox/templates/outbounds_direct.json.j2"
)


def _render(**extra_vars: object) -> dict:
    env = Environment()
    env.filters["to_json"] = json.dumps
    env.filters["bool"] = bool
    template = env.from_string(TEMPLATE.read_text(encoding="utf-8"))
    context: dict[str, object] = {
        "inventory_hostname": "qqg1299",
        "app_port_singbox_reality_aws": 443,
        "singbox_uuid_aws": "00000000-0000-0000-0000-000000000000",
        "hostvars": {
            "nat-jp3": {"nat_public_ipv4": "198.51.100.10", "singbox_reality_public_key": "pk-jp3", "singbox_reality_short_ids": ["11"]},
            "cc15": {"ansible_host": "198.51.100.20", "singbox_reality_public_key": "pk-cc15", "singbox_reality_short_ids": ["22"]},
        },
    }
    context.update(extra_vars)
    return json.loads(template.render(**context))


def test_localhost_http_outbounds_absent_when_undefined_or_empty() -> None:
    for extra in ({}, {"singbox_localhost_http_outbounds": []}):
        data = _render(**extra)
        outbounds = data["outbounds"]
        assert [o for o in outbounds if o.get("type") == "http"] == []
        cc15 = next(o for o in outbounds if o.get("tag") == "out-cc15")
        assert cc15["type"] == "vless"
        assert cc15["server"] == "198.51.100.20"


def test_localhost_http_outbounds_rendered_with_loopback_and_numeric_port() -> None:
    data = _render(
        singbox_localhost_http_outbounds=[
            {"tag": "out-cloady-use1", "port": 18103},
        ]
    )
    outbounds = data["outbounds"]
    http_outbounds = [o for o in outbounds if o.get("type") == "http"]
    assert http_outbounds == [
        {
            "type": "http",
            "tag": "out-cloady-use1",
            "server": "127.0.0.1",
            "server_port": 18103,
        }
    ]
    assert isinstance(http_outbounds[0]["server_port"], int)
    cc15 = next(o for o in outbounds if o.get("tag") == "out-cc15")
    assert cc15["type"] == "vless"
    assert cc15["server"] == "198.51.100.20"
