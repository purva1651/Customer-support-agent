import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import ValidationError

from app.config import AppConfig, load_config
from app.llm.factory import create_chat_model

ROOT = Path(__file__).resolve().parents[2]


def test_environment_overrides_yaml_and_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_MODEL=from-file\nXAI_API_KEY=file-key\n", encoding="utf-8")

    config = load_config(
        ROOT / "config/agent.yaml",
        env_file,
        {"LLM_PROVIDER": "openai", "LLM_MODEL": "from-process", "OPENAI_API_KEY": "env-key"},
    )

    assert config.llm.provider == "openai"
    assert config.llm.model == "from-process"
    assert config.secrets.openai_api_key == "env-key"
    assert config.secrets.xai_api_key == "file-key"
    assert config.crm.url == "http://localhost:9000"


def test_config_rejects_unknown_provider(tmp_path: Path) -> None:
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(
        "llm: {provider: unknown, model: x}\n"
        "agent: {}\nretrieval: {}\napi: {}\ncrm: {}\nobservability: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_config(yaml_path, tmp_path / "missing.env", {})


def test_llm_factory_requires_explicit_model_id() -> None:
    config = AppConfig.model_validate(
        {
            "llm": {"provider": "xai", "model": ""},
            "agent": {},
            "retrieval": {},
            "api": {},
            "crm": {},
            "observability": {},
        }
    )
    with pytest.raises(ValueError, match="LLM_MODEL"):
        create_chat_model(config)


def test_llm_factory_requires_provider_key() -> None:
    config = AppConfig.model_validate(
        {
            "llm": {"provider": "xai", "model": "configured-model"},
            "agent": {},
            "retrieval": {},
            "api": {},
            "crm": {},
            "observability": {},
        }
    )
    with pytest.raises(ValueError, match="XAI_API_KEY"):
        create_chat_model(config)


@pytest.mark.parametrize(
    ("provider", "dependency", "class_name", "credentials"),
    [
        ("xai", "langchain_openai", "ChatOpenAI", {"xai_api_key": "xai-key"}),
        ("openai", "langchain_openai", "ChatOpenAI", {"openai_api_key": "openai-key"}),
        (
            "anthropic",
            "langchain_anthropic",
            "ChatAnthropic",
            {"anthropic_api_key": "anthropic-key"},
        ),
        ("ollama", "langchain_ollama", "ChatOllama", {}),
    ],
)
def test_llm_factory_selects_configured_provider(
    provider: str,
    dependency: str,
    class_name: str,
    credentials: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    module = ModuleType(dependency)

    def fake_model(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    setattr(module, class_name, fake_model)
    monkeypatch.setitem(sys.modules, dependency, module)
    settings = {
        "llm": {"provider": provider, "model": "chosen-id", "temperature": 0.2},
        "agent": {},
        "retrieval": {},
        "api": {},
        "crm": {},
        "observability": {},
        "secrets": {**credentials, "xai_base_url": "https://api.x.ai/v1"},
    }
    model = create_chat_model(AppConfig.model_validate(settings))

    assert model is not None
    assert captured["model"] == "chosen-id"
    assert captured["temperature"] == 0.2
    if provider == "xai":
        assert captured["base_url"] == "https://api.x.ai/v1"
        assert captured["api_key"] == "xai-key"
