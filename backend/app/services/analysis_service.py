"""AI market analysis pipeline.

1. Select relevant stored items (scoped to the user, a time window and optionally one company).
2. De-duplicate near-identical stories and cap the context (item count + characters).
3. Re-use a cached analysis when the exact same source set was analysed recently.
4. Ask the LLM for JSON where every insight cites numbered sources.
5. Validate: insights citing unknown/no sources are discarded (grounding guard).
6. Persist the analysis with its sources and token/cost/latency usage.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.models import AIAnalysis, CollectedItem, Company, User
from app.schemas import AnalysisResult, AnalysisSource
from app.services.categorizer import CATEGORIES
from app.services.llm_service import LLMError, LLMService, estimate_tokens
from app.services.normalization import sha256

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
INSIGHT_SECTIONS = ["emerging_trends", "important_developments", "competitor_activity", "opportunities", "risks", "key_takeaways"]

SYSTEM_PROMPT = """You are a careful market intelligence analyst.
You will receive a numbered list of collected source items (headlines and short summaries).
Rules:
- Use ONLY information stated in the provided sources. Do not use outside knowledge. Do not speculate beyond what sources say.
- Every insight must cite the source numbers it is based on in its "sources" array (e.g. [1, 4]).
- If the sources do not support a section, return an empty list for it. Fewer, well-supported insights are better than many weak ones.
- Opportunities and risks must be framed as implications directly supported by cited sources.
- Be concise: each insight at most 40 words; market_summary at most 120 words with inline citations like [2].
Return ONLY a JSON object with exactly these keys:
{"market_summary": str,
 "emerging_trends": [{"text": str, "sources": [int]}],
 "important_developments": [...], "competitor_activity": [...],
 "opportunities": [...], "risks": [...], "key_takeaways": [...]}"""


class AnalysisInputError(Exception):
    pass


@dataclass
class ContextItem:
    ref: int
    item: CollectedItem


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


_DEDUP_STOPWORDS = {"the", "and", "for", "with", "its", "from", "into", "over", "after", "about", "show", "ask", "new", "says"}


def _tokens(title: str, ignore: set[str] = frozenset()) -> set[str]:
    # Truncating to 5 chars is a crude stemmer: acquire/acquires/acquiring -> "acqui".
    return {
        w[:5] for w in re.findall(r"[a-z0-9]+", title.lower())
        if len(w) > 2 and w not in _DEDUP_STOPWORDS and w not in ignore
    }


def _overlap(a: set[str], b: set[str]) -> float:
    """Overlap coefficient |A∩B| / min(|A|,|B|): robust to reworded or longer headline variants."""
    if min(len(a), len(b)) < 2:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _name_words(name: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", name.lower()))


def select_context(
    db: Session, user: User, company: Company | None, days: int, settings: Settings
) -> list[ContextItem]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(CollectedItem)
        .join(Company, Company.id == CollectedItem.company_id)
        .where(Company.user_id == user.id, CollectedItem.published_at >= since)
        .options(selectinload(CollectedItem.categories), selectinload(CollectedItem.company), selectinload(CollectedItem.source))
        .order_by(CollectedItem.published_at.desc(), CollectedItem.id.desc())
        .limit(settings.llm_max_context_items * 6)
    )
    if company is not None:
        stmt = stmt.where(CollectedItem.company_id == company.id)
    candidates = list(db.scalars(stmt))

    # Drop near-duplicate stories (same event reported by several outlets) to avoid paying for repeats.
    # Within one company its own name is ignored (every item shares it); across companies the full
    # title is compared with a stricter threshold so "A raises Series C" != "B raises Series C".
    unique: list[CollectedItem] = []
    seen: list[tuple[int, set[str], set[str]]] = []  # (company_id, tokens without company name, all tokens)
    for item in candidates:
        own = _tokens(item.title, _name_words(item.company.name))
        full = _tokens(item.title)
        if any(
            _overlap(own, s_own) >= 0.6 if cid == item.company_id else _overlap(full, s_full) >= 0.8
            for cid, s_own, s_full in seen
        ):
            continue
        seen.append((item.company_id, own, full))
        unique.append(item)

    # For market-wide analysis interleave companies so one noisy company can't fill the context.
    if company is None:
        buckets: dict[int, list[CollectedItem]] = defaultdict(list)
        for item in unique:
            buckets[item.company_id].append(item)
        interleaved: list[CollectedItem] = []
        while any(buckets.values()):
            for cid in list(buckets):
                if buckets[cid]:
                    interleaved.append(buckets[cid].pop(0))
        unique = interleaved

    selected: list[ContextItem] = []
    chars = 0
    for item in unique:
        if len(selected) >= settings.llm_max_context_items:
            break
        line_len = len(_format_line(0, item))
        if chars + line_len > settings.llm_max_context_chars:
            break
        chars += line_len
        selected.append(ContextItem(ref=len(selected) + 1, item=item))
    return selected


def _format_line(ref: int, item: CollectedItem) -> str:
    cats = ",".join(c.slug for c in item.categories) or "general"
    summary = (item.summary or "")[:280]
    line = f"[{ref}] {_utc(item.published_at):%Y-%m-%d} | {item.company.name} | {item.domain or item.source.name} | {cats}\n{item.title}"
    if summary:
        line += f"\n{summary}"
    return line + "\n"


def build_user_prompt(context: list[ContextItem], company: Company | None, tracked: list[Company]) -> str:
    if company is not None:
        competitors = [c.name for c in tracked if c.id != company.id and c.relation == "competitor"]
        focus = f"Focus company: {company.name}."
        if competitors:
            focus += f" Tracked competitors: {', '.join(competitors)}."
    else:
        own = [c.name for c in tracked if c.relation == "own"]
        comps = [c.name for c in tracked if c.relation == "competitor"]
        focus = f"Market-wide analysis of tracked companies: {', '.join(c.name for c in tracked)}."
        if own:
            focus += f" The user's own company: {', '.join(own)}."
        if comps:
            focus += f" Competitors: {', '.join(comps)}."
    lines = "\n".join(_format_line(c.ref, c.item) for c in context)
    return f"{focus}\n\nSOURCES:\n{lines}\nProduce the JSON analysis now."


def parse_and_validate(content: str, valid_refs: set[int]) -> tuple[AnalysisResult, int]:
    """Parse model output and drop any insight that cites no valid source. Returns (result, dropped)."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise LLMError("The AI response was not valid JSON.")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise LLMError("The AI response was not valid JSON.")
    if not isinstance(data, dict):
        raise LLMError("The AI response had an unexpected structure.")

    dropped = 0
    cleaned: dict = {"market_summary": str(data.get("market_summary") or "")[:2000]}
    for section in INSIGHT_SECTIONS:
        out = []
        for entry in data.get(section) or []:
            if not isinstance(entry, dict) or not str(entry.get("text") or "").strip():
                dropped += 1
                continue
            refs = []
            for r in entry.get("sources") or []:
                try:
                    refs.append(int(r))
                except (TypeError, ValueError):
                    continue
            refs = sorted({r for r in refs if r in valid_refs})
            if not refs:
                dropped += 1  # ungrounded insight
                continue
            out.append({"text": str(entry["text"]).strip()[:600], "sources": refs})
        cleaned[section] = out[:8]
    # Remove citations to non-existent sources from the free-text summary.
    cleaned["market_summary"] = re.sub(
        r"\[(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in valid_refs else "", cleaned["market_summary"]
    )
    try:
        return AnalysisResult.model_validate(cleaned), dropped
    except ValidationError:
        raise LLMError("The AI response had an unexpected structure.")


