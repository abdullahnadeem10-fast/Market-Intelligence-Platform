"""Transparent rule-based categorization of collected items (no LLM tokens spent).

Keywords match whole words; a trailing `*` makes a keyword a prefix (e.g. `restructur*`).
"""

import re

CATEGORIES: dict[str, tuple[str, list[str]]] = {
    "product": ("Product & Launches", ["launch*", "unveil*", "introduc*", "release*", "rolls out", "new feature*", "beta", "now available", "debut*"]),
    "funding": ("Funding & Investment", ["raise", "raises", "raised", "funding", "series [a-f]", "investment*", "investor*", "valuation", "ipo", "venture capital"]),
    "earnings": ("Earnings & Financials", ["earnings", "revenue*", "quarterly", "profit*", "guidance", "fiscal", "net loss", "margin*", "stock", "shares"]),
    "partnership": ("Partnerships", ["partner*", "collaborat*", "alliance", "teams up", "joint venture"]),
    "mna": ("Mergers & Acquisitions", ["acquir*", "acquisition*", "merger*", "buyout", "takeover"]),
    "legal": ("Legal & Regulatory", ["lawsuit*", "sue", "sues", "sued", "court", "regulator*", "regulation*", "antitrust", "fined", "fine", "investigation*", "inquiry", "probe", "ftc", "sec", "doj", "compliance", "ban", "banned"]),
    "leadership": ("Leadership & People", ["ceo", "cto", "cfo", "coo", "appoint*", "steps down", "resign*", "executive*", "board"]),
    "workforce": ("Layoffs & Hiring", ["layoff*", "job cuts", "cuts staff", "restructur*", "hiring", "headcount", "workforce"]),
    "security": ("Security & Incidents", ["breach*", "vulnerabilit*", "hack", "hacked", "hackers", "outage*", "exploit*", "ransomware", "leak*", "recall*", "incident*", "cyberattack*"]),
    "ai": ("AI & Technology", ["ai", "artificial intelligence", "machine learning", "llm*", "gpu*", "chip*", "inference", "neural", "generative", "model", "models", "agent*"]),
}


def _compile(keywords: list[str]) -> re.Pattern[str]:
    parts = []
    for kw in keywords:
        if kw.endswith("*"):
            parts.append(rf"\b{kw[:-1]}\w*")
        else:
            parts.append(rf"\b{kw}\b")
    return re.compile("|".join(parts), re.IGNORECASE)


_PATTERNS = {slug: _compile(kws) for slug, (_, kws) in CATEGORIES.items()}


def categorize(title: str, summary: str = "") -> list[str]:
    text = f"{title} {summary[:500]}"
    return [slug for slug, pattern in _PATTERNS.items() if pattern.search(text)]
