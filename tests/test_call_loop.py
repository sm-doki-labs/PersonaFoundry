"""사용자가 준 Lite 통화 행동셋의 제작 계약과 주제 분리를 검증한다."""

import pytest

from character_factory_poc.stages.s6_actions.catalog import build_prompt, clip_of
from character_factory_poc.stages.s6_actions.run import _duration, _resolve_config


def test_lite_has_idle_four_actions_and_separate_signature():
    cfg = _resolve_config(
        {
            "video_tier": "light",
            "motif": True,
            "signature": {"title": "찰칵", "motion": "손가락 프레임"},
        }
    )
    assert cfg["actions"] == [
        "idle_good",
        "speak_good",
        "cheering_good",
        "laughing_good",
        "greeting_good",
        "signature_good",
    ]
    assert [_duration(cfg, key) for key in cfg["actions"]] == [6] * 6
    assert cfg["generate_audio"] is False and cfg["pin_last_frame"] is True


def test_prompt_uses_scene_and_reference_not_son_details():
    cfg = _resolve_config(
        {
            "video_tier": "light",
            "motif": True,
            "signature": {"title": "손인사", "motion": "오른손을 한번 흔든다"},
            "video_scene": {"purpose": "친구와 집에서 대화", "referencePose": "앉은 자세"},
        }
    )
    clip = clip_of("greeting_good", cfg)
    prompt = build_prompt("greeting_good", "ch1", motif=True, clip=clip)
    assert "친구와 집에서 대화" in prompt and "앉은 자세" in prompt
    assert "15 to 20 degrees" in prompt and "3.0 seconds" in prompt
    for unwanted in ["KOREA", "swoosh", "black training", "hands clasped behind", "She is"]:
        assert unwanted not in prompt
    assert "existing logos" in prompt
    assert "No text, logos" not in prompt
    assert "middle-frame image" not in prompt


def test_keyframe_transport(tmp_path):
    from character_factory_poc.providers.base import VideoRequest
    from character_factory_poc.providers.fake_image import solid_png
    from character_factory_poc.providers.xai_video import XaiVideoModel

    photo = tmp_path / "middle.png"
    photo.write_bytes(solid_png(96, 96, (120, 120, 120)))
    model = XaiVideoModel(model="grok-imagine-video-1.5")
    req = VideoRequest(
        stage="s6",
        ref="test",
        prompt="pose",
        first_frame=str(photo),
        duration=6,
        last_frame=str(photo),
        keyframes=((2.0, str(photo)),),
    )
    body = model.body(req)
    assert body["keyframes"][0]["timestamp_s"] == 2.0
    assert body["keyframes"][0]["image"]["url"].startswith("data:image/")
    assert body["generate_audio"] is False


def test_postprocess_rejects_static_and_unreturned_motion(tmp_path):
    import cv2
    import numpy as np

    from character_factory_poc.stages.s6_actions.postprocess import select_cut

    ref = np.full((96, 96, 3), 160, dtype=np.uint8)
    cv2.rectangle(ref, (35, 15), (60, 75), (25, 50, 90), -1)
    photo = tmp_path / "ref.png"
    cv2.imwrite(str(photo), ref)
    for kind in ("static", "no_return", "return"):
        raw = tmp_path / (kind + ".mp4")
        writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), 20, (96, 96))
        for n in range(120):
            frame = ref.copy()
            if kind != "static" and n > 5 and (kind == "no_return" or n < 55):
                cv2.rectangle(frame, (28, 5), (70, 85), (200, 100, 60), -1)
            writer.write(frame)
        writer.release()
        result = select_cut(raw, photo, [2.5, 3.5])
        assert result["qualityApproved"] is False
        if kind == "return":
            assert 2.5 <= result["cutAtS"] <= 3.5
        else:
            assert result["cutAtS"] is None and result["status"] == "needs_review"


def test_strip_real_audio_and_preserve_talking_duration(tmp_path):
    import json
    import shutil
    import subprocess

    import pytest

    from character_factory_poc.providers.fake_image import solid_png
    from character_factory_poc.stages.s6_actions.postprocess import process

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg missing")
    photo = tmp_path / "ref.png"
    photo.write_bytes(solid_png(96, 96, (100, 80, 40)))
    raw = tmp_path / "with-audio.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(photo),
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=8000",
            "-t",
            "6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(raw),
        ],
        check=True,
        timeout=30,
    )
    data, report = process(raw, photo, {"trimWindowS": None})
    exported = tmp_path / "silent.mp4"
    exported.write_bytes(data)
    probe = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(exported)]
        )
    )
    assert not any(s["codec_type"] == "audio" for s in probe["streams"])
    assert abs(float(probe["streams"][0]["duration"]) - 6) < 0.1
    assert report["cutAtS"] is None and report["qualityApproved"] is False


