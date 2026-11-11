"""패키지 → api-svc 시드 묶음(`dokilabs-seed/1`).

규칙은 api-svc `scripts/seed.py`와 `app/models/character/*`를 읽고 이 프로젝트 코드로 다시
적었다(다른 저장소 코드는 import하지 않는다). 적재는 그 저장소의 `python -m scripts.seed load`가
한다.
"""

from __future__ import annotations

import json
import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from character_factory_poc.contracts.release import CharacterPackage, Video
from character_factory_poc.stages.export.doki_app.naming import (
    api_seed_ids,
    chapter_uid,
    character_uid,
    relative_file,
    revision_prefix,
    slug_for,
)
from character_factory_poc.stages.s6_actions.app_clips import APP_CLIPS
from character_factory_poc.stages.s6_actions.catalog import SIGNATURE_KEY

FORMAT = "dokilabs-seed/1"

#: api-svc `SEED_TABLES` 가운데 이 변환기가 쓰는 표. 나머지는 우리 캐릭터에 해당 행이 없다.
SEED_TABLES = [
    "character",
    "character_profile_card",
    "character_stage",
    "media",
    "file_store",
    "character_media",
    "character_clip",
    "character_clip_slot",
    "character_video",
]
#: 옛 스키마 표. 들어 있으면 적재가 거절한다(api-svc `validate_stage_bundle`).
LEGACY_TABLES = frozenset({"character_chapter", "character_stage_intro"})

_GENDER_KO = {"female": "여성", "male": "남성", "other": "기타"}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class ApiSeed:
    bundle: dict[str, Any]
    mapping: list[tuple[str, str, str]]
    unmapped: list[str]


