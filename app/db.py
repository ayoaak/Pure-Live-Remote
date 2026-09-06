from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .config import DB_PATH
from .schemas import RoomCreate, RoomUpdate


SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL,
    room_id TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    custom_name TEXT NOT NULL DEFAULT '',
    group_name TEXT NOT NULL DEFAULT 'Live',
    avatar_url TEXT NOT NULL DEFAULT '',
    current_cover_url TEXT NOT NULL DEFAULT '',
    last_live_cover_url TEXT NOT NULL DEFAULT '',
    logo_path TEXT NOT NULL DEFAULT '',
    current_cover_path TEXT NOT NULL DEFAULT '',
    last_live_cover_path TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    preferred_quality TEXT NOT NULL DEFAULT 'best',
    preferred_line TEXT NOT NULL DEFAULT 'auto',
    play_mode TEXT NOT NULL DEFAULT 'auto',
    last_status TEXT NOT NULL DEFAULT 'unknown',
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(platform, room_id)
);
CREATE INDEX IF NOT EXISTS idx_rooms_enabled_sort
ON rooms(enabled, sort_order, id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class RoomDatabase:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        return item

    def list_rooms(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM rooms"
        params: tuple[Any, ...] = ()
        if enabled_only:
            sql += " WHERE enabled = ?"
            params = (1,)
        sql += " ORDER BY sort_order ASC, id ASC"
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row(row) for row in rows if row is not None]

    def get_room(self, room_uuid: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM rooms WHERE uuid = ?", (room_uuid,)).fetchone()
        return self._row(row)

    def create_room(self, payload: RoomCreate) -> dict[str, Any]:
        now = _now()
        room_uuid = uuid4().hex
        values = payload.model_dump()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO rooms (
                    uuid, platform, room_id, source_url, name, custom_name,
                    group_name, avatar_url, current_cover_url, enabled,
                    sort_order, preferred_quality, preferred_line, play_mode,
                    last_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    room_uuid,
                    values["platform"].lower(),
                    values["room_id"],
                    values["source_url"],
                    values["name"],
                    values["custom_name"],
                    values["group_name"] or "Live",
                    values["avatar_url"],
                    values["current_cover_url"],
                    int(values["enabled"]),
                    values["sort_order"],
                    values["preferred_quality"],
                    values["preferred_line"],
                    values["play_mode"],
                    values["last_status"],
                    now,
                    now,
                ),
            )
        room = self.get_room(room_uuid)
        assert room is not None
        return room

    def update_room(self, room_uuid: str, payload: RoomUpdate) -> dict[str, Any] | None:
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return self.get_room(room_uuid)
        if "enabled" in changes:
            changes["enabled"] = int(bool(changes["enabled"]))
        changes["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in changes)
        values = list(changes.values()) + [room_uuid]
        with self.connection() as conn:
            cursor = conn.execute(f"UPDATE rooms SET {assignments} WHERE uuid = ?", values)
            if cursor.rowcount == 0:
                return None
        return self.get_room(room_uuid)

    def delete_room(self, room_uuid: str) -> bool:
        with self.connection() as conn:
            cursor = conn.execute("DELETE FROM rooms WHERE uuid = ?", (room_uuid,))
            return cursor.rowcount > 0

    def update_media(
        self,
        room_uuid: str,
        *,
        logo_path: str | None = None,
        current_cover_path: str | None = None,
        last_live_cover_path: str | None = None,
        last_live_cover_url: str | None = None,
        clear_current_cover: bool = False,
    ) -> dict[str, Any] | None:
        changes: dict[str, Any] = {"updated_at": _now()}
        if logo_path is not None:
            changes["logo_path"] = logo_path
        if current_cover_path is not None:
            changes["current_cover_path"] = current_cover_path
        if last_live_cover_path is not None:
            changes["last_live_cover_path"] = last_live_cover_path
        if last_live_cover_url is not None:
            changes["last_live_cover_url"] = last_live_cover_url
        if clear_current_cover:
            changes["current_cover_path"] = ""
            changes["current_cover_url"] = ""
        assignments = ", ".join(f"{key} = ?" for key in changes)
        values = list(changes.values()) + [room_uuid]
        with self.connection() as conn:
            cursor = conn.execute(f"UPDATE rooms SET {assignments} WHERE uuid = ?", values)
            if cursor.rowcount == 0:
                return None
        return self.get_room(room_uuid)
