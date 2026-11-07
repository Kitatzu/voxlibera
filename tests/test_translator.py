"""Characterization tests for Translator: they pin the current behaviour so the
provider extraction can be done as a pure refactor. No network, no real API key."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from voxlibera import translator as translator_module
from voxlibera.translation.gemini import GeminiTranslationAdapter
from voxlibera.translation.provider import ProviderReply
from voxlibera.translator import MAX_CONCURRENT_REQUESTS, TranslationResult, Translator


def make_response(payload, prompt_tokens=11, candidate_tokens=7, with_usage=True):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    usage = (
        SimpleNamespace(prompt_token_count=prompt_tokens, candidates_token_count=candidate_tokens)
        if with_usage
        else None
    )
    return SimpleNamespace(text=text, usage_metadata=usage)


class FakeGenaiClient:
    """Stands in for genai.Client: only `client.aio.models.generate_content` is used."""

    def __init__(self, behaviours):
        self._behaviours = list(behaviours)
        self.calls = []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate_content))

    async def _generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        behaviour = self._behaviours.pop(0)
        if isinstance(behaviour, Exception):
            raise behaviour
        if callable(behaviour):
            return await behaviour()
        return behaviour


def build_translator(client, target_languages=("es", "en"), glossary=(), context=""):
    return Translator(
        GeminiTranslationAdapter(client, "fake-model"), list(target_languages), list(glossary), context
    )


async def test_returns_a_cleaned_translation_for_every_target_language():
    client = FakeGenaiClient([make_response({"es": "  Hola mundo  ", "en": "Hello world"})])

    result = await build_translator(client).translate("Hello world", None)

    assert isinstance(result, TranslationResult)
    assert result.translations == {"es": "Hola mundo", "en": "Hello world"}
    assert result.input_tokens == 11
    assert result.output_tokens == 7
    assert result.latency_ms >= 0


async def test_leaves_out_languages_the_model_returned_empty_or_missing():
    client = FakeGenaiClient([make_response({"es": "Hola", "en": ""})])

    result = await build_translator(client, target_languages=("es", "en", "pt")).translate("Hi", None)

    assert result.translations == {"es": "Hola"}


async def test_token_counts_are_zero_when_the_response_has_no_usage():
    client = FakeGenaiClient([make_response({"es": "Hola", "en": "Hi"}, with_usage=False)])

    result = await build_translator(client).translate("Hi", None)

    assert (result.input_tokens, result.output_tokens) == (0, 0)


async def test_sends_only_the_sentence_when_there_is_no_previous_one():
    client = FakeGenaiClient([make_response({"es": "Hola", "en": "Hi"})])

    await build_translator(client).translate("Hi", None)

    assert client.calls[0]["contents"] == "Hi"
    assert client.calls[0]["model"] == "fake-model"


async def test_marks_the_previous_sentence_as_context_only():
    client = FakeGenaiClient([make_response({"es": "Hola", "en": "Hi"})])

    await build_translator(client).translate("Second sentence", "First sentence")

    prompt = client.calls[0]["contents"]
    assert "Previous sentence (context only, do not translate): First sentence" in prompt
    assert prompt.endswith("Sentence to translate: Second sentence")


async def test_system_instruction_carries_languages_glossary_and_context():
    client = FakeGenaiClient([make_response({"es": "Hola", "en": "Hi"})])
    translator = build_translator(
        client, target_languages=("es", "xx"), glossary=("Kubernetes", "URI"), context="A DevOps talk"
    )

    await translator.translate("Hi", None)

    instruction = client.calls[0]["config"].system_instruction
    assert "neutral Latin American Spanish (es)" in instruction
    assert "xx (xx)" in instruction  # unknown codes fall back to the code itself
    assert "Glossary: Kubernetes, URI" in instruction
    assert "Talk context: A DevOps talk" in instruction


async def test_empty_glossary_and_context_are_spelled_out_as_none():
    client = FakeGenaiClient([make_response({"es": "Hola", "en": "Hi"})])

    await build_translator(client).translate("Hi", None)

    instruction = client.calls[0]["config"].system_instruction
    assert "Glossary: (none)" in instruction
    assert "Talk context: (none)" in instruction


async def test_response_schema_requires_one_string_field_per_language():
    client = FakeGenaiClient([make_response({"es": "Hola", "en": "Hi"})])

    await build_translator(client).translate("Hi", None)

    schema = client.calls[0]["config"].response_schema
    assert schema["required"] == ["es", "en"]
    assert schema["properties"] == {"es": {"type": "string"}, "en": {"type": "string"}}


async def test_retries_once_after_a_failure_and_returns_the_second_attempt():
    client = FakeGenaiClient([RuntimeError("quota"), make_response({"es": "Hola", "en": "Hi"})])

    result = await build_translator(client).translate("Hi", None)

    assert result.translations == {"es": "Hola", "en": "Hi"}
    assert len(client.calls) == 2


async def test_gives_up_with_none_after_two_failed_attempts():
    client = FakeGenaiClient([RuntimeError("down"), RuntimeError("still down")])

    result = await build_translator(client).translate("Hi", None)

    assert result is None
    assert len(client.calls) == 2


async def test_malformed_json_counts_as_a_failed_attempt():
    client = FakeGenaiClient([make_response("not json"), make_response("{broken")])

    result = await build_translator(client).translate("Hi", None)

    assert result is None
    assert len(client.calls) == 2


async def test_a_slow_request_times_out_and_is_retried(monkeypatch):
    monkeypatch.setattr(translator_module, "REQUEST_TIMEOUT_SECONDS", 0.05)

    async def never_answers():
        await asyncio.sleep(5)

    client = FakeGenaiClient([never_answers, make_response({"es": "Hola", "en": "Hi"})])

    result = await build_translator(client).translate("Hi", None)

    assert result.translations == {"es": "Hola", "en": "Hi"}
    assert len(client.calls) == 2


async def test_never_runs_more_than_the_concurrency_limit_at_once():
    running = 0
    peak = 0

    async def slow_answer():
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return make_response({"es": "Hola", "en": "Hi"})

    sentence_count = MAX_CONCURRENT_REQUESTS * 3
    client = FakeGenaiClient([slow_answer] * sentence_count)
    translator = build_translator(client)

    results = await asyncio.gather(*(translator.translate(f"s{index}", None) for index in range(sentence_count)))

    assert all(result is not None for result in results)
    assert peak == MAX_CONCURRENT_REQUESTS


@pytest.mark.parametrize("unknown_code", ["ja", "ko"])
async def test_unknown_language_codes_are_still_requested(unknown_code):
    client = FakeGenaiClient([make_response({unknown_code: "ok"})])

    result = await build_translator(client, target_languages=(unknown_code,)).translate("Hi", None)

    assert result.translations == {unknown_code: "ok"}


class FakeTranslationProvider:
    """Implements the TranslationProvider port with canned replies, no genai involved."""

    def __init__(self, behaviours):
        self._behaviours = list(behaviours)
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        behaviour = self._behaviours.pop(0)
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour


async def test_orchestrator_works_with_any_provider_and_adds_the_latency():
    provider = FakeTranslationProvider([ProviderReply('{"es": "Hola", "en": "Hi"}', 5, 3)])
    translator = Translator(provider, ["es", "en"], [], "")

    result = await translator.translate("Hi", None)

    assert result.translations == {"es": "Hola", "en": "Hi"}
    assert (result.input_tokens, result.output_tokens) == (5, 3)
    assert result.latency_ms >= 0


async def test_the_request_handed_to_the_provider_is_complete():
    provider = FakeTranslationProvider([ProviderReply('{"es": "Hola"}')])
    translator = Translator(provider, ["es"], ["URI"], "A talk")

    await translator.translate("Second", "First")

    request = provider.requests[0]
    assert request.target_languages == ["es"]
    assert "Glossary: URI" in request.system_instruction
    assert request.prompt.endswith("Sentence to translate: Second")


async def test_a_provider_error_is_retried_once_then_succeeds():
    provider = FakeTranslationProvider([ConnectionError("boom"), ProviderReply('{"es": "Hola"}')])

    result = await Translator(provider, ["es"], [], "").translate("Hi", None)

    assert result.translations == {"es": "Hola"}
    assert len(provider.requests) == 2


async def test_two_provider_errors_give_none():
    provider = FakeTranslationProvider([ConnectionError("a"), ConnectionError("b")])

    assert await Translator(provider, ["es"], [], "").translate("Hi", None) is None


async def test_an_empty_reply_text_yields_empty_translations_not_a_failure():
    provider = FakeTranslationProvider([ProviderReply("")])

    result = await Translator(provider, ["es"], [], "").translate("Hi", None)

    assert result.translations == {}
    assert len(provider.requests) == 1


async def test_gemini_adapter_requests_json_with_minimal_thinking_and_no_tools():
    client = FakeGenaiClient([make_response({"es": "Hola", "en": "Hi"})])

    await build_translator(client).translate("Hi", None)

    config = client.calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.max_output_tokens == 1024
    assert config.thinking_config.thinking_level.name == "MINIMAL"
    assert config.automatic_function_calling.disable is True
