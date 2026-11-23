import httpx

from app.tools.bookings import booking_status_tool, cancel_booking_tool
from app.tools.contacts import update_contact_tool
from app.tools.tickets import create_ticket_tool


def test_customer_bound_tools_hide_customer_id_and_forward_it() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/bookings/B001":
            return httpx.Response(200, json={"id": "B001", "customer_id": "C001"})
        if request.url.path == "/bookings/B002/cancel":
            return httpx.Response(200, json={"fee": 10, "refund_amount": 90})
        if request.url.path == "/tickets":
            return httpx.Response(201, json={"ticket_id": "T-1001"})
        return httpx.Response(200, json={"id": "C001", "email": "new@example.com"})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://crm") as client:
        tools = [
            booking_status_tool("C001", client),
            cancel_booking_tool("C001", client),
            create_ticket_tool("C001", client),
            update_contact_tool("C001", client),
        ]
        assert [item.name for item in tools] == [
            "get_booking_status",
            "cancel_booking",
            "create_ticket",
            "update_contact",
        ]
        assert all("customer_id" not in item.args for item in tools)
        tools[0].invoke({"booking_id": "B001"})
        tools[1].invoke({"booking_id": "B002"})
        tools[2].invoke({"subject": "Help", "details": "Please help"})
        tools[3].invoke({"email": "new@example.com"})

    assert calls[0].url.params["customer_id"] == "C001"
    assert calls[1].url.params["customer_id"] == "C001"
    assert calls[2].read().decode() == (
        '{"customer_id":"C001","subject":"Help","details":"Please help"}'
    )
    assert calls[3].url.path == "/customers/C001/contact"
