import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LLMConfig(StrictConfig):
    provider: Literal["xai", "anthropic", "openai", "ollama"] = "xai"
    model: str = ""
    temperature: float = Field(default=0, ge=0, le=2)
    timeout_seconds: float = Field(default=30, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)


class AgentConfig(StrictConfig):
    max_steps: int = Field(default=8, ge=1, le=100)
    request_timeout_seconds: float = Field(default=45, gt=0)
    tool_retries: int = Field(default=2, ge=0, le=10)
    sentiment_escalation_threshold: float = Field(default=0.75, ge=0, le=1)
    memory_path: Path = Path("data/checkpoints.sqlite")
    approval_ttl_seconds: int = Field(default=600, gt=0)


class GuardrailsConfig(StrictConfig):
    max_message_chars: int = Field(default=2000, ge=1, le=2000)
    injection_patterns: list[str] = Field(default_factory=list)

    @field_validator("injection_patterns")
    @classmethod
    def patterns_must_compile(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid prompt-injection pattern: {pattern}") from exc
        return patterns


class AdminConfig(StrictConfig):
    max_upload_bytes: int = Field(default=10_485_760, gt=0)
    analytics_unresolved_limit: int = Field(default=50, gt=0)
    analytics_top_questions_limit: int = Field(default=10, gt=0)
    escalation_list_limit: int = Field(default=100, gt=0)


class RetrievalConfig(StrictConfig):
    knowledge_dir: Path = Path("knowledge_base")
    persist_dir: Path = Path("data/chroma")
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    chunk_size: int = Field(default=400, gt=0)
    chunk_overlap: int = Field(default=60, ge=0)
    candidate_count: int = Field(default=8, gt=0)
    result_count: int = Field(default=3, gt=0)
    rrf_k: int = Field(default=60, gt=0)
    min_score: float = Field(default=0.25, ge=0)


class APIConfig(StrictConfig):
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)


class MCPConfig(StrictConfig):
    host: str = "0.0.0.0"
    port: int = Field(default=8001, ge=1, le=65535)
    path: str = "/mcp"
    api_key_header: str = "X-API-Key"
    customer_id_header: str = "X-Customer-ID"
    session_id_header: str = "X-Session-ID"


class CRMConfig(StrictConfig):
    url: str = "http://localhost:9000"


class ObservabilityConfig(StrictConfig):
    langfuse_enabled: bool = True


class TranslationConfig(StrictConfig):
    enabled: bool = False
    model: str = "ai4bharat/indictrans2-en-indic-dist-200M"
    device: Literal["auto", "cpu", "cuda"] = "auto"


class SecretsConfig(StrictConfig):
    xai_api_key: str | None = None
    xai_base_url: str = "https://api.x.ai/v1"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    admin_api_key: str | None = None
    mcp_api_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    hf_token: str | None = None


class PromptTemplates(StrictConfig):
    router_system: str
    answer_system: str
    action_system: str
    small_talk_system: str
    escalation_system: str


class IntentDescriptions(StrictConfig):
    intents: dict[Literal["question", "action", "complaint", "small_talk"], str]


class ToolSetting(StrictConfig):
    enabled: bool = True
    requires_approval: bool = False
    timeout_seconds: float = Field(default=10, gt=0)
    retries: int = Field(default=2, ge=0, le=10)


class ToolSettings(StrictConfig):
    tools: dict[str, ToolSetting]


@dataclass(frozen=True)
class RuntimeFiles:
    config: "AppConfig"
    prompts: PromptTemplates
    intents: IntentDescriptions
    tool_settings: ToolSettings


class AppConfig(StrictConfig):
    llm: LLMConfig
    agent: AgentConfig
    retrieval: RetrievalConfig
    api: APIConfig
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    crm: CRMConfig
    observability: ObservabilityConfig
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    guardrails: GuardrailsConfig = Field(default_factory=GuardrailsConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)


def _read_yaml(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)
    if not isinstance(raw, dict):
        raise ValueError(f"Configuration file must contain a YAML mapping: {path}")
    return raw


def _overlay_environment(
    data: dict[str, object], environment: Mapping[str, str | None]
) -> None:
    llm = data.setdefault("llm", {})
    crm = data.setdefault("crm", {})
    secrets = data.setdefault("secrets", {})
    if not all(isinstance(section, dict) for section in (llm, crm, secrets)):
        raise ValueError("llm, crm, and secrets settings must be YAML mappings")

    overrides = {
        "LLM_PROVIDER": (llm, "provider"),
        "LLM_MODEL": (llm, "model"),
        "CRM_URL": (crm, "url"),
        "XAI_API_KEY": (secrets, "xai_api_key"),
        "XAI_BASE_URL": (secrets, "xai_base_url"),
        "ANTHROPIC_API_KEY": (secrets, "anthropic_api_key"),
        "OPENAI_API_KEY": (secrets, "openai_api_key"),
        "OLLAMA_BASE_URL": (secrets, "ollama_base_url"),
        "ADMIN_API_KEY": (secrets, "admin_api_key"),
        "MCP_API_KEY": (secrets, "mcp_api_key"),
        "LANGFUSE_PUBLIC_KEY": (secrets, "langfuse_public_key"),
        "LANGFUSE_SECRET_KEY": (secrets, "langfuse_secret_key"),
        "LANGFUSE_HOST": (secrets, "langfuse_host"),
        "HF_TOKEN": (secrets, "hf_token"),
    }
    for environment_key, (section, config_key) in overrides.items():
        value = environment.get(environment_key)
        if value:
            section[config_key] = value


def load_config(
    config_path: Path = Path("config/agent.yaml"),
    env_file: Path = Path(".env"),
    environ: Mapping[str, str] | None = None,
) -> AppConfig:
    """Read validated YAML settings, then apply .env and process environment overrides."""
    data = _read_yaml(config_path)
    file_environment = dotenv_values(env_file) if env_file.is_file() else {}
    merged_environment = {key: value for key, value in file_environment.items() if value}
    merged_environment.update(dict(environ if environ is not None else os.environ))
    _overlay_environment(data, merged_environment)
    return AppConfig.model_validate(data)


RuntimeModel = TypeVar("RuntimeModel", PromptTemplates, IntentDescriptions, ToolSettings)


def _load_runtime_model(path: Path, model: type[RuntimeModel]) -> RuntimeModel:
    return model.model_validate(_read_yaml(path))


def load_runtime_files(config_directory: Path = Path("config")) -> RuntimeFiles:
    return RuntimeFiles(
        config=load_config(config_directory / "agent.yaml"),
        prompts=_load_runtime_model(config_directory / "prompts.yaml", PromptTemplates),
        intents=_load_runtime_model(config_directory / "intents.yaml", IntentDescriptions),
        tool_settings=_load_runtime_model(config_directory / "tools.yaml", ToolSettings),
    )
