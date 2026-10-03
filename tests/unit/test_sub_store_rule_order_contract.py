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
    assert rules.index("RULE-SET,github,🚀 默认代理") < rules.index("RULE-SET,microsoft,DIRECT")
    assert "+.private-example.test" in profile["dns"]["fake-ip-filter"]

    group_names = {group["name"] for group in profile["proxy-groups"]}
    assert {"🚀 默认代理", "⚡ 快速节点", "🤖 AI 服务", "🇭🇰 港澳", "⚡ 国际流媒体", "⚡ 千兆极速"} <= group_names
    assert {
        "ai-services",
        "bilibili-hmt",
        "disney",
        "netflix",
        "spotify",
        "youtube",
        "telegram",
        "github",
        "microsoft",
        "apple",
        "proxy-domains",
        "cn-domains",
    } <= set(profile["rule-providers"])


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
        "bilibili-hmt",
        "github",
        "proxy-domains",
    ):
        assert required_name in structure_assertions

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
        "RULE-SET,ai-services,🤖 AI 服务",
        "DOMAIN-SUFFIX,googleapis.com,🤖 AI 服务",
        "DOMAIN-KEYWORD,cloudaicompanion,🤖 AI 服务",
        "DOMAIN-KEYWORD,cloudcode,🤖 AI 服务",
        "DOMAIN-SUFFIX,chat.openai.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,gemini.ai,🤖 AI 服务",
        "DOMAIN-SUFFIX,gemini.google.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,aistudio.google.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,api.bilibili.com,🇭🇰 港澳",
        "RULE-SET,bilibili-hmt,🇭🇰 港澳",
        "DOMAIN-SUFFIX,bilibili.tv,🇭🇰 港澳",
        "DOMAIN-SUFFIX,bilibili.com,DIRECT",
        "RULE-SET,youtube,⚡ 国际流媒体",
        "RULE-SET,disney,⚡ 国际流媒体",
        "RULE-SET,netflix,⚡ 国际流媒体",
        "RULE-SET,spotify,⚡ 国际流媒体",
        "RULE-SET,telegram,⚡ 千兆极速",
        "RULE-SET,github,🚀 默认代理",
        "RULE-SET,microsoft,DIRECT",
        "RULE-SET,apple,DIRECT",
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
        "RULE-SET,ai-services,🤖 AI 服务",
        "DOMAIN-SUFFIX,googleapis.com,🤖 AI 服务",
        "DOMAIN-KEYWORD,cloudaicompanion,🤖 AI 服务",
        "DOMAIN-KEYWORD,cloudcode,🤖 AI 服务",
        "DOMAIN-SUFFIX,chat.openai.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,gemini.ai,🤖 AI 服务",
        "DOMAIN-SUFFIX,gemini.google.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,aistudio.google.com,🤖 AI 服务",
        "RULE-SET,youtube,⚡ 国际流媒体",
        "RULE-SET,disney,⚡ 国际流媒体",
        "RULE-SET,netflix,⚡ 国际流媒体",
        "RULE-SET,spotify,⚡ 国际流媒体",
        "RULE-SET,telegram,⚡ 千兆极速",
        "RULE-SET,microsoft,DIRECT",
        "RULE-SET,apple,DIRECT",
    ]
    for rule in before_google:
        assert asserts_before(rule, broad_google)

    for rule in (
        "DOMAIN-SUFFIX,api.bilibili.com,🇭🇰 港澳",
        "RULE-SET,bilibili-hmt,🇭🇰 港澳",
        "DOMAIN-SUFFIX,bilibili.tv,🇭🇰 港澳",
    ):
        assert asserts_before(rule, broad_bilibili)

    for rule in (
        "RULE-SET,github,🚀 默认代理",
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
        "RULE-SET,bilibili-hmt,🇭🇰 港澳",
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

    assert "RULE-SET,proxy-domains,🚀 默认代理" in all_assertions
    assert "AND,((NETWORK,UDP),(DST-PORT,443)),REJECT" in all_assertions
    assert "RULE-SET,cn-domains,DIRECT" in all_assertions
    assert "GEOIP,CN,DIRECT" in all_assertions
    assert "NETWORK,udp,DIRECT" in all_assertions
