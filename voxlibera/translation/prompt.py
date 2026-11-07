"""Prompt building and reply parsing shared by every translation provider."""

import json

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


def build_system_instruction(target_languages: list[str], glossary: list[str], context: str) -> str:
    language_list = ", ".join(
        f"{LANGUAGE_NAMES.get(code, code)} ({code})" for code in target_languages
    )
    return SYSTEM_INSTRUCTION_TEMPLATE.format(
        language_list=language_list,
        glossary=", ".join(glossary) or "(none)",
        context=context or "(none)",
    )


def build_user_prompt(sentence: str, previous_sentence: str | None) -> str:
    if not previous_sentence:
        return sentence
    return (
        f"Previous sentence (context only, do not translate): {previous_sentence}\n"
        f"Sentence to translate: {sentence}"
    )


def parse_translations(text: str, target_languages: list[str]) -> dict[str, str]:
    """Keep only the requested languages the model actually filled in.

    Raises on malformed JSON so the caller can treat it as a failed attempt.
    """
    parsed = json.loads(text or "{}")
    return {
        code: str(parsed[code]).strip()
        for code in target_languages
        if parsed.get(code)
    }
