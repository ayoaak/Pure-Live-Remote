from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Pure Live Remote"
APP_VERSION = "0.2.0-test"
PORT = int(os.getenv("PORT", "35455"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data")).resolve()
DB_PATH = DATA_DIR / "pure_live_remote.db"
MEDIA_DIR = DATA_DIR / "media"
LOGO_DIR = MEDIA_DIR / "logo"
COVER_DIR = MEDIA_DIR / "cover"
DEFAULT_LOGO_PATH = MEDIA_DIR / "default-logo.png"
DEFAULT_COVER_PATH = MEDIA_DIR / "default-cover.jpg"


def ensure_data_dirs() -> None:
    for path in (DATA_DIR, MEDIA_DIR, LOGO_DIR, COVER_DIR):
        path.mkdir(parents=True, exist_ok=True)
