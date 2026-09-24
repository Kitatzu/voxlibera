"""Sentence translation with a Gemini Flash-Lite text model.

One request per committed sentence returns every target language at once, so
adding a language does not add requests (keeps us far from the daily request cap).
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {
    "es": "neutral Latin American Spanish",
    "en": "English",
    "pt": "Brazilian Portuguese",
    "fr": "French",
    "de": "German",
    "it": "Italian",
}

SYSTEM_INSTRUCTION_TEMPLATE = """You translate live conference subtitles. Each input is one sentence transcribed by speech recognition from a tech talk.

Rules:
- Translate the sentence into: {language_list}. If the source is already one of these languages, return a cleaned version of it in that field.
- Remove filler words, stutters and repetitions ("um", "you know", "the the", "o sea", "eh"). Only remove fillers: never remove meaningful words like "here" or "aquí", and never summarize, shorten or omit content.
- Speech recognition makes mistakes: use the glossary, the talk context and the previous sentence to fix obvious misrecognitions (e.g. "your eyes" -> "URIs").
- Keep glossary terms exactly as written, never translate them.
- Keep numbers, names and code identifiers unchanged.
- Output only JSON with one field per language code.

Glossary: {glossary}
Talk context: {context}"""

REQUEST_TIMEOUT_SECONDS = 10
MAX_CONCURRENT_REQUESTS = 4


@dataclass
class TranslationResult:
    translations: dict[str, str]
    latency_ms: float
    input_tokens: int
    output_tokens: int


class Translator:
    def __init__(self, client: genai.Client, model: str, target_languages: list[str],
                 glossary: list[str], context: str) -> None:
        self.client = client
        self.model = model
        self.target_languages = target_languages
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        language_list = ", ".join(
            f"{LANGUAGE_NAMES.get(code, code)} ({code})" for code in target_languages
        )
        self._config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION_TEMPLATE.format(
                language_list=language_list,
                glossary=", ".join(glossary) or "(none)",
                context=context or "(none)",
            ),
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {code: {"type": "string"} for code in target_languages},
                "required": target_languages,
            },
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
            max_output_tokens=1024,
        )

    async def translate(self, sentence: str, previous_sentence: str | None) -> TranslationResult | None:
        prompt = sentence if not previous_sentence else (
            f"Previous sentence (context only, do not translate): {previous_sentence}\n"
            f"Sentence to translate: {sentence}"
        )
        async with self._semaphore:
            for attempt in range(2):
                started = time.monotonic()
                try:
                    response = await asyncio.wait_for(
                        self.client.aio.models.generate_content(
                            model=self.model, contents=prompt, config=self._config
                        ),
                        timeout=REQUEST_TIMEOUT_SECONDS,
                    )
                    parsed = json.loads(response.text or "{}")
                    translations = {
                        code: str(parsed[code]).strip()
                        for code in self.target_languages
                        if parsed.get(code)
                    }
                    usage = response.usage_metadata
                    return TranslationResult(
                        translations=translations,
                        latency_ms=(time.monotonic() - started) * 1000,
                        input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                        output_tokens=(usage.candidates_token_count or 0) if usage else 0,
                    )
                except Exception as error:  # network, quota, malformed JSON: retry once
                    logger.warning("Translation attempt %s failed: %s", attempt + 1, error)
        return None
