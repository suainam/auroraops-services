"""Rendered Sub-Store rules preserve the first-match routing contract."""

import re
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = (
    ROOT
    / "collections/ansible_collections/vps/services/roles/docker_apps/templates"
)


def test_rendered_rules_keep_private_and_specific_routes_ahead_of_fallbacks():
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)),
        undefined=jinja2.StrictUndefined,
    )
    template = env.get_template("sub_store_capability_profile/routing_dns.yaml.j2")
    rendered = template.render(
        {
            "sub_store_capability_user_rules": [
                "DOMAIN-SUFFIX,private-example.test,DIRECT",
            ],
            "sub_store_capability_user_fake_ip_filter": [
                "+.private-example.test",
            ],
            "sub_store_capability_fake_ip_range": "198.19.0.0/16",
            "singbox_domain": "proxy.example.test",
        }
    )
    profile = yaml.safe_load(rendered)
    rules = profile["rules"]
    raw_shared_rules = yaml.safe_load(
        (TEMPLATES / "sub_store_capability_profile/rules.yaml").read_text(encoding="utf-8")
    )
    expected_rules = [
        "DOMAIN-SUFFIX,private-example.test,DIRECT",
    ] + raw_shared_rules
    assert rules == expected_rules
    assert "+.private-example.test" in profile["dns"]["fake-ip-filter"]


def test_served_mihomo_profile_uses_the_ordered_policy_and_defines_its_targets():
    jinja2 = pytest.importorskip("jinja2")
    import json
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)),
        undefined=jinja2.StrictUndefined,
    )
    env.filters["to_json"] = json.dumps
    template = env.get_template("sub_store_mihomo_profile.yaml.j2")
    synthetic_policy = {
        "singbox_domain": "proxy.example.test",
        "sub_store_mihomo_provider_suffix": "provider-example.yaml",
        "sub_store_capability_user_rules": [
            "DOMAIN-SUFFIX,private-example.test,DIRECT",
        ],
        "sub_store_capability_user_fake_ip_filter": [
            "+.private-example.test",
        ],
        "sub_store_capability_fake_ip_range": "198.19.0.0/16",
    }
    profile = yaml.safe_load(template.render(synthetic_policy))
    shared_policy = yaml.safe_load(
        env.get_template("sub_store_capability_profile/routing_dns.yaml.j2").render(
            synthetic_policy
        )
    )

    rules = profile["rules"]
    assert rules == shared_policy["rules"]
    assert rules[0] == "DOMAIN-SUFFIX,private-example.test,DIRECT"
    assert rules[-1] == "MATCH,🚀 默认代理"
    assert rules.index("GEOSITE,github,🚀 默认代理") < rules.index("GEOSITE,microsoft,DIRECT")
    assert "+.private-example.test" in profile["dns"]["fake-ip-filter"]

    group_names = {group["name"] for group in profile["proxy-groups"]}
    assert {"🚀 默认代理", "⚡ 快速节点", "🤖 AI 服务", "🇭🇰 港澳", "⚡ 国际流媒体", "⚡ 千兆极速"} <= group_names
    # 13 remote rule-providers eliminated (#218): profile defines 0 external rule-providers
    assert "rule-providers" not in profile or len(profile.get("rule-providers", {})) == 0
    rendered_text = template.render(synthetic_policy)
    assert "raw.githubusercontent.com" not in rendered_text
    assert ".mrs" not in rendered_text

    # Verify preserved routing precedence and target mappings
    assert rules.index("GEOSITE,category-ai-!cn,🤖 AI 服务") < rules.index("GEOSITE,google,🤖 AI 服务")
    assert rules.index("GEOSITE,bilibili@!cn,🇭🇰 港澳") < rules.index("DOMAIN-SUFFIX,bilibili.com,DIRECT")
    assert rules.index("GEOSITE,youtube,⚡ 国际流媒体") < rules.index("GEOSITE,geolocation-!cn,🚀 默认代理")
    assert rules.index("GEOSITE,disney,⚡ 国际流媒体") < rules.index("GEOSITE,geolocation-!cn,🚀 默认代理")
    assert rules.index("GEOSITE,netflix,⚡ 国际流媒体") < rules.index("GEOSITE,geolocation-!cn,🚀 默认代理")
    assert rules.index("GEOSITE,spotify,⚡ 国际流媒体") < rules.index("GEOSITE,geolocation-!cn,🚀 默认代理")
    assert rules.index("GEOSITE,telegram,⚡ 千兆极速") < rules.index("GEOSITE,geolocation-!cn,🚀 默认代理")
    assert rules.index("GEOSITE,github,🚀 默认代理") < rules.index("GEOSITE,microsoft,DIRECT")
    assert rules.index("GEOSITE,microsoft,DIRECT") < rules.index("GEOSITE,geolocation-!cn,🚀 默认代理")
    assert rules.index("GEOSITE,apple,DIRECT") < rules.index("GEOSITE,geolocation-!cn,🚀 默认代理")
    assert rules.index("GEOSITE,geolocation-!cn,🚀 默认代理") < rules.index("GEOSITE,cn,DIRECT")
    assert rules.index("GEOSITE,cn,DIRECT") < rules.index("MATCH,🚀 默认代理")

    # Verify DNS nameserver-policy consolidation
    dns = profile["dns"]
    assert "geosite:cn,private" in dns["nameserver-policy"]
    assert dns["nameserver-policy"]["geosite:cn,private"] == [
        "https://dns.alidns.com/dns-query",
        "https://doh.pub/dns-query",
    ]

