import json

import httpx

from app.config import get_settings
from app.routers.analysis import get_llm
from app.main import app
from app.services.analysis_service import parse_and_validate
from app.services.llm_service import OpenAICompatibleLLM
from tests.helpers import raw, seed_items


def _company_with_items(client, headers, db, name="Globex Cloud", relation="watch"):
    company = client.post("/companies", json={"name": name, "relation": relation}, headers=headers).json()
    seed_items(db, company["id"], [
        raw(f"{name} raises Series C funding", f"https://n.example.com/{name}-1", 1),
        raw(f"{name} suffers EU outage", f"https://n.example.com/{name}-2", 2),
        raw(f"{name} partners with Initech", f"https://n.example.com/{name}-3", 3),
    ])
    return company


def _fake_llm(content: str | None = None, status: int = 200, usage: dict | None = None, calls: list | None = None):
    settings = get_settings().model_copy(update={"llm_api_key": "test-key", "llm_model": "test-model"})

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        if calls is not None:
            calls.append(body)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "nope"}}, headers={"Retry-After": "0"})
        return httpx.Response(200, json={
            "model": "test-model",
            "choices": [{"message": {"content": content}}],
            "usage": usage if usage is not None else {"prompt_tokens": 900, "completion_tokens": 300},
        })

    llm = OpenAICompatibleLLM(settings, transport=httpx.MockTransport(handler))
    return llm


GOOD = json.dumps({
    "market_summary": "Globex raised funding [1] but had an outage [2] and cites a fake source [99].",
    "emerging_trends": [{"text": "Infrastructure partnerships", "sources": [3]}],
    "important_developments": [
        {"text": "Series C funding", "sources": [1]},
        {"text": "Invented fact with no source", "sources": []},
        {"text": "Hallucinated citation", "sources": [42]},
    ],
    "competitor_activity": [],
    "opportunities": [{"text": "Partnership channel", "sources": ["3"]}],
    "risks": [{"text": "Reliability concerns", "sources": [2]}],
    "key_takeaways": [{"text": "Mixed month", "sources": [1, 2]}],
})


def test_extractive_analysis_with_sources(client, alice, db):
    company = _company_with_items(client, alice, db)
    resp = client.post(f"/analysis/company/{company['id']}", json={"days": 30}, headers=alice)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "success"
    assert data["provider"] == "extractive"
    assert len(data["sources"]) == 3
    refs = {s["ref"] for s in data["sources"]}
    for section in ("important_developments", "risks", "key_takeaways"):
        for insight in data["result"][section]:
            assert set(insight["sources"]) <= refs and insight["sources"]
    assert any("outage" in i["text"] for i in data["result"]["risks"])

    history = client.get(f"/analysis/company/{company['id']}", headers=alice).json()
    assert len(history) == 1
    detail = client.get(f"/companies/{company['id']}", headers=alice).json()
    assert detail["latest_analysis"]["id"] == data["id"]


def test_llm_analysis_grounding_tokens_and_cache(client, alice, db):
    company = _company_with_items(client, alice, db)
    calls: list = []
    app.dependency_overrides[get_llm] = lambda: _fake_llm(GOOD, calls=calls)

    resp = client.post(f"/analysis/company/{company['id']}", json={}, headers=alice)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["provider"] == "openai-compatible"
    assert data["input_tokens"] == 900 and data["output_tokens"] == 300
    assert data["tokens_estimated"] is False
    assert data["cost_usd"] > 0
    devs = data["result"]["important_developments"]
    assert [d["text"] for d in devs] == ["Series C funding"]  # ungrounded insights removed
    assert data["result"]["opportunities"][0]["sources"] == [3]
    assert "[99]" not in data["result"]["market_summary"]
    assert len(data["sources"]) == 3

    # prompt contains only the numbered sources + instructions, and output is capped
    sent = calls[0]
    assert sent["max_tokens"] == get_settings().llm_max_output_tokens
    assert "[1]" in sent["messages"][1]["content"]
    assert "Use ONLY information" in sent["messages"][0]["content"]

    # second call with the same context is served from cache (no new LLM call)
    again = client.post(f"/analysis/company/{company['id']}", json={}, headers=alice).json()
    assert again["cached"] is True and again["id"] == data["id"]
    assert len(calls) == 1
    forced = client.post(f"/analysis/company/{company['id']}", json={"force": True}, headers=alice).json()
    assert forced["cached"] is False and len(calls) == 2

    usage = client.get("/usage/ai", headers=alice).json()
    assert usage["total_analyses"] == 2
    assert usage["input_tokens"] == 1800 and usage["output_tokens"] == 600