def extractive_analysis(context: list[ContextItem], company: Company | None, tracked: list[Company]) -> AnalysisResult:
    """Offline mode: a deterministic, rule-based digest built only from source headlines.

    No language model is involved; every line is a direct grouping/quotation of collected items.
    """
    by_cat: dict[str, list[ContextItem]] = defaultdict(list)
    for c in context:
        for cat in c.item.categories:
            by_cat[cat.slug].append(c)

    def headline(c: ContextItem) -> str:
        return f"{c.item.company.name}: {c.item.title}"

    def group(slugs: list[str], limit: int = 4) -> list[dict]:
        seen, out = set(), []
        for slug in slugs:
            for c in by_cat.get(slug, []):
                if c.ref not in seen:
                    seen.add(c.ref)
                    out.append({"text": headline(c), "sources": [c.ref]})
        return out[:limit]

    cat_counts = Counter({slug: len(v) for slug, v in by_cat.items()})
    trends = [
        {"text": f"{CATEGORIES[slug][0]}: {n} of {len(context)} recent items", "sources": [c.ref for c in by_cat[slug]][:6]}
        for slug, n in cat_counts.most_common(4) if n >= 2
    ]
    competitor_ids = {c.id for c in tracked if c.relation == "competitor"}
    comp_items = [c for c in context if c.item.company_id in competitor_ids and (company is None or c.item.company_id != company.id)]
    per_company = Counter(c.item.company.name for c in context)
    newest = context[0] if context else None
    summary_parts = [f"{len(context)} source items analysed"]
    if per_company:
        summary_parts.append("most active: " + ", ".join(f"{n} ({k})" for n, k in per_company.most_common(3)))
    if newest:
        summary_parts.append(f"latest: \"{newest.item.title}\" [{newest.ref}]")
    return AnalysisResult(
        market_summary="Extractive digest (no LLM configured). " + "; ".join(summary_parts) + ".",
        emerging_trends=trends,
        important_developments=group(["mna", "funding", "earnings", "product", "partnership"], 5),
        competitor_activity=[{"text": headline(c), "sources": [c.ref]} for c in comp_items[:5]],
        opportunities=group(["partnership", "product", "funding"], 3),
        risks=group(["security", "legal", "workforce"], 4),
        key_takeaways=[{"text": headline(c), "sources": [c.ref]} for c in context[:3]],
    )


