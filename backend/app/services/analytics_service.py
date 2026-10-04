"""Aggregations for the dashboard and analytics pages. All queries are scoped to one user."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import AIAnalysis, Category, CollectedItem, CollectionRun, Company, Source, item_categories

STOPWORDS = set(
    """a an and are as at be by for from has have how in into is it its of on or that the this to was were will with
    new says said after over about more than up out you your we our they their his her not but can could would should
    why what when who which all just now one two first last year years week day today report reports via vs show hn
    ask launch launches launched inc ltd corp company companies its it's says new more how get gets got make makes""".split()
)


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _user_items(user_id: int):
    return select(CollectedItem).join(Company, Company.id == CollectedItem.company_id).where(Company.user_id == user_id)


def overview(db: Session, user_id: int) -> dict:
    company_count = db.scalar(select(func.count(Company.id)).where(Company.user_id == user_id)) or 0
    base = select(func.count(CollectedItem.id)).join(Company).where(Company.user_id == user_id)
    total_items = db.scalar(base) or 0
    items_7d = db.scalar(base.where(CollectedItem.published_at >= _since(7))) or 0
    items_prev_7d = db.scalar(base.where(CollectedItem.published_at >= _since(14), CollectedItem.published_at < _since(7))) or 0
    analyses = db.scalar(select(func.count(AIAnalysis.id)).where(AIAnalysis.user_id == user_id, AIAnalysis.status == "success")) or 0
    last_run = db.scalar(select(CollectionRun).where(CollectionRun.user_id == user_id).order_by(CollectionRun.started_at.desc()))
    return {
        "tracked_companies": company_count,
        "total_items": total_items,
        "items_last_7d": items_7d,
        "items_prev_7d": items_prev_7d,
        "analyses": analyses,
        "last_run": None if last_run is None else {
            "id": last_run.id, "status": last_run.status, "started_at": last_run.started_at,
            "finished_at": last_run.finished_at, "items_new": last_run.items_new,
        },
    }


def activity_over_time(db: Session, user_id: int, days: int, company_id: int | None = None) -> list[dict]:
    day = cast(CollectedItem.published_at, Date)
    stmt = (
        select(day.label("day"), func.count(CollectedItem.id))
        .join(Company)
        .where(Company.user_id == user_id, CollectedItem.published_at >= _since(days))
        .group_by(day)
        .order_by(day)
    )
    if company_id is not None:
        stmt = stmt.where(CollectedItem.company_id == company_id)
    counts = {str(d): n for d, n in db.execute(stmt).all()}
    start = date.today() - timedelta(days=days - 1)
    return [{"date": str(start + timedelta(days=i)), "count": counts.get(str(start + timedelta(days=i)), 0)} for i in range(days)]


def items_by_company(db: Session, user_id: int, days: int) -> list[dict]:
    stmt = (
        select(Company.name, Company.relation, func.count(CollectedItem.id))
        .outerjoin(CollectedItem, (CollectedItem.company_id == Company.id) & (CollectedItem.published_at >= _since(days)))
        .where(Company.user_id == user_id)
        .group_by(Company.id, Company.name, Company.relation)
        .order_by(func.count(CollectedItem.id).desc())
    )
    return [{"company": n, "relation": r, "count": c} for n, r, c in db.execute(stmt).all()]


def activity_by_category(db: Session, user_id: int, days: int, company_id: int | None = None) -> list[dict]:
    stmt = (
        select(Category.name, func.count(CollectedItem.id))
        .join(item_categories, item_categories.c.category_id == Category.id)
        .join(CollectedItem, CollectedItem.id == item_categories.c.item_id)
        .join(Company, Company.id == CollectedItem.company_id)
        .where(Company.user_id == user_id, CollectedItem.published_at >= _since(days))
        .group_by(Category.name)
        .order_by(func.count(CollectedItem.id).desc())
    )
    if company_id is not None:
        stmt = stmt.where(CollectedItem.company_id == company_id)
    return [{"category": n, "count": c} for n, c in db.execute(stmt).all()]


