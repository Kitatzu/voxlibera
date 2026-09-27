# Vox Libera — Server ↔ Client Protocol

All endpoints are served by the FastAPI server (default `http://localhost:8000`).

## Admin key

If the server sets `VOXLIBERA_ADMIN_KEY`, `GET /api/rooms` returns `"admin_required": true` and:

- `POST` endpoints (`simulate`, `stop`, `reset`) need the header `X-Admin-Key: <key>` (401 otherwise).
- The audio ingest WebSocket needs a correct token in its first message, see below (closed with
  4401 otherwise).

Reading captions, rooms and exports never needs the key.

If the server binds to a non-loopback host with no `VOXLIBERA_ADMIN_KEY` set, it refuses to start
unless `VOXLIBERA_ALLOW_OPEN=1` is set (intended for a closed venue network only).

## REST

### `GET /api/rooms`

Metrics that don't exist yet are `null` (e.g. `translation_latency_ms` before the first translation,
`last_caption` before anything was heard). Clients must handle that.

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
      "estimated_cost_usd": 0.041,
      "source_language": "en",
      "last_caption": {"original": "Latest sentence heard.", "translations": {"es": "Última oración escuchada."}}
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

## WebSocket — audio source: `/ws/ingest/{room_id}`

The token is never sent as a query parameter (it would leak into logs, browser history and proxy
access logs). Instead, the client's **first message** must be JSON text:

```json
{"type": "auth", "token": "INGEST_TOKEN"}
```

Send this message even when the server has no admin key configured (`admin_required: false`):
in that case, send `"token": ""`. The server waits up to a few seconds for it; a missing, wrong,
or late auth message closes the connection with code 4401.

After a successful auth message, every following message must be a binary frame of raw PCM,
16-bit little-endian, 16 kHz, mono (ideally 100 ms = 3200 bytes each). One source per room; a
second source is rejected with close code 4409.

Limits, to protect the server from a misbehaving or malicious client:

- **Message size**: frames larger than 64 KiB are rejected and the connection is closed with the
  standard code 1009 (real audio chunks are ~3,200 bytes, so this leaves generous headroom).
- **Data rate**: sustained throughput above roughly 3x real-time PCM (96,000 bytes/second,
  averaged with some burst tolerance) closes the connection with app code 4429.
