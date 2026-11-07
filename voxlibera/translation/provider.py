"""The port every translation backend implements.

A provider makes exactly one attempt and raises on any failure. Timeouts, retries,
concurrency limits and metrics belong to `Translator`, so adapters stay tiny.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranslationRequest:
    system_instruction: str
    prompt: str
    target_languages: list[str]


@dataclass(frozen=True)
class ProviderReply:
    """Raw JSON text produced by the model plus the token usage it reported."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class TranslationProvider(Protocol):
    async def generate(self, request: TranslationRequest) -> ProviderReply:
        """Ask the model for one JSON object with one field per target language."""
        ...
