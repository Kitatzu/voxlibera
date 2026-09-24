"""Transcript exporters: SRT, WebVTT and plain text."""

from collections.abc import Iterable

from voxlibera.models import Segment

MAX_CAPTION_CHARACTERS = 84  # two lines of ~42 characters


def segment_text(segment: Segment, language: str) -> str:
    if language == "original":
        return segment.original
    return segment.translations.get(language) or segment.original


def _format_timestamp(seconds: float, decimal_separator: str) -> str:
    total_milliseconds = int(round(max(seconds, 0) * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}{decimal_separator}{milliseconds:03}"


def _caption_chunks(text: str, start: float, end: float) -> list[tuple[str, float, float]]:
    """Split long sentences into readable captions, spreading time by length."""
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        if current and len(" ".join([*current, word])) > MAX_CAPTION_CHARACTERS:
            chunks.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        chunks.append(" ".join(current))
    total_characters = sum(len(chunk) for chunk in chunks) or 1
    duration = max(end - start, 0.5)
    timed: list[tuple[str, float, float]] = []
    cursor = start
    for chunk in chunks:
        chunk_end = cursor + duration * len(chunk) / total_characters
        timed.append((chunk, cursor, chunk_end))
        cursor = chunk_end
    return timed


def _visible(segments: Iterable[Segment]) -> list[Segment]:
    """Sorted segments, without the ones blanked because the final transcript merged them."""
    return sorted((segment for segment in segments if segment.original), key=lambda item: item.start)


def _timed_captions(segments: Iterable[Segment], language: str) -> list[tuple[str, float, float]]:
    captions: list[tuple[str, float, float]] = []
    for segment in _visible(segments):
        captions.extend(_caption_chunks(segment_text(segment, language), segment.start, segment.end))
    return captions


def to_srt(segments: Iterable[Segment], language: str) -> str:
    blocks = []
    for number, (text, start, end) in enumerate(_timed_captions(segments, language), start=1):
        blocks.append(f"{number}\n{_format_timestamp(start, ',')} --> {_format_timestamp(end, ',')}\n{text}\n")
    return "\n".join(blocks)


def to_vtt(segments: Iterable[Segment], language: str) -> str:
    blocks = ["WEBVTT\n"]
    for text, start, end in _timed_captions(segments, language):
        blocks.append(f"{_format_timestamp(start, '.')} --> {_format_timestamp(end, '.')}\n{text}\n")
    return "\n".join(blocks)


def to_text(segments: Iterable[Segment], language: str) -> str:
    return "\n".join(segment_text(segment, language) for segment in _visible(segments)) + "\n"


EXPORTERS = {"srt": to_srt, "vtt": to_vtt, "txt": to_text}
MEDIA_TYPES = {"srt": "application/x-subrip", "vtt": "text/vtt", "txt": "text/plain"}
