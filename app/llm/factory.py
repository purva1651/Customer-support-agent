from langchain_core.language_models import BaseChatModel

from app.config import AppConfig


def create_chat_model(config: AppConfig) -> BaseChatModel:
    """Create the configured LangChain chat model without selecting a model implicitly."""
    if not config.llm.model.strip():
        raise ValueError("Set llm.model in config/agent.yaml or LLM_MODEL in the environment")

    common = {
        "model": config.llm.model,
        "temperature": config.llm.temperature,
        "timeout": config.llm.timeout_seconds,
        "max_retries": config.llm.max_retries,
    }
    if config.llm.provider == "xai":
        if not config.secrets.xai_api_key:
            raise ValueError("XAI_API_KEY is required when llm.provider is 'xai'")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            **common,
            base_url=config.secrets.xai_base_url,
            api_key=config.secrets.xai_api_key,
        )
    if config.llm.provider == "openai":
        if not config.secrets.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when llm.provider is 'openai'")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(**common, api_key=config.secrets.openai_api_key)
    if config.llm.provider == "anthropic":
        if not config.secrets.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when llm.provider is 'anthropic'")
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(**common, api_key=config.secrets.anthropic_api_key)
    if config.llm.provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=config.llm.model,
            temperature=config.llm.temperature,
            base_url=config.secrets.ollama_base_url,
        )
    raise ValueError(f"Unsupported LLM provider: {config.llm.provider}")
