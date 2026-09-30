"""Rendered server/client contract: one listener, independent authenticated exits."""
import json
import re
from pathlib import Path

import yaml
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

TEMPLATES = Path(__file__).resolve().parents[2] / "collections/ansible_collections/vps/services/roles/singbox/templates"


def test_shared_reality_keeps_direct_user_and_binds_each_extra_user_to_its_exit():
    env = Environment(loader=FileSystemLoader(TEMPLATES), undefined=ChainableUndefined)
    env.filters.update(bool=bool, to_json=json.dumps,
                       regex_replace=lambda value, pattern, replacement: re.sub(pattern, replacement, value))
    env.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    direct = dict(name="HK Reality", type="vless", port=443, sni="www.example.com", uuid="00000000-0000-4000-8000-000000000001")
    udp = dict(name="HK UDP", type="hysteria2", port=8443, password="test", sni="www.example.com")
    extras = [dict(direct, name=country, uuid=f"00000000-0000-4000-8000-00000000000{index}",
                   shared_inbound="HK Reality", relay_outbound=f"exit-{country}")
              for index, country in enumerate(("TW", "SG", "JP"), 2)]
    values = dict(singbox_nodes=[direct, udp], singbox_extra_nodes=extras,
                  singbox_socks_outbounds=[dict(tag=f"exit-{country}", server="proxy.example.com", server_port=1080,
                                              username='test"user', password='test\\password') for country in ("TW", "SG", "JP")],
                  docker_apps_singbox_reality_public_key="test-key", docker_apps_singbox_inbound_listen="0.0.0.0",
                  docker_apps_singbox_certificate_domain="example.com", singbox_reality_short_ids=["abcdef12"],
                  singbox_reality_private_key="test-private", inventory_hostname="example",
                  auroraops_roles={"services": {"ip2free_gateway": False}}, singbox_domain="example.com")
    render = lambda name: env.get_template(name).render(**values)
    inbounds = json.loads(render("inbounds_direct.json.j2"))["inbounds"]
    assert [(node["type"], node["listen_port"]) for node in inbounds] == [("vless", 443), ("hysteria2", 8443)]
    users = inbounds[0]["users"]
    assert users[0] == {"uuid": direct["uuid"], "flow": "xtls-rprx-vision"}
    assert {user["name"]: user["uuid"] for user in users[1:]} == {node["name"]: node["uuid"] for node in extras}
    rules = json.loads(render("route_direct.json.j2"))["route"]["rules"]
    assert [(rule["auth_user"], rule["outbound"]) for rule in rules if "auth_user" in rule] == [(["TW"], "exit-TW"), (["SG"], "exit-SG"), (["JP"], "exit-JP")]
    assert all("inbound" not in rule for rule in rules if "auth_user" in rule)
    assert next(index for index, rule in enumerate(rules) if "ip_cidr" in rule) < next(index for index, rule in enumerate(rules) if "auth_user" in rule)
    outbounds = json.loads(render("outbounds_direct.json.j2"))["outbounds"]
    assert {node["tag"] for node in outbounds if node["type"] == "socks"} == {"exit-TW", "exit-SG", "exit-JP"}
    assert all(node["password"] == 'test\\password' for node in outbounds if node["type"] == "socks")
    profile = yaml.safe_load(render("singbox_provider_profile.yaml.j2"))["proxies"]
    assert [(node["name"], node["type"], node["port"]) for node in profile] == [("HK Reality", "vless", 443), ("HK UDP", "hysteria2", 8443), ("TW", "vless", 443), ("SG", "vless", 443), ("JP", "vless", 443)]
    assert not any("username" in node or "proxy-password" in node for node in profile)
