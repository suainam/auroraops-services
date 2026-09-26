"""Contract tests for Pure Keyword-based Lightweight Grouping (#29, #30, #31, #32)."""

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
    """Ticket #30: proxy-providers template must disable health-check for metered SK."""
    template_content = (TEMPLATES_DIR / "proxy_providers.yaml.j2").read_text(encoding="utf-8")
    env = make_jinja_env()
    tpl = env.from_string(template_content)

    providers = [
        {"name": "baipiao", "enabled": True, "role": "public"},
        {"name": "sakura", "enabled": True, "role": "metered", "metered": True},
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


def test_profile_template_generates_bounded_clean_visible_groups():
    """Ticket #31: Profile template must yield exactly 9 visible groups in correct priority order."""
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
        {"name": "baipiao", "enabled": True, "role": "public"},
        {"name": "cc15", "enabled": True, "role": "private"},
        {"name": "qqg1299", "enabled": True, "role": "private"},
        {"name": "nat-hk084", "enabled": True, "role": "private"},
        {"name": "nat-hk216", "enabled": True, "role": "private"},
        {"name": "nat-jp3", "enabled": True, "role": "private"},
        {"name": "sakura", "enabled": True, "role": "metered", "metered": True},
    ]

    rendered = tpl.render(
        docker_apps_sub_store_capability_providers=providers,
        singbox_domain="uk.suai.eu.org",
        sub_store_capability_source_provider_suffix="cap-prov",
    )
    payload = yaml.safe_load(rendered)

    groups = payload.get("proxy-groups", [])
    visible_groups = [g["name"] for g in groups if not g.get("hidden", False)]

    # 1. Exactly 9 visible groups
    assert len(visible_groups) == 9, f"Expected 9 visible groups, got {len(visible_groups)}: {visible_groups}"

    # 2. Priority ordering: 5 services first, 4 entity pools last
    expected_order = [
        "🤖 AI 服务",
        "🐙 GitHub",
        "📹 YouTube",
        "📺 B站港澳台",
        "🚀 默认代理",
        "🖥️ 自建 VPS",
        "🧭 自建 NAT",
        "🌐 外部 BP · 全部",
        "🌸 外部 SK · 全部",
    ]
    assert visible_groups == expected_order

    group_map = {g["name"]: g for g in groups}

    # 3. Assert Bilibili group only contains meaningful HMT items
    bili_group = group_map["📺 B站港澳台"]
    assert bili_group["proxies"] == [
        "🧭 自建 NAT · 港澳",
        "🌐 外部 BP · 港澳台",
        "🌸 外部 SK · 港澳台",
        "DIRECT",
    ]

    # 4. Assert BP AI group uses precise regex avoiding baipiao match
    bp_ai = group_map["🌐 外部 BP · AI"]
    assert bp_ai["hidden"] is True
    bp_ai_re = re.compile(bp_ai["filter"])
    assert not bp_ai_re.search("[baipiao] 白嫖机场.com-官网")
    assert not bp_ai_re.search("[baipiao] 剩余流量：858.94 GB")
    assert bp_ai_re.search("[baipiao] 🇺🇸美国光速1-解锁GPT")
    assert bp_ai_re.search("[baipiao] 🇹🇼台湾家宽Gemini")
    assert bp_ai_re.search("[baipiao] 🇹🇼台湾trojan直连AI")

    # 5. Assert SK has zero probes
    sk_group = group_map["🌸 外部 SK · 全部"]
    assert sk_group["type"] == "select"
    assert "url" not in sk_group
    assert "interval" not in sk_group

    sk_hmt = group_map["🌸 外部 SK · 港澳台"]
    assert sk_hmt["type"] == "select"
    assert "url" not in sk_hmt


def test_mihomo_syntax_validation():
    """Ticket #32: Rendered profile must pass real /opt/homebrew/bin/mihomo -t -f."""
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
        {"name": "baipiao", "enabled": True, "role": "public"},
        {"name": "cc15", "enabled": True, "role": "private"},
        {"name": "qqg1299", "enabled": True, "role": "private"},
        {"name": "nat-hk084", "enabled": True, "role": "private"},
        {"name": "nat-hk216", "enabled": True, "role": "private"},
        {"name": "nat-jp3", "enabled": True, "role": "private"},
        {"name": "sakura", "enabled": True, "role": "metered", "metered": True},
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
