import sys
from types import ModuleType

from app.config import load_runtime_files
from app.observability import tracing


def test_trace_metadata_always_includes_customer_and_session() -> None:
    config = load_runtime_files().config

    run_config = tracing.create_run_config(config, "C001", "session-1")

    assert run_config["configurable"] == {"thread_id": "session-1"}
    assert run_config["metadata"]["langfuse_user_id"] == "C001"
    assert run_config["metadata"]["langfuse_session_id"] == "session-1"
    assert "callbacks" not in run_config


def test_trace_callback_is_added_when_langfuse_is_configured(monkeypatch) -> None:
    class FakeCallbackHandler:
        pass

    langfuse_package = ModuleType("langfuse")
    langfuse_package.__path__ = []  # type: ignore[attr-defined]
    langchain_module = ModuleType("langfuse.langchain")
    langchain_module.CallbackHandler = FakeCallbackHandler  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", langfuse_package)
    monkeypatch.setitem(sys.modules, "langfuse.langchain", langchain_module)
    monkeypatch.setattr(tracing, "_get_langfuse_client", lambda *_: object())
    config = load_runtime_files().config.model_copy(
        update={
            "secrets": load_runtime_files().config.secrets.model_copy(
                update={
                    "langfuse_public_key": "pk-test",
                    "langfuse_secret_key": "sk-test",
                }
            )
        }
    )

    run_config = tracing.create_run_config(config, "C002", "session-2")

    assert isinstance(run_config["callbacks"][0], FakeCallbackHandler)


def test_flush_is_a_noop_when_tracing_is_not_configured() -> None:
    tracing.flush_traces(load_runtime_files().config)
