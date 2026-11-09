import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.triage import validate


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


client = TestClient(app)


def create(message="I ordered vegan but there is cheese in it and I am allergic"):
    response = client.post("/tickets", json={"customer_message": message, "order_id": "ORD-1042"})
    assert response.status_code == 201
    return response.json()


def test_allergy_issue_is_high_urgency_and_escalated():
    ticket = create()
    assert ticket["urgency"] == "high"
    assert ticket["category"] == "allergy_safety"
    assert ticket["needs_human"] is True


def test_order_that_never_arrived_is_escalated():
    ticket = create("My order never arrived, it has been over an hour")
    assert ticket["category"] == "not_delivered"
    assert ticket["needs_human"] is True


def test_missing_item_is_medium_and_not_escalated():
    ticket = create("The fries were missing from my bag")
    assert ticket["category"] == "missing_or_wrong_item"
    assert ticket["urgency"] == "medium"
    assert ticket["needs_human"] is False


def test_history_records_every_change_in_order():
    ticket = create("What time do you open on Sunday?")
    client.post(f"/tickets/{ticket['id']}/status", json={"status": "in_progress"})
    client.post(f"/tickets/{ticket['id']}/status", json={"status": "resolved"})
    types = [e["type"] for e in client.get(f"/tickets/{ticket['id']}/history").json()]
    assert types == ["TicketCreated", "TicketTriaged", "StatusChanged", "StatusChanged"]
    assert client.get(f"/tickets/{ticket['id']}").json()["status"] == "resolved"


def test_same_status_twice_adds_no_event():
    ticket = create("What time do you open on Sunday?")
    client.post(f"/tickets/{ticket['id']}/status", json={"status": "in_progress"})
    client.post(f"/tickets/{ticket['id']}/status", json={"status": "in_progress"})
    assert len(client.get(f"/tickets/{ticket['id']}/history").json()) == 3


def test_invalid_status_is_rejected():
    ticket = create()
    response = client.post(f"/tickets/{ticket['id']}/status", json={"status": "done"})
    assert response.status_code == 422


def test_unknown_ticket_returns_404():
    assert client.get("/tickets/does-not-exist").status_code == 404


def test_filter_by_status():
    a = create("What time do you open on Sunday?")
    create("Do you have a kids menu?")
    client.post(f"/tickets/{a['id']}/status", json={"status": "resolved"})
    assert len(client.get("/tickets?status=open").json()) == 1


def test_llm_output_is_validated_before_use():
    assert validate('{"urgency": "high", "category": "payment"}')["source"] == "llm"
    assert validate('{"urgency": "critical", "category": "payment"}') is None  # not an allowed value
    assert validate("Sure! Here is the JSON you asked for") is None  # not JSON

def test_someone_elses_order_is_wrong_item():
    ticket = create("I got someone else's order")
    assert ticket["category"] == "missing_or_wrong_item"
    assert ticket["urgency"] == "medium"