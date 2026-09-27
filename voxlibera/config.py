import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml

from voxlibera.models import RoomConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Hosts that only accept connections from the same machine. Binding to anything else without an
# admin key would let anyone on the network broadcast fake audio or wipe transcripts.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

# Ingest WebSocket limits (see voxlibera/server.py). Real audio is 16-bit PCM at 16 kHz mono,
# i.e. 32,000 bytes/second (voxlibera/audio_input.py BYTES_PER_SECOND). Both the browser
# broadcaster and the CLI source send it in ~100 ms chunks (~3,200 bytes each).
INGEST_MAX_MESSAGE_BYTES = 64 * 1024  # ~20x a real chunk: generous headroom, still bounded
INGEST_RATE_WINDOW_SECONDS = 5.0  # sliding window used to average out normal jitter
INGEST_RATE_LIMIT_BYTES_PER_SECOND = 32_000 * 3  # 3x real-time throughput
INGEST_AUTH_TIMEOUT_SECONDS = 5.0  # time allowed for the first (auth) message to arrive
INGEST_MAX_AUTH_MESSAGE_CHARACTERS = 1024  # the auth message is tiny; anything bigger is rejected


class StartupSecurityDecision(Enum):
    """Outcome of evaluating whether it is safe to start the server with the given settings."""

    SECURE = "secure"  # loopback-only, or an admin key is set: nothing to warn about
    OPEN_ALLOWED = "open_allowed"  # exposed to the network, no key, but the operator opted in


class StartupSecurityError(RuntimeError):
    """Raised when starting would expose admin actions on the network with no admin key."""


def evaluate_startup_security(
    host: str, admin_key: str | None, allow_open: bool
) -> StartupSecurityDecision:
    """Decide whether it is safe to start the server bound to `host` with `admin_key`.

    Pure and side-effect free so it can be unit tested without touching argument parsing,
    environment variables, or uvicorn. `admin_key` should already be normalized (empty
    string treated as unset) by the caller, e.g. via `Settings.from_environment`.
    """
    if admin_key:
        return StartupSecurityDecision.SECURE
    if host in LOOPBACK_HOSTS:
        return StartupSecurityDecision.SECURE
    if allow_open:
        return StartupSecurityDecision.OPEN_ALLOWED
    raise StartupSecurityError(
        f"Refusing to start: bound to '{host}' with no VOXLIBERA_ADMIN_KEY set. Anyone who can "
        "reach this host could broadcast fake audio, stop a live room, or wipe a transcript. "
        "Set VOXLIBERA_ADMIN_KEY=<a long random value> in your .env file. If this is a closed "
        "venue network and you understand the risk, set VOXLIBERA_ALLOW_OPEN=1 instead."
    )


@dataclass
class Settings:
    transcribe_model: str = "gemini-3.5-transcribe-live"
    translate_model: str = "gemini-3.5-flash-lite"
    target_languages: list[str] = field(default_factory=lambda: ["es", "en", "pt"])
    rooms_file: Path = PROJECT_ROOT / "rooms.yaml"
    samples_dir: Path = PROJECT_ROOT / "samples"
    data_dir: Path = PROJECT_ROOT / "data"
    web_dir: Path = PROJECT_ROOT / "web"
    # One key protects every production action: broadcasting audio, simulate, stop, reset.
    # The audience never needs it. None = open (fine on a laptop or a closed venue network).
    admin_key: str | None = None
    # Prices in USD, used only for the dashboard cost estimate. Check ai.google.dev/pricing.
    transcription_usd_per_minute: float = 0.009
    translation_usd_per_million_input_tokens: float = 0.30
    translation_usd_per_million_output_tokens: float = 2.50
    # Ingest WebSocket hardening. Overridable per-instance (tests use tiny values); see the
    # module-level constants above for the rationale behind the defaults.
    ingest_auth_timeout_seconds: float = INGEST_AUTH_TIMEOUT_SECONDS
    ingest_max_message_bytes: int = INGEST_MAX_MESSAGE_BYTES
    ingest_rate_limit_bytes_per_second: float = INGEST_RATE_LIMIT_BYTES_PER_SECOND
    ingest_rate_window_seconds: float = INGEST_RATE_WINDOW_SECONDS

    @classmethod
    def from_environment(cls) -> "Settings":
        settings = cls()
        settings.transcribe_model = os.environ.get("VOXLIBERA_TRANSCRIBE_MODEL", settings.transcribe_model)
        settings.translate_model = os.environ.get("VOXLIBERA_TRANSLATE_MODEL", settings.translate_model)
        languages = os.environ.get("VOXLIBERA_TARGET_LANGUAGES")
        if languages:
            settings.target_languages = [code.strip() for code in languages.split(",") if code.strip()]
        for attribute, variable in (
            ("rooms_file", "VOXLIBERA_ROOMS_FILE"),
            ("samples_dir", "VOXLIBERA_SAMPLES_DIR"),
            ("data_dir", "VOXLIBERA_DATA_DIR"),
            ("web_dir", "VOXLIBERA_WEB_DIR"),
        ):
            if os.environ.get(variable):
                setattr(settings, attribute, Path(os.environ[variable]))
        settings.admin_key = (
            os.environ.get("VOXLIBERA_ADMIN_KEY") or os.environ.get("VOXLIBERA_INGEST_TOKEN") or None
        )
        return settings


def env_flag_is_set(value: str | None) -> bool:
    """True for an explicit opt-in value like "1"/"true"/"yes"; False for unset, "", "0", "false"."""
    if not value:
        return False
    return value.strip().lower() not in ("0", "false", "no")


def load_rooms(rooms_file: Path) -> list[RoomConfig]:
    with open(rooms_file, encoding="utf-8") as file:
        document = yaml.safe_load(file) or {}
    shared_glossary = document.get("glossary", [])
    rooms = []
    for entry in document.get("rooms", []):
        glossary = list(dict.fromkeys([*shared_glossary, *entry.get("glossary", [])]))
        rooms.append(RoomConfig(
            id=entry["id"],
            name=entry.get("name", entry["id"]),
            description=entry.get("description", ""),
            glossary=glossary,
        ))
    return rooms
