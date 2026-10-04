"""User A must never be able to read or modify user B's data."""

from tests.helpers import raw, seed_items


def _setup(client, alice, db):
    company = client.post("/companies", json={"name": "Initech"}, headers=alice).json()
    seed_items(db, company["id"], [raw("Initech ships secret product", "https://news.example.com/initech-1")])
    analysis = client.post(f"/analysis/company/{company['id']}", json={}, headers=alice)
    assert analysis.status_code == 200, analysis.text
    item_id = client.get("/items", headers=alice).json()["items"][0]["id"]
    return company, item_id, analysis.json()["id"]


def test_user_cannot_access_other_users_company(client, alice, bob, db):
    company, _, _ = _setup(client, alice, db)
    cid = company["id"]
    assert client.get(f"/companies/{cid}", headers=bob).status_code == 404
    assert client.delete(f"/companies/{cid}", headers=bob).status_code == 404
    assert client.post(f"/analysis/company/{cid}", json={}, headers=bob).status_code == 404
    assert client.get(f"/analysis/company/{cid}", headers=bob).status_code == 404
    assert client.get("/companies", headers=bob).json() == []
    # still intact for the owner
    assert client.get(f"/companies/{cid}", headers=alice).status_code == 200


def test_user_cannot_access_other_users_items_and_analyses(client, alice, bob, db):
    company, item_id, analysis_id = _setup(client, alice, db)
    assert client.get(f"/items/{item_id}", headers=bob).status_code == 404
    assert client.get("/items", headers=bob).json()["total"] == 0
    assert client.get(f"/items?company_id={company['id']}", headers=bob).json()["total"] == 0
    assert client.get(f"/analysis/{analysis_id}", headers=bob).status_code == 404
    assert client.get("/analysis/market", headers=bob).json() == []
    usage = client.get("/usage/ai", headers=bob).json()
    assert usage["total_analyses"] == 0
    dash = client.get("/analytics/dashboard", headers=bob).json()
    assert dash["overview"]["total_items"] == 0
    assert dash["recent_items"] == []


def test_user_cannot_see_other_users_collection_runs(client, alice, bob, monkeypatch):
    from app.services import collection_service

    monkeypatch.setattr(collection_service, "build_collectors", lambda settings, client: [])
    run = client.post("/collection/run", headers=alice).json()
    assert client.get(f"/collection/runs/{run['id']}", headers=bob).status_code == 404
    assert client.get("/collection/runs", headers=bob).json() == []
    assert len(client.get("/collection/runs", headers=alice).json()) == 1
