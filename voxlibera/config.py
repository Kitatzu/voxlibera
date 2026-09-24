import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from voxlibera.models import RoomConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