def test_llm_failure_is_graceful_and_recorded(client, alice, db):
    company = _company_with_items(client, alice, db)
    import app.services.llm_service as llm_mod

    llm_mod.time.sleep = lambda s: None  # don't actually wait between retries
    try:
        app.dependency_overrides[get_llm] = lambda: _fake_llm(status=429)
        resp = client.post(f"/analysis/company/{company['id']}", json={}, headers=alice)
        assert resp.status_code == 429
        assert "rate limiting" in resp.json()["detail"]

        app.dependency_overrides[get_llm] = lambda: _fake_llm(status=401)
        resp = client.post(f"/analysis/company/{company['id']}", json={"force": True}, headers=alice)
        assert resp.status_code == 502
        assert "test-key" not in resp.text

        app.dependency_overrides[get_llm] = lambda: _fake_llm("this is not json")
        resp = client.post(f"/analysis/company/{company['id']}", json={"force": True}, headers=alice)
        assert resp.status_code == 502
    finally:
        import time as _time

        llm_mod.time.sleep = _time.sleep

    usage = client.get("/usage/ai", headers=alice).json()
    assert usage["failed_analyses"] == 3


def test_missing_usage_falls_back_to_estimates(client, alice, db):
    company = _company_with_items(client, alice, db)
    app.dependency_overrides[get_llm] = lambda: _fake_llm(GOOD, usage={})
    data = client.post(f"/analysis/company/{company['id']}", json={}, headers=alice).json()
    assert data["tokens_estimated"] is True
    assert data["input_tokens"] > 0


def test_analysis_without_data_returns_422(client, alice):
    company = client.post("/companies", json={"name": "Empty Co"}, headers=alice).json()
    resp = client.post(f"/analysis/company/{company['id']}", json={}, headers=alice)
    assert resp.status_code == 422
    assert "Run a collection" in resp.json()["detail"]


def test_market_analysis_covers_multiple_companies(client, alice, db):
    _company_with_items(client, alice, db, "Globex Cloud", "own")
    _company_with_items(client, alice, db, "Initech AI", "competitor")
    data = client.post("/analysis/market", json={}, headers=alice).json()
    assert data["scope"] == "market"
    assert {s["company_name"] for s in data["sources"]} == {"Globex Cloud", "Initech AI"}
    assert data["result"]["competitor_activity"]  # competitor items surfaced
    assert client.get("/analysis/market", headers=alice).json()[0]["id"] == data["id"]


def test_context_is_capped_and_deduplicated(client, alice, db, monkeypatch):
    company = client.post("/companies", json={"name": "Bigco"}, headers=alice).json()
    items = [raw(f"Bigco story{i}a story{i}b story{i}c", f"https://n.example.com/b{i}", i / 10) for i in range(60)]
    # same story reported by another outlet with slightly different wording -> near-duplicate
    items.append(raw("Bigco story1a story1b story1c reported", "https://n.example.com/dupe", 0.01))
    seed_items(db, company["id"], items)
    data = client.post(f"/analysis/company/{company['id']}", json={}, headers=alice).json()
    assert data["context_item_count"] == get_settings().llm_max_context_items
    titles = [s["title"] for s in data["sources"]]
    assert len(titles) == len(set(titles))


def test_reworded_duplicate_headlines_are_sent_once(client, alice, db):
    amd = client.post("/companies", json={"name": "AMD"}, headers=alice).json()
    other = client.post("/companies", json={"name": "Initech"}, headers=alice).json()
    seed_items(db, amd["id"], [
        raw("AMD acquires World Labs", "https://n.example.com/w1", 1),
        raw("AMD acquires World Labs AI startup, upping the ante against Nvidia", "https://n.example.com/w2", 1.1),
        raw("AMD to Acquire World Labs to Advance the Future of AI", "https://n.example.com/w3", 1.2),
        raw("AMD acquiring Fei-Fei Li's World Labs AI firm in deal worth $8.2B", "https://n.example.com/w5", 1.3),
        raw("AMD raises Series C funding", "https://n.example.com/a4", 2),
        raw("AMD ships new EPYC server chips", "https://n.example.com/w4", 3),
    ])
    seed_items(db, other["id"], [raw("Initech raises Series C funding", "https://n.example.com/i1", 2)])
    data = client.post("/analysis/market", json={}, headers=alice).json()
    titles = [s["title"] for s in data["sources"]]
    assert sum("World Labs" in t for t in titles) == 1
    assert "AMD ships new EPYC server chips" in titles
    # different companies with similar wording are different events
    assert "AMD raises Series C funding" in titles and "Initech raises Series C funding" in titles


def test_parse_and_validate_handles_code_fences():
    result, dropped = parse_and_validate("```json\n" + GOOD + "\n```", {1, 2, 3})
    assert dropped == 2
    assert result.risks[0].sources == [2]
