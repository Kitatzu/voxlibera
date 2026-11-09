"""Build the configured translation provider, failing early with a readable message."""

from urllib.parse import urlparse

from google import genai

from voxlibera.config import Settings
from voxlibera.translation.gemini import GeminiTranslationAdapter
from voxlibera.translation.openai_compatible import OpenAICompatibleAdapter
from voxlibera.translation.provider import TranslationProvider

HOSTED_OPENAI_HOST = "api.openai.com"


class TranslationConfigError(ValueError):
    """The translation settings cannot produce a working provider."""


def create_translation_provider(settings: Settings, gemini_client: genai.Client) -> TranslationProvider:
    provider_name = settings.translation_provider
    if provider_name == "gemini":
        return GeminiTranslationAdapter(gemini_client, settings.translate_model)
    if provider_name == "openai":
        uses_hosted_openai = urlparse(settings.translation_base_url).hostname == HOSTED_OPENAI_HOST
        # A Gemini model name is only a mistake against OpenAI itself: Gemini also serves an
        # OpenAI-compatible endpoint where that name is exactly right.
        if uses_hosted_openai and settings.translate_model.startswith("gemini"):
            raise TranslationConfigError(
                "VOXLIBERA_TRANSLATION_PROVIDER=openai with the default OpenAI endpoint needs "
                "VOXLIBERA_TRANSLATE_MODEL set to an OpenAI model (for example gpt-5-mini), "
                f"not '{settings.translate_model}'."
            )
        if uses_hosted_openai and not settings.translation_api_key:
            raise TranslationConfigError(
                "Translating with OpenAI needs an API key: set VOXLIBERA_TRANSLATION_API_KEY (or "
                "OPENAI_API_KEY). Local servers such as Ollama do not need one."
            )
        return OpenAICompatibleAdapter(
            settings.translation_base_url, settings.translate_model, settings.translation_api_key
        )
    raise TranslationConfigError(
        f"Unknown VOXLIBERA_TRANSLATION_PROVIDER '{provider_name}'. Use 'gemini' or 'openai'."
    )
