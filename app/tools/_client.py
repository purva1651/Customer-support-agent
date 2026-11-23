from typing import Any

import httpx


def crm_request(
    client: httpx.Client,
    method: str,
    path: str,
    customer_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    response = client.request(
        method,
        path,
        params={"customer_id": customer_id}
        if method == "GET" or path.startswith("/bookings/")
        else None,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()
