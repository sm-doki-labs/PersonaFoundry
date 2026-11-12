"""앱 통화 클립의 jev 라벨 — 반응 키워드, 감정 분류, 공장이 지은 몸짓의 '이럴 때' 문구."""

from __future__ import annotations

import pytest

from character_factory_poc.stages.export.doki_app.api_svc import build_seed, validate_seed_bundle
from character_factory_poc.stages.export.doki_app.clip_labels import jev_use_when, trigger_of
from character_factory_poc.stages.export.settings import API_SVC_HEAD
from character_factory_poc.stages.s6_actions.catalog import signature_clip
from character_factory_poc.stages.s11_release.package import build_package, load_package
from tests.test_twin_export import _approved

LITE = [
    "idle_good",
    "speak_good",
    "cheering_good",
    "laughing_good",
    "greeting_good",
    "signature_good",
]


@pytest.mark.parametrize(
    ("key", "trigger"),
    [
        ("amused_good_strong", "amused"),
        ("glad_good_2", "glad"),
        ("angry_bad", "angry"),
        ("signature_good", "signature"),
        ("idle_good", None),
        ("speak_good", None),
        ("smile_talking", None),
    ],
)
def test_trigger_follows_live_emotion_sets(key, trigger):
    assert trigger_of(key) == trigger


@pytest.fixture
def package(tmp_path):
    ctx, cid, _, _ = _approved(tmp_path, "PROMPT_ONLY")
    build_package(ctx, cid)
    return load_package(ctx, cid)


def _with_videos(package, keys, signature=None):
    pkg, folder = package
    base = next(v for v in pkg.videos if v.kind == "ACTION")
    sig = signature_clip(
        signature or {"title": "찰칵 세리머니", "motion": "두 손으로 카메라를 만든다"}
    )
    videos = [v for v in pkg.videos if v.kind == "INTRO"]
    for key in keys:
        extra = (
            {"title": sig["title"], "description": sig["description"], "useWhen": sig["useWhen"]}
            if key == "signature_good"
            else {"title": key, "useWhen": f"{key} 쓸 때"}
        )
        videos.append(base.model_copy(update={"clipKey": key, "chapterNo": 1, **extra}))
    return pkg.model_copy(update={"videos": videos}), folder


def _clips(seed):
    tables = seed.bundle["tables"]
    clip = tables["character_clip"]
    rows = {
        r[clip["columns"].index("id")]: dict(zip(clip["columns"], r, strict=True))
        for r in clip["rows"]
    }
    triggers = {}
    for row in tables.get("character_clip_trigger", {"rows": []})["rows"]:
        triggers.setdefault(rows[row[1]]["clip_key"], []).append(row[2])
    return {r["clip_key"]: r for r in rows.values()}, triggers


def test_motif_lite_reactions_are_auto_picked_with_triggers(package):
    pkg, folder = _with_videos(package, LITE)
    seed = build_seed(
        pkg, folder, exported_at="2026-11-13T00:00:00Z", alembic_revision=API_SVC_HEAD
    )
    clips, triggers = _clips(seed)
    for key in ("cheering_good", "laughing_good", "greeting_good", "signature_good"):
        assert clips[key]["pick_role"] == "emotion", key  # special 이면 jev 후보에서 빠진다
        assert triggers[key] == [key.split("_")[0]]
    assert "idle_good" not in triggers and "speak_good" not in triggers
    assert validate_seed_bundle(seed.bundle) == []
    assert sorted(seed.bundle["table_order"]) == sorted(seed.bundle["tables"])
    fs = seed.bundle["tables"]["file_store"]
    lengths = [r[fs["columns"].index("length")] for r in fs["rows"]]
    assert any(isinstance(n, int) and n > 0 for n in lengths)  # 영상 길이(초)


def test_signature_use_when_points_only_at_present_gestures(package):
    pkg, folder = _with_videos(package, LITE)
    seed = build_seed(
        pkg, folder, exported_at="2026-11-13T00:00:00Z", alembic_revision=API_SVC_HEAD
    )
    clips, _ = _clips(seed)
    text = clips["signature_good"]["use_when"]
    assert text.startswith("시그니처 — 찰칵 세리머니.")
    assert "「찰칵 세리머니 해 주세요」" in text
    assert "첫인사·작별 인사 → greeting" in text and "가벼운 농담 → laughing" in text
    assert "도전을 앞둔 응원 → cheering" in text
    assert "칭찬을 받았다 → 영상 없이 idle" in text  # shy 가 없는 캐릭터
    assert "반가운 인사, 축하" not in text  # s6 기본 문구를 되풀이하지 않는다
    assert "→ signature" in clips["greeting_good"]["use_when"]
    assert "→ signature" in clips["cheering_good"]["use_when"]


def test_signature_with_app_set_points_at_app_emotions(package):
    pkg, folder = _with_videos(
        package,
        ["idle_good", "glad_good", "amused_good", "encouraging_good", "shy_good", "signature_good"],
        signature={
            "title": "엄지 척",
            "motion": "엄지를 든다",
            "useWhen": "상대가 경기 얘기를 할 때.",
        },
    )
    seed = build_seed(
        pkg, folder, exported_at="2026-11-13T00:00:00Z", alembic_revision=API_SVC_HEAD
    )
    clips, _ = _clips(seed)
    text = clips["signature_good"]["use_when"]
    assert "그 밖에: 상대가 경기 얘기를 할 때." in text
    for part in ("→ glad", "→ amused", "→ encouraging", "→ shy"):
        assert part in text
    assert clips["glad_good"]["use_when"] == "glad_good 쓸 때"  # 운영 세트 문구는 그대로


def test_export_text_does_not_touch_video_identity():
    """s6 의 useWhen(영상 재생성 판정 기준)은 그대로이고, 내보낼 때만 바뀐다."""
    sig = signature_clip({"title": "찰칵", "motion": "카메라"})
    assert sig["useWhen"].startswith("찰칵 — 이 사람을 대표하는 시그니처 포즈.")
    from character_factory_poc.contracts.release import Video

    video = Video(
        videoId="v",
        kind="ACTION",
        clipKey="glad_good",
        durationS=3,
        file="f",
        provider="p",
        synthetic=True,
    )
    assert jev_use_when(video, [video]) is None
