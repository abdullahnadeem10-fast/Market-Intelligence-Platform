from tests.helpers import raw, seed_items


def _seed(client, alice, db):
    acme = client.post("/companies", json={"name": "Acme", "relation": "own"}, headers=alice).json()
    globex = client.post("/companies", json={"name": "Globex", "relation": "competitor"}, headers=alice).json()
    seed_items(db, acme["id"], [
        raw("Acme raises Series B funding", "https://n.example.com/1", 1),
        raw("Acme launches robot arm", "https://n.example.com/2", 10),
        raw("Acme and Globex partner on robotics", "https://n.example.com/3", 40),
    ])
    seed_items(db, globex["id"], [
        raw("Globex outage hits customers", "https://n.example.com/4", 2),
        raw("Globex cloud outage postmortem", "https://n.example.com/5", 3),
    ])
    return acme, globex


def test_search_filters(client, alice, db):
    acme, globex = _seed(client, alice, db)
    assert client.get("/items", headers=alice).json()["total"] == 5
    assert client.get(f"/items?company_id={globex['id']}", headers=alice).json()["total"] == 2
    assert client.get("/items?q=outage", headers=alice).json()["total"] == 2
    assert client.get("/items?q=robot arm", headers=alice).json()["total"] == 1  # all words must match
    assert client.get("/items?category=funding", headers=alice).json()["total"] == 1
    assert client.get("/items?category=security", headers=alice).json()["total"] == 2
    assert client.get("/items?q=100%25", headers=alice).json()["total"] == 0  # LIKE wildcard escaped

    from datetime import date, timedelta

    d = (date.today() - timedelta(days=5)).isoformat()
    assert client.get(f"/items?date_from={d}", headers=alice).json()["total"] == 3
    assert client.get(f"/items?date_to={d}", headers=alice).json()["total"] == 2
    bad = client.get(f"/items?date_from={date.today()}&date_to={d}", headers=alice)
    assert bad.status_code == 422

    page = client.get("/items?page=2&page_size=2&sort=oldest", headers=alice).json()
    assert page["page"] == 2 and len(page["items"]) == 2
    assert client.get("/items?page_size=1000", headers=alice).status_code == 422


def test_dashboard_analytics(client, alice, db):
    _seed(client, alice, db)
    dash = client.get("/analytics/dashboard?days=30", headers=alice).json()
    assert dash["overview"]["tracked_companies"] == 2
    assert dash["overview"]["total_items"] == 5
    assert dash["overview"]["items_last_7d"] == 3
    assert len(dash["activity"]) == 30
    assert sum(p["count"] for p in dash["activity"]) == 4  # one item is 40 days old
    assert {r["company"]: r["count"] for r in dash["by_company"]} == {"Acme": 2, "Globex": 2}
    assert any(c["category"] == "Security & Incidents" and c["count"] == 2 for c in dash["by_category"])
    mentions = {m["company"]: m["mentions"] for m in dash["mentions"]}
    assert mentions["Globex"] == 2
    assert any(t["term"] == "outage" for t in dash["trends"])
    assert [c["company"] for c in dash["competitors"]] == ["Globex", "Globex"]
    assert len(dash["recent_items"]) == 5


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": True}