def run_analysis(
    db: Session,
    user: User,
    company: Company | None,
    days: int,
    force: bool,
    llm: LLMService | None,
    settings: Settings | None = None,
) -> tuple[AIAnalysis, bool]:
    """Run (or reuse) an analysis. Returns (analysis, cached). Raises AnalysisInputError / LLMError."""
    settings = settings or get_settings()
    context = select_context(db, user, company, days, settings)
    if not context:
        raise AnalysisInputError(
            "No collected data in the selected time window. Run a collection first or widen the window."
        )
    tracked = list(db.scalars(select(Company).where(Company.user_id == user.id)))
    provider = llm.provider if llm else "extractive"
    model = llm.model if llm else "rule-based"
    scope = "company" if company else "market"
    item_ids = [c.item.id for c in context]
    context_hash = sha256(f"{PROMPT_VERSION}|{scope}|{company.id if company else 0}|{provider}|{model}|{item_ids}")

    if not force:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.analysis_cache_minutes)
        cached = db.scalar(
            select(AIAnalysis)
            .where(
                AIAnalysis.user_id == user.id,
                AIAnalysis.context_hash == context_hash,
                AIAnalysis.status == "success",
                AIAnalysis.created_at >= cutoff,
            )
            .order_by(AIAnalysis.created_at.desc())
        )
        if cached is not None:
            return cached, True

    analysis = AIAnalysis(
        user_id=user.id,
        company_id=company.id if company else None,
        scope=scope,
        provider=provider,
        model=model,
        context_hash=context_hash,
        context_item_count=len(context),
        sources=[c.item for c in context],
    )
    refs_meta = {"source_refs": item_ids}

    if llm is None:
        started = time.perf_counter()
        result = extractive_analysis(context, company, tracked)
        analysis.status = "success"
        analysis.result = {**result.model_dump(), **refs_meta, "dropped_insights": 0}
        analysis.latency_ms = int((time.perf_counter() - started) * 1000)
    else:
        user_prompt = build_user_prompt(context, company, tracked)
        try:
            resp = llm.complete_json(SYSTEM_PROMPT, user_prompt, settings.llm_max_output_tokens)
            result, dropped = parse_and_validate(resp.content, {c.ref for c in context})
        except LLMError as exc:
            analysis.status = "failed"
            analysis.error = exc.message
            analysis.result = refs_meta
            analysis.input_tokens = estimate_tokens(SYSTEM_PROMPT + user_prompt)
            analysis.tokens_estimated = True
            db.add(analysis)
            db.commit()
            raise
        analysis.status = "success"
        analysis.model = resp.model
        analysis.result = {**result.model_dump(), **refs_meta, "dropped_insights": dropped}
        analysis.input_tokens = resp.input_tokens
        analysis.output_tokens = resp.output_tokens
        analysis.tokens_estimated = resp.tokens_estimated
        analysis.latency_ms = resp.latency_ms
        analysis.cost_usd = round(
            resp.input_tokens / 1_000_000 * settings.llm_input_cost_per_million
            + resp.output_tokens / 1_000_000 * settings.llm_output_cost_per_million,
            6,
        )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis, False


def analysis_sources(db: Session, analysis: AIAnalysis) -> list[AnalysisSource]:
    ref_ids: list[int] = (analysis.result or {}).get("source_refs") or []
    if not ref_ids:
        return []
    items = {
        i.id: i
        for i in db.scalars(
            select(CollectedItem)
            .where(CollectedItem.id.in_(ref_ids))
            .options(selectinload(CollectedItem.company), selectinload(CollectedItem.source))
        )
    }
    out = []
    for ref, item_id in enumerate(ref_ids, start=1):
        item = items.get(item_id)
        if item is None:
            continue  # source item deleted (e.g. company removed)
        out.append(
            AnalysisSource(
                ref=ref, item_id=item.id, title=item.title, url=item.url, source=item.source.name,
                company_name=item.company.name, published_at=item.published_at,
            )
        )
    return out
