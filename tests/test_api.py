from fastapi.testclient import TestClient

from rentinel.api import app


def test_check_endpoint(monkeypatch):
    monkeypatch.setenv("RENTINEL_DB_PATH", ":memory:")
    monkeypatch.delenv("RENTINEL_LLM_BASE_URL", raising=False)
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        r = client.post("/v1/check", json={
            "title": "2 bedroom downtown", "price": 1100, "bedrooms": 2, "cma": "Halifax",
            "description": "I'm overseas. Send the deposit to hold the unit and I will courier the keys.",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["label"] == "high"
        assert {s["agent"] for s in body["signals"]} >= {"firewall", "scam_patterns", "price"}
        assert body["data_as_of"]["rent_baseline"] == "illustrative sample"


def test_local_image_paths_are_ignored_from_api(monkeypatch):
    monkeypatch.setenv("RENTINEL_DB_PATH", ":memory:")
    with TestClient(app) as client:
        r = client.post("/v1/check", json={"title": "x", "image_paths": ["/etc/passwd"]})
        assert r.status_code == 200
        assert next(s for s in r.json()["signals"] if s["agent"] == "images")["confidence"] == 0.0
