"""Gemini text-model adapter for the translation port."""

from google import genai
from google.genai import types

from voxlibera.translation.provider import ProviderReply, TranslationRequest


class GeminiTranslationAdapter:
    def __init__(self, client: genai.Client, model: str) -> None:
        self._client = client
        self._model = model

    async def generate(self, request: TranslationRequest) -> ProviderReply:
        config = types.GenerateContentConfig(
            system_instruction=request.system_instruction,
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {code: {"type": "string"} for code in request.target_languages},
                "required": request.target_languages,
            },
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
            max_output_tokens=1024,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = await self._client.aio.models.generate_content(
            model=self._model, contents=request.prompt, config=config
        )
        usage = response.usage_metadata
        return ProviderReply(
            text=response.text or "",
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        )
