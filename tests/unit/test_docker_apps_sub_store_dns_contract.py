import json
import re
from pathlib import Path

import jinja2
import yaml


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = (
    ROOT
    / "collections/ansible_collections/vps/services/roles/docker_apps/templates"
)


def _regex_replace(value: str, pattern: str, replacement: str) -> str:
    return re.sub(pattern, replacement, value)


def test_capability_profile_renders_cc15_dns_contract():
    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATE_ROOT)),
        undefined=jinja2.StrictUndefined,
    )
    environment.filters["regex_replace"] = _regex_replace
    environment.filters["to_json"] = json.dumps
    template = environment.get_template("sub_store_capability_profile.yaml.j2")
    rendered = template.render(
        docker_apps_sub_store_capability_providers=[],
        sub_store_capability_provider_display_groups={},
        sub_store_capability_fake_ip_range="198.19.0.0/16",
        singbox_domain="proxy.example.com",
        sub_store_capability_private_rules=[],
        sub_store_capability_private_fake_ip_filter=["+.corp.example.com"],
        sub_store_capability_private_tun_route_exclude_address=[],
    )
    profile = yaml.safe_load(rendered)
    dns = profile["dns"]

    assert dns["respect-rules"] is True
    assert dns["nameserver"] == [
        "223.5.5.5",
        "119.29.29.29",
        "https://dns.alidns.com/dns-query",
        "https://doh.pub/dns-query",
    ]
    assert dns["proxy-server-nameserver"] == ["223.5.5.5", "119.29.29.29"]
    assert "fallback" not in dns
    assert "fallback-filter" not in dns
    assert "geosite:cn" not in dns["fake-ip-filter"]
    assert "+.corp.example.com" in dns["fake-ip-filter"]
    assert "geosite:cn" in dns["nameserver-policy"]