def test_verify_checks_served_profile_rule_precedence_without_logging():
    tasks = yaml.safe_load(
        (
            ROOT
            / "collections/ansible_collections/vps/services/roles/docker_apps/tasks/verify.yml"
        ).read_text(encoding="utf-8")
    )
    structure_task = next(
        item
        for item in tasks
        if item.get("name") == "Validate public Sub-Store Mihomo profile structure"
    )
    structure_assertions = "\n".join(structure_task["ansible.builtin.assert"]["that"])
    assert structure_task["no_log"] is True
    for required_name in (
        "🚀 默认代理",
        "⚡ 快速节点",
        "🤖 AI 服务",
        "🇭🇰 港澳",
        "⚡ 千兆极速",
    ):
        assert required_name in structure_assertions
    assert "rule-providers" in structure_assertions

    task = next(
        item
        for item in tasks
        if item.get("name") == "Validate public Sub-Store Mihomo rule precedence"
    )

    process_fallback_task = next(
        item
        for item in tasks
        if item.get("name")
        == "Validate public Sub-Store destination rules precede process fallbacks"
    )
    assert "fail_msg" in task["ansible.builtin.assert"]
    assert "fail_msg" in process_fallback_task["ansible.builtin.assert"]

    process_fallback_rules = {
        "GEOSITE,category-ads-all,REJECT",
        "DOMAIN,ad.com,REJECT",
        "DOMAIN-SUFFIX,doubleclick.net,REJECT",
        "DOMAIN-KEYWORD,tracker,REJECT",
        "GEOSITE,category-ai-!cn,🤖 AI 服务",
        "DOMAIN-SUFFIX,googleapis.com,🤖 AI 服务",
        "DOMAIN-KEYWORD,cloudaicompanion,🤖 AI 服务",
        "DOMAIN-KEYWORD,cloudcode,🤖 AI 服务",
        "DOMAIN-SUFFIX,chat.openai.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,gemini.ai,🤖 AI 服务",
        "DOMAIN-SUFFIX,gemini.google.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,aistudio.google.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,api.bilibili.com,🇭🇰 港澳",
        "GEOSITE,bilibili@!cn,🇭🇰 港澳",
        "DOMAIN-SUFFIX,bilibili.tv,🇭🇰 港澳",
        "DOMAIN-SUFFIX,bilibili.com,DIRECT",
        "GEOSITE,youtube,⚡ 国际流媒体",
        "GEOSITE,disney,⚡ 国际流媒体",
        "GEOSITE,netflix,⚡ 国际流媒体",
        "GEOSITE,spotify,⚡ 国际流媒体",
        "GEOSITE,telegram,⚡ 千兆极速",
        "GEOSITE,github,🚀 默认代理",
        "GEOSITE,microsoft,DIRECT",
        "GEOSITE,apple,DIRECT",
        "GEOSITE,google,🤖 AI 服务",
    }
    assert process_fallback_task["no_log"] is True
    assert set(process_fallback_task["loop"]) == process_fallback_rules
    process_assertions = "\n".join(process_fallback_task["ansible.builtin.assert"]["that"])
    assert "item" in process_assertions
    assert "^PROCESS-NAME-REGEX," in process_assertions
    assert "^PROCESS-PATH" in process_assertions

    assert task["no_log"] is True
    assertions = task["ansible.builtin.assert"]["that"]
    normalized_assertions = [re.sub(r"\s+", "", assertion) for assertion in assertions]
    all_assertions = "\n".join(assertions)

    def asserts_before(first: str, second: str) -> bool:
        first = re.sub(r"\s+", "", first)
        second = re.sub(r"\s+", "", second)
        pattern = rf"index\('{re.escape(first)}'\)<.*?index\('{re.escape(second)}'\)"
        return any(re.search(pattern, assertion) for assertion in normalized_assertions)

    assert "sub_store_capability_user_rules" in all_assertions
    broad_google = "GEOSITE,google,🤖 AI 服务"
    broad_bilibili = "DOMAIN-SUFFIX,bilibili.com,DIRECT"
    before_google = [
        "GEOSITE,category-ads-all,REJECT",
        "DOMAIN,ad.com,REJECT",
        "DOMAIN-SUFFIX,doubleclick.net,REJECT",
        "DOMAIN-KEYWORD,tracker,REJECT",
        "GEOSITE,category-ai-!cn,🤖 AI 服务",
        "DOMAIN-SUFFIX,googleapis.com,🤖 AI 服务",
        "DOMAIN-KEYWORD,cloudaicompanion,🤖 AI 服务",
        "DOMAIN-KEYWORD,cloudcode,🤖 AI 服务",
        "DOMAIN-SUFFIX,chat.openai.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,gemini.ai,🤖 AI 服务",
        "DOMAIN-SUFFIX,gemini.google.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,aistudio.google.com,🤖 AI 服务",
        "GEOSITE,youtube,⚡ 国际流媒体",
        "GEOSITE,disney,⚡ 国际流媒体",
        "GEOSITE,netflix,⚡ 国际流媒体",
        "GEOSITE,spotify,⚡ 国际流媒体",
        "GEOSITE,telegram,⚡ 千兆极速",
        "GEOSITE,microsoft,DIRECT",
        "GEOSITE,apple,DIRECT",
    ]
    for rule in before_google:
        assert asserts_before(rule, broad_google)

    for rule in (
        "DOMAIN-SUFFIX,api.bilibili.com,🇭🇰 港澳",
        "GEOSITE,bilibili@!cn,🇭🇰 港澳",
        "DOMAIN-SUFFIX,bilibili.tv,🇭🇰 港澳",
    ):
        assert asserts_before(rule, broad_bilibili)

    for rule in (
        "GEOSITE,github,🚀 默认代理",
        broad_google,
    ):
        normalized_rule = re.sub(r"\s+", "", rule)
        assert any(
            f"index('{normalized_rule}')<" in assertion
            and "select('match','^PROCESS-NAME-REGEX,')" in assertion
            for assertion in normalized_assertions
        )

    for rule in (
        "DOMAIN-SUFFIX,api.bilibili.com,🇭🇰 港澳",
        "GEOSITE,bilibili@!cn,🇭🇰 港澳",
        "DOMAIN-SUFFIX,bilibili.tv,🇭🇰 港澳",
        broad_bilibili,
    ):
        normalized_rule = re.sub(r"\s+", "", rule)
        for process_selector in ("^PROCESS-NAME-REGEX,", "^PROCESS-PATH"):
            assert any(
                f"index('{normalized_rule}')<" in assertion
                and f"select('match','{process_selector}')" in assertion
                for assertion in normalized_assertions
            )

    assert "GEOSITE,geolocation-!cn,🚀 默认代理" in all_assertions
    assert "AND,((NETWORK,UDP),(DST-PORT,443)),REJECT" in all_assertions
    assert "GEOSITE,cn,DIRECT" in all_assertions
    assert "GEOIP,CN,DIRECT" in all_assertions
    assert "NETWORK,udp,DIRECT" in all_assertions


