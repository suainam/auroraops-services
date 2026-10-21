"""JSON client profile must publish the same node semantics as the Mihomo YAML.

The JSON entry is a first-class managed artifact (#344): sing-box native clients
consume `<token>.json`, Mihomo clients consume `<token>.yaml`, and the two are
generated from the same node facts. A difference in port, Reality metadata or
node set is a silent misconfiguration for whichever client format is unlucky,
so the assertion here is on the *parsed* artifacts, not on template source.
"""
import json
import re
from pathlib import Path

import yaml
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

TEMPLATES = Path(__file__).resolve().parents[2] / "collections/ansible_collections/vps/services/roles/singbox/templates"

# Names Mihomo appends for its port-hopping duplicate of a Hysteria2 node. It is
# a client-side convenience for the same server node, not an additional node.
HOPPING_SUFFIX = "-hopping"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), undefined=ChainableUndefined)
    env.filters.update(bool=bool, to_json=json.dumps,
                       regex_replace=lambda value, pattern, replacement: re.sub(pattern, replacement, value))
    env.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    # Ansible exposes `is regex` as a test; plain Jinja2 does not, and both
    # profiles use it to decide whether a node name already carries a flag.
    env.tests["regex"] = lambda value, pattern: re.search(pattern, str(value)) is not None
    return env


def _values() -> dict:
    # The fixture mirrors the protocol set the hubs actually publish: TCP VLESS
    # (Reality), gRPC VLESS, Hysteria2, AnyTLS and TUIC, plus an extra relay
    # node. A fixture that omits gRPC/TUIC would let the compact provider drop
    # those nodes without any test noticing.
    direct = dict(name="HK Reality", type="vless", port=443, sni="www.example.com",
                  uuid="00000000-0000-4000-8000-000000000001")
    grpc = dict(name="HK gRPC", type="vless", port=30054, sni="www.example.com",
                transport="grpc", service_name="grpc-vless",
                uuid="00000000-0000-4000-8000-000000000002")
    # An nginx-terminated node listens on node.port with TLS disabled
    # (inbounds_direct.json.j2), so its client-facing destination is 443. The
    # JSON profile already published 443; the Mihomo profiles published
    # node.port, an address no client can complete a handshake against.
    nginx = dict(name="HK Nginx", type="vless", port=8443, sni="www.example.com",
                 uuid="00000000-0000-4000-8000-000000000009", behind_nginx=True)
    udp = dict(name="HK UDP", type="hysteria2", port=8443, password="test", sni="www.example.com")
    anytls = dict(name="HK AnyTLS", type="anytls", port=30057, password="test",
                  sni="www.example.com", insecure=True)
    tuic = dict(name="HK TUIC", type="tuic", port=30058, password="test",
                uuid="00000000-0000-4000-8000-000000000003", sni="www.example.com",
                alpn="h3", insecure=True)
    extras = [dict(direct, name=country, uuid=f"00000000-0000-4000-8000-00000000000{index}",
                   shared_inbound="HK Reality", relay_outbound=f"exit-{country}")
              for index, country in enumerate(("TW", "SG", "JP"), 4)]
    return dict(singbox_nodes=[direct, grpc, nginx, udp, anytls, tuic],
                singbox_extra_nodes=extras,
                docker_apps_singbox_reality_public_key="test-key",
                docker_apps_singbox_inbound_listen="0.0.0.0",
                docker_apps_singbox_certificate_domain="example.com",
                singbox_reality_short_ids=["abcdef12"], singbox_reality_private_key="test-private",
                inventory_hostname="example", singbox_domain="example.com",
                docker_apps_country_flags={"UNKNOWN": "🌍"},
                docker_apps_singbox_host_country="UNKNOWN")


def _render(name: str) -> str:
    return _env().get_template(name).render(**_values())


def _mihomo_nodes() -> list[dict]:
    proxies = yaml.safe_load(_render("singbox_client_profile.yaml.j2"))["proxies"]
    return [proxy for proxy in proxies if not proxy["name"].endswith(HOPPING_SUFFIX)]


def _singbox_nodes() -> list[dict]:
    outbounds = json.loads(_render("singbox_client_profile.json.j2"))["outbounds"]
    return [outbound for outbound in outbounds
            if outbound["type"] in {"vless", "trojan", "hysteria2", "anytls", "tuic"}]


def _mihomo_semantics(node: dict) -> tuple:
    # Mihomo flattens TLS into `tls: true` plus top-level `servername`, and puts
    # Reality material in `reality-opts`. Normalising both formats onto one
    # tuple is what makes the comparison about connection behaviour instead of
    # about each client's key names.
    reality = node.get("reality-opts") or {}
    return (
        node.get("type"),
        node.get("server"),
        node.get("port"),
        node.get("uuid") or node.get("password"),
        node.get("servername") or node.get("sni"),
        reality.get("public-key"),
        reality.get("short-id"),
        node.get("flow"),
    )


def _singbox_semantics(node: dict) -> tuple:
    tls = node.get("tls") or {}
    reality = tls.get("reality") or {}
    return (
        node.get("type"),
        node.get("server"),
        node.get("server_port"),
        node.get("uuid") or node.get("password"),
        tls.get("server_name"),
        reality.get("public_key"),
        reality.get("short_id"),
        node.get("flow"),
    )


def test_json_profile_is_valid_json_with_the_same_nodes_as_mihomo():
    mihomo = sorted((node["name"], _mihomo_semantics(node)) for node in _mihomo_nodes())
    singbox = sorted((node["tag"], _singbox_semantics(node)) for node in _singbox_nodes())
    assert singbox == mihomo


def test_json_selector_members_are_unique_and_resolve():
    outbounds = json.loads(_render("singbox_client_profile.json.j2"))["outbounds"]
    tags = [outbound["tag"] for outbound in outbounds]
    assert len(tags) == len(set(tags)), f"duplicate outbound tags: {tags}"
    selector = next(outbound for outbound in outbounds if outbound["type"] == "selector")
    assert len(selector["outbounds"]) == len(set(selector["outbounds"]))
    assert set(selector["outbounds"]) <= set(tags)
    assert selector["default"] in selector["outbounds"]


def _display_name(name: str) -> str:
    # Both published profiles prefix a flag when the node name does not already
    # start with a non-ASCII one; the compact provider keeps the raw name
    # because Sub-Store applies its own labels.
    return name if name[0] > "\x7f" else f"🌍 {name}"


def test_compact_provider_publishes_the_same_nodes_on_the_same_ports():
    compact = yaml.safe_load(_render("singbox_provider_profile.yaml.j2"))["proxies"]
    json_nodes = _singbox_nodes()
    # Not a subset check: the compact provider publishes the same node set as
    # the other two formats, including gRPC, AnyTLS and TUIC. An equality check
    # is what catches a protocol branch going missing from one template.
    assert [(_display_name(node["name"]), _mihomo_semantics(node)) for node in compact] == [
        (node["tag"], _singbox_semantics(node)) for node in json_nodes
    ]