from tests.test_actions import flow  # noqa: E402, F401


def test_factory_freezes_keyframe_and_detects_changed_source(flow):  # noqa: F811
    from character_factory_poc.common.store import read_json
    from character_factory_poc.pipeline.approve import approve_gate
    from character_factory_poc.providers.fake_image import solid_png
    from character_factory_poc.stages.s6_actions.run import _carry, run_s6, s6_config

    ctx, cid, video = flow
    folder = ctx.character_dir(cid)
    middle = folder / "pose.png"
    middle.write_bytes(solid_png(96, 96, (100, 80, 40)))
    ctx.config.stages["s6"] = {
        "video_tier": "light",
        "motif": True,
        "signature": {
            "title": "찰칵",
            "motion": "손가락 프레임",
            "template": "camera_click",
            "middleFramePath": "pose.png",
            "middleFrameAtS": 2.0,
        },
    }
    out = run_s6(ctx, cid)
    inputs = read_json(out / "inputs.json")
    assert inputs["productionProfile"] == "call-loop-v1"
    assert len(video.submits) == 6
    assert all(
        r.duration == 6 and not r.generate_audio and r.last_frame == r.first_frame
        for r in video.submits
    )
    req = next(r for r in video.submits if "signature_good" in r.ref)
    assert len(req.keyframes) == 1 and req.keyframes[0][0] == 2.0
    assert "keyframes/ch1-signature_good" in req.keyframes[0][1]
    assert inputs["chapters"][0]["actions"][-1]["production"]["middleFrame"]["sha256"]
    approve_gate(ctx, cid, "G5b", {"decision": "APPROVE"})
    assert _carry(ctx, cid, s6_config(ctx, cid)) == (out.name, {})
    middle.write_bytes(solid_png(96, 96, (200, 80, 40)))
    previous, changes = _carry(ctx, cid, s6_config(ctx, cid))
    assert previous == out.name and set(changes) == {"ch1-signature_good"}


@pytest.mark.parametrize("resumable", [True, False])
def test_postprocess_retry_reuses_paid_raw_without_resubmit(flow, tmp_path, monkeypatch, resumable):  # noqa: F811
    import shutil
    import subprocess
    from dataclasses import replace

    import pytest

    from character_factory_poc.common.errors import VideoGenerationError
    from character_factory_poc.providers.fake_video import FakeVideoModel
    from character_factory_poc.stages.s6_actions import postprocess
    from character_factory_poc.stages.s6_actions.run import run_s6

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg missing")
    raw = tmp_path / "real.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=gray:s=96x96:r=12:d=6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(raw),
        ],
        check=True,
        timeout=30,
    )

    class RenderedFake(FakeVideoModel):
        name = "xai_video"

        def collect(self, job_id, request):
            return replace(super().collect(job_id, request), data=raw.read_bytes())

    ctx, cid, _ = flow
    video = RenderedFake()
    video.resumable = resumable
    ctx.use_video(video)
    ctx.config.stages["s6"] = {
        "video_tier": "light",
        "motif": True,
        "signature": {"title": "인사", "motion": "손인사"},
    }
    from threading import Barrier

    all_downloaded = Barrier(6)
    with monkeypatch.context() as patch:

        def fail(*args):
            all_downloaded.wait(10)
            raise VideoGenerationError("postprocess interrupted")

        patch.setattr(postprocess, "process", fail)
        with pytest.raises(VideoGenerationError, match="interrupted"):
            run_s6(ctx, cid)
    submitted_before = len(video.submits)
    collected_before = len(video.collects)
    from character_factory_poc.stages.s6_actions.run import plan_calls, s6_config

    assert sum(p.calls for p in plan_calls(ctx, s6_config(ctx, cid), cid)) == 0
    out = run_s6(ctx, cid)
    assert out.name == "va1"
    assert len(video.submits) == 6
    assert len(video.collects) - collected_before == 6 - submitted_before


