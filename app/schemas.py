from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

LiveStatusValue = Literal["live", "offline", "replay", "unknown", "banned"]
PlayModeValue = Literal["auto", "redirect", "proxy"]


class RoomCreate(BaseModel):
    platform: str = Field(min_length=1, max_length=32)
    room_id: str = Field(min_length=1, max_length=128)
    source_url: str = Field(default="", max_length=2048)
    name: str = Field(default="", max_length=256)
    custom_name: str = Field(default="", max_length=256)
    group_name: str = Field(default="Live", max_length=128)
    avatar_url: str = Field(default="", max_length=2048)
    current_cover_url: str = Field(default="", max_length=2048)
    enabled: bool = True
    sort_order: int = 0
    preferred_quality: str = Field(default="best", max_length=128)
    preferred_line: str = Field(default="auto", max_length=128)
    play_mode: PlayModeValue = "auto"
    last_status: LiveStatusValue = "unknown"

    @field_validator("platform", "room_id")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator(
        "source_url",
        "name",
        "custom_name",
        "group_name",
        "avatar_url",
        "current_cover_url",
        "preferred_quality",
        "preferred_line",
    )
    @classmethod
    def strip_optional(cls, value: str) -> str:
        return value.strip()


class RoomUpdate(BaseModel):
    source_url: str | None = Field(default=None, max_length=2048)
    name: str | None = Field(default=None, max_length=256)
    custom_name: str | None = Field(default=None, max_length=256)
    group_name: str | None = Field(default=None, max_length=128)
    avatar_url: str | None = Field(default=None, max_length=2048)
    current_cover_url: str | None = Field(default=None, max_length=2048)
    enabled: bool | None = None
    sort_order: int | None = None
    preferred_quality: str | None = Field(default=None, max_length=128)
    preferred_line: str | None = Field(default=None, max_length=128)
    play_mode: PlayModeValue | None = None
    last_status: LiveStatusValue | None = None
    last_error: str | None = Field(default=None, max_length=2000)

    @field_validator(
        "source_url",
        "name",
        "custom_name",
        "group_name",
        "avatar_url",
        "current_cover_url",
        "preferred_quality",
        "preferred_line",
        "last_error",
    )
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value
