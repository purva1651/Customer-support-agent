import asyncio
import base64
from typing import Any

import pytest

from app.config import DocumentIntelligenceConfig
from app.integrations.document_intelligence import (
    DocumentIntelligenceClient,
    DocumentIntelligenceDisabled,
)


def test_disabled_document_intelligence_client_rejects_extraction() -> None:
    client = DocumentIntelligenceClient(DocumentIntelligenceConfig())

    with pytest.raises(DocumentIntelligenceDisabled):
        asyncio.run(client.extract_fields("invoice.pdf", b"invoice"))


def test_document_intelligence_client_calls_configured_mcp_tool() -> None:
    config = DocumentIntelligenceConfig(
        enabled=True,
        url="http://document-agent:8001/mcp",
        file_argument="file_base64",
        filename_argument="filename",
        document_type_argument="document_type",
    )
    client = DocumentIntelligenceClient(config, api_key="doc-secret")
    captured: dict[str, Any] = {}

    async def fake_call_tool(
        arguments: dict[str, str], headers: dict[str, str]
    ) -> dict[str, Any]:
        captured["arguments"] = arguments
        captured["headers"] = headers
        return {"invoice_number": "INV-123"}

    client._call_tool = fake_call_tool  # type: ignore[method-assign]
    result = asyncio.run(
        client.extract_fields("invoice.pdf", b"invoice bytes", "invoice")
    )

    assert result == {"invoice_number": "INV-123"}
    assert captured["arguments"] == {
        "file_base64": base64.b64encode(b"invoice bytes").decode("ascii"),
        "filename": "invoice.pdf",
        "document_type": "invoice",
    }
    assert captured["headers"] == {"Authorization": "Bearer doc-secret"}


def test_document_intelligence_client_omits_optional_document_type() -> None:
    config = DocumentIntelligenceConfig(
        enabled=True,
        url="http://document-agent:8001/mcp",
        document_type_argument=None,
    )
    client = DocumentIntelligenceClient(config)
    captured: dict[str, Any] = {}

    async def fake_call_tool(
        arguments: dict[str, str], headers: dict[str, str]
    ) -> dict[str, Any]:
        captured.update(arguments)
        return {"document_type": "invoice"}

    client._call_tool = fake_call_tool  # type: ignore[method-assign]
    asyncio.run(client.extract_fields("invoice.pdf", b"invoice bytes"))

    assert "document_type" not in captured
