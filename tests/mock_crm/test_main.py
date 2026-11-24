from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mock_crm.main import app


@pytest.fixture
def crm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CRM_DB_PATH", str(tmp_path / "crm.sqlite3"))
    with TestClient(app) as client:
        yield client


def test_health_and_seeded_booking(crm: TestClient) -> None:
    assert crm.get("/health").json() == {"status": "ok"}
    booking = crm.get("/bookings/B001", params={"customer_id": "C001"})
    assert booking.status_code == 200
    assert booking.json()["route"] == "Ahmedabad to Mumbai"


def test_cross_customer_booking_is_same_404_as_missing(crm: TestClient) -> None:
    unauthorized = crm.get("/bookings/B001", params={"customer_id": "C002"})
    missing = crm.get("/bookings/DOES-NOT-EXIST", params={"customer_id": "C002"})
    assert unauthorized.status_code == missing.status_code == 404
    assert unauthorized.json() == missing.json() == {"detail": "Booking not found"}


def test_cross_customer_cancellation_is_same_404_as_missing(crm: TestClient) -> None:
    unauthorized = crm.post("/bookings/B001/cancel", params={"customer_id": "C002"})
    missing = crm.post("/bookings/DOES-NOT-EXIST/cancel", params={"customer_id": "C002"})

    assert unauthorized.status_code == missing.status_code == 404
    assert unauthorized.json() == missing.json() == {"detail": "Booking not found"}
    assert crm.get("/bookings/B001", params={"customer_id": "C001"}).json()["status"] == "confirmed"


def test_cancellation_fee_and_repeat_conflict(crm: TestClient) -> None:
    cancelled = crm.post("/bookings/B001/cancel", params={"customer_id": "C001"})
    assert cancelled.status_code == 200
    assert cancelled.json()["fee"] == 120.0
    assert cancelled.json()["refund_amount"] == 1080.0
    repeated = crm.post("/bookings/B001/cancel", params={"customer_id": "C001"})
    assert repeated.status_code == 409


def test_ticket_validation_and_creation(crm: TestClient) -> None:
    blank = crm.post("/tickets", json={"customer_id": "C001", "subject": "  ", "details": "x"})
    assert blank.status_code == 422

    unknown = crm.post(
        "/tickets", json={"customer_id": "C999", "subject": "Help", "details": "Details"}
    )
    assert unknown.status_code == 404

    created = crm.post(
        "/tickets", json={"customer_id": "C001", "subject": "Help", "details": "Details"}
    )
    assert created.status_code == 201
    assert created.json()["ticket_id"] == "T-1001"


def test_contact_update_validation(crm: TestClient) -> None:
    empty = crm.patch("/customers/C001/contact", json={})
    assert empty.status_code == 422
    invalid = crm.patch("/customers/C001/contact", json={"email": "invalid"})
    assert invalid.status_code == 422
    updated = crm.patch("/customers/C001/contact", json={"email": "new@example.com"})
    assert updated.status_code == 200
    assert updated.json()["email"] == "new@example.com"
