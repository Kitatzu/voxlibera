# Vox Libera — Server ↔ Client Protocol

All endpoints are served by the FastAPI server (default `http://localhost:8000`).

## Admin key

If the server sets `VOXLIBERA_ADMIN_KEY`, `GET /api/rooms` returns `"admin_required": true` and:

- `POST` endpoints (`simulate`, `stop`, `reset`) need the header `X-Admin-Key: <key>` (401 otherwise).
- The audio ingest WebSocket needs `?token=<key>` (closed with 4401 otherwise).

Reading captions, rooms and exports never needs the key.

## REST

### `GET /api/rooms`

```json
{
  "languages": ["original", "es", "en", "pt"],
  "rooms": [
    {
      "id": "main-stage",
      "name": "Main Stage",
      "description": "Keynotes",
      "status": "idle | starting | live | rotating | error | stopped",
      "source_connected": true,
      "source_kind": "websocket | simulation | null",
      "audio_seconds": 312.4,
      "segments": 58,
      "subscribers": 12,
      "sessions_opened": 2,
      "rotations": 1,
      "errors": 0,
      "last_error": null,
      "caption_lag_seconds": 1.2,
      "translation_latency_ms": 1350,
      "estimated_cost_usd": 0.041
    }
  ]
}
```

### `POST /api/rooms/{room_id}/simulate`

Body: `{"sample": "talk-en.opus"}` (a file name from `GET /api/samples`).
Starts feeding the sample file into the room at real-time speed. Returns `{"ok": true}`.

### `POST /api/rooms/{room_id}/stop`

Stops the current source (simulation or websocket) and closes the Gemini session.

### `GET /api/samples`

`{"samples": ["talk-en.opus", "talk-es.opus"]}`

### `GET /api/rooms/{room_id}/export?format=srt|vtt|txt&lang=original|es|en|pt`

Downloads the full transcript of the room so far as a file.

## WebSocket — audience: `/ws/rooms/{room_id}`

On connect the server sends the history, then live events. All messages are JSON.

```json
{"type": "history", "segments": [Segment, ...], "status": "live"}
{"type": "interim", "text": "words the speaker is saying right now", "language": "en"}
{"type": "segment", "segment": Segment}
{"type": "status", "status": "live"}
```

`Segment`:

```json
{
  "id": 17,
  "start": 83.2,
  "end": 87.9,
  "source_language": "en",
  "original": "APIs are contract driven interfaces.",
  "translations": {"es": "Las APIs son interfaces basadas en contratos.", "en": "...", "pt": "..."},
  "final": false
}
```

Rules for clients:

- **Upsert segments by `id`.** The same segment is sent again when its translations arrive
  and again if the final transcript corrects it.
- `translations` can be `{}` while the translation is in flight: show `original` meanwhile.
- **Hide segments whose `original` is empty.** That happens when the final transcript merged the
  sentence into a previous one (which is re-sent with the merged text).
- `interim` is the not-yet-committed tail of what the speaker is saying, in the source language.
  It replaces the previous interim (never append). Show it only when the viewer picked `original`,
  or dimmed while waiting for translations.
- `start` / `end` are seconds since the room's audio started.

## WebSocket — audio source: `/ws/ingest/{room_id}?token=INGEST_TOKEN`

Binary frames of raw PCM, 16-bit little-endian, 16 kHz, mono (ideally 100 ms = 3200 bytes each).
One source per room; a second source is rejected with close code 4409.
