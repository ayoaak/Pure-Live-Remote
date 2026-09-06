from __future__ import annotations

from typing import Any


def _escape(value: str) -> str:
    return value.replace('"', "'").replace("\r", " ").replace("\n", " ").strip()


def build_playlist(rooms: list[dict[str, Any]], base_url: str) -> str:
    base_url = base_url.rstrip("/")
    lines = ["#EXTM3U"]
    for room in rooms:
        room_uuid = room["uuid"]
        display_name = room.get("custom_name") or room.get("name") or f"{room['platform']}:{room['room_id']}"
        group_name = room.get("group_name") or room.get("platform") or "Live"
        logo_url = f"{base_url}/media/logo/{room_uuid}.png"
        cover_url = f"{base_url}/media/cover/{room_uuid}"
        attributes = (
            f'tvg-id="{_escape(room_uuid)}" '
            f'tvg-name="{_escape(display_name)}" '
            f'tvg-logo="{_escape(logo_url)}" '
            f'tvg-cover="{_escape(cover_url)}" '
            f'group-title="{_escape(group_name)}" '
            f'platform="{_escape(room.get("platform", ""))}"'
        )
        lines.append(f"#EXTINF:-1 {attributes},{_escape(display_name)}")
        lines.append(f"{base_url}/play/{room_uuid}")
    return "\n".join(lines) + "\n"
