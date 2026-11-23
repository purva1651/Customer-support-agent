import re


class PromptInjectionDetector:
    def __init__(self, patterns: list[str]) -> None:
        self._patterns = [re.compile(pattern) for pattern in patterns]

    def detect(self, message: str) -> bool:
        return any(pattern.search(message) is not None for pattern in self._patterns)
