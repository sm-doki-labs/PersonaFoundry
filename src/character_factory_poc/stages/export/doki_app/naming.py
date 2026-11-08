"""캐릭터 묶음의 이름·ID 규칙. 두 대상이 같은 characterUid를 쓰게 한다."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path

from character_factory_poc.common.errors import FactoryError

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


# 11월 7일 로컬 앱 시연에 적재한 오리지널. 기존 PK와 CDN 키를 그대로 쓴다.
_LEGACY_CHARACTER = "cf-20261107-cf-20261107-testpath-s07"
_LEGACY_BASES = {
    "character": 900001,
    "character_profile_card": 900002,
    "character_stage": 900101,
    "media": 901001,
    "file_store": 1803002,  # 예전 식: 902001 + 첫 media_id(901001)
    "character_media": 903001,
    "character_clip": 904001,
    "character_video": 905001,
    "character_clip_slot": 906001,
}
_BLOCK_SIZE = 1024


def _block(character_id: str) -> int:
    # Android ID는 양수 Int다. 기존 시드보다 높게 시작하고 시퀀스에도 여유를 둔다.
    return 2_000_000 + (character_uid(character_id).int % (1 << 20)) * _BLOCK_SIZE


def api_seed_ids(character_id: str, peers: Iterable[str] = ()) -> Callable[[str, int], int]:
    """표별 PK 공간이 독립이므로 같은 구간을 각 표에 쓴다. 순서·패키지 판에는 무관하다."""
    legacy = character_id == _LEGACY_CHARACTER
    base = _block(character_id)
    for other in peers:
        if legacy or other in (character_id, _LEGACY_CHARACTER):
            continue
        if _block(other) == base:
            raise FactoryError(
                f"앱 시드 ID 구간이 겹쳐요: {character_id}, {other}. 새 캐릭터 ID를 정해 주세요."
            )

    def row_id(table: str, offset: int = 0) -> int:
        if not 0 <= offset < _BLOCK_SIZE:
            raise FactoryError(f"{table} ID가 캐릭터 구간을 벗어나요: {offset}")
        return (_LEGACY_BASES[table] if legacy else base) + offset

    return row_id


def revision_prefix(character_id: str, package_rev: str, *, twin: bool) -> str:
    """콘텐츠 판 이름 앞부분. 모티브는 패키지 판마다 이름이 달라야 해서 판을 붙인다.

    내보내기(chat-svc·api-svc)와 적재 확인이 같은 이름을 쓰도록 여기서만 정한다.
    """
    slug = slug_for(character_id)
    return f"{slug}-{package_rev}" if twin else slug


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
    "api_seed_ids",
    "chapter_uid",
    "character_uid",
    "relative_file",
    "slug_for",
]