def test_idle_has_no_lip_motion_and_is_not_trimmed():
    cfg = _resolve_config(
        {"video_tier": "light", "motif": True, "signature": {"title": "인사", "motion": "손인사"}}
    )
    idle = clip_of("idle_good", cfg)
    text = build_prompt("idle_good", "ch1", motif=True, clip=idle)
    assert idle["playType"] == "idle" and idle["pickRole"] is None
    assert idle["production"]["trimWindowS"] is None
    assert "No lip movement at any time" in text and "6 seconds of quiet listening" in text
    assert "continuous natural talking" not in text and "three to five syllables" not in text


def test_partial_scene_override_keeps_interview_purpose(tmp_path):
    from character_factory_poc.common.store import read_json
    from character_factory_poc.pipeline.origin import write_video_scene
    from character_factory_poc.web.sources import Settings

    body = Settings.model_validate({"videoTier": "light", "videoScene": {"wardrobe": "흰 셔츠"}})
    write_video_scene(tmp_path, body.videoScene.model_dump(exclude_unset=True))
    assert read_json(tmp_path / "video-settings.json")["videoScene"] == {"wardrobe": "흰 셔츠"}


def test_keyframes_reject_shared_grid_slot(tmp_path):
    from character_factory_poc.common.errors import VideoGenerationError
    from character_factory_poc.providers.base import VideoRequest
    from character_factory_poc.providers.fake_image import solid_png
    from character_factory_poc.providers.xai_video import XaiVideoModel

    photo = tmp_path / "photo.png"
    photo.write_bytes(solid_png(96, 96, (80, 80, 80)))
    req = VideoRequest(
        stage="s6",
        ref="test",
        prompt="pose",
        first_frame=str(photo),
        duration=6,
        keyframes=((2.0, str(photo)), (2.1, str(photo))),
    )
    with pytest.raises(VideoGenerationError, match="중간 프레임"):
        XaiVideoModel().body(req)


def test_incomplete_raw_cache_never_submits_again(flow, monkeypatch):  # noqa: F811
    from character_factory_poc.common.errors import CheckFailed, VideoGenerationError
    from character_factory_poc.stages.s6_actions import run as runner
    from character_factory_poc.stages.s6_actions.run import plan_calls, run_s6, s6_config

    ctx, cid, video = flow
    video.resumable = False
    ctx.config.stages["s6"] = {
        "video_tier": "light",
        "motif": True,
        "signature": {"title": "인사", "motion": "손인사"},
    }
    original = runner.write_once_json

    def interrupted(path, obj):
        if path.parent.name == "raw":
            raise VideoGenerationError("interrupted receipt write")
        return original(path, obj)

    with monkeypatch.context() as patch:
        patch.setattr(runner, "write_once_json", interrupted)
        with pytest.raises(VideoGenerationError):
            run_s6(ctx, cid)
    submits = len(video.submits)
    with pytest.raises(CheckFailed, match="불완전"):
        plan_calls(ctx, s6_config(ctx, cid), cid)
    with pytest.raises(CheckFailed, match="불완전"):
        run_s6(ctx, cid)
    assert len(video.submits) == submits


def test_signature_only_rejection_keeps_basics_and_exact_keyframe_timing(flow):  # noqa: F811
    from character_factory_poc.common.store import read_json
    from character_factory_poc.pipeline.approve import approve_gate
    from character_factory_poc.providers.fake_image import solid_png
    from character_factory_poc.stages.s6_actions.run import _carry, plan_calls, run_s6, s6_config
    from tests.test_actions import request_changes

    ctx, cid, video = flow
    middle = ctx.character_dir(cid) / "pose.png"
    middle.write_bytes(solid_png(96, 96, (80, 70, 90)))
    ctx.config.stages["s6"] = {
        "video_tier": "light",
        "motif": True,
        "signature": {
            "title": "인사",
            "motion": "손인사",
            "middleFramePath": "pose.png",
            "middleFrameAtS": 2.49,
        },
    }
    out = run_s6(ctx, cid)
    request_changes(ctx, cid, "ch1-signature_good")
    middle.write_bytes(solid_png(96, 96, (80, 170, 90)))
    assert sum(p.calls for p in plan_calls(ctx, s6_config(ctx, cid), cid)) == 1
    out2 = run_s6(ctx, cid)
    assert len(video.submits) == 7
    assert read_json(out2 / "inputs.json")["previousRev"] == out.name
    approve_gate(ctx, cid, "G5b", {"decision": "APPROVE"})
    ctx.config.stages["s6"]["signature"]["middleFrameAtS"] = 2.51
    assert set(_carry(ctx, cid, s6_config(ctx, cid))[1]) == {"ch1-signature_good"}
