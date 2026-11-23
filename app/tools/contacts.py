import httpx
from langchain_core.tools import BaseTool, tool

from app.tools._client import crm_request


def update_contact_tool(customer_id: str, client: httpx.Client) -> BaseTool:
    @tool("update_contact")
    def update_contact(email: str | None = None, phone: str | None = None) -> dict[str, object]:
        """Update one or both contact details for the current customer."""
        return crm_request(
            client,
            "PATCH",
            f"/customers/{customer_id}/contact",
            customer_id,
            json={"email": email, "phone": phone},
        )

    return update_contact
