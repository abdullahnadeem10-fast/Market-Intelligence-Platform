import json

import httpx
import pytest
from sqlalchemy import select

from app.collectors.base import CompanyQuery, InvalidResponseError, RateLimitedError, CollectorError
from app.collectors.gdelt import GdeltNewsCollector
from app.collectors.hackernews import HackerNewsCollector
from app.collectors.rss import RssFeedCollector
from app.db import SessionLocal
from app.models import CollectedItem, CollectionRun, Company
from app.services import collection_service
from app.services.categorizer import categorize
from app.services.normalization import InvalidItem, canonicalize_url, normalize_item
from tests.helpers import FailingGdelt, FakeCollector, raw, seed_items


# ---------- normalization ----------
def test_canonicalize_url_strips_tracking_and_normalizes():
    a = canonicalize_url("http://WWW.Example.com/news/story/?utm_source=x&id=5#frag")
    b = canonicalize_url("https://example.com/news/story?id=5&fbclid=abc")
    assert a == b == "https://example.com/news/story?id=5"
    with pytest.raises(InvalidItem):
        canonicalize_url("javascript:alert(1)")


def test_normalize_item_cleans_html_and_validates():
    item = normalize_item(raw("  Acme &amp; Co   <b>raises</b> funds ", "https://x.com/a", summary="<p>Hello <i>world</i></p>"))
    assert item.title == "Acme & Co raises funds"
    assert item.summary == "Hello world"
    assert item.domain == "x.com"
    with pytest.raises(InvalidItem):
        normalize_item(raw("", "https://x.com/b"))


def test_categorizer_rules():
    assert "funding" in categorize("Acme raises $50M Series B")
    assert "security" in categorize("Globex suffers major outage")
    assert "legal" not in categorize("A refined approach to pricing")  # 'fine' is whole-word only


# ---------- duplicate handling ----------
def _company(db, user_name="Acme Robotics") -> Company:
    from app.models import User

    user = User(email=f"{user_name.replace(' ', '').lower()}@example.com", password_hash="x")
    db.add(user)
    db.flush()
    company = Company(user_id=user.id, name=user_name, name_normalized=user_name.lower())
    db.add(company)
    db.commit()
    return company


def test_duplicates_are_detected_by_url_and_title(db):
    company = _company(db)
    first = [
        raw("Acme Robotics launches arm", "https://news.example.com/arm?utm_source=hn"),
        raw("Acme Robotics raises Series C", "https://other.example.com/funding"),
        raw("Acme Robotics raises Series C", "https://third.example.com/syndicated"),  # same story, in-batch dup
    ]
    assert seed_items(db, company.id, first) == (2, 1, 0)

    second = [
        raw("Acme Robotics launches arm", "https://news.example.com/arm"),  # same URL after canonicalization
        raw("Acme Robotics Raises Series C - The Daily", "https://fourth.example.com/x"),  # same title, publisher suffix
        raw("Acme Robotics hires new CTO", "https://news.example.com/cto"),
        raw("", "https://news.example.com/empty"),  # invalid
    ]
    assert seed_items(db, company.id, second) == (1, 2, 1)
    assert db.scalar(select(CollectedItem).where(CollectedItem.title.like("%CTO%"))) is not None
    assert len(db.scalars(select(CollectedItem)).all()) == 3


# ---------- pipeline / failure isolation ----------
def test_collection_run_stores_items_and_records_run(db):
    company = _company(db)
    collector = FakeCollector({company.name: [raw("Acme Robotics opens factory", "https://n.example.com/f")]})
    run = collection_service.start_run(db, company.user_id, "manual")
    collection_service.execute_run(SessionLocal, run.id, collectors=[collector])

    db.expire_all()
    run = db.get(CollectionRun, run.id)
    assert run.status == "success"
    assert run.items_new == 1 and run.items_fetched == 1
    assert run.finished_at is not None
    assert db.get(Company, company.id).last_collected_at is not None
    stored = db.scalars(select(CollectedItem)).one()
    assert stored.collection_run_id == run.id

    # running again yields only duplicates
    run2 = collection_service.start_run(db, company.user_id, "manual")
    collection_service.execute_run(SessionLocal, run2.id, collectors=[collector])
    db.expire_all()
    run2 = db.get(CollectionRun, run2.id)
    assert (run2.items_new, run2.items_duplicate) == (0, 1)


