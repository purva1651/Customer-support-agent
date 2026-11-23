from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from mock_crm import db
from mock_crm.schemas import (
    BookingResponse,
    CancellationResponse,
    ContactUpdate,
    CustomerContactResponse,
    TicketCreate,
    TicketResponse,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    db.initialize_database()
    yield


app = FastAPI(title="Mock Booking CRM", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/bookings/{booking_id}", response_model=BookingResponse)
def get_booking(booking_id: str, customer_id: str = Query(min_length=1)) -> dict[str, object]:
    booking = db.fetch_booking(booking_id, customer_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


@app.post("/bookings/{booking_id}/cancel", response_model=CancellationResponse)
def post_cancel_booking(
    booking_id: str, customer_id: str = Query(min_length=1)
) -> dict[str, object]:
    try:
        result = db.cancel_booking(booking_id, customer_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return result


@app.post("/tickets", response_model=TicketResponse, status_code=201)
def post_ticket(ticket: TicketCreate) -> dict[str, object]:
    if not db.customer_exists(ticket.customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    return db.create_ticket(ticket.customer_id, ticket.subject, ticket.details)


@app.patch("/customers/{customer_id}/contact", response_model=CustomerContactResponse)
def patch_contact(customer_id: str, update: ContactUpdate) -> dict[str, object]:
    customer = db.update_contact(customer_id, update.model_dump(exclude_unset=True))
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer
