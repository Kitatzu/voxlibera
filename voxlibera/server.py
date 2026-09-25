"""FastAPI app: REST + WebSocket API and the static web frontend."""

import argparse
import asyncio
import contextlib
import logging
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from google import genai
from pydantic import BaseModel

from voxlibera.broadcaster import Broadcaster
from voxlibera.config import Settings, load_rooms
from voxlibera.exporters import EXPORTERS, MEDIA_TYPES
from voxlibera.room import Room

logger = logging.getLogger("voxlibera")

AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".opus", ".m4a", ".flac", ".webm", ".pcm"}
CLOSE_ROOM_NOT_FOUND = 4404
CLOSE_UNAUTHORIZED = 4401
CLOSE_SOURCE_BUSY = 4409
CLOSE_SOURCE_STOPPED = 4410


class SimulateRequest(BaseModel):
    sample: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    broadcaster = Broadcaster()
    rooms: dict[str, Room] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Get a key at https://aistudio.google.com/apikey and "
                "put GEMINI_API_KEY=your-key in a .env file in the project folder."
            )
        client = genai.Client()  # reads GEMINI_API_KEY
        for room_config in load_rooms(settings.rooms_file):
            rooms[room_config.id] = Room(room_config, settings, client, broadcaster)
        logger.info("Serving rooms: %s", ", ".join(rooms))
        yield
        await asyncio.gather(*(room.stop_source() for room in rooms.values()), return_exceptions=True)

    app = FastAPI(title="Vox Libera", lifespan=lifespan)
    app.state.rooms = rooms

    def get_room(room_id: str) -> Room:
        room = rooms.get(room_id)
        if room is None:
            raise HTTPException(status_code=404, detail=f"Unknown room '{room_id}'")
        return room

    def is_admin(key: str | None) -> bool:
        if not settings.admin_key:
            return True
        return key is not None and secrets.compare_digest(key.encode(), settings.admin_key.encode())

    def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
        if not is_admin(x_admin_key):
            raise HTTPException(status_code=401, detail="Admin key required")

    admin_only = [Depends(require_admin)]

    @app.get("/healthz")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/api/rooms")
    async def list_rooms() -> dict:
        return {
            "languages": ["original", *settings.target_languages],
            "admin_required": bool(settings.admin_key),
            "rooms": [room.snapshot() for room in rooms.values()],
        }

    @app.get("/api/samples")
    async def list_samples() -> dict:
        samples = []
        if settings.samples_dir.exists():
            samples = sorted(
                path.name for path in settings.samples_dir.iterdir()
                if path.suffix.lower() in AUDIO_EXTENSIONS
            )
        return {"samples": samples}

    @app.post("/api/rooms/{room_id}/simulate", dependencies=admin_only)
    async def simulate(room_id: str, request: SimulateRequest) -> dict:
        room = get_room(room_id)
        sample_path = (settings.samples_dir / request.sample).resolve()
        if sample_path.parent != settings.samples_dir.resolve() or not sample_path.is_file():
            raise HTTPException(status_code=404, detail="Unknown sample")
        try:
            started = await room.start_simulation(sample_path)
        except Exception as error:
            raise HTTPException(status_code=502, detail=f"Could not start: {error}") from error
        if not started:
            raise HTTPException(status_code=409, detail="Room already has an audio source")
        return {"ok": True}

    @app.post("/api/rooms/{room_id}/stop", dependencies=admin_only)
    async def stop(room_id: str) -> dict:
        await get_room(room_id).stop_source()
        return {"ok": True}

    @app.post("/api/rooms/{room_id}/reset", dependencies=admin_only)
    async def reset(room_id: str) -> dict:
        room = get_room(room_id)
        if room.has_source:
            raise HTTPException(status_code=409, detail="Stop the audio source before resetting")
        room.reset_transcript()
        return {"ok": True}

    @app.get("/api/rooms/{room_id}/export")
    async def export(room_id: str, format: str = Query("srt"), lang: str = Query("original")) -> Response:
        room = get_room(room_id)
        if format not in EXPORTERS:
            raise HTTPException(status_code=400, detail=f"format must be one of {sorted(EXPORTERS)}")
        if lang != "original" and lang not in settings.target_languages:
            raise HTTPException(status_code=400, detail="Unknown language")
        filename = f"{room_id}-{lang}.{format}"
        return Response(
            content=room.export(format, lang),
            media_type=f"{MEDIA_TYPES[format]}; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.websocket("/ws/rooms/{room_id}")
    async def audience(websocket: WebSocket, room_id: str) -> None:
        room = rooms.get(room_id)
        await websocket.accept()
        if room is None:
            await websocket.close(code=CLOSE_ROOM_NOT_FOUND, reason="Unknown room")
            return
        subscription = broadcaster.subscribe(room_id)

        async def forward_events() -> None:
            await websocket.send_json({"type": "history", "segments": room.history(), "status": room.status})
            while (message := await subscription.next_message()) is not None:
                await websocket.send_json(message)

        async def wait_for_disconnect() -> None:
            while True:
                await websocket.receive_text()  # raises once the viewer leaves

        tasks = [asyncio.create_task(forward_events()), asyncio.create_task(wait_for_disconnect())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            broadcaster.unsubscribe(room_id, subscription)
            with contextlib.suppress(Exception):
                await websocket.close()

    @app.websocket("/ws/ingest/{room_id}")
    async def ingest(websocket: WebSocket, room_id: str, token: str | None = None) -> None:
        room = rooms.get(room_id)
        await websocket.accept()
        if room is None:
            await websocket.close(code=CLOSE_ROOM_NOT_FOUND, reason="Unknown room")
            return
        if not is_admin(token):
            await websocket.close(code=CLOSE_UNAUTHORIZED, reason="Invalid token")
            return
        try:
            generation = await room.start_source("websocket")
        except Exception as error:
            await websocket.close(code=1011, reason=f"Could not start transcription: {error}"[:120])
            return
        if not generation:
            await websocket.close(code=CLOSE_SOURCE_BUSY, reason="Room already has an audio source")
            return
        try:
            while True:
                chunk = await websocket.receive_bytes()
                if not room.is_current_source(generation):
                    # Stopped from the dashboard (or replaced): hang up so the tab stops sending.
                    await websocket.close(code=CLOSE_SOURCE_STOPPED, reason="Stopped from the dashboard")
                    return
                room.feed_audio(chunk, generation)
        except (WebSocketDisconnect, RuntimeError, KeyError):
            pass
        finally:
            if room.is_current_source(generation):
                await room.stop_source()

    if settings.web_dir.exists():
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env support (KEY=VALUE lines); real environment variables win."""
    if not os.path.isfile(path):
        return
    with open(path, "rb") as file:
        raw = file.read()
    # PowerShell 5.1 `echo > .env` writes UTF-16 with a BOM.
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    for line in raw.decode(encoding).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    import uvicorn

    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the Vox Libera server")
    parser.add_argument("--host", default=os.environ.get("VOXLIBERA_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("VOXLIBERA_PORT", "8000")))
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(), host=arguments.host, port=arguments.port)


if __name__ == "__main__":
    main()
