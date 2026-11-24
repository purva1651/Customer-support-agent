import logging
from functools import lru_cache
from typing import Any

from app.config import AppConfig

logger = logging.getLogger(__name__)


def create_run_config(
    config: AppConfig,
    customer_id: str,
    session_id: str,
) -> dict[str, Any]:
    run_config: dict[str, Any] = {
        "configurable": {"thread_id": session_id},
        "metadata": {
            "langfuse_user_id": customer_id,
            "langfuse_session_id": session_id,
            "langfuse_tags": ["ticket-support-agent"],
        },
    }
    if not _has_credentials(config):
        return run_config

    try:
        _get_langfuse_client(
            config.secrets.langfuse_public_key or "",
            config.secrets.langfuse_secret_key or "",
            config.secrets.langfuse_host,
        )
        from langfuse.langchain import CallbackHandler

        run_config["callbacks"] = [CallbackHandler()]
    except Exception:
        logger.exception("Langfuse tracing could not be initialized; continuing without tracing")
    return run_config


def flush_traces(config: AppConfig) -> None:
    if not _has_credentials(config):
        return
    try:
        client = _get_langfuse_client(
            config.secrets.langfuse_public_key or "",
            config.secrets.langfuse_secret_key or "",
            config.secrets.langfuse_host,
        )
        client.flush()
    except Exception:
        logger.exception("Langfuse traces could not be flushed")


def _has_credentials(config: AppConfig) -> bool:
    return (
        config.observability.langfuse_enabled
        and bool(config.secrets.langfuse_public_key)
        and bool(config.secrets.langfuse_secret_key)
    )


@lru_cache(maxsize=4)
def _get_langfuse_client(public_key: str, secret_key: str, host: str) -> Any:
    from langfuse import Langfuse, get_client

    Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    return get_client()
