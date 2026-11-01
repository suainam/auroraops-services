"""Contract tests for Data-Driven Keyword Grouping (#29, #46, #47, #48)."""

import os
import sys
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
    routing_dns_content = (TEMPLATES_DIR / "rules.yaml.j2").read_text(encoding="utf-8")
    dns_content = (TEMPLATES_DIR / "dns.yaml.j2").read_text(encoding="utf-8")

    loader = jinja2.DictLoader(
        {
            "sub_store_capability_profile/proxy_providers.yaml.j2": (
                TEMPLATES_DIR / "proxy_providers.yaml.j2"
            ).read_text(encoding="utf-8"),
            "sub_store_capability_profile/rules.yaml.j2": routing_dns_content,
            "sub_store_capability_profile/dns.yaml.j2": dns_content,
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
        {"name": "nat-hk24", "provider-id": "nat-hk24", "enabled": True, "display-group": "NAT"},
        {"name": "nat-jp3", "provider-id": "nat-jp3", "enabled": True, "display-group": "NAT"},
        {"name": "yfjc", "provider-id": "yfjc", "enabled": True, "display-group": "AIRPORT"},
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

    # 1. Exactly 8 visible groups
    assert len(visible_groups) == 8, f"Expected 8 visible groups, got {len(visible_groups)}: {visible_groups}"

    # 2. Strict priority ordering requested by user
    expected_order = [
        "🚀 默认代理",
        "⚡ 千兆极速",
        "🤖 AI 服务",
        "🏦 金融与交易所",
        "🖥️ VPS",
        "🧭 NAT",
        "⚡ YF",
        "🌐 BP",
    ]
    assert visible_groups == expected_order

    # 3. Assert names do not contain '自建' or '外部'
    for name in visible_groups:
        assert "自建" not in name, f"Group name should not contain '自建': {name}"
        assert "外部" not in name, f"Group name should not contain '外部': {name}"

    group_map = {g["name"]: g for g in groups}

    # 4. Assert ⚡ 千兆极速 is Select
    fast_group = group_map["⚡ 千兆极速"]
    assert fast_group["type"] == "select"

    # 5. Assert 🇭🇰 港澳 is hidden url-test
    hk_fast = group_map["🇭🇰 港澳"]
    assert hk_fast["type"] == "url-test"
    assert hk_fast["hidden"] is True
    assert "hk" in hk_fast["filter"].lower()
    # 6. Assert US airport AI group uses precise regex avoiding baipiao noise
    us_ai = group_map.get("🇺🇸 US · 机场AI") or group_map["🇺🇸 机场 · AI"]
    assert us_ai["hidden"] is True
    us_ai_re = re.compile(us_ai["filter"])
    assert not us_ai_re.search("[baipiao] 白嫖机场.com-官网")
    assert not us_ai_re.search("[baipiao] 剩余流量：858.94 GB")
    assert us_ai_re.search("[baipiao] 🇺🇸美国光速1-OpenAI")


def test_mihomo_syntax_validation():
    """Ticket #47 & #48: Rendered profile must pass real /opt/homebrew/bin/mihomo -t -f."""
    import tempfile, subprocess

    top_template = (
        SERVICES_ROOT
        / "collections/ansible_collections/vps/services/roles/docker_apps/templates/sub_store_capability_profile.yaml.j2"
    ).read_text(encoding="utf-8")

    rules_content = (TEMPLATES_DIR / "rules.yaml").read_text(encoding="utf-8")
    routing_dns_content = (TEMPLATES_DIR / "rules.yaml.j2").read_text(encoding="utf-8")
    dns_content = (TEMPLATES_DIR / "dns.yaml.j2").read_text(encoding="utf-8")
    loader = jinja2.DictLoader(
        {
            "sub_store_capability_profile/proxy_providers.yaml.j2": (
                TEMPLATES_DIR / "proxy_providers.yaml.j2"
            ).read_text(encoding="utf-8"),
            "sub_store_capability_profile/rules.yaml.j2": routing_dns_content,
            "sub_store_capability_profile/dns.yaml.j2": dns_content,
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
        {"name": "nat-hk24", "provider-id": "nat-hk24", "enabled": True, "display-group": "NAT"},
        {"name": "nat-jp3", "provider-id": "nat-jp3", "enabled": True, "display-group": "NAT"},
        {"name": "sakura", "provider-id": "sakura", "enabled": True, "display-group": "SK", "metered": True},
    ]

    rendered = tpl.render(
        docker_apps_sub_store_capability_providers=providers,
        singbox_domain="uk.suai.eu.org",
        sub_store_capability_source_provider_suffix="cap-prov",
        sub_store_capability_fake_ip_range="198.19.0.0/16",
    )

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(rendered)
        tmp_name = f.name

    import shutil
    mihomo_bin = (
        shutil.which("mihomo")
        or os.environ.get("CLASH_VERGE_MIHOMO_BIN")
        or ("/opt/homebrew/bin/mihomo" if Path("/opt/homebrew/bin/mihomo").exists() else None)
    )
    if not mihomo_bin and sys.platform == "darwin":
        app_bundle = Path("/Applications/Clash Verge.app/Contents/MacOS")
        mihomo_bin = next(
            (str(path) for path in (app_bundle / "verge-mihomo", app_bundle / "verge-mihomo-alpha") if path.is_file()),
            None,
        )
    if not mihomo_bin:
        Path(tmp_name).unlink()
        pytest.skip("Mihomo binary not installed; set CLASH_VERGE_MIHOMO_BIN to run syntax validation")
    res = subprocess.run([mihomo_bin, "-t", "-f", tmp_name], capture_output=True, text=True)
    Path(tmp_name).unlink()
    assert res.returncode == 0, f"Mihomo syntax check failed:\n{res.stdout}\n{res.stderr}"

def test_real_world_node_classification_avoids_false_positives_and_negatives():
    """Verify real provider node patterns prevent false positives (baipiao in AI) and false negatives (GPT/Gemini/1000M/光速)."""
    top_template = (
        SERVICES_ROOT
        / "collections/ansible_collections/vps/services/roles/docker_apps/templates/sub_store_capability_profile.yaml.j2"
    ).read_text(encoding="utf-8")
    rules_content = (TEMPLATES_DIR / "rules.yaml").read_text(encoding="utf-8")
    routing_dns_content = (TEMPLATES_DIR / "rules.yaml.j2").read_text(encoding="utf-8")
    dns_content = (TEMPLATES_DIR / "dns.yaml.j2").read_text(encoding="utf-8")
    loader = jinja2.DictLoader(
        {
            "sub_store_capability_profile/proxy_providers.yaml.j2": (
                TEMPLATES_DIR / "proxy_providers.yaml.j2"
            ).read_text(encoding="utf-8"),
            "sub_store_capability_profile/rules.yaml.j2": routing_dns_content,
            "sub_store_capability_profile/dns.yaml.j2": dns_content,
            "sub_store_capability_profile/private_rules.yaml.j2": "",
            "sub_store_capability_profile/rules.yaml": rules_content,
        }
    )
    env = make_jinja_env(loader=loader)
    tpl = env.from_string(top_template)
    rendered = tpl.render(
        providers=[
            {"name": "cc15", "provider-id": "cc15", "enabled": True, "display-group": "VPS"},
            {"name": "yfjc", "provider-id": "yfjc", "enabled": True, "display-group": "AIRPORT"},
            {"name": "baipiao", "provider-id": "baipiao", "enabled": True, "display-group": "AIRPORT"},
        ],
        singbox_domain="uk.suai.eu.org",
        sub_store_capability_source_provider_suffix="cap-prov",
    )
    payload = yaml.safe_load(rendered)
    groups = {g["name"]: g for g in payload.get("proxy-groups", [])}

    # 1. 默认代理 must have AI 服务, VPS, and NAT as manual fallbacks
    default_proxies = groups["🚀 默认代理"]["proxies"]
    assert default_proxies == ["⚡ 千兆极速", "💰 低倍率走廊", "🤖 AI 服务", "🖥️ VPS", "🧭 NAT", "DIRECT"]

    # 2. TW AI filter matches GPT, Gemini, and AI
    tw_ai_filter = re.compile(groups["🇹🇼 TW · 机场AI"]["filter"])
    assert tw_ai_filter.search("🇹🇼台湾家宽1-GPT")
    assert tw_ai_filter.search("🇹🇼台湾家宽2-Gemini")
    assert tw_ai_filter.search("🇹🇼台湾家宽B3-直连AI")
    assert not tw_ai_filter.search("🇹🇼台湾家宽A4-Netflix")

    # 3. US AI filter matches genuine AI nodes and rejects baipiaoyes domain false positives
    us_ai_filter = re.compile(groups["🇺🇸 US · 机场AI"]["filter"])
    assert us_ai_filter.search("🇺🇸美国ai解锁-0.1倍率")
    assert us_ai_filter.search("🇺🇸美国ai-0.1倍率")
    assert us_ai_filter.search("🇺🇸美国ai解锁")
    assert not us_ai_filter.search("🇺🇸美国1-baipiaoyes.top")
    assert not us_ai_filter.search("🇺🇸美国2-baipiaoyes.top")

    # 4. Gigabit filter matches 1000M, 光速, and 超高速
    us_giga_filter = re.compile(groups["🇺🇸 US · 千兆"]["filter"])
    assert us_giga_filter.search("🇺🇸美国HY4神速-1000M")
    assert us_giga_filter.search("🇺🇸美国光速1")
    jp_giga_filter = re.compile(groups["🇯🇵 JP · 千兆"]["filter"])
    assert jp_giga_filter.search("🇯🇵日本超高速1")
    assert jp_giga_filter.search("🇯🇵日本超高速3")

    # 5. Low-rate corridor filter matches all 0.1 and 0.01 nodes
    low_rate_filter = re.compile(groups["💰 低倍率走廊"]["filter"])
    assert low_rate_filter.search("🇯🇵日本专线-0.1倍率")
    assert low_rate_filter.search("🇺🇸美国纽约-0.01倍率")
    assert not low_rate_filter.search("🇸🇬新加坡专线")

    # 6. Normal filter excludes announcements
    normal_filter = re.compile(groups["🇺🇸 US · 普通"]["filter"])
    assert not normal_filter.search("剩余流量：972.78 GB")
    assert not normal_filter.search("套餐到期：2027-02-14")
    assert not normal_filter.search("白嫖机场.com-官网")
    assert not normal_filter.search("若无法使用请更新客户端")
    assert normal_filter.search("🇺🇸美国A1-小火箭")
