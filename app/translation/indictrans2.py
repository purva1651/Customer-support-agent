import json
import re
from functools import lru_cache
from threading import Lock
from typing import Any

from app.config import TranslationConfig
from app.schemas import ChatResponse

_TARGET_LANGUAGES = {"Hindi": "hin_Deva", "Gujarati": "guj_Gujr"}
_IDENTIFIER_FIELDS = {
    "booking_id",
    "ticket_id",
    "customer_id",
    "email",
    "phone",
    "url",
    "departs_at",
    "created_at",
    "seat",
}


def translate_chat_response(
    response: ChatResponse,
    language: str,
    settings: TranslationConfig,
    hf_token: str | None = None,
) -> ChatResponse:
    target_language = _TARGET_LANGUAGES.get(language)
    if target_language is None:
        return response
    translator = _get_translator(settings.model, settings.device, hf_token)
    pending_action = response.pending_action
    if pending_action is not None:
        pending_action = pending_action.model_copy(
            update={
                "description": translator.translate(
                    pending_action.description, target_language
                )
            }
        )
    return response.model_copy(
        update={
            "reply": _translate_reply(response.reply, translator, target_language),
            "escalation_summary": (
                translator.translate(response.escalation_summary, target_language)
                if response.escalation_summary
                else None
            ),
            "pending_action": pending_action,
        }
    )


def _translate_reply(text: str, translator: Any, target_language: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return translator.translate(text, target_language)
    if not isinstance(payload, (dict, list)):
        return translator.translate(text, target_language)
    return json.dumps(
        _translate_json_values(payload, translator, target_language),
        ensure_ascii=False,
    )


def _translate_json_values(value: Any, translator: Any, target_language: str) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                item
                if key in _IDENTIFIER_FIELDS
                else _translate_json_values(item, translator, target_language)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_translate_json_values(item, translator, target_language) for item in value]
    if isinstance(value, str):
        return translator.translate(value, target_language)
    return value


@lru_cache(maxsize=1)
def _get_translator(model_name: str, requested_device: str, hf_token: str | None) -> Any:
    import torch
    from IndicTransToolkit import IndicProcessor
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    if requested_device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = requested_device
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("IndicTrans2 is configured for CUDA, but CUDA is unavailable")
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
        token=hf_token,
    )
    model = AutoModelForSeq2SeqLM.from_pretrained(
        model_name,
        trust_remote_code=True,
        token=hf_token,
    ).to(device)
    model.eval()
    return _IndicTrans2(model, tokenizer, IndicProcessor(inference=True), torch, device)


class _IndicTrans2:
    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        processor: Any,
        torch: Any,
        device: str,
    ) -> None:
        self._model = model
        self._tokenizer = tokenizer
        self._processor = processor
        self._torch = torch
        self._device = device
        self._lock = Lock()

    def translate(self, text: str, target_language: str) -> str:
        with self._lock:
            segments = [
                segment.strip()
                for segment in re.split(r"(?<=[.!?।])\s+|\n+", text)
                if segment.strip()
            ]
            if not segments:
                return ""
            preprocessed = self._processor.preprocess_batch(
                segments,
                src_lang="eng_Latn",
                tgt_lang=target_language,
                visualize=False,
            )
            inputs = self._tokenizer(
                preprocessed,
                padding="longest",
                truncation=True,
                max_length=256,
                return_tensors="pt",
            ).to(self._device)
            with self._torch.inference_mode():
                generated = self._model.generate(
                    **inputs,
                    num_beams=5,
                    num_return_sequences=1,
                    max_length=256,
                )
            decoded = self._tokenizer.batch_decode(
                generated,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            )
            translated = self._processor.postprocess_batch(decoded, lang=target_language)
            return " ".join(translated)
