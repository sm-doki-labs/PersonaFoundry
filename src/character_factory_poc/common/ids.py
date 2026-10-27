"""ID 형식과 발급 (명세 §6, D-0011)."""

from __future__ import annotations

import re
from datetime import date

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def check_slug(slug: str) -> str:
    if not _SLUG_RE.match(slug):
        raise ValueError(f"slug 형식이 아니다(소문자·숫자·하이픈): {slug!r}")
    return slug


def brief_id(slug: str, on: date | None = None) -> str:
    d = (on or date.today()).strftime("%Y%m%d")
    return f"bf-{d}-{check_slug(slug)}"


def character_id(slug: str, on: date | None = None) -> str:
    d = (on or date.today()).strftime("%Y%m%d")
    return f"cf-{d}-{check_slug(slug)}"


ID_PATTERNS = {
    "brief_id": re.compile(r"^bf-\d{8}-[a-z0-9-]+$"),
    "character_id": re.compile(r"^cf-\d{8}-[a-z0-9-]+$"),
    "reference_rev": re.compile(r"^rf\d+$"),
    "appearance_rev": re.compile(r"^ar\d+$"),
    "plan_rev": re.compile(r"^pr\d+$"),
    "persona_version": re.compile(r"^pv\d+$"),
    "dataset_rev": re.compile(r"^ds\d+$"),
    "release_rev": re.compile(r"^rl\d+$"),
    "chapter_id": re.compile(r"^ch[123]$"),
}


def is_valid(kind: str, value: str) -> bool:
    return bool(ID_PATTERNS[kind].match(value))
