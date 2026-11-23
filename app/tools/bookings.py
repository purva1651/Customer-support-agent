import httpx
from langchain_core.tools import BaseTool, tool

from app.tools._client import crm_request


def booking_status_tool(customer_id: str, client: httpx.Client) -> BaseTool:
    @tool("get_booking_status")
    def get_booking_status(booking_id: str) -> dict[str, object]:
        """Get the status and details of a booking owned by the current customer."""
        return crm_request(client, "GET", f"/bookings/{booking_id}", customer_id)

    return get_booking_status


def cancel_booking_tool(customer_id: str, client: httpx.Client) -> BaseTool:
    @tool("cancel_booking")
    def cancel_booking(booking_id: str) -> dict[str, object]:
        """Cancel a booking after customer approval; returns the fee and refund amount."""
        return crm_request(client, "POST", f"/bookings/{booking_id}/cancel", customer_id)

    return cancel_booking
