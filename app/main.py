from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_COVER_PATH,
    DEFAULT_LOGO_PATH,
    PORT,
    PUBLIC_BASE_URL,
    ensure_data_dirs,
)
from .db import RoomDatabase
from .media import MediaError, cache_avatar, cache_cover, ensure_default_media, existing_or_default, remove_room_media
from .playlist import build_playlist
from .schemas import RoomCreate, RoomUpdate

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
db = RoomDatabase()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_data_dirs()
    ensure_default_media()
    db.initialize()
    yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, docs_url="/docs", redoc_url=None, lifespan=lifespan)


def public_base_url(request: Request) -> str:
    return PUBLIC_BASE_URL or str(request.base_url).rstrip("/")


async def refresh_room_media(room: dict) -> tuple[dict, list[str]]:
    errors: list[str] = []
    logo_path: str | None = None
    current_cover_path: str | None = None
    last_cover_path: str | None = None
    last_cover_url: str | None = None

    if room.get("avatar_url"):
        try:
            logo_path = await cache_avatar(room["uuid"], room["avatar_url"])
        except Exception as exc:  # preserve media diagnostics in admin/API.
            errors.append(f"avatar: {exc}")

    cover_url = room.get("current_cover_url", "")
    if cover_url:
        try:
            is_live = room.get("last_status") == "live"
            current_cover_path, last_cover_path = await cache_cover(room["uuid"], cover_url, live=is_live)
            last_cover_url = cover_url
        except Exception as exc:
            errors.append(f"cover: {exc}")

    updated = db.update_media(
        room["uuid"],
        logo_path=logo_path,
        current_cover_path=current_cover_path,
        last_live_cover_path=last_cover_path,
        last_live_cover_url=last_cover_url,
        clear_current_cover=room.get("last_status") in {"offline", "replay", "banned"},
    )
    assert updated is not None
    if errors:
        updated = db.update_room(room["uuid"], RoomUpdate(last_error="; ".join(errors))) or updated
    else:
        updated = db.update_room(room["uuid"], RoomUpdate(last_error="")) or updated
    return updated, errors


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": APP_NAME, "version": APP_VERSION, "admin": "/admin", "playlist": "/playlist.m3u", "branch_policy": "Unverified changes belong to Test before promotion to main."}


@app.get("/health", tags=["system"])
def health() -> dict[str, object]:
    try:
        room_count = len(db.list_rooms())
        database = "ok"
    except Exception as exc:
        room_count = 0
        database = f"error: {exc}"
    return {"status": "ok" if database == "ok" else "degraded", "service": APP_NAME, "version": APP_VERSION, "port": PORT, "public_base_url": PUBLIC_BASE_URL, "database": database, "rooms": room_count}


@app.get("/playlist.m3u", response_class=PlainTextResponse, tags=["playlist"])
def playlist(request: Request) -> PlainTextResponse:
    content = build_playlist(db.list_rooms(enabled_only=True), public_base_url(request))
    return PlainTextResponse(content, media_type="audio/x-mpegurl; charset=utf-8", headers={"Cache-Control": "no-store"})


@app.get("/play/{room_uuid}", tags=["playback"])
def play_placeholder(room_uuid: str) -> None:
    room = db.get_room(room_uuid)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    raise HTTPException(status_code=501, detail="platform resolver is scheduled for Phase 3; room management/M3U are active")


@app.get("/media/logo/{room_uuid}.png", tags=["media"])
def room_logo(room_uuid: str) -> FileResponse:
    room = db.get_room(room_uuid)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    path = existing_or_default(room.get("logo_path", ""), DEFAULT_LOGO_PATH)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=300"})


@app.get("/media/cover/{room_uuid}", tags=["media"])
def room_cover(room_uuid: str) -> FileResponse:
    room = db.get_room(room_uuid)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    effective = room.get("current_cover_path") if room.get("last_status") == "live" else ""
    effective = effective or room.get("last_live_cover_path", "")
    path = existing_or_default(effective, DEFAULT_COVER_PATH)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=60"})


@app.get("/api/rooms", tags=["rooms"])
def api_list_rooms() -> list[dict]:
    return db.list_rooms()


@app.post("/api/rooms", status_code=status.HTTP_201_CREATED, tags=["rooms"])
async def api_create_room(payload: RoomCreate) -> dict:
    try:
        room = db.create_room(payload)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="platform + room_id already exists") from exc
    room, media_errors = await refresh_room_media(room)
    return {"room": room, "media_errors": media_errors}


@app.get("/api/rooms/{room_uuid}", tags=["rooms"])
def api_get_room(room_uuid: str) -> dict:
    room = db.get_room(room_uuid)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    return room


