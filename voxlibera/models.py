from dataclasses import asdict, dataclass, field


@dataclass
class Segment:
    id: int
    start: float
    end: float
    original: str
    source_language: str | None = None
    translations: dict[str, str] = field(default_factory=dict)
    final: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RoomConfig:
    id: str
    name: str
    description: str = ""
    glossary: list[str] = field(default_factory=list)
