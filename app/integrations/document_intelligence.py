import asyncio
import base64
import json
import logging
from datetime import timedelta
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.config import DocumentIntelligenceConfig

logger = logging.getLogger(__name__)


class DocumentIntelligenceDisabled(RuntimeError):
    """Raised when the optional Document Intelligence MCP service is not configured."""


class DocumentIntelligenceError(RuntimeError):
    """Raised when the configured Document Intelligence MCP service cannot extract fields."""


class DocumentIntelligenceClient:
    def __init__(
        self,
        config: DocumentIntelligenceConfig,
        api_key: str | None = None,
    ) -> None:
        self._config = config
        self._api_key = api_key

    @property
    def enabled(self) -> bool:
        return self._config.enabled and bool(self._config.url)

    async def extract_fields(
        self,
        filename: str,
        content: bytes,
        document_type: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled or self._config.url is None:
            raise DocumentIntelligenceDisabled

        arguments = {
            self._config.file_argument: base64.b64encode(content).decode("ascii"),
            self._config.filename_argument: filename,
        }
        if document_type and self._config.document_type_argument:
            arguments[self._config.document_type_argument] = document_type

        headers: dict[str, str] = {}
        if self._api_key:
            headers[self._config.api_key_header] = (
                f"{self._config.api_key_prefix}{self._api_key}"
            )

        try:
            return await asyncio.wait_for(
                self._call_tool(arguments, headers),
                timeout=self._config.timeout_seconds,
            )
        except DocumentIntelligenceError:
            logger.exception("Document Intelligence MCP tool returned an error")
            raise
        except Exception as exc:
            logger.exception("Document Intelligence MCP request failed")
            raise DocumentIntelligenceError(
                "The Document Intelligence MCP service could not complete the request"
            ) from exc

    async def _call_tool(
        self,
        arguments: dict[str, str],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        assert self._config.url is not None
        timeout = self._config.timeout_seconds
        async with httpx.AsyncClient(headers=headers, timeout=timeout) as http_client:
            async with streamable_http_client(
                self._config.url,
                http_client=http_client,
            ) as (read_stream, write_stream, _get_session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        self._config.tool_name,
                        arguments,
                        read_timeout_seconds=timedelta(seconds=timeout),
                    )

        if result.isError:
            raise DocumentIntelligenceError("The remote extraction tool returned an error")
        if result.structuredContent is not None:
            return result.structuredContent

        text_parts = [item.text for item in result.content if getattr(item, "type", None) == "text"]
        if text_parts:
            try:
                parsed = json.loads("\n".join(text_parts))
            except json.JSONDecodeError as exc:
                raise DocumentIntelligenceError(
                    "The remote extraction tool did not return structured fields"
                ) from exc
            if isinstance(parsed, dict):
                return parsed

        raise DocumentIntelligenceError("The remote extraction tool returned no structured fields")