@app.patch("/api/rooms/{room_uuid}", tags=["rooms"])
async def api_update_room(room_uuid: str, payload: RoomUpdate) -> dict:
    room = db.update_room(room_uuid, payload)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    # Status changes to offline/replay/banned must keep last_live_cover but stop
    # exposing a stale current-session file as the active cover.
    if room.get("last_status") in {"offline", "replay", "banned"}:
        room = db.update_media(room_uuid, clear_current_cover=True) or room
    room, media_errors = await refresh_room_media(room)
    return {"room": room, "media_errors": media_errors}


@app.delete("/api/rooms/{room_uuid}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, tags=["rooms"])
def api_delete_room(room_uuid: str) -> Response:
    if not db.delete_room(room_uuid):
        raise HTTPException(status_code=404, detail="room not found")
    remove_room_media(room_uuid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/rooms/{room_uuid}/refresh-media", tags=["media"])
async def api_refresh_media(room_uuid: str) -> dict:
    room = db.get_room(room_uuid)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    room, media_errors = await refresh_room_media(room)
    return {"room": room, "media_errors": media_errors}


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin(request: Request, message: str = "") -> HTMLResponse:
    return templates.TemplateResponse("admin.html", {"request": request, "rooms": db.list_rooms(), "base_url": public_base_url(request), "message": message})


@app.post("/admin/rooms", include_in_schema=False)
async def admin_create_room(
    platform: str = Form(...), room_id: str = Form(...), source_url: str = Form(""), name: str = Form(""),
    group_name: str = Form("Live"), avatar_url: str = Form(""), current_cover_url: str = Form(""), last_status: str = Form("unknown"),
) -> RedirectResponse:
    try:
        room = db.create_room(RoomCreate(platform=platform, room_id=room_id, source_url=source_url, name=name, group_name=group_name, avatar_url=avatar_url, current_cover_url=current_cover_url, last_status=last_status))
        _, errors = await refresh_room_media(room)
        message = "已添加" if not errors else "已添加；媒体缓存失败：" + "; ".join(errors)
    except sqlite3.IntegrityError:
        message = "该平台和房间号已存在"
    except Exception as exc:
        message = f"添加失败：{exc}"
    return RedirectResponse(f"/admin?message={quote_plus(message)}", status_code=303)


@app.get("/admin/rooms/{room_uuid}/edit", response_class=HTMLResponse, include_in_schema=False)
def admin_edit_room(request: Request, room_uuid: str) -> HTMLResponse:
    room = db.get_room(room_uuid)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    return templates.TemplateResponse("edit_room.html", {"request": request, "room": room})


@app.post("/admin/rooms/{room_uuid}/update", include_in_schema=False)
async def admin_update_room(
    room_uuid: str, name: str = Form(""), custom_name: str = Form(""), group_name: str = Form("Live"),
    source_url: str = Form(""), avatar_url: str = Form(""), current_cover_url: str = Form(""), last_status: str = Form("unknown"),
    play_mode: str = Form("auto"), preferred_quality: str = Form("best"), preferred_line: str = Form("auto"), sort_order: int = Form(0), enabled: int = Form(1),
) -> RedirectResponse:
    payload = RoomUpdate(name=name, custom_name=custom_name, group_name=group_name, source_url=source_url, avatar_url=avatar_url, current_cover_url=current_cover_url, last_status=last_status, play_mode=play_mode, preferred_quality=preferred_quality, preferred_line=preferred_line, sort_order=sort_order, enabled=bool(enabled))
    room = db.update_room(room_uuid, payload)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    _, errors = await refresh_room_media(room)
    message = "已保存" if not errors else "已保存；媒体缓存失败：" + "; ".join(errors)
    return RedirectResponse(f"/admin?message={quote_plus(message)}", status_code=303)


@app.post("/admin/rooms/{room_uuid}/refresh-media", include_in_schema=False)
async def admin_refresh_media(room_uuid: str) -> RedirectResponse:
    room = db.get_room(room_uuid)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    _, errors = await refresh_room_media(room)
    message = "媒体已刷新" if not errors else "媒体刷新失败：" + "; ".join(errors)
    return RedirectResponse(f"/admin?message={quote_plus(message)}", status_code=303)


@app.post("/admin/rooms/{room_uuid}/delete", include_in_schema=False)
def admin_delete_room(room_uuid: str) -> RedirectResponse:
    if db.delete_room(room_uuid):
        remove_room_media(room_uuid)
        message = "已删除"
    else:
        message = "直播间不存在"
    return RedirectResponse(f"/admin?message={quote_plus(message)}", status_code=303)
