"""Sentence translation orchestrator, independent of the model provider.

One request per committed sentence returns every target language at once, so
adding a language does not add requests (keeps us far from the daily request cap).
The provider makes one attempt; this class adds the concurrency limit, the timeout,
one retry and the latency measurement.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from voxlibera.translation.prompt import build_system_instruction, build_user_prompt, parse_translations
from voxlibera.translation.provider import TranslationProvider, TranslationRequest

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10
MAX_CONCURRENT_REQUESTS = 4


@dataclass
class TranslationResult:
    translations: dict[str, str]
    latency_ms: float
    input_tokens: int
    output_tokens: int


class Translator:
    def __init__(self, provider: TranslationProvider, target_languages: list[str],
                 glossary: list[str], context: str) -> None:
        self.provider = provider
        self.target_languages = target_languages
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self._system_instruction = build_system_instruction(target_languages, glossary, context)

    async def translate(self, sentence: str, previous_sentence: str | None) -> TranslationResult | None:
        request = TranslationRequest(
            system_instruction=self._system_instruction,
            prompt=build_user_prompt(sentence, previous_sentence),
            target_languages=self.target_languages,
        )
        async with self._semaphore:
            for attempt in range(2):
                started = time.monotonic()
                try:
                    reply = await asyncio.wait_for(
                        self.provider.generate(request), timeout=REQUEST_TIMEOUT_SECONDS
                    )
                    translations = parse_translations(reply.text, self.target_languages)
                    return TranslationResult(
                        translations=translations,
                        latency_ms=(time.monotonic() - started) * 1000,
                        input_tokens=reply.input_tokens,
                        output_tokens=reply.output_tokens,
                    )
                except Exception as error:  # network, quota, malformed JSON: retry once
                    logger.warning("Translation attempt %s failed: %s", attempt + 1, error)
        return None
