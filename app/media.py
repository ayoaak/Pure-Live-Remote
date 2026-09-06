from __future__ import annotations

import io
import shutil
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageDraw, ImageOps

from .config import COVER_DIR, DEFAULT_COVER_PATH, DEFAULT_LOGO_PATH, LOGO_DIR, ensure_data_dirs

MAX_IMAGE_BYTES = 10 * 1024 * 1024
DOWNLOAD_TIMEOUT = httpx.Timeout(15.0, connect=8.0)


class MediaError(RuntimeError):
    pass


def ensure_default_media() -> None:
    ensure_data_dirs()
    if not DEFAULT_LOGO_PATH.exists():
        image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 248, 248), fill=(78, 82, 88, 255))
        draw.ellipse((82, 58, 174, 150), fill=(210, 213, 218, 255))
        draw.rounded_rectangle((58, 145, 198, 225), radius=55, fill=(210, 213, 218, 255))
        image.save(DEFAULT_LOGO_PATH, format="PNG")
    if not DEFAULT_COVER_PATH.exists():
        image = Image.new("RGB", (1280, 720), (49, 52, 57))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((440, 250, 840, 470), radius=40, fill=(88, 92, 99))
        draw.polygon([(590, 300), (590, 420), (710, 360)], fill=(220, 222, 226))
        image.save(DEFAULT_COVER_PATH, format="JPEG", quality=88, optimize=True)


def _validate_remote_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MediaError("media URL must be http(s)")
    return url


async def download_image(url: str) -> bytes:
    url = _validate_remote_url(url)
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("GET", url, headers={"User-Agent": "Pure-Live-Remote/0.2"}) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if content_type and "image" not in content_type:
                raise MediaError(f"unexpected media content type: {content_type}")
            buffer = bytearray()
            async for chunk in response.aiter_bytes():
                buffer.extend(chunk)
                if len(buffer) > MAX_IMAGE_BYTES:
                    raise MediaError("image exceeds 10 MiB limit")
    return bytes(buffer)


def normalize_avatar_bytes(data: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            square = ImageOps.fit(source.convert("RGBA"), (256, 256), method=Image.Resampling.LANCZOS)
    except Exception as exc:
        raise MediaError(f"invalid avatar image: {exc}") from exc
    mask = Image.new("L", (256, 256), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 255, 255), fill=255)
    output = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    output.paste(square, (0, 0), mask)
    output.save(destination, format="PNG", optimize=True)


def normalize_cover_bytes(data: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            image = source.convert("RGB")
            image.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
            image.save(destination, format="JPEG", quality=90, optimize=True)
    except Exception as exc:
        raise MediaError(f"invalid cover image: {exc}") from exc


async def cache_avatar(room_uuid: str, url: str) -> str:
    data = await download_image(url)
    destination = LOGO_DIR / f"{room_uuid}.png"
    normalize_avatar_bytes(data, destination)
    return str(destination)


async def cache_cover(room_uuid: str, url: str, *, live: bool) -> tuple[str, str | None]:
    data = await download_image(url)
    if live:
        current = COVER_DIR / f"{room_uuid}-current.jpg"
        last = COVER_DIR / f"{room_uuid}-last.jpg"
        normalize_cover_bytes(data, current)
        shutil.copyfile(current, last)
        return str(current), str(last)
    last = COVER_DIR / f"{room_uuid}-last.jpg"
    normalize_cover_bytes(data, last)
    return "", str(last)


def remove_room_media(room_uuid: str) -> None:
    for path in (
        LOGO_DIR / f"{room_uuid}.png",
        COVER_DIR / f"{room_uuid}-current.jpg",
        COVER_DIR / f"{room_uuid}-last.jpg",
    ):
        path.unlink(missing_ok=True)


def existing_or_default(path_value: str, default: Path) -> Path:
    path = Path(path_value) if path_value else default
    return path if path.exists() else default
