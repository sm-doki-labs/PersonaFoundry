"""S6·G5b의 생성·선택·부분 재생성·재개를 가짜 공급자로 검증한다."""

from __future__ import annotations

import re
from dataclasses import replace

import cv2
import pytest

from acf.cli import main
from acf.common.canonical import sha256_file
from acf.common.config import ProviderConfig
from acf.common.errors import (
    BudgetExceeded,
    CheckFailed,
    FactoryError,
    GateNotApprovedError,
    VideoGenerationError,
    VideoTimeoutError,
)
from acf.common.store import read_json, verify_manifest
from acf.contracts.video import VIDEO_ID
from acf.pipeline.approve import approve_gate
from acf.pipeline.orchestrator import RunOptions, run_until
from acf.providers.fake_image import FakeImageModel, solid_png
from acf.providers.fake_video import FakeVideoModel
from acf.stages.s4_frames.approve import load_approved_frames
from acf.stages.s4_frames.run import run_s4
from acf.stages.s6_actions.app_clips import APP_CLIPS
from tests.support.flow import approve_plan_v2, make_ctx, through_s2
from tests.test_scene_flow import backgrounds, poses, scenes, through_pose


@pytest.fixture
def flow(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    agents.set("s4a", backgrounds)
    agents.set("s4b-scene", scenes)
    agents.set("s4b-pose", poses)
    cid = through_s2(ctx)
    approve_plan_v2(ctx, cid)
    through_pose(ctx, cid)
    run_s4(ctx, cid)
    approve_gate(ctx, cid, "G4", {"decision": "APPROVE"})
    video = FakeVideoModel()
    ctx.use_video(video)
    return ctx, cid, video


def run(ctx, cid):
    from acf.stages.s6_actions.run import run_s6

    return run_s6(ctx, cid)


def picks(out):
    return {c["actionId"]: c["asset"]["candidateId"] for c in read_json(out / "clips.json")}


def request_changes(ctx, cid, aid="ch2-glad_good"):
    approve_gate(
        ctx,
        cid,
        "G5b",
        {
            "decision": "REQUEST_CHANGES",
            "requestedChanges": [{"field": aid, "note": "고개 움직임을 줄여 주세요"}],
        },
    )


def test_s6_requires_g4(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    cid = through_s2(ctx)
    with pytest.raises(GateNotApprovedError, match="G4"):
        run(ctx, cid)
    assert not (ctx.character_dir(cid) / "s6-actions").exists()


def test_offline_l2_pins_good_and_neutral_frames_and_records_18_clips(flow):
    from acf.stages.s6_actions.catalog import STAGE_NOTES

    ctx, cid, video = flow
    before_images = len(ctx._image.requests)
    out = run(ctx, cid)
    approved, frames_dir = load_approved_frames(ctx, cid)
    inputs = read_json(out / "inputs.json")
    assert out.name == "va1" and inputs["schemaVersion"] == "action-inputs-v2"
    assert inputs["frameRev"] == approved.frameRev and inputs["preset"] == "l2"
    assert "duration" not in inputs
    image_requests = ctx._image.requests[before_images:]
    assert len(image_requests) == 3
    for frame, chapter, req in zip(
        approved.frames, inputs["chapters"], image_requests, strict=True
    ):
        good = out / "first-frames" / f"{frame.chapterId}-good.png"
        bad = out / chapter["badFrame"]["path"]
        assert good.read_bytes() == (frames_dir / frame.path).read_bytes()
        assert sha256_file(good) == frame.sha256 == chapter["goodFrame"]["sha256"]
        assert req.stage == "s6" and req.reference_images == (str(good),)
        assert req.ref == f"{cid}/va1/{frame.chapterId}-bad-frame"
        assert req.size == "1024x1536"
        assert "calm neutral unsmiling" in req.prompt and "same person" in req.prompt
        assert req.negative_prompt == "smile, text, watermark, logo, hand on face"
        source = chapter["badFrameSource"]
        assert source["source"] == chapter["goodFrame"]
        assert source["provider"] == "fake_image" and source["model"] == "fake-image"
        assert source["rawSize"] == [43, 64] and source["croppedSize"] == [36, 64]
        assert source["prompt"] == req.prompt and source["negativePrompt"] == req.negative_prompt
        assert (out / f"first-frames/{frame.chapterId}-bad-raw.png").is_file()
        h, w = cv2.imread(str(bad)).shape[:2]
        assert (w, h) == (36, 64) and sha256_file(bad) == chapter["badFrame"]["sha256"]
        assert chapter["stageNote"] == STAGE_NOTES[frame.chapterId]
    assert len(video.submits) == 18
    app = {c["key"]: c for c in APP_CLIPS}
    for req in video.submits:
        aid = req.ref.split("/")[-1].removesuffix("-v1")
        ch, key = aid.split("-", 1)
        assert (req.stage, req.aspect_ratio, req.resolution) == ("s6", "9:16", "720p")
        assert req.duration == (15 if key.startswith("idle_") else 10)
        assert not req.generate_audio and "speaking" not in req.prompt.lower()
        assert app[key]["motion"] in req.prompt and STAGE_NOTES[ch] in req.prompt
        mood = app[key]["mood"]
        assert req.first_frame == str(out / f"first-frames/{ch}-{mood}.png")
    clips = read_json(out / "clips.json")
    assert [c["actionId"] for c in clips] == [
        f"ch{ch}-{key}"
        for ch in range(1, 4)
        for key in ("idle_good", "idle_bad", "glad_good", "amused_good", "shy_good", "sorry_good")
    ]
    for clip in clips:
        asset = clip["asset"]
        assert clip["schemaVersion"] == "action-clip-v2"
        assert clip["pickRole"] == (None if clip["playType"] == "idle" else "emotion")
        assert clip["actionCategory"] is None and clip["title"] == app[clip["actionKey"]]["title"]
        assert re.fullmatch(VIDEO_ID, asset["videoId"])
        assert asset["videoId"] == f"vd-{cid}-{clip['actionId']}-va1-1"
        assert asset["fileSha256"] == sha256_file(out / asset["filePath"])
        name = f"{clip['actionId']}-v1.json"
        job = read_json(out / "jobs" / name)
        assert job["status"] == "DONE" and job["stage"] == "s6"
        chapter = next(ch for ch in inputs["chapters"] if ch["chapterId"] == clip["chapterId"])
        assert job["firstFrameSha256"] == chapter[f"{clip['mood']}Frame"]["sha256"]
        assert read_json(out / "assets" / name) == asset
    page = (out / "gate-G5b.html").read_text("utf-8")
    assert page.count("<video ") == 18 and page.count("<img ") == 6
    assert "G5b 동작 영상 선택" in page and f"acf gate import {cid} G5b" in page
    for text in (
        "REQUEST_CHANGES",
        "제외",
        "미소 출발",
        "무표정 출발",
        "15초",
        "10초",
        "사용 조건",
        "움직임 프롬프트",
        "기본 대기 (미소)",
    ):
        assert text in page
    assert "https://" not in page and "http://" not in page
    calls = [c for c in ctx.ledger(cid).calls() if c["stage"] == "s6"]
    assert len(calls) == 21 and sum(c["kind"] == "VIDEO" for c in calls) == 18
    assert ctx.state(cid).stage("s6").status == "AWAITING_HUMAN"
    assert ctx.state(cid).gate("G5b").status == "AWAITING_HUMAN"
    assert verify_manifest(out) == []


def test_select_can_exclude_actions_and_load_approved_videos(flow):
    from acf.stages.s6_actions.approve import load_approved_actions

    ctx, cid, _ = flow
    with pytest.raises(GateNotApprovedError):
        load_approved_actions(ctx, cid)
    ctx.config.stages["s6"] = {"candidates": 2}
    out = run(ctx, cid)
    chosen = picks(out)
    del chosen["ch1-idle_good"]
    approve_gate(
        ctx,
        cid,
        "G5b",
        {"decision": "SELECT", "picks": chosen, "excluded": ["ch1-idle_good"], "minutes": 2},
    )
    approved, rev_dir = load_approved_actions(ctx, cid)
    assert rev_dir == out and approved.actionRev == "va1"
    assert approved.excluded == ["ch1-idle_good"] and len(approved.clips) == 17
    assert approved.schemaVersion == "action-videos-approved-v2"
    action_inputs = {
        a["actionId"]: a for ch in read_json(out / "inputs.json")["chapters"] for a in ch["actions"]
    }
    for clip in approved.clips:
        spec = action_inputs[clip.actionId]
        assert clip.stage == int(clip.chapterId[2]) and clip.clipKey == spec["actionKey"]
        assert (clip.title, clip.description, clip.useWhen, clip.duration) == (
            spec["title"],
            spec["description"],
            spec["useWhen"],
            spec["duration"],
        )
        assert clip.video.id == "v2"
        assert sha256_file(out / clip.video.path) == clip.video.sha256
    record = read_json(ctx.character_dir(cid) / "gates/G5b-va1.json")
    assert record["selections"] == [f"{aid}:v2" for aid in chosen]
    assert ctx.state(cid).gate("G5b").status == "APPROVED"
    assert verify_manifest(out) == []


@pytest.mark.parametrize(
    "invalid",
    [
        "unknown",
        "missing",
        "chapter",
        "candidate",
        "overlap",
        "duplicate",
        "bad_picks",
        "bad_excluded",
    ],
)
def test_invalid_selection_leaves_gate_and_artifacts_untouched(flow, invalid):
    ctx, cid, _ = flow
    out = run(ctx, cid)
    answer = {"decision": "SELECT", "picks": picks(out), "excluded": []}
    if invalid == "unknown":
        answer["picks"]["ch1-unknown"] = "v1"
    elif invalid == "missing":
        del answer["picks"]["ch1-idle_good"]
    elif invalid == "chapter":
        answer["excluded"] = [a for a in answer["picks"] if a.startswith("ch1-")]
        answer["picks"] = {a: c for a, c in answer["picks"].items() if a not in answer["excluded"]}
    elif invalid == "candidate":
        answer["picks"]["ch1-idle_good"] = "v99"
    elif invalid == "overlap":
        answer["excluded"] = ["ch1-idle_good"]
    elif invalid == "duplicate":
        del answer["picks"]["ch1-idle_good"]
        answer["excluded"] = ["ch1-idle_good", "ch1-idle_good"]
    elif invalid == "bad_picks":
        answer["picks"] = []
    else:
        answer["excluded"] = [None]
    before = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    with pytest.raises(FactoryError):
        approve_gate(ctx, cid, "G5b", answer)
    assert ctx.state(cid).gate("G5b").status == "AWAITING_HUMAN"
    assert not (ctx.character_dir(cid) / "gates/G5b-va1.json").exists()
    assert {p: p.read_bytes() for p in out.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize(
    "changes",
    [
        [],
        [{"field": "ch1-missing", "note": "수정"}],
        [{"field": "ch1-idle_good", "note": " "}],
        [{"field": "ch1-idle_good", "note": "수정"}] * 2,
        [{"field": [], "note": "수정"}],
    ],
)
def test_invalid_change_request_does_not_decide_gate(flow, changes):
    ctx, cid, _ = flow
    run(ctx, cid)
    with pytest.raises(FactoryError):
        approve_gate(ctx, cid, "G5b", {"decision": "REQUEST_CHANGES", "requestedChanges": changes})
    assert ctx.state(cid).gate("G5b").status == "AWAITING_HUMAN"


def test_request_changes_regenerates_one_action_and_copies_other_assets(flow):
    from acf.stages.s6_actions.run import plan_calls, s6_config

    ctx, cid, video = flow
    first = run(ctx, cid)
    original = read_json(first / "clips.json")
    original_bytes = (first / "manifest.sha256").read_bytes()
    request_changes(ctx, cid)
    assert plan_calls(ctx, s6_config(ctx), cid)[0].calls == 1
    before_images = len(ctx._image.requests)
    ctx.max_calls = 1
    video.submits.clear()
    second = run(ctx, cid)
    assert second.name == "va2" and len(video.submits) == 1
    assert len(ctx._image.requests) == before_images
    for old, new in zip(
        read_json(first / "inputs.json")["chapters"],
        read_json(second / "inputs.json")["chapters"],
        strict=True,
    ):
        assert old["goodFrame"] == new["goodFrame"] and old["badFrame"] == new["badFrame"]
        assert new["badFrameSource"] == old["badFrameSource"] | {"reusedFrom": "va1"}
        for name in (
            f"{old['chapterId']}-good.png",
            f"{old['chapterId']}-bad.png",
            f"{old['chapterId']}-bad-raw.png",
        ):
            assert (first / "first-frames" / name).read_bytes() == (
                second / "first-frames" / name
            ).read_bytes()
    assert "Reviewer note: 고개 움직임을 줄여 주세요" in video.submits[0].prompt
    inputs = read_json(second / "inputs.json")
    assert inputs["previousRev"] == "va1" and inputs["regenerate"] == ["ch2-glad_good"]
    for old, new in zip(original, read_json(second / "clips.json"), strict=True):
        if new["actionId"] == "ch2-glad_good":
            assert new["reusedFrom"] is None and "-va2-" in new["asset"]["videoId"]
        else:
            assert new["reusedFrom"] == "va1" and old["asset"] == new["asset"]
            rel = new["asset"]["filePath"]
            assert (first / rel).read_bytes() == (second / rel).read_bytes()
            name = f"{new['actionId']}-v1.json"
            assert (first / "assets" / name).read_bytes() == (second / "assets" / name).read_bytes()
    assert (first / "manifest.sha256").read_bytes() == original_bytes
    assert verify_manifest(second) == []


def test_repeated_partial_regeneration_preserves_reused_prompt_and_note(flow):
    ctx, cid, video = flow
    run(ctx, cid)
    request_changes(ctx, cid, "ch1-idle_good")
    second = run(ctx, cid)
    previous = read_json(second / "inputs.json")["chapters"][0]["actions"][0]
    assert previous["reviewNote"] == "고개 움직임을 줄여 주세요"
    request_changes(ctx, cid, "ch2-glad_good")
    video.submits.clear()
    third = run(ctx, cid)
    reused = read_json(third / "inputs.json")["chapters"][0]["actions"][0]
    assert reused == previous
    assert len(video.submits) == 1
    clip = next(c for c in read_json(third / "clips.json") if c["actionId"] == "ch1-idle_good")
    assert clip["reusedFrom"] == "va2" and clip["asset"]["settings"]["prompt"] == reused["prompt"]


@pytest.mark.parametrize(
    "changed",
    [
        "actions",
        "candidates",
        "durations",
        "resolution",
        "aspect_ratio",
        "generate_audio",
        "frames",
        "reject",
    ],
)
def test_changed_inputs_or_reject_regenerate_full_set(flow, changed):
    from acf.stages.s6_actions.run import plan_calls, s6_config

    ctx, cid, video = flow
    run(ctx, cid)
    if changed == "reject":
        approve_gate(ctx, cid, "G5b", {"decision": "REJECT"})
    else:
        request_changes(ctx, cid)
        if changed == "frames":
            run_s4(ctx, cid)
            approve_gate(ctx, cid, "G4", {"decision": "APPROVE"})
        else:
            values = {
                "actions": [
                    "idle_bad",
                    "idle_good",
                    "glad_good",
                    "amused_good",
                    "shy_good",
                    "sorry_good",
                ],
                "candidates": 2,
                "durations": {"emotion": 6},
                "resolution": "480p",
                "aspect_ratio": "1:1",
                "generate_audio": True,
            }
            ctx.config.stages["s6"] = {changed: values[changed]}
    count = 36 if changed == "candidates" else 18
    assert [p.calls for p in plan_calls(ctx, s6_config(ctx), cid)] == [3, count]
    video.submits.clear()
    out = run(ctx, cid)
    assert len(video.submits) == count
    assert all(c["reusedFrom"] is None for c in read_json(out / "clips.json"))


@pytest.mark.parametrize("timeout", [False, True])
def test_resume_reuses_revision_and_completed_jobs(flow, timeout):
    ctx, cid, _ = flow

    class Flaky(FakeVideoModel):
        def collect(self, job_id, request):
            if len(self.collects) == 1:
                self.collects.append(job_id)
                error = (
                    VideoTimeoutError(job_id, "대기 중")
                    if timeout
                    else VideoGenerationError("실패")
                )
                raise error
            return super().collect(job_id, request)

    flaky = Flaky()
    ctx.use_video(flaky)
    with pytest.raises(VideoGenerationError):
        run(ctx, cid)
    assert ctx.state(cid).stage("s6").status == "CHECK_FAILED"
    first_dir = ctx.character_dir(cid) / "s6-actions/va1"
    before_images = len(ctx._image.requests)
    inputs = (first_dir / "inputs.json").read_bytes()
    done = (first_dir / "assets/ch1-idle_good-v1.json").read_bytes()
    job = read_json(first_dir / "jobs/ch1-idle_bad-v1.json")
    assert job["status"] == ("SUBMITTED" if timeout else "FAILED")
    working = FakeVideoModel()
    ctx.use_video(working)
    out = run(ctx, cid)
    assert len(ctx._image.requests) == before_images
    assert out == first_dir and len(working.submits) == (16 if timeout else 17)
    assert len(working.collects) == 17
    assert not any(r.ref.endswith("ch1-idle_good-v1") for r in working.submits)
    assert (out / "inputs.json").read_bytes() == inputs
    assert (out / "assets/ch1-idle_good-v1.json").read_bytes() == done


def test_resume_after_process_interrupt(flow):
    ctx, cid, _ = flow

    class Interrupted(FakeVideoModel):
        def submit(self, request):
            raise KeyboardInterrupt

    ctx.use_video(Interrupted())
    with pytest.raises(KeyboardInterrupt):
        run(ctx, cid)
    assert ctx.state(cid).stage("s6").status == "RUNNING"
    ctx.use_video(FakeVideoModel())
    assert run(ctx, cid).name == "va1"


@pytest.mark.parametrize(
    "cfg",
    [
        {"preset": "missing"},
        {"preset": []},
        {"actions": ["missing"]},
        {"actions": ["idle_good", "idle_good"]},
        {"actions": "idle_good"},
        {"actions": [[]]},
        {"candidates": 0},
        {"candidates": 5},
        {"candidates": True},
        {"candidates": "two"},
        {"durations": {"idle": 0}},
        {"durations": {"emotion": 16}},
        {"durations": {"special": True}},
        {"durations": {"emotion": "10"}},
        {"durations": []},
        {"resolution": "360p"},
        {"aspect_ratio": "9/16"},
        {"aspect_ratio": "0:16"},
        {"aspect_ratio": None},
        {"aspect_ratio": []},
    ],
)
def test_bad_config_fails_before_calls_or_writes(flow, cfg):
    ctx, cid, video = flow
    ctx.config.stages["s6"] = cfg
    before = {p: p.read_bytes() for p in ctx.character_dir(cid).rglob("*") if p.is_file()}
    images = len(ctx._image.requests)
    with pytest.raises(CheckFailed):
        run(ctx, cid)
    assert not (ctx.character_dir(cid) / "s6-actions").exists() and not video.submits
    assert {p: p.read_bytes() for p in ctx.character_dir(cid).rglob("*") if p.is_file()} == before
    assert len(ctx._image.requests) == images


def test_budget_and_provider_settings_checked_before_writes(flow):
    ctx, cid, video = flow
    before = (ctx.character_dir(cid) / "state.json").read_bytes()
    ctx.max_calls = 20
    with pytest.raises(BudgetExceeded):
        run(ctx, cid)
    assert (ctx.character_dir(cid) / "state.json").read_bytes() == before
    assert not (ctx.character_dir(cid) / "s6-actions").exists() and not video.submits
    ctx.max_calls = None

    class Unsupported(FakeVideoModel):
        def check_settings(self, duration, resolution):
            assert not (ctx.character_dir(cid) / "s6-actions").exists()
            raise VideoGenerationError("지원하지 않는 설정")

    ctx.use_video(Unsupported())
    with pytest.raises(VideoGenerationError):
        run(ctx, cid)
    assert not (ctx.character_dir(cid) / "s6-actions").exists()
    assert ctx.state(cid).stage("s6").status == "CHECK_FAILED"


def test_non_mp4_is_rejected(flow):
    ctx, cid, _ = flow

    class Broken(FakeVideoModel):
        def collect(self, job_id, request):
            return replace(super().collect(job_id, request), data=b"<html>error</html>")

    ctx.use_video(Broken())
    with pytest.raises(VideoGenerationError, match="MP4"):
        run(ctx, cid)
    out = ctx.character_dir(cid) / "s6-actions/va1"
    assert read_json(out / "jobs/ch1-idle_good-v1.json")["status"] == "FAILED"
    assert not (out / "clips.json").exists()


def test_dry_run_shows_plan_without_side_effects(flow, capsys):
    ctx, cid, video = flow
    char_dir = ctx.character_dir(cid)
    before = {p: p.read_bytes() for p in char_dir.rglob("*") if p.is_file()}
    assert main(["--root", str(ctx.config.root), "video", "actions", cid]) == 0
    output = capsys.readouterr().out
    assert "무표정 첫 프레임 3장" in output
    assert "동작 영상 18편" in output and "0.00 USD" in output
    assert before == {p: p.read_bytes() for p in char_dir.rglob("*") if p.is_file()}
    assert not video.submits


def test_orchestrator_reaches_g5b_and_auto_approval_selects_v1(flow):
    from acf.stages.s6_actions.approve import load_approved_actions

    ctx, cid, _ = flow
    log = run_until(ctx, cid, RunOptions(until="G5b"))
    assert log.stopped_at == "G5b" and "G5b" in log.waiting
    assert ctx.state(cid).gate("G5b").status == "AWAITING_HUMAN"
    approve_gate(ctx, cid, "G5b", {"decision": "APPROVE"})
    approved, _ = load_approved_actions(ctx, cid)
    assert len(approved.clips) == 18 and all(c.video.id == "v1" for c in approved.clips)


def test_catalog_prompts_and_cost_plans(flow):
    from acf.stages.s6_actions.catalog import CATALOG, PRESETS, STAGE_NOTES, build_prompt
    from acf.stages.s6_actions.run import plan_calls, s6_config

    ctx, _, _ = flow
    assert list(CATALOG) == [c["key"] for c in APP_CLIPS]
    assert len(CATALOG) == 37 and PRESETS["standard"] == list(CATALOG)
    for clip in APP_CLIPS:
        key = clip["key"]
        assert CATALOG[key]["pickRole"] == (None if clip["playType"] == "idle" else "emotion")
        for ch in ("ch1", "ch2", "ch3"):
            prompt = build_prompt(key, ch)
            assert prompt == (
                clip["motion"] + " " + STAGE_NOTES[ch] + " "
                "Keep the same person, face, outfit and background as the first frame. "
                "No text, logos or extra people."
            )
            assert "speaking" not in prompt.lower()
    assert build_prompt("glad_good", "ch2", review_note="slower").endswith("Reviewer note: slower")
    ctx.config.providers["video"] = ProviderConfig(
        adapter="xai_video", model="grok-imagine-video-1.5-lite"
    )
    plans = plan_calls(ctx, s6_config(ctx))
    assert [p.calls for p in plans] == [3, 18]
    assert plans[-1].est_cost_usd == pytest.approx(6 * (15 * 0.03 + 0.01) + 12 * (10 * 0.03 + 0.01))
    ctx.config.stages["s6"] = {"preset": "standard"}
    standard = plan_calls(ctx, s6_config(ctx))
    assert [p.calls for p in standard] == [3, 111]
    assert standard[-1].est_cost_usd == pytest.approx(
        6 * (15 * 0.03 + 0.01) + 105 * (10 * 0.03 + 0.01)
    )
    ctx.config.providers["video"] = replace(ctx.config.providers["video"], model="unknown")
    with pytest.raises(CheckFailed, match="단가"):
        plan_calls(ctx, s6_config(ctx))


def test_good_only_override_needs_no_image_edit_and_merges_durations(flow):
    from acf.stages.s6_actions.run import plan_calls, s6_config

    ctx, cid, video = flow
    ctx.config.stages["s6"] = {
        "preset": "standard",
        "actions": ["idle_good", "glad_good"],
        "durations": {"emotion": 6},
    }
    cfg = s6_config(ctx)
    assert cfg["durations"] == {"idle": 15, "emotion": 6, "special": 6}
    assert [p.calls for p in plan_calls(ctx, cfg, cid)] == [6]
    before_images = len(ctx._image.requests)
    out = run(ctx, cid)
    assert len(ctx._image.requests) == before_images and len(video.submits) == 6
    inputs = read_json(out / "inputs.json")
    assert inputs["preset"] == "custom"
    for ch in inputs["chapters"]:
        assert ch["badFrame"] is None and ch["badFrameSource"] is None
    assert {r.duration for r in video.submits} == {6, 15}
    assert (out / "gate-G5b.html").read_text().count("<img ") == 3


@pytest.mark.parametrize("data", [b"not an image", solid_png(64, 64, (0, 0, 0))])
def test_invalid_neutral_frame_fails_before_video_submission(flow, data):
    ctx, cid, video = flow

    class BadImage(FakeImageModel):
        def generate(self, request):
            return replace(super().generate(request), data=data)

    ctx.use_image(BadImage())
    with pytest.raises(CheckFailed):
        run(ctx, cid)
    assert not video.submits
    assert ctx.state(cid).stage("s6").status == "CHECK_FAILED"
