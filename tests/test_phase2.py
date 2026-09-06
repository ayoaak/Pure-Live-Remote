from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

from PIL import Image

_TEST_DATA = tempfile.mkdtemp(prefix="pure-live-remote-test-")
os.environ["DATA_DIR"] = _TEST_DATA
os.environ["PUBLIC_BASE_URL"] = "http://127.0.0.1:35455"

from app.db import RoomDatabase  # noqa: E402
from app.media import normalize_avatar_bytes  # noqa: E402
from app.playlist import build_playlist  # noqa: E402
from app.schemas import RoomCreate, RoomUpdate  # noqa: E402


def test_room_crud_and_playlist_media_attributes() -> None:
    db = RoomDatabase(Path(_TEST_DATA) / "test.db")
    db.initialize()
    room = db.create_room(RoomCreate(platform="bilibili", room_id="123", name="主播A", group_name="测试"))
    assert room["platform"] == "bilibili"
    assert room["enabled"] is True

    playlist = build_playlist(db.list_rooms(enabled_only=True), "http://127.0.0.1:35455")
    assert 'tvg-logo="http://127.0.0.1:35455/media/logo/' in playlist
    assert 'tvg-cover="http://127.0.0.1:35455/media/cover/' in playlist
    assert "主播A" in playlist

    updated = db.update_room(room["uuid"], RoomUpdate(custom_name="主播A-改", enabled=False))
    assert updated is not None and updated["custom_name"] == "主播A-改"
    assert db.list_rooms(enabled_only=True) == []

    db.update_media(
        room["uuid"],
        current_cover_path="/tmp/current.jpg",
        last_live_cover_path="/tmp/last.jpg",
        last_live_cover_url="https://example.com/last.jpg",
    )
    db.update_media(room["uuid"], clear_current_cover=True)
    media_state = db.get_room(room["uuid"])
    assert media_state is not None
    assert media_state["current_cover_path"] == ""
    assert media_state["last_live_cover_path"] == "/tmp/last.jpg"
    assert media_state["last_live_cover_url"] == "https://example.com/last.jpg"

    assert db.delete_room(room["uuid"]) is True
    assert db.get_room(room["uuid"]) is None


def test_avatar_is_normalized_to_256px_circle_png(tmp_path: Path) -> None:
    source = Image.new("RGB", (500, 300), (255, 0, 0))
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG")
    destination = tmp_path / "avatar.png"
    normalize_avatar_bytes(buffer.getvalue(), destination)

    with Image.open(destination) as image:
        assert image.size == (256, 256)
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0
        assert image.getpixel((128, 128))[3] == 255
