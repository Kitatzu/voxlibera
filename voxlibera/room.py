"""A room (stage): one audio source -> transcription -> sentences -> translations -> audience."""

import asyncio
import contextlib
import json
import logging
import threading
from pathlib import Path

from google import genai

from voxlibera import audio_input
from voxlibera.broadcaster import Broadcaster
from voxlibera.config import Settings
from voxlibera.exporters import EXPORTERS
from voxlibera.live_transcriber import LiveTranscriber, TranscriptCallbacks
from voxlibera.models import RoomConfig, Segment
from voxlibera.segmenter import SegmenterUpdate, SentenceSegmenter
from voxlibera.translator import Translator

logger = logging.getLogger(__name__)

SIMULATION_TAIL_SECONDS = 6  # keep the session open after a sample ends to get the last words
SMOOTHING = 0.2  # exponential moving average weight for latency metrics


class Room:
    def __init__(self, config: RoomConfig, settings: Settings, client: genai.Client,
                 broadcaster: Broadcaster) -> None:
        self.config = config
        self.settings = settings
        self.client = client
        self.broadcaster = broadcaster
        self.status = "idle"
        self.source_kind: str | None = None
        self.segments: dict[int, Segment] = {}
        self.audio_bytes = 0
        self.source_language: str | None = None
        self.translation_latency_ms: float | None = None
        self.caption_lag_seconds: float | None = None
        self.translation_input_tokens = 0
        self.translation_output_tokens = 0
        self._next_segment_id = 1
        self._utterance_segment_ids: list[int] = []
        self._segmenter = SentenceSegmenter()
        self._transcriber: LiveTranscriber | None = None
        self._translator = Translator(
            client, settings.translate_model, settings.target_languages,
            config.glossary, f"{config.name}: {config.description}",
        )
        self._background_tasks: set[asyncio.Task] = set()
        self._simulation_process = None
        self._source_lock = asyncio.Lock()
        self._previous_stats = {"sessions_opened": 0, "rotations": 0, "errors": 0}
        self._last_error: str | None = None
        self._transcript_file = settings.data_dir / f"{config.id}.jsonl"
        self._load_transcript()

    # --- source lifecycle --------------------------------------------------

    @property
    def audio_seconds(self) -> float:
        return self.audio_bytes / audio_input.BYTES_PER_SECOND

    @property
    def has_source(self) -> bool:
        return self.source_kind is not None

    async def start_source(self, kind: str) -> bool:
        async with self._source_lock:
            if self.has_source:
                return False
            self.source_kind = kind
            self._set_status("starting")
            self._transcriber = LiveTranscriber(
                self.client, self.settings.transcribe_model, self.config.glossary,
                TranscriptCallbacks(
                    on_interim=self._on_interim,
                    on_final=self._on_final,
                    on_state_change=self._on_transcriber_state_change,
                ),
            )
            try:
                await self._transcriber.start()
            except Exception as error:
                self._last_error = str(error)
                self.source_kind = None
                self._transcriber = None
                self._set_status("error")
                raise
            self._set_status("live")
            return True

    def feed_audio(self, chunk: bytes) -> None:
        self.audio_bytes += len(chunk)
        if self._transcriber is not None:
            self._transcriber.feed(chunk)

    async def stop_source(self) -> None:
        async with self._source_lock:
            if not self.has_source:
                return
            self._stop_simulation_process()
            if self._transcriber is not None:
                self._keep_stats(self._transcriber)
                await self._transcriber.stop()
                self._transcriber = None
            self._apply_update(self._segmenter.flush(self.audio_seconds))
            self.source_kind = None
            self._set_status("stopped")

    async def start_simulation(self, sample_path: Path) -> bool:
        command = audio_input.file_command(str(sample_path), realtime=True)
        if not await self.start_source("simulation"):
            return False
        loop = asyncio.get_running_loop()
        process = audio_input.start_process(command)
        self._simulation_process = process

        def pump() -> None:
            audio_input.pump_chunks(process, lambda chunk: loop.call_soon_threadsafe(self.feed_audio, chunk))
            loop.call_soon_threadsafe(self._schedule, self._finish_simulation(process))

        threading.Thread(target=pump, daemon=True, name=f"simulation-{self.config.id}").start()
        return True

    async def _finish_simulation(self, process) -> None:
        await asyncio.sleep(SIMULATION_TAIL_SECONDS)
        if self._simulation_process is process:
            await self.stop_source()

    def _stop_simulation_process(self) -> None:
        process, self._simulation_process = self._simulation_process, None
        if process is not None and process.poll() is None:
            process.kill()

    # --- transcript pipeline -----------------------------------------------

    def _on_interim(self, text: str, language: str | None) -> None:
        if language:
            self.source_language = language
        self._apply_update(self._segmenter.on_interim(text, self.audio_seconds))
        self._publish({"type": "interim", "text": self._segmenter.pending_text,
                       "language": self.source_language})

    def _on_final(self, text: str, language: str | None) -> None:
        if language:
            self.source_language = language
        self._apply_update(self._segmenter.on_final(text, self.audio_seconds))
        self._publish({"type": "interim", "text": "", "language": self.source_language})

    def _apply_update(self, update: SegmenterUpdate) -> None:
        for correction in update.corrections:
            if correction.utterance_index >= len(self._utterance_segment_ids):
                continue
            segment = self.segments[self._utterance_segment_ids[correction.utterance_index]]
            segment.original = correction.text
            segment.translations = {}
            self._store_and_publish(segment)
            if correction.text:
                self._request_translation(segment)

        for sentence in update.committed:
            segment = Segment(
                id=self._next_segment_id,
                start=round(sentence.start, 2),
                end=round(sentence.end, 2),
                original=sentence.text,
                source_language=self.source_language,
            )
            self._next_segment_id += 1
            self.segments[segment.id] = segment
            self._utterance_segment_ids.append(segment.id)
            self._store_and_publish(segment)
            self._request_translation(segment)

        if update.utterance_finished:
            for segment_id in self._utterance_segment_ids:
                self.segments[segment_id].final = True
            self._utterance_segment_ids = []

    def _request_translation(self, segment: Segment) -> None:
        previous = self.segments.get(segment.id - 1)
        self._schedule(self._translate(segment, segment.original, previous.original if previous else None))

    async def _translate(self, segment: Segment, text: str, previous_text: str | None) -> None:
        result = await self._translator.translate(text, previous_text)
        if result is None:
            self._last_error = f"translation failed for segment {segment.id}"
            return
        if segment.original != text:
            return  # corrected meanwhile; a newer translation is on its way
        segment.translations = result.translations
        self.translation_input_tokens += result.input_tokens
        self.translation_output_tokens += result.output_tokens
        self.translation_latency_ms = self._smooth(self.translation_latency_ms, result.latency_ms)
        self.caption_lag_seconds = self._smooth(
            self.caption_lag_seconds, max(self.audio_seconds - segment.end, 0)
        )
        self._store_and_publish(segment)

    # --- persistence, publishing, metrics ----------------------------------

    def _store_and_publish(self, segment: Segment) -> None:
        self._publish({"type": "segment", "segment": segment.to_dict()})
        try:
            self._transcript_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._transcript_file, "a", encoding="utf-8") as file:
                file.write(json.dumps(segment.to_dict(), ensure_ascii=False) + "\n")
        except OSError as error:
            logger.warning("Could not persist segment: %s", error)

    def _load_transcript(self) -> None:
        if not self._transcript_file.exists():
            return
        with open(self._transcript_file, encoding="utf-8") as file:
            for line in file:
                with contextlib.suppress(ValueError, TypeError):
                    segment = Segment(**json.loads(line))
                    self.segments[segment.id] = segment  # later lines upsert earlier ones
        if self.segments:
            self._next_segment_id = max(self.segments) + 1
            last_end = max(segment.end for segment in self.segments.values())
            self.audio_bytes = int(last_end * audio_input.BYTES_PER_SECOND)
            self._segmenter.last_commit_end = last_end

    def reset_transcript(self) -> None:
        self.segments.clear()
        self._utterance_segment_ids = []
        self._next_segment_id = 1
        self.audio_bytes = 0
        # Metrics describe the current transcript: a new talk starts from zero.
        self.translation_input_tokens = 0
        self.translation_output_tokens = 0
        self.translation_latency_ms = None
        self.caption_lag_seconds = None
        self._segmenter = SentenceSegmenter()
        with contextlib.suppress(OSError):
            self._transcript_file.unlink(missing_ok=True)
        self._publish({"type": "history", "segments": [], "status": self.status})

    def _publish(self, message: dict) -> None:
        self.broadcaster.publish(self.config.id, message)

    def _set_status(self, status: str) -> None:
        self.status = status
        self._publish({"type": "status", "status": status})

    def _on_transcriber_state_change(self) -> None:
        transcriber = self._transcriber
        if transcriber is None or self.status in ("stopped", "idle"):
            return
        if transcriber.stats.last_error:
            self._last_error = transcriber.stats.last_error
        if transcriber.stats.rotating:
            new_status = "rotating"
        elif transcriber.active is None:
            new_status = "error"
        else:
            new_status = "live"
        if new_status != self.status:
            self._set_status(new_status)

    def _keep_stats(self, transcriber: LiveTranscriber) -> None:
        for name in self._previous_stats:
            self._previous_stats[name] += getattr(transcriber.stats, name)

    def _schedule(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    @staticmethod
    def _smooth(current: float | None, sample: float) -> float:
        return sample if current is None else current * (1 - SMOOTHING) + sample * SMOOTHING

    def estimated_cost_usd(self) -> float:
        transcription = self.audio_seconds / 60 * self.settings.transcription_usd_per_minute
        translation = (
            self.translation_input_tokens * self.settings.translation_usd_per_million_input_tokens
            + self.translation_output_tokens * self.settings.translation_usd_per_million_output_tokens
        ) / 1_000_000
        return transcription + translation

    def snapshot(self) -> dict:
        stats = dict(self._previous_stats)
        if self._transcriber is not None:
            for name in stats:
                stats[name] += getattr(self._transcriber.stats, name)
        return {
            "id": self.config.id,
            "name": self.config.name,
            "description": self.config.description,
            "status": self.status,
            "source_connected": self.has_source,
            "source_kind": self.source_kind,
            "audio_seconds": round(self.audio_seconds, 1),
            "segments": len(self.segments),
            "subscribers": self.broadcaster.subscriber_count(self.config.id),
            "sessions_opened": stats["sessions_opened"],
            "rotations": stats["rotations"],
            "errors": stats["errors"],
            "last_error": self._last_error,
            "caption_lag_seconds": round(self.caption_lag_seconds, 2) if self.caption_lag_seconds is not None else None,
            "translation_latency_ms": round(self.translation_latency_ms) if self.translation_latency_ms is not None else None,
            "estimated_cost_usd": round(self.estimated_cost_usd(), 4),
            "source_language": self.source_language,
            "last_caption": self._last_caption(),
        }

    def _last_caption(self) -> dict | None:
        """Latest visible sentence, so production can check at a glance what the room is hearing."""
        for segment in sorted(self.segments.values(), key=lambda item: item.id, reverse=True):
            if segment.original:
                return {"original": segment.original, "translations": segment.translations}
        return None

    def history(self) -> list[dict]:
        return [segment.to_dict() for segment in sorted(self.segments.values(), key=lambda item: item.id)]

    def export(self, format_name: str, language: str) -> str:
        return EXPORTERS[format_name](self.segments.values(), language)
