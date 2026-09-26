"""Contract tests for Data-Driven Keyword Grouping (#29, #46, #47, #48)."""

import json
import re
from pathlib import Path
import jinja2
import pytest
import yaml

SERVICES_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = (
    SERVICES_ROOT
    / "collections/ansible_collections/vps/services/roles/docker_apps/templates/sub_store_capability_profile"
)


def make_jinja_env(loader=None):
    env = jinja2.Environment(loader=loader)
    env.filters["to_json"] = json.dumps
    return env


def test_proxy_providers_disables_health_check_for_metered_sakura():
    """Ticket #46: proxy-providers template must disable health-check for metered SK."""
    template_content = (TEMPLATES_DIR / "proxy_providers.yaml.j2").read_text(encoding="utf-8")
    env = make_jinja_env()
    tpl = env.from_string(template_content)

    providers = [
        {"name": "baipiao", "provider-id": "baipiao", "enabled": True, "display-group": "BP"},
        {"name": "sakura", "provider-id": "sakura", "enabled": True, "display-group": "SK", "metered": True},
    ]

    rendered = tpl.render(
        capability_providers=providers,
        singbox_domain="uk.suai.eu.org",
        sub_store_capability_source_provider_suffix="cap-prov",
    )
    payload = yaml.safe_load(rendered)

    bp = payload["proxy-providers"]["source-baipiao"]
    assert bp["health-check"]["enable"] is True

    sk = payload["proxy-providers"]["source-sakura"]
    assert sk["health-check"]["enable"] is False
    assert "url" not in sk["health-check"]


def test_profile_template_generates_bounded_clean_10_visible_groups():
    """Ticket #46 & #47: Profile template must yield exactly 10 visible groups in strict requested order."""
    top_template = (
        SERVICES_ROOT
        / "collections/ansible_collections/vps/services/roles/docker_apps/templates/sub_store_capability_profile.yaml.j2"
    ).read_text(encoding="utf-8")

    rules_content = (TEMPLATES_DIR / "rules.yaml").read_text(encoding="utf-8")

    loader = jinja2.DictLoader(
        {
            "sub_store_capability_profile/proxy_providers.yaml.j2": (
                TEMPLATES_DIR / "proxy_providers.yaml.j2"
            ).read_text(encoding="utf-8"),
            "sub_store_capability_profile/rule_providers.yaml.j2": (
                TEMPLATES_DIR / "rule_providers.yaml.j2"
            ).read_text(encoding="utf-8"),
            "sub_store_capability_profile/routing_dns.yaml.j2": f"rules:\n{rules_content}\ndns: {{}}\n",
            "sub_store_capability_profile/private_rules.yaml.j2": "",
            "sub_store_capability_profile/rules.yaml": rules_content,
        }
    )
    env = make_jinja_env(loader=loader)
    tpl = env.from_string(top_template)

    # Note: Using native display-group tags without hardcoding
    providers = [
        {"name": "baipiao", "provider-id": "baipiao", "enabled": True, "display-group": "BP"},
        {"name": "cc15", "provider-id": "cc15", "enabled": True, "display-group": "VPS"},
        {"name": "qqg1299", "provider-id": "qqg1299", "enabled": True, "display-group": "VPS"},
        {"name": "nat-hk084", "provider-id": "nat-hk084", "enabled": True, "display-group": "NAT"},
        {"name": "nat-hk216", "provider-id": "nat-hk216", "enabled": True, "display-group": "NAT"},
        {"name": "nat-jp3", "provider-id": "nat-jp3", "enabled": True, "display-group": "NAT"},
        {"name": "sakura", "provider-id": "sakura", "enabled": True, "display-group": "SK", "metered": True},
    ]

    rendered = tpl.render(
        docker_apps_sub_store_capability_providers=providers,
        singbox_domain="uk.suai.eu.org",
        sub_store_capability_source_provider_suffix="cap-prov",
    )
    payload = yaml.safe_load(rendered)

    groups = payload.get("proxy-groups", [])
    visible_groups = [g["name"] for g in groups if not g.get("hidden", False)]

    # 1. Exactly 10 visible groups
    assert len(visible_groups) == 10, f"Expected 10 visible groups, got {len(visible_groups)}: {visible_groups}"

    # 2. Strict priority ordering requested by user
    expected_order = [
        "🚀 默认代理",
        "🤖 AI 服务",
        "🛡️ AI 容灾",
        "📹 视频开发",
        "⚡ 千兆优选",
        "📺 B站港澳",
        "🖥️ VPS",
        "🧭 NAT",
        "🌐 BP",
        "🌸 SK",
    ]
    assert visible_groups == expected_order

    # 3. Assert names do not contain '自建' or '外部'
    for name in visible_groups:
        assert "自建" not in name, f"Group name should not contain '自建': {name}"
        assert "外部" not in name, f"Group name should not contain '外部': {name}"

    group_map = {g["name"]: g for g in groups}

    # 4. Assert 千兆优选 is Fallback
    fast_group = group_map["⚡ 千兆优选"]
    assert fast_group["type"] == "fallback"
    assert "1000M" in fast_group["filter"]

    # 5. Assert B站港澳 defaults to 香港优选 (url-test)
    bili_group = group_map["📺 B站港澳"]
    assert bili_group["proxies"][0] == "香港优选"
    hk_fast = group_map["香港优选"]
    assert hk_fast["type"] == "url-test"
    assert hk_fast["hidden"] is True
    assert "hk" in hk_fast["filter"].lower()

    # 6. Assert BP AI group uses precise regex avoiding baipiao match
    bp_ai = group_map["🌐 BP · AI"]
    assert bp_ai["hidden"] is True
    bp_ai_re = re.compile(bp_ai["filter"])
    assert not bp_ai_re.search("[baipiao] 白嫖机场.com-官网")
    assert not bp_ai_re.search("[baipiao] 剩余流量：858.94 GB")
    assert bp_ai_re.search("[baipiao] 🇺🇸美国光速1-解锁GPT")
    assert bp_ai_re.search("[baipiao] 🇹🇼台湾家宽Gemini")
    assert bp_ai_re.search("[baipiao] 🇹🇼台湾trojan直连AI")

    # 7. Assert SK has zero probes
    sk_group = group_map["🌸 SK"]
    assert sk_group["type"] == "select"
    assert "url" not in sk_group
    assert "interval" not in sk_group