def _png_size(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(_PNG_SIGNATURE) or len(data) < 24:
        return None
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


class _Builder:
    def __init__(self, bundle: dict[str, Any]):
        self.bundle = bundle
        self.tables = bundle["tables"]

    def add(self, table: str, columns: list[str], row: list[Any]) -> None:
        spec = self.tables.setdefault(table, {"columns": columns, "rows": []})
        if spec["columns"] != columns:
            raise ValueError(f"{table} 컬럼 목록이 행마다 다르다")
        spec["rows"].append(row)


def _stage_row(
    character_id: int,
    stage_id: int,
    stage_uid: str,
    stage_no: int,
    chapter,
    slug: str,
    quest_revision: str,
    exported_at: str,
) -> list[Any]:
    return [
        stage_id,
        character_id,
        stage_no,
        chapter.title,  # display_name
        None,  # appearance_note
        None,  # unlock_rule
        exported_at,  # created_at
        chapter.intro,  # intro_story
        stage_uid,
        "MISSION",
        chapter.relationshipStage,
        chapter.title,
        chapter.goal,
        20,  # turn_limit(MISSION은 필수)
        f"{slug}-{chapter.chapterId}",
        quest_revision,
        None,  # synced_at
        exported_at,  # updated_at
    ]


def build_seed(
    package: CharacterPackage,
    package_dir: Path,
    *,
    exported_at: str,
    alembic_revision: str,
    default_voice_id: str | None = None,
) -> ApiSeed:
    # 정식 패키지는 characters/<cid>/s11-release/pkN 아래 있다. 동시에 내보내도
    # 이미 생성된 캐릭터 폴더 이름만 대조하면 된다(다른 캐릭터의 출처는 읽지 않는다).
    release = package_dir.parent
    peers = ()
    if release.name == "s11-release" and release.parent.name == package.characterId:
        peers = (p.name for p in release.parent.parent.iterdir() if p.is_dir())
    row_id = api_seed_ids(package.characterId, peers)
    character_id = row_id("character", 0)
    slug = slug_for(package.characterId)
    uid = str(character_uid(package.characterId))
    profile = package.profile
    mapping: list[tuple[str, str, str]] = []
    unmapped: list[str] = []

    builder = _Builder(
        {
            "format": FORMAT,
            "exported_at": exported_at,
            "alembic_revision": alembic_revision,
            "table_order": list(SEED_TABLES),
            "tables": {},
        }
    )

    twin = package.twin
    voice_bundle_id = None
    if twin:
        unmapped.append(f"twin.chapterTemplate={twin.chapterTemplate} (api-svc 관계 틀 칸이 없다)")
        mapping.extend(
            [
                ("twin.disclosure", "api-svc character.disclosure_label", ""),
                ("twin.startButtonLabel", "api-svc character.call_start_label", ""),
            ]
        )
        voice_id = twin.voiceId or (UUID(default_voice_id) if default_voice_id else None)
        if voice_id is None:
            unmapped.append("twin.voiceId (기본 한국어 음성이 없다. default_voice_id가 필요하다)")
        else:
            voice_bundle_id = character_id
            builder.bundle["table_order"][:0] = ["character_voice", "character_voice_language"]
            builder.add("character_voice", ["id", "name"], [voice_bundle_id, slug])
            builder.add(
                "character_voice_language",
                ["id", "character_voice_id", "language", "voice_id"],
                [voice_bundle_id, voice_bundle_id, package.locale, str(voice_id)],
            )
            mapping.append(
                (
                    "twin.voiceId" if twin.voiceId else "export.doki_app.default_voice_id",
                    "api-svc character_voice_language.voice_id",
                    "ko",
                )
            )

    builder.add(
        "character",
        [
            "id",
            "name",
            "handle",
            "gender",
            "age",
            "description",
            "job",
            "height",
            "hobby",
            "likes",
            "tmi",
            "call_enabled",
            "is_active",
            "character_uid",
            "chat_enabled",
            "audience_rating",
            "tagline",
            "voice_id",
            "disclosure_label",
            "call_start_label",
        ],
        [
            character_id,
            profile.name,
            slug,
            _GENDER_KO[profile.gender],
            profile.age,
            profile.description,
            profile.job,
            None,
            profile.hobby,
            profile.likes,
            profile.tmiItems[0].text if profile.tmiItems else None,
            True,
            True,
            uid,
            True,
            "ALL",
            profile.tagline,
            voice_bundle_id,
            twin.disclosure if twin else None,
            twin.startButtonLabel if twin else None,
        ],
    )
    for source in (
        "profile.name",
        "profile.gender",
        "profile.age",
        "profile.job",
        "profile.tagline",
        "profile.description",
        "profile.hobby",
        "profile.likes",
    ):
        mapping.append((source, f"api-svc character.{source.split('.')[1]}", ""))
    mapping.append(
        ("profile.tmiItems[0].text", "api-svc character.tmi", "첫 TMI만 한 줄 칸에 넣는다")
    )

    builder.add(
        "character_profile_card",
        [
            "id",
            "character_id",
            "locale",
            "name",
            "tagline",
            "description",
            "job",
            "hobby",
            "likes",
            "tmi",
            "mbti",
            "favorite_foods",
            "favorite_drink",
            "dislikes",
            "ideal_date",
            "everyday_habit",
            "tmi_items",
            "tags",
        ],
        [
            row_id("character_profile_card", 0),
            character_id,
            "ko",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            profile.mbti or None,
            None,
            None,
            profile.dislikes,
            None,
            None,
            [{"text": item.text, "reveal_stage": item.revealStage} for item in profile.tmiItems],
            list(profile.tags),
        ],
    )
    mapping.append(("profile.tags", "api-svc character_profile_card.tags", ""))
    mapping.append(("profile.mbti", "api-svc character_profile_card.mbti", ""))
    mapping.append(("profile.dislikes", "api-svc character_profile_card.dislikes", ""))
    mapping.append(
        (
            "profile.tmiItems",
            "api-svc character_profile_card.tmi_items",
            "{text, reveal_stage} 목록으로 바꾼다",
        )
    )
    unmapped.extend(
        [
            "plan.profileCard.favoriteFoods (character-package-v1 profile에 칸이 없다)",
            "plan.profileCard.favoriteDrink (character-package-v1 profile에 칸이 없다)",
            "plan.profileCard.idealDate (character-package-v1 profile에 칸이 없다)",
            "plan.profileCard.everydayHabit (character-package-v1 profile에 칸이 없다)",
        ]
    )

    prefix = revision_prefix(package.characterId, package.packageRev, twin=bool(twin))
    quest_revision = f"{prefix}-quest-v1"
    for index, chapter in enumerate(sorted(package.chapters, key=lambda c: c.chapterNo), start=1):
        builder.add(
            "character_stage",
            [
                "id",
                "character_id",
                "stage_no",
                "display_name",
                "appearance_note",
                "unlock_rule",
                "created_at",
                "intro_story",
                "stage_uid",
                "mode",
                "entry_relationship_stage",
                "title",
                "goal",
                "turn_limit",
                "stage_slug",
                "chat_content_revision",
                "synced_at",
                "updated_at",
            ],
            _stage_row(
                character_id,
                row_id("character_stage", index),
                str(chapter_uid(package.characterId, chapter.chapterId)),
                index,
                chapter,
                slug,
                quest_revision,
                exported_at,
            ),
        )
    mapping.append(
        ("chapters[].chapterNo", "api-svc character_stage.stage_no", "챕터 1~3을 단계 1~3으로 둔다")
    )
    mapping.append(("chapters[].title", "api-svc character_stage.title/display_name", ""))
    mapping.append(("chapters[].intro", "api-svc character_stage.intro_story", ""))
    mapping.append(("chapters[].goal", "api-svc character_stage.goal", ""))
    mapping.append(
        ("chapters[].relationshipStage", "api-svc character_stage.entry_relationship_stage", "")
    )

    media_no = 0

    def add_media(path: Path, media_type: str, rel: str) -> int:
        nonlocal media_no
        index = media_no
        media_no += 1
        media_id = row_id("media", index)
        data = path.read_bytes()
        size = _png_size(data) if media_type == "image" else None
        key = f"api-svc/protected/characters/{character_id}/{slug}/{rel}"
        builder.add("media", ["id", "media_type", "status"], [media_id, media_type, "ready"])
        builder.add(
            "file_store",
            [
                "id",
                "media_id",
                "variant_type",
                "key",
                "description",
                "size_byte",
                "width",
                "height",
                "length",
                "source_ref",
            ],
            [
                row_id("file_store", index),
                media_id,
                "original",
                key,
                f"{package.characterId}/{package.packageRev}/{rel}",
                len(data),
                size[0] if size else None,
                size[1] if size else None,
                None,
                key,
            ],
        )
        return media_id

    hero_id = add_media(
        relative_file(package_dir, package.appearance.heroImage), "image", "hero.png"
    )
    mapping.append(
        ("appearance.heroImage", "api-svc media/file_store + character_media(profile_photo)", "")
    )
    mapping.append(("media.key", "api-svc file_store.key", "상대 키만 쓴다(CDN 절대 URL 없음)"))

    link_no = 0
    link_no += 1
    builder.add(
        "character_media",
        ["id", "character_id", "media_id", "usage_type", "content_order", "character_stage_id"],
        [row_id("character_media", link_no), character_id, hero_id, "profile_photo", 0, None],
    )

    frame_ids: dict[str, int] = {}
    for chapter in package.chapters:
        frame_ids[chapter.chapterId] = add_media(
            relative_file(package_dir, chapter.frame),
            "image",
            f"chapters/{chapter.chapterId}/frame.png",
        )
        link_no += 1
        builder.add(
            "character_media",
            ["id", "character_id", "media_id", "usage_type", "content_order", "character_stage_id"],
            [
                row_id("character_media", link_no),
                character_id,
                frame_ids[chapter.chapterId],
                "stage_photo",
                chapter.chapterNo,
                row_id("character_stage", chapter.chapterNo),
            ],
        )
    mapping.append(
        (
            "chapters[].frame",
            "api-svc media/file_store + character_media(stage_photo)",
            "단계별 대표 사진",
        )
    )

    intro_videos = [v for v in package.videos if v.kind == "INTRO"]
    if intro_videos:
        video = intro_videos[0]
        media_id = add_media(relative_file(package_dir, video.file), "video", "videos/intro.mp4")
        builder.add(
            "character_video",
            [
                "id",
                "character_id",
                "media_id",
                "context",
                "description",
                "emotion",
                "intent",
                "is_active",
                "created_at",
                "play_type",
                "mood_from",
            ],
            [
                row_id("character_video", 0),
                character_id,
                media_id,
                "calls",
                video.title or "소개 영상",
                "neutral",
                None,
                True,
                exported_at,
                "idle",
                None,
            ],
        )
        link_no += 1
        builder.add(
            "character_media",
            ["id", "character_id", "media_id", "usage_type", "content_order", "character_stage_id"],
            [row_id("character_media", link_no), character_id, media_id, "explore_video", 0, None],
        )
        mapping.append(("videos[INTRO]", "api-svc character_video(context=calls, idle)", ""))
        mapping.append(
            ("videos[INTRO].file", "api-svc media/file_store + character_media(explore_video)", "")
        )

    clip_no = 0
    for video in sorted(
        (v for v in package.videos if v.kind == "ACTION"),
        key=lambda v: (v.chapterNo or 0, v.clipKey),
    ):
        chapter_no = video.chapterNo or 1
        clip_no += 1
        rel = f"chapters/ch{chapter_no}/{video.clipKey}.mp4"
        media_id = add_media(relative_file(package_dir, video.file), "video", rel)
        builder.add(
            "character_clip",
            [
                "id",
                "media_id",
                "clip_key",
                "generation",
                "title",
                "description",
                "mood",
                "status",
                "source",
                "meta",
                "created_at",
                "character_stage_id",
                "access_tier",
                "audience_rating",
                "action_category",
                "use_when",
                "pick_role",
            ],
            [
                row_id("character_clip", clip_no),
                media_id,
                video.clipKey,
                "v1",
                video.title,
                video.description,
                _mood(video),
                "live",
                "pipeline",
                {
                    "synthetic": video.synthetic,
                    "provider": video.provider,
                    "duration_seconds": video.durationS,
                    "source": f"{package.characterId}/{package.packageRev}",
                    "polarity": "positive" if _mood(video) == "good" else "negative",
                },
                exported_at,
                row_id("character_stage", chapter_no),
                "free",
                "ALL",
                None,
                video.useWhen or None,
                _pick_role(video),
            ],
        )
        # 재생 위치. 앱은 슬롯이 있어야 통화 화면(call-clips)에 클립을 싣는다.
        # 운영 데이터와 같은 규칙: idle_* → idle, 나머지 → reaction(시작 무드 = 클립 무드).
        is_idle = video.clipKey.startswith("idle")
        builder.add(
            "character_clip_slot",
            ["id", "clip_id", "play_type", "mood_from", "label", "icon", "sort_order", "is_active"],
            [
                row_id("character_clip_slot", clip_no),
                row_id("character_clip", clip_no),
                "idle" if is_idle else "reaction",
                None if is_idle else _mood(video),
                None,
                None,
                None,
                True,
            ],
        )
    mapping.append(
        (
            "videos[ACTION]",
            "api-svc character_clip(clip_key·title·description·use_when·pick_role)",
            "표정은 mood(good/bad)로 바꾼다",
        )
    )

    # 단계별 미리보기 영상: 그 단계의 첫 동작 영상을 쓴다.
    previewed: set[int] = set()
    for video in sorted(
        (v for v in package.videos if v.kind == "ACTION"),
        key=lambda v: (v.chapterNo or 0, v.clipKey),
    ):
        chapter_no = video.chapterNo or 1
        if chapter_no in previewed:
            continue
        previewed.add(chapter_no)
        link_no += 1
        media = next(
            (
                row
                for row in builder.tables["character_clip"]["rows"]
                if row[2] == video.clipKey and row[11] == row_id("character_stage", chapter_no)
            ),
            None,
        )
        if media is None:
            continue
        builder.add(
            "character_media",
            ["id", "character_id", "media_id", "usage_type", "content_order", "character_stage_id"],
            [
                row_id("character_media", link_no),
                character_id,
                media[1],
                "stage_preview",
                chapter_no,
                row_id("character_stage", chapter_no),
            ],
        )
    mapping.append(
        (
            "videos[ACTION] (단계별 첫 영상)",
            "api-svc character_media(stage_preview)",
            "단계 화면에서 재생할 미리보기",
        )
    )

    unmapped.extend(
        [
            "persona.* (api-svc에 대화 프롬프트 칸이 없다: chat-svc 몫)",
            "sft.* (api-svc 콘텐츠 테이블에 학습 결과 칸이 없다)",
            "appearance.spec (앱 표에 외모 명세 칸이 없다: 기준 이미지만 적재한다)",
            "gates[] (대상 시스템에 관문 기록 표가 없다)",
            "videos[].synthetic (앱 표에 칸이 없어 character_clip.meta에만 남긴다)",
        ]
    )
    unmapped.extend(clip_count_warnings(builder.bundle))
    return ApiSeed(bundle=builder.bundle, mapping=mapping, unmapped=unmapped)


def _mood(video: Video) -> str:
    return "bad" if video.expression == "bad" else "good"


def _pick_role(video: Video) -> str | None:
    if video.clipKey.startswith("idle_"):
        return None
    return "special" if video.clipKey not in _EMOTION_KEYS else "emotion"


#: §D-0040의 감정 세트 이름(대기·감정 반응). 그 밖의 이름은 특별 행동으로 본다.
#: S6 앱 카탈로그(APP_CLIPS)는 api-svc 감정 세트 사본이라 전부 감정이다. 여기서 빠지면
#: pick_role=special로 나가 서버의 답변 뒤 몸짓 후보(followup-clip)에서 사라진다.
#: 모티브 시그니처 포즈(D-0165)도 '이럴 때'를 보고 자동으로 고르는 감정 반응으로 내보낸다.
_EMOTION_KEYS = frozenset({clip["key"] for clip in APP_CLIPS} | {SIGNATURE_KEY}) | frozenset(
    {
        "idle_good",
        "idle_bad",
        "glad_good",
        "amused_good",
        "shy_good",
        "sorry_good",
        "relieved_bad",
        "sympathy_bad",
        "sorry_bad",
        "hurt_bad",
        "sad_bad",
        "worried_good",
        "happy_good",
        "excited_good",
        "calm_good",
        "proud_good",
        "teasing_good",
    }
)


def clip_count_warnings(bundle: dict, min_clips: int = 10) -> list[str]:
    """시드에 실제로 담긴 character_clip 행만 세고, 영상이 없는 단계도 보고한다."""
    tables = bundle["tables"]
    counts: Counter[int] = Counter()
    if clips := tables.get("character_clip"):
        stage_id = clips["columns"].index("character_stage_id")
        counts.update(row[stage_id] for row in clips["rows"])
    warnings = []
    if stages := tables.get("character_stage"):
        stage_id = stages["columns"].index("id")
        stage_no = stages["columns"].index("stage_no")
        for row in stages["rows"]:
            count = counts[row[stage_id]]
            if count < min_clips:
                warnings.append(
                    f"경고: ch{row[stage_no]} 영상 {count}편. 앱의 단계 개방 기준"
                    f"(stage.min_clips={min_clips})에 미달한다."
                )
    return warnings


def validate_seed_bundle(bundle: dict) -> list[str]:
    """api-svc `validate_stage_bundle` 규칙과 우리 묶음 규칙을 이 코드로 다시 검사한다."""
    problems: list[str] = []
    if bundle.get("format") != FORMAT:
        problems.append(f"format이 {FORMAT}가 아니다")
    tables = bundle.get("tables")
    if not isinstance(tables, dict):
        return problems + ["tables가 객체가 아니다"]
    legacy = LEGACY_TABLES & set(tables)
    if legacy:
        problems.append(f"옛 표가 들어 있다: {sorted(legacy)}")
    unknown = set(tables) - set(SEED_TABLES) - {"character_voice", "character_voice_language"}
    if unknown:
        problems.append(f"SEED_TABLES 밖의 표: {sorted(unknown)}")
    order = bundle.get("table_order") or []
    if sorted(order) != sorted(tables):
        problems.append("table_order와 tables가 다르다")
    stage = tables.get("character_stage")
    if stage is not None and "stage_uid" not in stage["columns"]:
        problems.append("character_stage에 stage_uid가 없다(062_stage_consolidation)")
        return problems
    for name, spec in tables.items():
        if len(spec["columns"]) != len(set(spec["columns"])):
            problems.append(f"{name}: 컬럼이 중복됐다")
        for row in spec["rows"]:
            if len(row) != len(spec["columns"]):
                problems.append(f"{name}: 행 길이가 컬럼 수와 다르다")
                break
    problems.extend(_referential_problems(tables))
    return problems


def _referential_problems(tables: dict) -> list[str]:
    """FK·체크 제약을 이 코드로 다시 확인한다(적재 전에 잡는다).

    아래 행 인덱스는 위에서 적은 `columns` 순서다(character_media는 stage id가 5번째,
    clip은 stage id가 11번째).
    """
    problems: list[str] = []
    characters = {row[0] for row in tables.get("character", {"rows": []})["rows"]}
    stages = {row[0]: row for row in tables.get("character_stage", {"rows": []})["rows"]}
    media = {row[0]: row for row in tables.get("media", {"rows": []})["rows"]}
    for row in tables.get("character_stage", {"rows": []})["rows"]:
        if row[1] not in characters:
            problems.append(f"character_stage {row[0]}: character_id가 없다")
        if row[9] == "FREE_CHAT" and row[13] is not None:
            problems.append(f"character_stage {row[0]}: FREE_CHAT은 turn_limit이 null이어야 한다")
        if row[9] == "MISSION" and row[13] is None:
            problems.append(f"character_stage {row[0]}: MISSION은 turn_limit이 필요하다")
        if row[10] not in {"STRANGER", "ACQUAINTANCE", "FLIRTING", "DATING"}:
            problems.append(f"character_stage {row[0]}: entry_relationship_stage가 이상하다")
    for row in tables.get("file_store", {"rows": []})["rows"]:
        if row[1] not in media:
            problems.append(f"file_store {row[0]}: media_id가 없다")
        key = row[3] or ""
        if key.startswith("http://") or key.startswith("https://") or key.startswith("/"):
            problems.append(f"file_store {row[0]}: key는 상대 키여야 한다")
        if not isinstance(row[5], int) or row[5] <= 0:
            problems.append(f"file_store {row[0]}: size_byte가 필요하다")
    for row in tables.get("character_media", {"rows": []})["rows"]:
        if row[2] not in media:
            problems.append(f"character_media {row[0]}: media_id가 없다")
        scoped = row[3] in {"stage_preview", "stage_success", "stage_fail", "stage_photo"}
        if scoped != (row[5] is not None):
            problems.append(f"character_media {row[0]}: usage_type과 character_stage_id가 어긋난다")
        if row[5] is not None and row[5] not in stages:
            problems.append(f"character_media {row[0]}: character_stage_id가 없다")
        kind = media[row[2]][1] if row[2] in media else None
        if row[3] in {"explore_video", "stage_preview"} and kind != "video":
            problems.append(f"character_media {row[0]}: 영상 슬롯에 사진이 들어갔다")
        if row[3] in {"profile_photo", "stage_photo"} and kind != "image":
            problems.append(f"character_media {row[0]}: 사진 슬롯에 영상이 들어갔다")
    seen_clips: set[tuple[int, str, str]] = set()
    for row in tables.get("character_clip", {"rows": []})["rows"]:
        if row[1] not in media:
            problems.append(f"character_clip {row[0]}: media_id가 없다")
        if row[11] not in stages:
            problems.append(f"character_clip {row[0]}: character_stage_id가 없다")
        if row[6] not in {"good", "bad"}:
            problems.append(f"character_clip {row[0]}: mood가 good·bad가 아니다")
        if row[16] not in {None, "emotion", "special"}:
            problems.append(f"character_clip {row[0]}: pick_role이 이상하다")
        if row[14] not in {None, "aegyo", "touch", "sexy", "private"}:
            problems.append(f"character_clip {row[0]}: action_category가 이상하다")
        key = (row[11], row[2], row[3])
        if key in seen_clips:
            problems.append(f"character_clip {row[0]}: (단계, clip_key, generation) 중복")
        seen_clips.add(key)
    return problems


def write_seed(path: Path, bundle: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


__all__ = [
    "FORMAT",
    "LEGACY_TABLES",
    "SEED_TABLES",
    "ApiSeed",
    "build_seed",
    "clip_count_warnings",
    "validate_seed_bundle",
    "write_seed",
]
