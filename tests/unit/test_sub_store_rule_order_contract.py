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
    expected_rules = [
        "DOMAIN-SUFFIX,private-example.test,DIRECT",
        "GEOSITE,category-ads-all,REJECT",
        "DOMAIN,ad.com,REJECT",
        "DOMAIN-SUFFIX,doubleclick.net,REJECT",
        "DOMAIN-KEYWORD,tracker,REJECT",
        "DOMAIN-SUFFIX,argotunnel.com,DIRECT",
        "DOMAIN-SUFFIX,cftunnel.com,DIRECT",
        "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
        "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
        "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
        "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
        "IP-CIDR,224.0.0.0/4,DIRECT,no-resolve",
        "IP-CIDR,::1/128,DIRECT,no-resolve",
        "IP-CIDR6,fe80::/10,DIRECT,no-resolve",
        "DOMAIN,localhost,DIRECT",
        "DST-PORT,22,DIRECT",
        "DST-PORT,6868,DIRECT",
        "DOMAIN-SUFFIX,aliyuncs.com,DIRECT",
        "DOMAIN-SUFFIX,163.com,DIRECT",
        "DOMAIN-SUFFIX,netease.com,DIRECT",
        "DOMAIN-SUFFIX,uuremote.com,DIRECT",
        "RULE-SET,ai-services,🤖 AI 服务",
        "DOMAIN-SUFFIX,googleapis.com,🤖 AI 服务",
        "DOMAIN-KEYWORD,cloudaicompanion,🤖 AI 服务",
        "DOMAIN-KEYWORD,cloudcode,🤖 AI 服务",
        "DOMAIN-SUFFIX,chat.openai.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,gemini.ai,🤖 AI 服务",
        "DOMAIN-SUFFIX,gemini.google.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,aistudio.google.com,🤖 AI 服务",
        "DOMAIN-SUFFIX,api.bilibili.com,📺 B站港澳",
        "RULE-SET,bilibili-hmt,📺 B站港澳",
        "DOMAIN-SUFFIX,bilibili.tv,📺 B站港澳",
        "DOMAIN-SUFFIX,bilibili.com,DIRECT",
        "RULE-SET,youtube,📹 视频开发",
        "RULE-SET,disney,📹 视频开发",
        "RULE-SET,netflix,📹 视频开发",
        "RULE-SET,spotify,📹 视频开发",
        "RULE-SET,telegram,🚀 默认代理",
        "RULE-SET,github,🚀 默认代理",
        "RULE-SET,microsoft,DIRECT",
        "RULE-SET,apple,DIRECT",
        "GEOSITE,google,🤖 AI 服务",
        "PROCESS-NAME-REGEX,(?i)^(claude|chatgpt|gpt|gemini|agy|antigravity|opencode|pi|omp|oh-my-pi|cursor|windsurf)(\\.exe)?$,🤖 AI 服务",
        "PROCESS-NAME-REGEX,(?i)^(Claude|ChatGPT|Cursor|Windsurf|Antigravity)\\s+Helper.*$,🤖 AI 服务",
        "PROCESS-PATH,/usr/bin/wget,🚀 默认代理",
        "PROCESS-PATH-WILDCARD,/usr/*/wget,🚀 默认代理",
        "PROCESS-PATH-REGEX,.*bin/wget,🚀 默认代理",
        "PROCESS-PATH,C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe,🚀 默认代理",
        "PROCESS-PATH-REGEX,(?i).*Application\\\\chrome.*,🚀 默认代理",
        "RULE-SET,proxy-domains,🚀 默认代理",
        "AND,((NETWORK,UDP),(DST-PORT,443)),REJECT",
        "RULE-SET,cn-domains,DIRECT",
        "GEOIP,CN,DIRECT",
        "NETWORK,udp,DIRECT",
        "MATCH,🚀 默认代理",
    ]
    assert rules == expected_rules
    assert "+.private-example.test" in profile["dns"]["fake-ip-filter"]


def test_verify_checks_served_profile_rule_precedence_without_logging():
    tasks = yaml.safe_load(
        (
            ROOT
            / "collections/ansible_collections/vps/services/roles/docker_apps/tasks/verify.yml"
        ).read_text(encoding="utf-8")
    )
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
        "DOMAIN-SUFFIX,api.bilibili.com,📺 B站港澳",
        "RULE-SET,bilibili-hmt,📺 B站港澳",
        "DOMAIN-SUFFIX,bilibili.tv,📺 B站港澳",
        "DOMAIN-SUFFIX,bilibili.com,DIRECT",
        "RULE-SET,youtube,📹 视频开发",
        "RULE-SET,disney,📹 视频开发",
        "RULE-SET,netflix,📹 视频开发",
        "RULE-SET,spotify,📹 视频开发",
        "RULE-SET,telegram,🚀 默认代理",
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
        "RULE-SET,youtube,📹 视频开发",
        "RULE-SET,disney,📹 视频开发",
        "RULE-SET,netflix,📹 视频开发",
        "RULE-SET,spotify,📹 视频开发",
        "RULE-SET,telegram,🚀 默认代理",
        "RULE-SET,microsoft,DIRECT",
        "RULE-SET,apple,DIRECT",
    ]
    for rule in before_google:
        assert asserts_before(rule, broad_google)

    for rule in (
        "DOMAIN-SUFFIX,api.bilibili.com,📺 B站港澳",
        "RULE-SET,bilibili-hmt,📺 B站港澳",
        "DOMAIN-SUFFIX,bilibili.tv,📺 B站港澳",
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
        "DOMAIN-SUFFIX,api.bilibili.com,📺 B站港澳",
        "RULE-SET,bilibili-hmt,📺 B站港澳",
        "DOMAIN-SUFFIX,bilibili.tv,📺 B站港澳",
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
