import httpx
from langchain_core.tools import BaseTool, tool

from app.tools._client import crm_request


def request_refund_tool(customer_id: str, client: httpx.Client) -> BaseTool:
    @tool("request_refund")
    def request_refund(booking_id: str, reason: str) -> dict[str, object]:
        """Submit a refund request for review; this does not issue or promise a refund."""
        return crm_request(
            client,
            "POST",
            f"/bookings/{booking_id}/refund-requests",
            customer_id,
            json={"reason": reason},
        )

    return request_refund