def test_offline_rendered_profile_passes_mihomo_validation(tmp_path):
    """Issue #218: Rendered offline profile contains 0 remote rule-providers and validates under Mihomo."""
    import os
    import shutil
    import subprocess
    jinja2 = pytest.importorskip("jinja2")
    import json

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)),
        undefined=jinja2.StrictUndefined,
    )
    env.filters["to_json"] = json.dumps
    template = env.get_template("sub_store_capability_profile.yaml.j2")
    context = {
        "docker_apps_sub_store_capability_providers": [
            {"name": "cc15", "provider-id": "cc15", "display-group": "VPS", "enabled": True},
            {"name": "qqg1299", "provider-id": "qqg1299", "display-group": "VPS", "enabled": True},
            {"name": "nat-jp3", "provider-id": "nat-jp3", "display-group": "NAT", "enabled": True},
            {"name": "hk96-resi", "provider-id": "hk96-resi", "display-group": "NAT", "enabled": True},
            {"name": "yfjc", "provider-id": "yfjc", "display-group": "AIRPORT", "enabled": True},
            {"name": "baipiao", "provider-id": "baipiao", "display-group": "BP", "enabled": True},
            {"name": "sakura", "provider-id": "sakura", "display-group": "SK", "enabled": True},
        ],
        "singbox_domain": "stout7183.suai.eu.org",
        "sub_store_capability_fake_ip_range": "198.19.0.0/16",
        "sub_store_capability_source_provider_suffix": "cap-prov",
        "sub_store_capability_private_rules": [],
        "sub_store_capability_private_fake_ip_filter": ["+.corp.example.com"],
        "sub_store_capability_private_tun_route_exclude_address": [],
    }
    rendered = template.render(context)
    assert "raw.githubusercontent.com" not in rendered
    assert "rule-providers" not in rendered

    mihomo_bin = shutil.which("mihomo") or "/Applications/Clash Verge.app/Contents/MacOS/verge-mihomo"
    if not os.path.exists(mihomo_bin):
        pytest.skip(f"mihomo binary not found at {mihomo_bin}")

    geodata_dir = os.path.expanduser(
        "~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev"
    )
    if not os.path.exists(geodata_dir):
        pytest.skip(f"Client geodata directory not found at {geodata_dir}")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(rendered, encoding="utf-8")

    res = subprocess.run(
        [mihomo_bin, "-t", "-d", geodata_dir, "-f", str(config_file)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Mihomo validation failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
