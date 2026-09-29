"""Contract test verifying Sub-Store capability pool sync empty pool safety (#20, #21, #22)."""

import sys
from pathlib import Path
import pytest
import yaml

PROFILER_DIR = (
    Path(__file__).resolve().parents[2]
    / "collections/ansible_collections/vps/services/roles/docker_apps/files/sub_store_profiler"
)
if str(PROFILER_DIR) not in sys.path:
    sys.path.insert(0, str(PROFILER_DIR))

from pool_sync import render_profile  # noqa: E402


SAMPLE_TEMPLATE = """
proxy-providers:
  source-main:
    type: http
    url: https://example.com/subs
proxy-groups:
  - name: "⚡ 自动优选"
    type: fallback
    proxies:
      - "🇭🇰 港澳 · 自动优选"
      - "🇹🇼 台湾 · 自动优选"
      - "🇯🇵 日本 · 自动优选"
      - "🇸🇬 新加坡 · 自动优选"
      - "🇺🇸 美国 · 自动优选"
      - "🇪🇺 欧洲 · 自动优选"
      - "🌐 其他 · 自动优选"
      - "快速 · 自动优选"
      - "🛡️ 稳定优先"
  - name: "🇭🇰 港澳 · 自动优选"
    type: url-test
    use: [source-main]
    filter: __FILTER_REGION_HK_MO__
  - name: "🇹🇼 台湾 · 自动优选"
    type: url-test
    use: [source-main]
    filter: __FILTER_REGION_TW__
  - name: "🇯🇵 日本 · 自动优选"
    type: url-test
    use: [source-main]
    filter: __FILTER_REGION_JP__
  - name: "🇸🇬 新加坡 · 自动优选"
    type: url-test
    use: [source-main]
    filter: __FILTER_REGION_SG__
  - name: "🇺🇸 美国 · 自动优选"
    type: url-test
    use: [source-main]
    filter: __FILTER_REGION_US__
  - name: "🇪🇺 欧洲 · 自动优选"
    type: url-test
    use: [source-main]
    filter: __FILTER_REGION_EUROPE__
  - name: "🌐 其他 · 自动优选"
    type: url-test
    use: [source-main]
    filter: __FILTER_REGION_OTHER__
  - name: "🛡️ 稳定优先"
    type: select
    proxies: [DIRECT]
  - name: "AI · BP 稳定"
    type: url-test
    filter: __FILTER_AI__
  - name: "纯净 · BP 稳定"
    type: url-test
    filter: __FILTER_PURE_LOW_RISK__
  - name: "快速 · 自动优选"
    type: url-test
    filter: __FILTER_BASELINE__
"""


def test_empty_regional_groups_are_pruned_from_auto_selection():
    """Ticket #20: Empty regional groups must be pruned from '⚡ 自动优选' and proxy-groups."""
    names = {
        "region-hk-mo": ["HK-Node-1"],
        "region-tw": ["TW-Node-1"],
        "region-jp": [],  # Empty JP region
        "region-sg": [],
        "region-us": [],
        "region-europe": [],
        "region-other": [],
        "baseline": ["HK-Node-1", "TW-Node-1"],
        "ai": ["HK-Node-1"],
        "pure-low-risk": ["HK-Node-1"],
    }
    rendered, lkg = render_profile(SAMPLE_TEMPLATE, names)
    payload = yaml.safe_load(rendered)

    group_map = {g["name"]: g for g in payload["proxy-groups"]}

    auto_group = group_map["⚡ 自动优选"]
    assert "🇯🇵 日本 · 自动优选" not in auto_group["proxies"]
    assert "🇭🇰 港澳 · 自动优选" in auto_group["proxies"]
    assert "🇹🇼 台湾 · 自动优选" in auto_group["proxies"]
    assert "🛡️ 稳定优先" in auto_group["proxies"]

    # Pruned from top-level proxy-groups as well
    assert "🇯🇵 日本 · 自动优选" not in group_map
    assert "🇭🇰 港澳 · 自动优选" in group_map


def test_empty_capability_pool_does_not_resurrect_with_baseline():
    """Ticket #22: Empty capability pool must not fall back to baseline members."""
    names = {
        "region-hk-mo": ["HK-Node-1"],
        "region-tw": [],
        "region-jp": [],
        "region-sg": [],
        "region-us": [],
        "region-europe": [],
        "region-other": [],
        "baseline": ["Non-AI-Baseline-Node"],
        "ai": [],  # Empty AI pool
        "pure-low-risk": [],
    }
    rendered, lkg = render_profile(SAMPLE_TEMPLATE, names)
    payload = yaml.safe_load(rendered)

    group_map = {g["name"]: g for g in payload["proxy-groups"]}
    ai_group = group_map["AI · BP 稳定"]
    # Should fail-closed to ^$, never use Non-AI-Baseline-Node
    assert ai_group["filter"] == "^$"
    assert "Non-AI-Baseline-Node" not in ai_group["filter"]


def test_all_regions_empty_safely_falls_back_to_stable_prioritized():
    """Ticket #21: When all regions are empty, auto-selection retains stable prioritized fallback."""
    names = {
        "region-hk-mo": [],
        "region-tw": [],
        "region-jp": [],
        "region-sg": [],
        "region-us": [],
        "region-europe": [],
        "region-other": [],
        "baseline": ["Some-Node"],
        "ai": ["Some-Node"],
        "pure-low-risk": ["Some-Node"],
    }
    rendered, lkg = render_profile(SAMPLE_TEMPLATE, names)
    payload = yaml.safe_load(rendered)

    group_map = {g["name"]: g for g in payload["proxy-groups"]}
    auto_group = group_map["⚡ 自动优选"]
    assert auto_group["proxies"] == ["快速 · 自动优选", "🛡️ 稳定优先"] or "🛡️ 稳定优先" in auto_group["proxies"]
