import os
from typing import Any

import httpx


class APIError(RuntimeError):
    """An error returned by the support agent API."""


class SupportAPI:
    def __init__(
        self,
        base_url: str | None = None,
        admin_api_key: str | None = None,
        timeout_seconds: float = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("API_BASE_URL", "http://localhost:8000")).rstrip("/")
        self.admin_api_key = admin_api_key or os.getenv("ADMIN_API_KEY", "")
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout_seconds, transport=transport
        )

    def __enter__(self) -> "SupportAPI":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def chat(
        self,
        customer_id: str,
        session_id: str,
        message: str,
        language: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/chat",
            json={
                "customer_id": customer_id,
                "session_id": session_id,
                "message": message,
                "language": language,
            },
        )

    def approve(self, action_id: str, approved: bool) -> dict[str, Any]:
        return self._request(
            "POST", "/approve", json={"action_id": action_id, "approved": approved}
        )

    def knowledge(self) -> dict[str, Any]:
        return self._admin("GET", "/admin/knowledge")

    def upload_knowledge(self, filename: str, content: bytes) -> dict[str, Any]:
        return self._admin(
            "POST",
            "/admin/knowledge/upload",
            files={"file": (filename, content)},
        )

    def add_knowledge_url(self, url: str) -> dict[str, Any]:
        return self._admin("POST", "/admin/knowledge/url", json={"url": url})

    def reindex(self) -> dict[str, Any]:
        return self._admin("POST", "/admin/knowledge/reindex")

    def delete_knowledge(self, title: str) -> dict[str, Any]:
        return self._admin("DELETE", "/admin/knowledge", params={"title": title})

    def analytics(self) -> dict[str, Any]:
        return self._admin("GET", "/admin/analytics")

    def escalations(self) -> dict[str, Any]:
        return self._admin("GET", "/admin/escalations")

    def _admin(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.admin_api_key:
            raise APIError("Enter the admin API key to use admin endpoints.")
        headers = dict(kwargs.pop("headers", {}))
        headers["X-Admin-Key"] = self.admin_api_key
        return self._request(method, path, headers=headers, **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise APIError(f"Could not reach the support API at {self.base_url}: {exc}") from exc
        if response.is_error:
            try:
                payload = response.json()
                detail = (
                    payload.get("detail", response.text)
                    if isinstance(payload, dict)
                    else response.text
                )
            except ValueError:
                detail = response.text
            raise APIError(f"API request failed ({response.status_code}): {detail}")
        try:
            result = response.json()
        except ValueError as exc:
            raise APIError("The support API returned an invalid JSON response.") from exc
        if not isinstance(result, dict):
            raise APIError("The support API returned an unexpected response.")
        return result
