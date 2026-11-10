"""D-0119: 등급별 호출 계획과 한 챕터 생성·승인, 시드의 단계 개방 경고를 검증한다."""

import pytest

from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.stages.export.doki_app.api_svc import clip_count_warnings
from character_factory_poc.stages.export.export import export_doki_app
from character_factory_poc.stages.s6_actions.app_clips import APP_CLIPS
from character_factory_poc.stages.s6_actions.approve import load_approved_actions
from character_factory_poc.stages.s6_actions.run import plan_calls, run_s6, s6_config
from character_factory_poc.stages.s11_release.package import build_package
from tests.support.export_flow import approve_package, full_flow
from tests.support.flow import make_ctx
from tests.test_actions import flow, request_changes  # noqa: F401
from tests.test_s11_export import HEADS, _settings

CORE = """idle_good idle_bad glad_good amused_good shy_good sorry_good pouty_good
          surprised_good sad_good displeased_good""".split()
PRO = (
    CORE
    + """affection_good flutter_good playful_good worried_good hurt_good sympathy_good
                curious_good joy_good sheepish_good angry_bad""".split()
)
APP_KEYS = [c["key"] for c in APP_CLIPS]


@pytest.mark.parametrize(
    ("tier", "chapters", "keys", "total"),
    [
        ("light", ("ch1",), CORE, 10),
        ("standard", ("ch1", "ch2", "ch3"), CORE, 30),
        ("pro", ("ch1", "ch2", "ch3"), PRO, 60),
        ("max", ("ch1", "ch2", "ch3"), APP_KEYS, 111),
    ],
)
def test_dry_run(tmp_path, tier, chapters, keys, total):
    ctx, _ = make_ctx(
        tmp_path, f'[stages.s6]\nvideo_tier="{tier}"\npreset="standard"\nactions=["idle_bad"]'
    )
    cfg = s6_config(ctx)
    assert cfg["chapters"] == chapters and cfg["actions"] == keys
    assert len(set(keys)) == len(keys) and set(keys) <= set(APP_KEYS)
    image, video = plan_calls(ctx, cfg)
    assert image.calls == len(chapters) and video.calls == total
    assert f"동작 영상 {total}편 ({len(chapters)}챕터" in video.description


def test_old_standard_is_a_preset_only(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    for preset in ("standard", "full37"):
        ctx.config.stages["s6"] = {"preset": preset}
        cfg = s6_config(ctx)
        assert cfg["preset"] == "full37" and cfg["actions"] == APP_KEYS
    ctx.config.stages["s6"] = {"video_tier": "full37"}
    with pytest.raises(CheckFailed, match="video_tier"):
        s6_config(ctx)


@pytest.mark.parametrize(
    ("tier", "total", "seconds"),
    [("light", 10, 110), ("standard", 20, 210), ("pro", 28, 290), ("max", 37, 380)],
)
def test_motif_tiers_are_one_scene(tmp_path, tier, total, seconds):
    """D-0164: 모티브는 배경 하나·같은 옷. 등급은 몸짓 수로만 갈리고 단계당 최소 10편을 지킨다."""
    from character_factory_poc.stages.s6_actions.catalog import MOTIF_VIDEO_TIERS
    from character_factory_poc.stages.s6_actions.run import _resolve_config

    ctx, _ = make_ctx(tmp_path)
    cfg = _resolve_config({"video_tier": tier, "motif": True})
    assert cfg["chapters"] == ("ch1",) and len(cfg["actions"]) == total
    assert set(MOTIF_VIDEO_TIERS["light"].actions) <= set(cfg["actions"]) <= set(APP_KEYS)
    assert len(set(cfg["actions"])) == total
    image, video = plan_calls(ctx, cfg)
    assert image.calls == 1 and video.calls == total
    assert (
        sum(cfg["durations"]["idle" if k.startswith("idle") else "emotion"] for k in cfg["actions"])
        == seconds
    )


def test_motif_prompt_drops_relationship_stage():
    from character_factory_poc.stages.s6_actions.catalog import MOTIF_STAGE_NOTE, build_prompt

    prompt = build_prompt("glad_good", "ch1", motif=True)
    assert MOTIF_STAGE_NOTE in prompt and "Relationship stage" not in prompt
    assert "Relationship stage 1" in build_prompt("glad_good", "ch1")


def test_light_generates_and_approves_only_ch1(flow):  # noqa: F811
    ctx, cid, video = flow
    ctx.config.stages["s6"] = {"video_tier": "light"}
    before = len(ctx._image.requests)
    out = run_s6(ctx, cid)
    chapters = read_json(out / "inputs.json")["chapters"]
    assert [ch["chapterId"] for ch in chapters] == ["ch1"]
    assert len(ctx._image.requests) - before == 1 and len(video.submits) == 10
    request_changes(ctx, cid, "ch1-glad_good")
    ctx.config.stages["s6"] = {"video_tier": "standard"}
    assert [p.calls for p in plan_calls(ctx, s6_config(ctx), cid)] == [3, 30]
    ctx.config.stages["s6"] = {"video_tier": "light"}
    assert [p.calls for p in plan_calls(ctx, s6_config(ctx), cid)] == [1]
    run_s6(ctx, cid)
    approve_gate(ctx, cid, "G5b", {"decision": "APPROVE"})
    approved, _ = load_approved_actions(ctx, cid)
    assert [c.actionId for c in approved.clips] == [f"ch1-{key}" for key in CORE]


def test_clip_warnings_use_each_exported_stage():
    tables = {
        "character_stage": {"columns": ["stage_no", "id"], "rows": [[1, 11], [2, 22], [3, 33]]},
        "character_clip": {"columns": ["character_stage_id"], "rows": [[11]] * 10 + [[22]] * 2},
    }
    warnings = clip_count_warnings({"tables": tables})
    assert len(warnings) == 2 and "ch2 영상 2편" in warnings[0] and "ch3 영상 0편" in warnings[1]
    assert clip_count_warnings({"tables": tables}, min_clips=2) == [
        warnings[1].replace("=10", "=2")
    ]


def test_export_reports_short_stages_without_blocking(tmp_path):
    ctx, cid = full_flow(tmp_path)
    build_package(ctx, cid)
    approve_package(ctx, cid)
    result, out = export_doki_app(ctx, cid, settings=_settings(tmp_path), heads=HEADS)
    warnings = clip_count_warnings(read_json(out / "doki-app/api-svc/seed.json"))
    assert len(warnings) == 3 and set(warnings) <= set(result.unmapped)
    assert ctx.state(cid).stage("sx").status == "APPROVED"
