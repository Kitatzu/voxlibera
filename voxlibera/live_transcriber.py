"""Continuous transcription over gemini-3.5-transcribe-live with seamless session rotation.

A Live API session lasts ~590 s. The server sends GoAway ~50 s before closing and
aborts with 1008 if the client doesn't close. Rotation:

1. GoAway (or proactive timer) -> open a second session and feed audio to both.
2. The old session keeps producing captions until its next final transcript,
   then it is closed and the new one takes over.
3. The new session's first utterance repeats a few seconds already transcribed;
   those words are stripped by comparing with the old session's last final.

If the old session never produces a final, the handoff is forced before the
deadline, flushing its pending interim text as final.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from voxlibera.text_utils import strip_overlap

logger = logging.getLogger(__name__)

AUDIO_MIME_TYPE = "audio/pcm;rate=16000"
AUDIO_QUEUE_CHUNKS = 600  # 60 s of 100 ms chunks buffered per session at most
PROACTIVE_ROTATION_SECONDS = 540
MAX_HANDOFF_WAIT_SECONDS = 30
RECONNECT_BACKOFF_SECONDS = (1, 2, 5, 10)


@dataclass
class TranscriberStats:
    sessions_opened: int = 0
    rotations: int = 0
    errors: int = 0
    last_error: str | None = None
    last_transcript_at: float | None = None
    rotating: bool = False


class _LiveSession:
    """One Gemini Live connection with its own audio queue and send/receive tasks."""

    def __init__(self, number: int, client: genai.Client, model: str,
                 config: types.LiveConnectConfig) -> None:
        self.number = number
        self.client = client
        self.model = model
        self.config = config
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=AUDIO_QUEUE_CHUNKS)
        self.opened_at = time.monotonic()
        self.last_interim_text = ""
        self.overlap_reference: str | None = None
        self.closed = False
        self._connection_context = None
        self._session = None
        self._tasks: list[asyncio.Task] = []

    async def open(self, on_message: Callable, on_failure: Callable) -> None:
        self._connection_context = self.client.aio.live.connect(model=self.model, config=self.config)
        self._session = await self._connection_context.__aenter__()
        self.opened_at = time.monotonic()
        self._tasks = [
            asyncio.create_task(self._send_loop(on_failure)),
            asyncio.create_task(self._receive_loop(on_message, on_failure)),
        ]

    def feed(self, chunk: bytes) -> None:
        if self.closed:
            return
        if self.audio_queue.full():
            self.audio_queue.get_nowait()  # drop the oldest audio rather than block the room
        self.audio_queue.put_nowait(chunk)

    async def _send_loop(self, on_failure: Callable) -> None:
        try:
            while True:
                chunk = await self.audio_queue.get()
                await self._session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type=AUDIO_MIME_TYPE)
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await on_failure(self, error)

    async def _receive_loop(self, on_message: Callable, on_failure: Callable) -> None:
        try:
            while True:
                async for message in self._session.receive():
                    await on_message(self, message)
                if self.closed:
                    return
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await on_failure(self, error)

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        current = asyncio.current_task()
        for task in self._tasks:
            if task is not current:
                task.cancel()
        if self._connection_context is not None:
            with contextlib.suppress(Exception):
                await self._connection_context.__aexit__(None, None, None)


@dataclass
class TranscriptCallbacks:
    on_interim: Callable[[str, str | None], None]
    on_final: Callable[[str, str | None], None]
    on_state_change: Callable[[], None] = field(default=lambda: None)


class LiveTranscriber:
    def __init__(self, client: genai.Client, model: str, glossary: list[str],
                 callbacks: TranscriptCallbacks) -> None:
        self.client = client
        self.model = model
        self.callbacks = callbacks
        self.stats = TranscriberStats()
        self.config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            input_audio_transcription=types.AudioTranscriptionConfig(
                custom_vocabulary=glossary[:1000] or None,
                mode="VERBATIM",
            ),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=300,
                )
            ),
        )
        self.active: _LiveSession | None = None
        self.incoming: _LiveSession | None = None
        self._session_counter = 0
        self._handoff_deadline: float | None = None
        self._lock = asyncio.Lock()
        self._supervisor: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self.active = await self._open_session_with_retry()
        self._supervisor = asyncio.create_task(self._supervise())

    def feed(self, chunk: bytes) -> None:
        for session in (self.active, self.incoming):
            if session is not None:
                session.feed(chunk)

    async def stop(self) -> None:
        self._stopping = True
        if self._supervisor:
            self._supervisor.cancel()
        for session in (self.incoming, self.active):
            if session is not None:
                await session.close()
        self.active = None
        self.incoming = None

    # --- session lifecycle -------------------------------------------------

    async def _open_session(self) -> _LiveSession:
        self._session_counter += 1
        session = _LiveSession(self._session_counter, self.client, self.model, self.config)
        await session.open(self._handle_message, self._handle_failure)
        self.stats.sessions_opened += 1
        logger.info("Opened live session #%s", session.number)
        return session

    async def _open_session_with_retry(self) -> _LiveSession:
        attempt = 0
        while True:
            try:
                return await self._open_session()
            except Exception as error:
                self._record_error(f"connect failed: {error}")
                delay = RECONNECT_BACKOFF_SECONDS[min(attempt, len(RECONNECT_BACKOFF_SECONDS) - 1)]
                attempt += 1
                await asyncio.sleep(delay)

    async def _begin_rotation(self, reason: str) -> None:
        if self.incoming is not None or self._stopping or self.stats.rotating:
            return
        logger.info("Rotating live session (%s)", reason)
        self.stats.rotating = True
        self._handoff_deadline = time.monotonic() + MAX_HANDOFF_WAIT_SECONDS
        self.callbacks.on_state_change()
        try:
            self.incoming = await self._open_session()
        except Exception as error:
            self._record_error(f"rotation connect failed: {error}")
            self.stats.rotating = False
            self._handoff_deadline = None

    async def _complete_handoff(self, overlap_reference: str) -> None:
        async with self._lock:
            if self.incoming is None:
                return
            previous, self.active, self.incoming = self.active, self.incoming, None
            self.active.overlap_reference = overlap_reference
            self.stats.rotations += 1
            self.stats.rotating = False
            self._handoff_deadline = None
        self.callbacks.on_state_change()
        if previous is not None:
            await previous.close()
            logger.info("Handoff complete: session #%s -> #%s", previous.number, self.active.number)

    async def _supervise(self) -> None:
        while not self._stopping:
            await asyncio.sleep(1)
            active = self.active
            if active is None:
                continue
            age = time.monotonic() - active.opened_at
            if age > PROACTIVE_ROTATION_SECONDS and self.incoming is None:
                await self._begin_rotation("proactive timer")
            if self._handoff_deadline and time.monotonic() > self._handoff_deadline and self.incoming:
                pending = active.last_interim_text
                if pending:
                    self.callbacks.on_final(pending, None)
                await self._complete_handoff(pending)

    # --- message handling --------------------------------------------------

    async def _handle_message(self, session: _LiveSession, message: types.LiveServerMessage) -> None:
        if message.go_away is not None and session is self.active:
            logger.info("GoAway on session #%s: %s", session.number, message.go_away.time_left)
            asyncio.create_task(self._begin_rotation("go_away"))

        content = message.server_content
        if content is None or session is not self.active:
            return  # the incoming session stays silent until handoff

        interim = content.interim_input_transcription
        if interim is not None and interim.text:
            text = self._without_overlap(session, interim.text)
            session.last_interim_text = text
            self.stats.last_transcript_at = time.monotonic()
            if text:
                self.callbacks.on_interim(text, interim.language_code)

        final = content.input_transcription
        if final is not None and final.text:
            text = self._without_overlap(session, final.text)
            session.overlap_reference = None  # only the first utterance after handoff overlaps
            session.last_interim_text = ""
            self.stats.last_transcript_at = time.monotonic()
            if text:
                self.callbacks.on_final(text, final.language_code)
            if self.incoming is not None:
                await self._complete_handoff(text or final.text)

    def _without_overlap(self, session: _LiveSession, text: str) -> str:
        if not session.overlap_reference:
            return text
        return strip_overlap(session.overlap_reference, text)

    async def _handle_failure(self, session: _LiveSession, error: Exception) -> None:
        if session.closed or self._stopping:
            return
        self._record_error(f"session #{session.number}: {error}")
        await session.close()
        if session is self.incoming:
            self.incoming = None
            self.stats.rotating = False
            self._handoff_deadline = None
            return
        if session is self.active:
            if session.last_interim_text:
                self.callbacks.on_final(session.last_interim_text, None)
            if self.incoming is not None:
                await self._complete_handoff(session.last_interim_text)
            else:
                self.active = None
                self.callbacks.on_state_change()
                self.active = await self._open_session_with_retry()
                self.callbacks.on_state_change()

    def _record_error(self, description: str) -> None:
        logger.warning("Transcriber error: %s", description)
        self.stats.errors += 1
        self.stats.last_error = description[:300]
        self.callbacks.on_state_change()
