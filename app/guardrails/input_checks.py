import re

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class InvalidAgentInput(ValueError):
    """Raised when an agent invocation bypasses the validated REST schema."""


def validate_agent_input(
    customer_id: str,
    session_id: str,
    message: str,
    max_message_chars: int = 2000,
) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(customer_id):
        raise InvalidAgentInput("invalid customer identifier")
    if not _IDENTIFIER_PATTERN.fullmatch(session_id):
        raise InvalidAgentInput("invalid session identifier")
    if not message or not message.strip():
        raise InvalidAgentInput("message must not be blank")
    normalized = message.strip()
    if len(normalized) > max_message_chars:
        raise InvalidAgentInput("message exceeds the configured size limit")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in normalized):
        raise InvalidAgentInput("message contains unsupported control characters")
    return normalized
