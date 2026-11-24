import json
from typing import Any

from app.config import TranslationConfig
from app.schemas import ChatResponse, PendingActionResponse
from app.translation.indictrans2 import translate_chat_response


class _FakeTranslator:
    def __init__(self) -> None:
        self.targets: list[str] = []

    def translate(self, text: str, target_language: str) -> str:
        self.targets.append(target_language)
        return f"{target_language}:{text}"


def test_hindi_and_gujarati_responses_translate_user_facing_fields(
    monkeypatch: Any,
) -> None:
    translator = _FakeTranslator()
    monkeypatch.setattr(
        "app.translation.indictrans2._get_translator", lambda *args: translator
    )
    response = ChatResponse(
        reply="Your booking is confirmed.",
        intent="question",
        pending_action=PendingActionResponse(
            action_id="a1", description="Cancel booking B001."
        ),
        escalated=True,
        escalation_summary=(
            "The customer needs help. The agent checked the booking. A human will review it."
        ),
    )
    settings = TranslationConfig(enabled=True)

    hindi = translate_chat_response(response, "Hindi", settings)
    gujarati = translate_chat_response(response, "Gujarati", settings)

    assert hindi.reply.startswith("hin_Deva:")
    assert hindi.pending_action is not None
    assert hindi.pending_action.description.startswith("hin_Deva:")
    assert hindi.escalation_summary is not None
    assert hindi.escalation_summary.startswith("hin_Deva:")
    assert gujarati.reply.startswith("guj_Gujr:")
    assert set(translator.targets) == {"hin_Deva", "guj_Gujr"}


def test_translation_preserves_booking_identifiers_in_structured_tool_reply(
    monkeypatch: Any,
) -> None:
    translator = _FakeTranslator()
    monkeypatch.setattr(
        "app.translation.indictrans2._get_translator", lambda *args: translator
    )
    response = ChatResponse(
        reply=json.dumps(
            {"booking_id": "B001", "route": "Ahmedabad to Mumbai", "status": "confirmed"}
        ),
        intent="action",
    )

    translated = translate_chat_response(response, "Hindi", TranslationConfig(enabled=True))
    result = json.loads(translated.reply)

    assert result["booking_id"] == "B001"
    assert result["route"].startswith("hin_Deva:")
