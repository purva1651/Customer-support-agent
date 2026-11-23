import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastapi import Request

from app.agent.approvals import ApprovalStore
from app.agent.nodes import AgentServices
from app.agent.runtime import AgentRuntime, create_runtime
from app.api.analytics import AnalyticsStore
from app.config import AppConfig, load_runtime_files
from app.ingestion.chunker import KnowledgeChunker
from app.ingestion.indexer import KnowledgeIndexer
from app.llm.factory import create_chat_model
from app.retrieval.hybrid_search import HybridSearch
from app.retrieval.keyword_search import KeywordSearch
from app.retrieval.reranker import BGEReranker
from app.retrieval.vector_store import create_vector_store
from app.tools.bookings import booking_status_tool, cancel_booking_tool
from app.tools.contacts import update_contact_tool
from app.tools.tickets import create_ticket_tool


@dataclass
class AppServices:
    config: AppConfig
    runtime: AgentRuntime
    indexer: KnowledgeIndexer
    analytics: AnalyticsStore
    knowledge_dir: Path
    crm_client: httpx.Client

    async def close(self) -> None:
        await self.runtime.close()
        self.crm_client.close()


async def create_services(config_directory: Path = Path("config")) -> AppServices:
    runtime_files = load_runtime_files(config_directory)
    config = runtime_files.config
    knowledge_dir = config.retrieval.knowledge_dir
    chat_model = create_chat_model(config)
    crm_client = httpx.Client(
        base_url=config.crm.url,
        timeout=config.agent.request_timeout_seconds,
    )
    vector_store = await asyncio.to_thread(
        create_vector_store,
        config.retrieval.persist_dir,
        config.retrieval.embedding_model,
    )
    keyword_search = KeywordSearch()
    chunker = KnowledgeChunker(
        chunk_size=config.retrieval.chunk_size,
        chunk_overlap=config.retrieval.chunk_overlap,
    )
    indexer = KnowledgeIndexer(knowledge_dir, vector_store, keyword_search, chunker)
    await asyncio.to_thread(indexer.sync)
    retriever = HybridSearch(
        keyword_search,
        vector_store,
        await asyncio.to_thread(BGEReranker, config.retrieval.reranker_model),
        candidate_count=config.retrieval.candidate_count,
        result_count=config.retrieval.result_count,
        rrf_k=config.retrieval.rrf_k,
        sync_callback=indexer.sync,
    )

    def tools_for_customer(customer_id: str) -> dict[str, Any]:
        return {
            "get_booking_status": booking_status_tool(customer_id, crm_client),
            "cancel_booking": cancel_booking_tool(customer_id, crm_client),
            "create_ticket": create_ticket_tool(customer_id, crm_client),
            "update_contact": update_contact_tool(customer_id, crm_client),
        }

    agent_services = AgentServices(
        llm=chat_model,
        config=config,
        prompts=runtime_files.prompts,
        intents=runtime_files.intents,
        tool_settings=runtime_files.tool_settings,
        tools_for_customer=tools_for_customer,
        retriever=retriever,
        approval_store=ApprovalStore(
            config.agent.memory_path.with_name("approvals.sqlite3"),
            ttl_seconds=config.agent.approval_ttl_seconds,
        ),
    )
    runtime = await create_runtime(agent_services, config)
    analytics = AnalyticsStore(config.agent.memory_path.with_name("analytics.sqlite3"))
    return AppServices(config, runtime, indexer, analytics, knowledge_dir, crm_client)


def get_services(request: Request) -> AppServices:
    return request.app.state.services