def test_failing_source_does_not_crash_run(db):
    company = _company(db)
    good = FakeCollector({company.name: [raw("Acme Robotics opens factory", "https://n.example.com/f")]})
    run = collection_service.start_run(db, company.user_id, "manual")
    collection_service.execute_run(SessionLocal, run.id, collectors=[good, FailingGdelt()])
    db.expire_all()
    run = db.get(CollectionRun, run.id)
    assert run.status == "partial"
    assert run.items_new == 1
    assert run.error_count == 1
    assert run.details["errors"][0]["source"] == "gdelt"
    assert "timed out" in run.details["errors"][0]["error"]


def test_all_sources_failing_marks_run_failed(db):
    company = _company(db)
    run = collection_service.start_run(db, company.user_id, "manual")
    collection_service.execute_run(SessionLocal, run.id, collectors=[FakeCollector(fail=True)])
    db.expire_all()
    assert db.get(CollectionRun, run.id).status == "failed"


def test_unexpected_exception_in_collector_is_contained(db):
    company = _company(db)

    class Boom(FakeCollector):
        def fetch(self, company):
            raise RuntimeError("kaboom")

    run = collection_service.start_run(db, company.user_id, "manual")
    collection_service.execute_run(SessionLocal, run.id, collectors=[Boom()])
    db.expire_all()
    run = db.get(CollectionRun, run.id)
    assert run.status == "failed"
    assert "kaboom" not in json.dumps(run.details)  # internal details not exposed


def test_concurrent_runs_are_rejected(db):
    company = _company(db)
    collection_service.start_run(db, company.user_id, "manual")
    with pytest.raises(collection_service.CollectionAlreadyRunning):
        collection_service.start_run(db, company.user_id, "manual")


def test_run_collection_api(client, alice, monkeypatch):
    client.post("/companies", json={"name": "Acme Robotics"}, headers=alice)
    fake = FakeCollector({"Acme Robotics": [raw("Acme Robotics partners with Globex", "https://n.example.com/p")]})
    monkeypatch.setattr(collection_service, "build_collectors", lambda settings, http: [fake])

    resp = client.post("/collection/run", headers=alice)
    assert resp.status_code == 202
    run_id = resp.json()["id"]
    run = client.get(f"/collection/runs/{run_id}", headers=alice).json()  # background task already ran
    assert run["status"] == "success"
    assert run["items_new"] == 1
    items = client.get("/items", headers=alice).json()
    assert items["items"][0]["title"] == "Acme Robotics partners with Globex"
    assert "Partnerships" in items["items"][0]["categories"]
    status = client.get("/collection/status", headers=alice).json()
    assert status["interval_minutes"] > 0


# ---------- individual collectors (HTTP mocked) ----------
def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _no_sleep(collector):
    collector._sleep = lambda s: None
    return collector


def test_hackernews_collector_parses_and_filters():
    def handler(request: httpx.Request):
        assert request.url.host == "hn.algolia.com"
        return httpx.Response(200, json={"hits": [
            {"objectID": "1", "title": "Acme Robotics unveils arm", "url": "https://acme.example/arm", "points": 120, "author": "pg", "created_at_i": 1_790_000_000},
            {"objectID": "2", "title": "Unrelated story about robots", "url": "https://x.example", "created_at_i": 1_790_000_000},
            {"objectID": "3", "title": "Ask HN: Acme Robotics hiring?", "story_text": "<p>Is <b>Acme Robotics</b> hiring?</p>", "created_at_i": 1_790_000_000},
        ]})

    items = HackerNewsCollector(_client(handler)).fetch(CompanyQuery(id=1, name="Acme Robotics"))
    assert [i.external_id for i in items] == ["hn:1", "hn:3"]
    assert items[0].score == 120
    assert items[1].url == "https://news.ycombinator.com/item?id=3"
    assert items[1].summary == "Is Acme Robotics hiring?"


def test_collector_handles_timeouts_and_invalid_json():
    def timeout_handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(CollectorError, match="timed out"):
        _no_sleep(HackerNewsCollector(_client(timeout_handler))).fetch(CompanyQuery(id=1, name="Acme"))

    bad = _client(lambda r: httpx.Response(200, text="<html>oops</html>"))
    with pytest.raises(InvalidResponseError):
        _no_sleep(HackerNewsCollector(bad)).fetch(CompanyQuery(id=1, name="Acme"))

    wrong_shape = _client(lambda r: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(InvalidResponseError):
        _no_sleep(HackerNewsCollector(wrong_shape)).fetch(CompanyQuery(id=1, name="Acme"))


def test_collector_retries_then_succeeds_on_server_error():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"hits": []})

    assert _no_sleep(HackerNewsCollector(_client(handler))).fetch(CompanyQuery(id=1, name="Acme")) == []
    assert calls["n"] == 2


