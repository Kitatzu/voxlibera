"""Adapter for any OpenAI-compatible Chat Completions endpoint.

Works with OpenAI itself and with servers that copy its API: Ollama, vLLM, LM Studio.
Point `base_url` at the server (for Ollama: http://localhost:11434/v1).
"""

import re

import httpx

from voxlibera.translation.provider import ProviderReply, TranslationRequest

CONNECTION_TIMEOUT_SECONDS = 30.0  # Translator.REQUEST_TIMEOUT_SECONDS is the real limit

_CODE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def strip_code_fence(text: str) -> str:
    """Small local models often wrap JSON in a markdown fence even when told not to."""
    match = _CODE_FENCE.match(text.strip())
    return match.group(1) if match else text


class OpenAICompatibleAdapter:
    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 http_client: httpx.AsyncClient | None = None) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        # Local servers need no key, so the header is only sent when one is configured.
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http_client = http_client or httpx.AsyncClient(timeout=CONNECTION_TIMEOUT_SECONDS)
        # Some servers (LM Studio documents only json_schema) answer 400 to JSON mode. We then
        # drop the parameter for good: the prompt already demands JSON and parsing tolerates fences.
        self._send_response_format = True

    async def generate(self, request: TranslationRequest) -> ProviderReply:
        response = await self._post(request)
        if response.status_code == 400 and self._send_response_format:
            self._send_response_format = False
            response = await self._post(request)
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"] or ""
        usage = body.get("usage") or {}
        return ProviderReply(
            text=strip_code_fence(content),
            input_tokens=usage.get("prompt_tokens") or 0,
            output_tokens=usage.get("completion_tokens") or 0,
        )

    async def _post(self, request: TranslationRequest) -> httpx.Response:
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_instruction},
                {"role": "user", "content": request.prompt},
            ],
            "stream": False,
        }
        if self._send_response_format:
            body["response_format"] = {"type": "json_object"}
        return await self._http_client.post(self._url, headers=self._headers, json=body)

    async def aclose(self) -> None:
        await self._http_client.aclose()
