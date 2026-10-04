from tests.helpers import raw, seed_items


def test_create_list_get_delete_company(client, alice, db):
    resp = client.post(
        "/companies",
        json={"name": "  Acme   Robotics ", "description": "Robots", "website": "https://acme.example.com", "relation": "competitor", "ticker": "acme"},
        headers=alice,
    )
    assert resp.status_code == 201, resp.text
    company = resp.json()
    assert company["name"] == "Acme Robotics"
    assert company["ticker"] == "ACME"
    assert company["relation"] == "competitor"

    seed_items(db, company["id"], [raw("Acme Robotics launches new arm", "https://news.example.com/a1")])

    listed = client.get("/companies", headers=alice).json()
    assert [c["name"] for c in listed] == ["Acme Robotics"]
    assert listed[0]["item_count"] == 1

    detail = client.get(f"/companies/{company['id']}", headers=alice).json()
    assert detail["company"]["description"] == "Robots"
    assert detail["stats"]["total_items"] == 1
    assert len(detail["timeline"]) == 30
    assert detail["recent_items"][0]["title"] == "Acme Robotics launches new arm"
    assert "Product & Launches" in detail["recent_items"][0]["categories"]

    assert client.delete(f"/companies/{company['id']}", headers=alice).status_code == 204
    assert client.get(f"/companies/{company['id']}", headers=alice).status_code == 404
    assert client.get("/items", headers=alice).json()["total"] == 0  # items cascade-deleted


def test_duplicate_company_name_is_rejected(client, alice):
    assert client.post("/companies", json={"name": "Globex"}, headers=alice).status_code == 201
    resp = client.post("/companies", json={"name": "globex"}, headers=alice)
    assert resp.status_code == 409


def test_same_company_name_allowed_for_different_users(client, alice, bob):
    assert client.post("/companies", json={"name": "Globex"}, headers=alice).status_code == 201
    assert client.post("/companies", json={"name": "Globex"}, headers=bob).status_code == 201


def test_company_validation(client, alice):
    assert client.post("/companies", json={"name": "   "}, headers=alice).status_code == 422
    assert client.post("/companies", json={"name": "X", "website": "not a url"}, headers=alice).status_code == 422
    assert client.post("/companies", json={"name": "X", "relation": "partner"}, headers=alice).status_code == 422
    assert client.post("/companies", json={"name": "X" * 121}, headers=alice).status_code == 422
    assert client.post("/companies", json={"name": "X", "ticker": "DROP TABLE;"}, headers=alice).status_code == 422


def test_unknown_company_returns_404(client, alice):
    assert client.get("/companies/9999", headers=alice).status_code == 404
    assert client.delete("/companies/9999", headers=alice).status_code == 404
