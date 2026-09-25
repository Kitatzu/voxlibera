import pytest
from fastapi.testclient import TestClient

from voxlibera.config import Settings
from voxlibera.server import create_app


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-used")
    rooms_file = tmp_path / "rooms.yaml"
    rooms_file.write_text("rooms:\n  - id: main\n    name: Main\n", encoding="utf-8")
    return Settings(rooms_file=rooms_file, data_dir=tmp_path / "data", samples_dir=tmp_path / "samples",
                    web_dir=tmp_path / "web")


def test_open_server_does_not_require_admin(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/rooms").json()["admin_required"] is False
        assert client.post("/api/rooms/main/stop").status_code == 200


def test_admin_actions_require_the_key(settings):
    settings.admin_key = "secret"
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/rooms").json()["admin_required"] is True
        assert client.post("/api/rooms/main/stop").status_code == 401
        assert client.post("/api/rooms/main/stop", headers={"X-Admin-Key": "wrong"}).status_code == 401
        assert client.post("/api/rooms/main/stop", headers={"X-Admin-Key": "secret"}).status_code == 200
        response = client.post("/api/rooms/main/simulate", json={"sample": "../rooms.yaml"},
                               headers={"X-Admin-Key": "secret"})
        assert response.status_code == 404  # path traversal rejected


def test_ingest_rejects_wrong_key(settings):
    settings.admin_key = "secret"
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/ingest/main?token=wrong") as websocket:
            message = websocket.receive()
            assert message["type"] == "websocket.close"
            assert message["code"] == 4401


def test_stale_source_audio_is_ignored_after_a_new_source_starts(settings, monkeypatch):
    # Real bug: a broadcast tab stopped from the dashboard kept its socket open and its audio
    # was mixed into the next broadcast. Each source now has a generation; stale audio is dropped.
    from voxlibera.room import Room

    async def fake_start(self):
        return None

    monkeypatch.setattr("voxlibera.live_transcriber.LiveTranscriber.start", fake_start)
    monkeypatch.setattr("voxlibera.live_transcriber.LiveTranscriber.stop", fake_start)
    with TestClient(create_app(settings)) as client:
        room: Room = client.app.state.rooms["main"]
        first_generation = client.portal.call(room.start_source, "websocket")
        client.portal.call(room.stop_source)
        second_generation = client.portal.call(room.start_source, "websocket")
        assert first_generation and second_generation and first_generation != second_generation

        room.feed_audio(b"\x00" * 3200, first_generation)   # zombie tab
        room.feed_audio(b"\x00" * 3200, second_generation)  # current tab
        assert room.audio_bytes == 3200
        assert not room.is_current_source(first_generation)
        assert room.is_current_source(second_generation)


def test_audience_needs_no_key_and_gets_history(settings):
    settings.admin_key = "secret"
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/rooms/main") as websocket:
            assert websocket.receive_json() == {"type": "history", "segments": [], "status": "idle"}


def test_export_returns_attachment(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/rooms/main/export?format=srt&lang=es")
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
