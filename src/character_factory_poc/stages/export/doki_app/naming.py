"""캐릭터 묶음의 이름·ID 규칙. 두 대상이 같은 characterUid를 쓰게 한다."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
_UID_NAMESPACE = uuid.UUID("6f3f5d2a-0b7c-5c1e-9a58-0d6a1f4b0c11")


def slug_for(character_id: str) -> str:
    """`cf-20261027-name` → `cf-20261027-name`(소문자·하이픈만 남긴다)."""
    slug = re.sub(r"[^a-z0-9-]+", "-", character_id.lower()).strip("-")
    if not _SLUG.match(slug):
        raise ValueError(f"콘텐츠 트리 slug로 쓸 수 없다: {character_id!r}")
    return slug


def character_uid(character_id: str) -> uuid.UUID:
    """두 시스템이 같은 캐릭터를 같은 UID로 가리키게 한다(결정적)."""
    return uuid.uuid5(_UID_NAMESPACE, f"cfp:{character_id}")


def chapter_uid(character_id: str, chapter_id: str) -> uuid.UUID:
    return uuid.uuid5(_UID_NAMESPACE, f"cfp:{character_id}:{chapter_id}")


def relative_file(package_dir: Path, rel: str) -> Path:
    """패키지 루트 밖으로 나가는 경로를 거절한다."""
    path = (package_dir / rel).resolve()
    root = package_dir.resolve()
    if root not in path.parents and path != root:
        raise ValueError(f"패키지 밖 경로다: {rel}")
    return path


__all__ = [
    "chapter_uid",
    "character_uid",
    "relative_file",
    "slug_for",
]