def test_rate_limited_source_is_skipped_for_rest_of_run(db):
    from app.collectors.base import RateLimitedError as RLE
    from app.models import User

    user = User(email="rl@example.com", password_hash="x")
    db.add(user)
    db.flush()
    for name in ("A Corp", "B Corp", "C Corp"):
        db.add(Company(user_id=user.id, name=name, name_normalized=name.lower()))
    db.commit()

    class Limited(FakeCollector):
        key = "gdelt"

        def fetch(self, company):
            self.calls += 1
            raise RLE("GDELT News: rate limited by provider (HTTP 429)")

    limited = Limited()
    run = collection_service.start_run(db, user.id, "manual")
    collection_service.execute_run(SessionLocal, run.id, collectors=[limited])
    db.expire_all()
    run = db.get(CollectionRun, run.id)
    assert limited.calls == 1  # not called again for B Corp / C Corp
    assert run.details["sources"]["gdelt"]["skipped"] == 2
    assert run.status == "failed"


def test_gdelt_rate_limit_and_parsing(monkeypatch):
    monkeypatch.setattr(GdeltNewsCollector, "_cooldown_until", 0.0)
    limited = _client(lambda r: httpx.Response(200, text="Please limit requests to one every 5 seconds"))
    c = _no_sleep(GdeltNewsCollector(limited))
    c.min_interval_seconds = 0
    with pytest.raises(RateLimitedError):
        c.fetch(CompanyQuery(id=1, name="Globex"))
    # cooldown: the next call fails fast without an HTTP request
    with pytest.raises(RateLimitedError, match="cooling down"):
        c.fetch(CompanyQuery(id=1, name="Globex"))
    monkeypatch.setattr(GdeltNewsCollector, "_cooldown_until", 0.0)

    http_429 = _no_sleep(GdeltNewsCollector(_client(lambda r: httpx.Response(429))))
    http_429.min_interval_seconds = 0
    with pytest.raises(RateLimitedError):
        http_429.fetch(CompanyQuery(id=1, name="Globex"))
    monkeypatch.setattr(GdeltNewsCollector, "_cooldown_until", 0.0)

    ok = _client(lambda r: httpx.Response(200, json={"articles": [
        {"url": "https://news.example/g1", "title": "Globex expands", "seendate": "20261001T101500Z", "domain": "news.example", "language": "English"},
    ]}))
    c = _no_sleep(GdeltNewsCollector(ok))
    c.min_interval_seconds = 0
    items = c.fetch(CompanyQuery(id=1, name="Globex"))
    assert items[0].published_at.isoformat() == "2026-10-01T10:15:00+00:00"

    empty = _no_sleep(GdeltNewsCollector(_client(lambda r: httpx.Response(200, json={}))))
    empty.min_interval_seconds = 0
    assert empty.fetch(CompanyQuery(id=1, name="Globex")) == []


RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Acme News</title>
<item><title>Acme ships v2</title><link>https://acme.example/blog/v2</link><guid>v2</guid>
<pubDate>Wed, 01 Oct 2026 09:00:00 GMT</pubDate><description>&lt;p&gt;Big release&lt;/p&gt;</description></item>
<item><title>Ancient post</title><link>https://acme.example/blog/old</link><pubDate>Mon, 01 Jan 2018 09:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_rss_collector_respects_robots_and_parses():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        return httpx.Response(200, text=RSS, headers={"content-type": "application/rss+xml"})

    collector = RssFeedCollector(_client(handler))
    q = CompanyQuery(id=1, name="Acme", rss_url="https://acme.example/feed.xml")
    assert collector.is_applicable(q)
    assert not collector.is_applicable(CompanyQuery(id=1, name="Acme"))
    items = collector.fetch(q)
    assert [i.title for i in items] == ["Acme ships v2"]  # old item outside lookback skipped
    assert items[0].summary == "Big release"

    blocked = CompanyQuery(id=1, name="Acme", rss_url="https://acme.example/private/feed.xml")
    with pytest.raises(CollectorError, match="robots.txt"):
        collector.fetch(blocked)
