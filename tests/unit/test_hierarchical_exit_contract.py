"""Contract tests for Data-Driven Hierarchical Proxy Groups & AI Exit Control (#23, #24, #25, #26)."""

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


SAMPLE_HIERARCHICAL_TEMPLATE = """
proxy-providers:
  source-cc15:
    type: http
    url: https://example.com/cc15.yaml
    health-check:
      enable: true
      url: https://www.gstatic.com/generate_204
  source-sakura:
    type: http
    url: https://example.com/sakura.yaml
    health-check:
      enable: false
proxy-groups:
  - name: "🤖 AI 服务"
    type: select
    proxies:
      - "🛡️ 自建优先 (AI 容灾)"
      - "🖥️ 自建 VPS · AI"
      - "🧭 自建 NAT · AI"
      - "🌐 外部 BP · AI"
      - "🌸 外部 SK · 全部"
      - DIRECT
  - name: "🛡️ 自建优先 (AI 容灾)"
    type: fallback
    proxies:
      - "🖥️ 自建 VPS · AI"
      - "🧭 自建 NAT · AI"
      - "🌐 外部 BP · AI"
    url: https://chatgpt.com/cdn-cgi/trace
    interval: 300
    lazy: true
  - name: "⚡ BP 千兆优选"
    type: url-test
    use: [source-cc15]
    filter: "(?i)1000M|神速|快"
    url: https://www.gstatic.com/generate_204
  - name: "🖥️ 自建 VPS · AI"
    type: fallback
    use: [source-cc15]
    filter: __FILTER_AI__
  - name: "🧭 自建 NAT · AI"
    type: fallback
    use: [source-cc15]
    filter: __FILTER_AI__
  - name: "🌐 外部 BP · AI"
    type: fallback
    use: [source-cc15]
    filter: "(?i)AI|Gemini|ChatGPT|GPT"
  - name: "🌸 外部 SK · 全部"
    type: select
    proxies: [DIRECT]
"""


def test_metered_source_has_no_probe_and_is_excluded_from_auto_groups():
    """Ticket #24: Metered provider (SK) has health-check disabled and appears in 0 auto groups."""
    names = {
        "baseline": ["cc15-node", "sk-node"],
        "ai": ["cc15-node"],
        "pure-low-risk": ["cc15-node"],
    }
    rendered, _ = render_profile(SAMPLE_HIERARCHICAL_TEMPLATE, names)
    payload = yaml.safe_load(rendered)

    # 1. Assert provider level health-check is disabled for sakura
    prov_sakura = payload["proxy-providers"]["source-sakura"]
    assert prov_sakura["health-check"]["enable"] is False

    # 2. Assert metered source never appears in auto groups (fallback/url-test)
    for group in payload["proxy-groups"]:
        if group.get("type") in ["fallback", "url-test"]:
            assert "🌸 外部 SK · 全部" not in group.get("proxies", [])
            assert "source-sakura" not in group.get("use", [])


def test_ai_fallback_prioritizes_private_and_uses_valid_probe_url():
    """Ticket #25: AI Fallback group puts private sources before public and uses chatgpt trace URL."""
    names = {
        "baseline": ["cc15-node"],
        "ai": ["cc15-node"],
        "pure-low-risk": ["cc15-node"],
    }
    rendered, _ = render_profile(SAMPLE_HIERARCHICAL_TEMPLATE, names)
    payload = yaml.safe_load(rendered)

    group_map = {g["name"]: g for g in payload["proxy-groups"]}
    ai_auto = group_map["🛡️ 自建优先 (AI 容灾)"]

    assert ai_auto["type"] == "fallback"
    assert ai_auto["url"] == "https://chatgpt.com/cdn-cgi/trace"

    # Private before public
    proxies = ai_auto["proxies"]
    vps_idx = proxies.index("🖥️ 自建 VPS · AI")
    nat_idx = proxies.index("🧭 自建 NAT · AI")
    bp_idx = proxies.index("🌐 外部 BP · AI")
    assert vps_idx < nat_idx < bp_idx


def test_bounded_clean_group_count_and_mihomo_syntax():
    """Ticket #26: Total groups bounded <= 15, valid with mihomo -t."""
    import tempfile, subprocess
    names = {
        "baseline": ["node-1"],
        "ai": ["node-1"],
        "pure-low-risk": ["node-1"],
    }
    rendered, _ = render_profile(SAMPLE_HIERARCHICAL_TEMPLATE, names)
    payload = yaml.safe_load(rendered)

    assert len(payload["proxy-groups"]) <= 15

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("mixed-port: 17890\nmode: rule\n" + rendered)
        tmp_name = f.name

    res = subprocess.run(["/opt/homebrew/bin/mihomo", "-t", "-f", tmp_name], capture_output=True, text=True)
    Path(tmp_name).unlink()
    assert res.returncode == 0, f"Mihomo validation failed:\n{res.stdout}\n{res.stderr}"
