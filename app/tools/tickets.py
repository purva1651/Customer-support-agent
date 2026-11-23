import httpx
from langchain_core.tools import BaseTool, tool

from app.tools._client import crm_request


def create_ticket_tool(customer_id: str, client: httpx.Client) -> BaseTool:
    @tool("create_ticket")
    def create_ticket(subject: str, details: str) -> dict[str, object]:
        """Create a support ticket for the current customer."""
        return crm_request(
            client,
            "POST",
            "/tickets",
            customer_id,
            json={"customer_id": customer_id, "subject": subject, "details": details},
        )

    return create_ticket
