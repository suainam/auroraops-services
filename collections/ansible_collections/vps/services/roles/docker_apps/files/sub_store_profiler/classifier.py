"""4-dimensional Semantic Classifier and Node Cleanser for Sub-Store nodes.

Classifies nodes along 4 orthogonal dimensions:
- REGION (HK, JP, SG, US, TW, KR, GB, TR, NG, AR, RU, MY, etc.)
- TIER (专线, 家宽, 中转)
- CAPABILITY (AI, Stream)
- COST (0.01x, 0.1x)

Also filters non-proxy metadata noise.
"""
from __future__ import annotations

import re
from typing import Optional

# 0. Noise filter: rejects metadata, notice, or advisory entries
NOISE_RE = re.compile(
    r"(?i)剩余流量|流量剩余|到期|过期|官网|网址|公告|套餐|重置|客服|群组|频道|防失联|教程|客户端|提示|建议|下载|traffic|expire|expiry|reset|website"
)

# 1. 4-Dimensional semantic rules
REGION_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("HK", re.compile(r"(?i)香港|HK|Hong\s*Kong|🇭🇰")),
    ("JP", re.compile(r"(?i)日本|JP|Japan|Tokyo|Osaka|AWS日本|🇯🇵")),
    ("SG", re.compile(r"(?i)新加坡|SG|Singapore|狮城|🇸🇬")),
    ("US", re.compile(r"(?i)美国|US|America|凤凰城|纽约|洛杉矶|波特兰|硅谷|🇺🇸")),
    ("TW", re.compile(r"(?i)台湾|TW|Taiwan|台北|🇹🇼")),
    ("KR", re.compile(r"(?i)韩国|Korea|KR|首尔|🇰🇷")),
    ("GB", re.compile(r"(?i)英国|UK|GB|伦敦|🇬🇧")),
    ("TR", re.compile(r"(?i)土耳其|Turkey|TR|伊斯坦布尔|🇹🇷")),
    ("NG", re.compile(r"(?i)尼日利亚|Nigeria|NG|拉各斯|🇳🇬")),
    ("AR", re.compile(r"(?i)阿根廷|Argentina|AR|🇦🇷")),
    ("RU", re.compile(r"(?i)俄罗斯|Russia|RU|莫斯科|🇷🇺")),
    ("IN", re.compile(r"(?i)印度|India|\bIN\b|🇮🇳")),
    ("PK", re.compile(r"(?i)巴基斯坦|Pakistan|\bPK\b|🇵🇰")),
    ("MY", re.compile(r"(?i)马来西亚|Malaysia|\bMY\b|吉隆坡|🇲🇾")),
]
TIER_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("专线", re.compile(r"(?i)IEPL|IPLC|专线")),
    ("家宽", re.compile(r"(?i)家宽|家庭|Residential|Home|resi")),
    ("千兆", re.compile(r"(?i)千兆|1000M|1\.8G|大带宽|无限|神速")),
    ("大带宽", re.compile(r"(?i)千兆|1000M|1\.8G|大带宽|无限|神速")),
    ("中转", re.compile(r"(?i)中转|BGP|HY|直连")),
]

# Capability regex with boundary protection to prevent false positive matches on pinyin syllables (e.g. baipiao, shanghai)
CAPABILITY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("AI", re.compile(r"(?i)(?:^|[^a-z])ai(?:[^a-z]|$)|chatgpt|gpt|claude|gemini|解锁")),
    ("Stream", re.compile(r"(?i)Netflix|Disney|油管|去广告")),
]

COST_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("0.01x", re.compile(r"0\.01(?:倍|x)?")),
    ("0.1x", re.compile(r"0\.1(?:倍|x)?")),
]


def classify_and_clean_node(name: str) -> Optional[str]:
    """Clean and decorate node name with semantic brackets, or None if noise."""
    if not name or not isinstance(name, str):
        return None
    cleaned_name = name.strip()
    if NOISE_RE.search(cleaned_name):
        return None

    tags: list[str] = []

    # 1. Region
    for r_code, r_pat in REGION_RULES:
        if r_pat.search(cleaned_name):
            tags.append(f"[{r_code}]")
            break

    # 2. Tier
    tier_matched = False
    for t_code, t_pat in TIER_RULES:
        if t_pat.search(cleaned_name):
            tags.append(f"[{t_code}]")
            tier_matched = True
    if not tier_matched:
        tags.append("[普通]")
    # 3. Capability
    for c_code, c_pat in CAPABILITY_RULES:
        if c_pat.search(cleaned_name):
            tags.append(f"[{c_code}]")

    # 4. Cost
    for m_code, m_pat in COST_RULES:
        if m_pat.search(cleaned_name):
            tags.append(f"[{m_code}]")

    if tags:
        return f"{' '.join(tags)} {cleaned_name}"
    return cleaned_name