def items_by_source(db: Session, user_id: int, days: int) -> list[dict]:
    stmt = (
        select(Source.name, func.count(CollectedItem.id))
        .join(CollectedItem, CollectedItem.source_id == Source.id)
        .join(Company, Company.id == CollectedItem.company_id)
        .where(Company.user_id == user_id, CollectedItem.published_at >= _since(days))
        .group_by(Source.name)
    )
    return [{"source": n, "count": c} for n, c in db.execute(stmt).all()]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def mention_counts(db: Session, user_id: int, days: int) -> list[dict]:
    """How often each tracked company is mentioned across ALL of the user's collected items."""
    companies = db.scalars(select(Company).where(Company.user_id == user_id)).all()
    out = []
    for c in companies:
        pattern = f"%{_escape_like(c.name)}%"
        n = db.scalar(
            select(func.count(CollectedItem.id))
            .join(Company, Company.id == CollectedItem.company_id)
            .where(
                Company.user_id == user_id,
                CollectedItem.published_at >= _since(days),
                or_(CollectedItem.title.ilike(pattern, escape="\\"), CollectedItem.summary.ilike(pattern, escape="\\")),
            )
        ) or 0
        out.append({"company": c.name, "mentions": n})
    return sorted(out, key=lambda r: r["mentions"], reverse=True)


def trending_terms(db: Session, user_id: int, days: int, limit: int = 12) -> list[dict]:
    """Most frequent terms in headlines this period vs the previous period of equal length."""
    company_words = set()
    for name in db.scalars(select(Company.name).where(Company.user_id == user_id)):
        company_words |= set(re.findall(r"[a-z0-9]+", name.lower()))
    rows = db.execute(
        select(CollectedItem.title, CollectedItem.published_at)
        .join(Company, Company.id == CollectedItem.company_id)
        .where(Company.user_id == user_id, CollectedItem.published_at >= _since(days * 2))
        .limit(5000)
    ).all()
    current, previous = Counter(), Counter()
    cutoff = _since(days)
    for title, published in rows:
        published = published if published.tzinfo else published.replace(tzinfo=timezone.utc)
        words = [w for w in re.findall(r"[a-z][a-z0-9\-]+", title.lower()) if len(w) > 2 and w not in STOPWORDS and w not in company_words]
        terms = set(words) | {f"{a} {b}" for a, b in zip(words, words[1:])}
        (current if published >= cutoff else previous).update(terms)
    ranked = [(t, n) for t, n in current.most_common(limit * 6) if n >= 2]
    # A unigram that almost always appears inside a frequent bigram ("world" in "world labs") adds
    # nothing; keep the more descriptive bigram only.
    bigrams = [(t, n) for t, n in ranked if " " in t]
    covered = {
        word for bigram, bn in bigrams for word in bigram.split() if current[word] <= bn + max(1, bn // 4)
    }
    result = []
    for term, n in ranked:
        if len(result) >= limit:
            break
        if " " not in term and term in covered:
            continue
        if " " in term and any(term in r["term"] and r["count"] >= n for r in result):
            continue
        result.append({"term": term, "count": n, "previous": previous.get(term, 0)})
    return result


def competitor_activity(db: Session, user_id: int, days: int, limit: int = 8) -> list[dict]:
    items = db.scalars(
        _user_items(user_id)
        .where(Company.relation == "competitor", CollectedItem.published_at >= _since(days))
        .options(selectinload(CollectedItem.company), selectinload(CollectedItem.categories))
        .order_by(CollectedItem.published_at.desc())
        .limit(limit)
    ).all()
    return [
        {"id": i.id, "company": i.company.name, "title": i.title, "url": i.url, "published_at": i.published_at,
         "categories": [c.name for c in i.categories]}
        for i in items
    ]
