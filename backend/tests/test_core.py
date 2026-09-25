"""Core guarantees of the prototype. Run from backend/:  .venv/Scripts/python -m pytest -q  (needs a seeded DB)."""
from fastapi.testclient import TestClient

from app import agent
from app.main import app


def _client():
    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    return c


def test_hero_shipment_story():
    with TestClient(app):
        a = _client().get("/api/shipments/Q4821").json()["analysis"]
    assert abs(a["declared_remaining_days"] - 6.2) < 0.05
    assert 1.8 < a["estimated_remaining_days"] < 2.9
    assert a["estimated_remaining_days"] <= a["declared_remaining_days"]  # never extends the declared life
    assert a["classification"] == "MID" and a["risk_level"] == "HIGH"
    assert a["compliance"]["status"] == "CONDITIONAL"
    rec = a["recommendation"]
    assert rec["optimized"]["expected_waste_pct"] < rec["current_route"]["expected_waste_pct"]
    # waterfall reconciles with the total loss
    assert abs(sum(f["days"] for f in a["explanation"]["factors"]) - a["loss_days"]) < 0.02


def test_hold_blocks_redistribution():
    with TestClient(app):
        c = _client()
        held = c.get("/api/shipments?classification=HOLD&limit=1").json()["items"][0]
        opts = c.post(f"/api/shipments/{held['shipment_id']}/simulate", json={}).json()["options"]
    assert all(not o["available"] for o in opts if o["key"] != "hold")


def test_rbac_and_auth():
    with TestClient(app) as c:
        assert c.get("/api/dashboard").status_code == 401
        tok = c.post("/api/auth/login", json={"username": "retailer", "password": "retailer123"}).json()["token"]
        r = c.post("/api/shipments/Q4821/optimize", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403
        assert c.post("/api/sensors/ingest", json={"device_id": "X", "shipment_id": "Q4821",
                                                   "readings": [{"ts": "2026-09-25T14:00:00"}]}).status_code == 401


def test_agent_guardrails():
    assert agent.BANNED.search("This lot is still safe to eat")
    assert agent.BANNED.search("we can extend the expiry by two days")
    assert not agent.BANNED.search("Eligible for food-rescue review")
    assert agent._numbers_grounded("waste falls to 9.7% from 36.8%", '{"a": 9.7, "b": 36.8}') == []
    assert agent._numbers_grounded("waste falls to 4.2%", '{"a": 9.7}') == ["4.2"]
