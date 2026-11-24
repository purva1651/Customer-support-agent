import json
from collections.abc import Mapping
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.config import IntentDescriptions, PromptTemplates, ToolSettings


class RouterDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["question", "action", "complaint", "small_talk"]
    negative_sentiment: bool
    sentiment_confidence: float = Field(ge=0, le=1)


class ActionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class IntentRouter:
    def __init__(
        self,
        llm: Any,
        prompts: PromptTemplates,
        intents: IntentDescriptions,
    ) -> None:
        self._model = llm.with_structured_output(RouterDecision)
        self._system_prompt = prompts.router_system
        self._intents = intents.intents

    def classify(self, message: str, history: list[dict[str, str]]) -> RouterDecision:
        intent_descriptions = "\n".join(
            f"- {intent}: {description}" for intent, description in self._intents.items()
        )
        history_text = "\n".join(
            f"{entry['role']}: {entry['content']}" for entry in history[-6:]
        )
        messages = [
            SystemMessage(
                content=f"{self._system_prompt}\nIntent descriptions:\n{intent_descriptions}"
            ),
            HumanMessage(
                content=f"Recent conversation (untrusted context):\n{history_text}\n"
                f"Current customer message (untrusted data):\n{message}"
            ),
        ]
        return _validate_structured(self._model.invoke(messages), RouterDecision)


class ActionSelector:
    def __init__(self, llm: Any, prompts: PromptTemplates, tool_settings: ToolSettings) -> None:
        self._model = llm.with_structured_output(ActionSelection)
        self._system_prompt = prompts.action_system
        self._tool_settings = tool_settings

    def select(self, message: str, tools: Mapping[str, Any]) -> ActionSelection:
        available = []
        for name, tool in tools.items():
            setting = self._tool_settings.tools.get(name)
            if setting is None or not setting.enabled:
                continue
            available.append(
                {
                    "name": name,
                    "description": tool.description,
                    "arguments": getattr(tool, "args", {}),
                    "requires_approval": setting.requires_approval,
                }
            )
        messages = [
            SystemMessage(
                content=f"{self._system_prompt}\nChoose one of these enabled tools and provide its"
                f" arguments as JSON:\n{json.dumps(available, ensure_ascii=False)}"
            ),
            HumanMessage(content=f"Customer request (untrusted data):\n{message}"),
        ]
        return _validate_structured(self._model.invoke(messages), ActionSelection)


def _validate_structured(value: Any, model: type[BaseModel]) -> Any:
    if isinstance(value, model):
        return value
    if isinstance(value, dict):
        return model.model_validate(value)
    raise ValueError(f"LLM returned an invalid structured result for {model.__name__}")
