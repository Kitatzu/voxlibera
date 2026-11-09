"""Translation settings from the environment and the provider factory."""

import pytest

from voxlibera.config import OPENAI_BASE_URL, Settings
from voxlibera.translation.factory import TranslationConfigError, create_translation_provider
from voxlibera.translation.gemini import GeminiTranslationAdapter
from voxlibera.translation.openai_compatible import OpenAICompatibleAdapter

TRANSLATION_VARIABLES = (
    "VOXLIBERA_TRANSLATION_PROVIDER",
    "VOXLIBERA_TRANSLATION_BASE_URL",
    "VOXLIBERA_TRANSLATION_API_KEY",
    "VOXLIBERA_TRANSLATION_USD_PER_MILLION_INPUT_TOKENS",
    "VOXLIBERA_TRANSLATION_USD_PER_MILLION_OUTPUT_TOKENS",
    "VOXLIBERA_TRANSLATE_MODEL",
    "OPENAI_API_KEY",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for variable in TRANSLATION_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def settings_from(monkeypatch, **variables):
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    return Settings.from_environment()


def test_defaults_keep_using_gemini_with_its_prices():
    settings = Settings.from_environment()

    assert settings.translation_provider == "gemini"
    assert settings.translation_base_url == OPENAI_BASE_URL
    assert settings.translation_api_key is None
    assert settings.translation_usd_per_million_input_tokens == 0.30
    assert settings.translation_usd_per_million_output_tokens == 2.50


def test_provider_name_is_normalized(monkeypatch):
    settings = settings_from(monkeypatch, VOXLIBERA_TRANSLATION_PROVIDER="  OpenAI ")

    assert settings.translation_provider == "openai"


def test_another_provider_starts_with_zero_prices(monkeypatch):
    settings = settings_from(monkeypatch, VOXLIBERA_TRANSLATION_PROVIDER="openai")

    assert settings.translation_usd_per_million_input_tokens == 0.0
    assert settings.translation_usd_per_million_output_tokens == 0.0


def test_prices_can_be_set_explicitly(monkeypatch):
    settings = settings_from(
        monkeypatch,
        VOXLIBERA_TRANSLATION_PROVIDER="openai",
        VOXLIBERA_TRANSLATION_USD_PER_MILLION_INPUT_TOKENS="0.15",
        VOXLIBERA_TRANSLATION_USD_PER_MILLION_OUTPUT_TOKENS="0.60",
    )

    assert settings.translation_usd_per_million_input_tokens == 0.15
    assert settings.translation_usd_per_million_output_tokens == 0.60


def test_a_price_that_is_not_a_number_is_rejected_with_its_variable_name(monkeypatch):
    monkeypatch.setenv("VOXLIBERA_TRANSLATION_USD_PER_MILLION_INPUT_TOKENS", "cheap")

    with pytest.raises(ValueError, match="VOXLIBERA_TRANSLATION_USD_PER_MILLION_INPUT_TOKENS"):
        Settings.from_environment()


def test_the_api_key_prefers_the_voxlibera_variable_over_openai_api_key(monkeypatch):
    settings = settings_from(monkeypatch, VOXLIBERA_TRANSLATION_API_KEY="mine", OPENAI_API_KEY="shared")

    assert settings.translation_api_key == "mine"


def test_the_api_key_falls_back_to_openai_api_key(monkeypatch):
    assert settings_from(monkeypatch, OPENAI_API_KEY="shared").translation_api_key == "shared"


def test_the_api_key_never_appears_in_the_settings_repr(monkeypatch):
    settings = settings_from(monkeypatch, VOXLIBERA_TRANSLATION_API_KEY="sk-super-secret")

    assert "sk-super-secret" not in repr(settings)


def test_gemini_provider_is_the_default_adapter():
    provider = create_translation_provider(Settings(), gemini_client=object())

    assert isinstance(provider, GeminiTranslationAdapter)


def test_openai_provider_builds_the_compatible_adapter():
    settings = Settings(translation_provider="openai", translate_model="gpt-5-mini", translation_api_key="sk-test")

    assert isinstance(create_translation_provider(settings, gemini_client=object()), OpenAICompatibleAdapter)


def test_a_local_server_needs_no_api_key():
    settings = Settings(
        translation_provider="openai",
        translate_model="gemma3:4b",
        translation_base_url="http://localhost:11434/v1",
    )

    assert isinstance(create_translation_provider(settings, gemini_client=object()), OpenAICompatibleAdapter)


def test_a_gemini_model_name_against_the_openai_endpoint_is_rejected():
    settings = Settings(translation_provider="openai", translation_api_key="sk-test")

    with pytest.raises(TranslationConfigError, match="VOXLIBERA_TRANSLATE_MODEL"):
        create_translation_provider(settings, gemini_client=object())


def test_hosted_openai_without_a_key_is_rejected():
    settings = Settings(translation_provider="openai", translate_model="gpt-5-mini")

    with pytest.raises(TranslationConfigError, match="API key"):
        create_translation_provider(settings, gemini_client=object())


def test_an_unknown_provider_is_rejected_and_named():
    with pytest.raises(TranslationConfigError, match="'claude'"):
        create_translation_provider(Settings(translation_provider="claude"), gemini_client=object())


GEMINI_OPENAI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"


def test_a_gemini_model_is_accepted_on_geminis_own_openai_compatible_endpoint():
    settings = Settings(
        translation_provider="openai",
        translate_model="gemini-3.5-flash-lite",
        translation_base_url=GEMINI_OPENAI_ENDPOINT,
        translation_api_key="gemini-key",
    )

    assert isinstance(create_translation_provider(settings, gemini_client=object()), OpenAICompatibleAdapter)


def test_a_non_openai_endpoint_without_a_key_is_not_blocked():
    settings = Settings(
        translation_provider="openai", translate_model="gemini-3.5-flash-lite", translation_base_url=GEMINI_OPENAI_ENDPOINT
    )

    assert isinstance(create_translation_provider(settings, gemini_client=object()), OpenAICompatibleAdapter)
