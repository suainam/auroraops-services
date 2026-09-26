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


def test_profile_template_generates_bounded_clean_13_groups():
    """Ticket #31: Profile template must yield <= 15 proxy-groups with explicit manual entries."""
    top_template = (
        SERVICES_ROOT
        / "collections/ansible_collections/vps/services/roles/docker_apps/templates/sub_store_capability_profile.yaml.j2"
    ).read_text(encoding="utf-8")

    loader = jinja2.DictLoader(
        {
            "sub_store_capability_profile/proxy_providers.yaml.j2": (
                TEMPLATES_DIR / "proxy_providers.yaml.j2"
            ).read_text(encoding="utf-8"),
            "sub_store_capability_profile/rule_providers.yaml.j2": "rule-providers: {}\n",
            "sub_store_capability_profile/routing_dns.yaml.j2": "rules: []\ndns: {}\n",
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
    assert 10 <= len(groups) <= 15, f"Expected ~13 groups, got {len(groups)}"

    group_map = {g["name"]: g for g in groups}

    ai_service = group_map["🤖 AI 服务"]
    assert "🛡️ 自建优先 (AI 容灾)" in ai_service["proxies"]
    assert "🌸 外部 SK · 全部" in ai_service["proxies"]

    ai_auto = group_map["🛡️ 自建优先 (AI 容灾)"]
    assert ai_auto["type"] == "fallback"
    assert ai_auto["url"] == "https://chatgpt.com/cdn-cgi/trace"
    assert "🌸 外部 SK · 全部" not in ai_auto["proxies"]
    assert "source-sakura" not in ai_auto.get("use", [])

    video_service = group_map["📹 视频与大流量"]
    assert "⚡ BP 千兆优选" in video_service["proxies"]

    bp_fast = group_map["⚡ BP 千兆优选"]
    assert bp_fast["type"] == "url-test"
    assert "1000M" in bp_fast["filter"]

    sk_group = group_map["🌸 外部 SK · 全部"]
    assert sk_group["type"] == "select"
    assert "url" not in sk_group
    assert "interval" not in sk_group


def test_mihomo_syntax_validation():
    """Ticket #32: Rendered profile must pass real /opt/homebrew/bin/mihomo -t -f."""
    import tempfile, subprocess

    top_template = (
        SERVICES_ROOT
        / "collections/ansible_collections/vps/services/roles/docker_apps/templates/sub_store_capability_profile.yaml.j2"
    ).read_text(encoding="utf-8")

    loader = jinja2.DictLoader(
        {
            "sub_store_capability_profile/proxy_providers.yaml.j2": (
                TEMPLATES_DIR / "proxy_providers.yaml.j2"
            ).read_text(encoding="utf-8"),
            "sub_store_capability_profile/rule_providers.yaml.j2": "rule-providers: {}\n",
            "sub_store_capability_profile/routing_dns.yaml.j2": "rules: []\ndns: {}\n",
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
