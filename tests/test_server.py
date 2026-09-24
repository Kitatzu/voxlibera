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
