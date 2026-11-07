"""OpenAICompatibleAdapter against a mocked transport: no network, no API key."""

import json

import httpx
import pytest

from voxlibera.translation.openai_compatible import OpenAICompatibleAdapter, strip_code_fence
from voxlibera.translation.provider import TranslationRequest
from voxlibera.translator import Translator

REQUEST = TranslationRequest(system_instruction="SYSTEM TEXT", prompt="Hello", target_languages=["es", "en"])


def completion(content, usage=None):
    body = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body)


def build_adapter(handler, base_url="http://localhost:11434/v1", api_key=None):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatibleAdapter(base_url, "gemma3:4b", api_key, http_client=client)


async def test_posts_a_chat_completion_with_system_and_user_messages():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return completion('{"es": "Hola", "en": "Hello"}')

    await build_adapter(handler).generate(REQUEST)

    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["body"] == {
        "model": "gemma3:4b",
        "messages": [
            {"role": "system", "content": "SYSTEM TEXT"},
            {"role": "user", "content": "Hello"},
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
    }


async def test_a_trailing_slash_in_the_base_url_is_harmless():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return completion("{}")

    await build_adapter(handler, base_url="http://localhost:8000/v1/").generate(REQUEST)

    assert captured["url"] == "http://localhost:8000/v1/chat/completions"


async def test_sends_the_api_key_as_a_bearer_token():
    captured = {}

    def handler(request):
        captured["authorization"] = request.headers.get("authorization")
        return completion("{}")

    await build_adapter(handler, api_key="sk-test").generate(REQUEST)

    assert captured["authorization"] == "Bearer sk-test"


async def test_sends_no_authorization_header_for_a_local_server_without_a_key():
    captured = {}

    def handler(request):
        captured["headers"] = dict(request.headers)
        return completion("{}")

    await build_adapter(handler).generate(REQUEST)

    assert "authorization" not in captured["headers"]


async def test_maps_token_usage_from_the_response():
    reply = await build_adapter(
        lambda request: completion("{}", usage={"prompt_tokens": 42, "completion_tokens": 9})
    ).generate(REQUEST)

    assert (reply.input_tokens, reply.output_tokens) == (42, 9)


async def test_missing_usage_counts_as_zero_tokens():
    reply = await build_adapter(lambda request: completion("{}")).generate(REQUEST)

    assert (reply.input_tokens, reply.output_tokens) == (0, 0)


async def test_null_content_becomes_empty_text():
    reply = await build_adapter(lambda request: completion(None)).generate(REQUEST)

    assert reply.text == ""


@pytest.mark.parametrize(
    "wrapped",
    ['```json\n{"es": "Hola"}\n```', '```\n{"es": "Hola"}\n```', '  ```JSON\n{"es": "Hola"}```  '],
)
async def test_unwraps_markdown_code_fences_that_small_models_add(wrapped):
    reply = await build_adapter(lambda request: completion(wrapped)).generate(REQUEST)

    assert json.loads(reply.text) == {"es": "Hola"}


def test_plain_json_is_left_untouched():
    assert strip_code_fence('{"es": "Hola"}') == '{"es": "Hola"}'


async def test_an_http_error_raises_so_the_translator_can_retry():
    adapter = build_adapter(lambda request: httpx.Response(500, json={"error": "overloaded"}))

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.generate(REQUEST)


async def test_a_body_without_choices_raises():
    adapter = build_adapter(lambda request: httpx.Response(200, json={"unexpected": True}))

    with pytest.raises((KeyError, IndexError)):
        await adapter.generate(REQUEST)


async def test_translator_works_end_to_end_through_the_adapter():
    adapter = build_adapter(
        lambda request: completion('```json\n{"es": "Hola", "en": "Hello"}\n```', {"prompt_tokens": 4, "completion_tokens": 2})
    )

    result = await Translator(adapter, ["es", "en"], [], "").translate("Hello", None)

    assert result.translations == {"es": "Hola", "en": "Hello"}
    assert (result.input_tokens, result.output_tokens) == (4, 2)


async def test_translator_retries_after_a_server_error():
    responses = [httpx.Response(503), completion('{"es": "Hola"}')]

    result = await Translator(build_adapter(lambda request: responses.pop(0)), ["es"], [], "").translate("Hi", None)

    assert result.translations == {"es": "Hola"}


async def test_aclose_closes_the_http_client():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: completion("{}")))
    adapter = OpenAICompatibleAdapter("http://localhost/v1", "model", http_client=client)

    await adapter.aclose()

    assert client.is_closed


async def test_falls_back_to_no_json_mode_when_the_server_rejects_response_format():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "'response_format.type' must be 'json_schema'"})
        return completion('{"es": "Hola"}')

    adapter = build_adapter(handler)

    first = await adapter.generate(REQUEST)
    second = await adapter.generate(REQUEST)

    assert json.loads(first.text) == {"es": "Hola"}
    assert json.loads(second.text) == {"es": "Hola"}
    # One rejected attempt with JSON mode, one retry without it, then JSON mode stays off.
    assert ["response_format" in body for body in bodies] == [True, False, False]


async def test_a_400_without_json_mode_is_a_real_error():
    adapter = build_adapter(lambda request: httpx.Response(400, json={"error": "bad model"}))

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.generate(REQUEST)