def test_mihomo_syntax_validation():
    """Ticket #47 & #48: Rendered profile must pass real /opt/homebrew/bin/mihomo -t -f."""
    import tempfile, subprocess

    top_template = (
        SERVICES_ROOT
        / "collections/ansible_collections/vps/services/roles/docker_apps/templates/sub_store_capability_profile.yaml.j2"
    ).read_text(encoding="utf-8")

    rules_content = (TEMPLATES_DIR / "rules.yaml").read_text(encoding="utf-8")

    loader = jinja2.DictLoader(
        {
            "sub_store_capability_profile/proxy_providers.yaml.j2": (
                TEMPLATES_DIR / "proxy_providers.yaml.j2"
            ).read_text(encoding="utf-8"),
            "sub_store_capability_profile/rule_providers.yaml.j2": (
                TEMPLATES_DIR / "rule_providers.yaml.j2"
            ).read_text(encoding="utf-8"),
            "sub_store_capability_profile/routing_dns.yaml.j2": f"rules:\n{rules_content}\ndns: {{}}\n",
            "sub_store_capability_profile/private_rules.yaml.j2": "",
            "sub_store_capability_profile/rules.yaml": rules_content,
        }
    )
    env = make_jinja_env(loader=loader)
    tpl = env.from_string(top_template)

    providers = [
        {"name": "baipiao", "provider-id": "baipiao", "enabled": True, "display-group": "BP"},
        {"name": "cc15", "provider-id": "cc15", "enabled": True, "display-group": "VPS"},
        {"name": "qqg1299", "provider-id": "qqg1299", "enabled": True, "display-group": "VPS"},
        {"name": "nat-hk084", "provider-id": "nat-hk084", "enabled": True, "display-group": "NAT"},
        {"name": "nat-hk216", "provider-id": "nat-hk216", "enabled": True, "display-group": "NAT"},
        {"name": "nat-jp3", "provider-id": "nat-jp3", "enabled": True, "display-group": "NAT"},
        {"name": "sakura", "provider-id": "sakura", "enabled": True, "display-group": "SK", "metered": True},
    ]

    rendered = tpl.render(
        docker_apps_sub_store_capability_providers=providers,
        singbox_domain="uk.suai.eu.org",
        sub_store_capability_source_provider_suffix="cap-prov",
    )

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(rendered)
        tmp_name = f.name

    res = subprocess.run(["/opt/homebrew/bin/mihomo", "-t", "-f", tmp_name], capture_output=True, text=True)
    Path(tmp_name).unlink()

    assert res.returncode == 0, f"Mihomo syntax check failed:\n{res.stdout}\n{res.stderr}"
