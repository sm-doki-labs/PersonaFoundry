import json
import shutil
from pathlib import Path

import pytest

from character_factory_poc import cli
from character_factory_poc.common.config import load_env_file
from character_factory_poc.common.schema import validate
from character_factory_poc.pipeline.batch import run_batch
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake_image import FakeImageModel, solid_png
from character_factory_poc.providers.fake_video import FakeVideoModel
from character_factory_poc.stages.s0_source import parse, run
from character_factory_poc.stages.s4_frames.prompt import TWIN_IDENTITY

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "twin"


@pytest.fixture
def rig(tmp_path, monkeypatch):
    photo = tmp_path / "synthetic.png"
    photo.write_bytes(solid_png(18, 32, (2, 3, 4)))
    image, video = FakeImageModel(), FakeVideoModel()
    monkeypatch.setattr(
        "character_factory_poc.pipeline.context.make_image_model", lambda cfg: image
    )
    monkeypatch.setattr(
        "character_factory_poc.pipeline.context.make_video_model", lambda cfg: video
    )

    def invoke(*opts):
        return cli.main(["--root", str(tmp_path), "twin", "precheck", "--photo", str(photo), *opts])

    return invoke, photo, image, video


def read_report(root):
    (path,) = (root / "runs").glob("characters/*/precheck-result.json")
    return path.parent, json.loads(path.read_text())["steps"]


def test_default_plan_no_provider_or_files(rig, tmp_path, capsys):
    invoke, photo, image, video = rig
    photo.unlink()  # 승인 전에는 실제 사진 없이도 계획을 검토한다.
    (tmp_path / "factory.toml").write_text(
        '[providers.image]\nadapter="codex_image"\n[providers.video]\nadapter="xai_video"\n'
    )
    assert invoke() == 0
    output = capsys.readouterr().out
    for s in (
        "codex_image",
        "gpt-6.1-sol",
        "grok-imagine-video-1.5",
        "$0.85",
        "기준 얼굴",
        "편집 이미지",
        "6초",
        "precheck-result.json",
    ):
        assert s in output
    assert not image.requests and not video.submits and not video.collects
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("flags", [(), ("--image-only",), ("--video-only",)])
def test_single_artifacts_and_first_frame(rig, tmp_path, flags):
    invoke, photo, image, video = rig
    assert invoke("--execute", *flags) == 0
    folder, steps = read_report(tmp_path)
    want_image = "--video-only" not in flags
    want_video = "--image-only" not in flags
    assert len(image.requests) == int(want_image)
    assert len(video.submits) == len(video.collects) == int(want_video)
    assert [s["kind"] for s in steps] == (
        (["image"] if want_image else []) + (["video"] if want_video else [])
    )
    assert all(s["status"] == "SUCCESS" and (folder / s["artifact"]).is_file() for s in steps)
    if want_image:
        req = image.requests[0]
        assert TWIN_IDENTITY in req.prompt and "fictional" not in req.prompt
        assert Path(req.reference_images[0]) == photo
        assert Path(req.reference_images[1]).is_file()
    if want_video:
        req = video.submits[0]
        assert (req.duration, req.generate_audio, req.aspect_ratio) == (6, False, "9:16")
        assert Path(req.first_frame) == (folder / "first-frame.png" if want_image else photo)
        assert steps[-1]["jobId"] == video.collects[0]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("request rejected", "REFUSED"),
        ("content_policy_violation", "SAFETY_BLOCKED"),
        ("connection refused", "ERROR"),
        ("HTTP 429", "ERROR"),
    ],
)
def test_image_failure_skips_video_and_redacts_body(rig, tmp_path, monkeypatch, error, expected):
    invoke, _, image, video = rig

    def fail(req):
        raise RuntimeError(error + " sensitive-payload")

    monkeypatch.setattr(image, "generate", fail)
    assert invoke("--execute") == 1
    folder, steps = read_report(tmp_path)
    assert [s["status"] for s in steps] == [expected, "SKIPPED"]
    assert not video.submits
    assert "sensitive-payload" not in (folder / "precheck-result.json").read_text()


def test_submitted_video_block_preserves_job_and_frame(rig, tmp_path, monkeypatch):
    invoke, _, _, video = rig

    def fail(job, req):
        raise RuntimeError("safety block")

    monkeypatch.setattr(video, "collect", fail)
    assert invoke("--execute") == 1
    folder, steps = read_report(tmp_path)
    assert [s["status"] for s in steps] == ["SUCCESS", "SAFETY_BLOCKED"]
    assert steps[-1]["jobId"] == "fake-job-1" and len(video.submits) == 1
    assert (folder / "first-frame.png").is_file() and not (folder / "clip.mp4").exists()


@pytest.mark.parametrize(
    "config",
    [
        "[budget]\nmax_calls_per_command=1",
        '[budget]\nmax_cost_usd_per_command=0.18\n[providers.video]\nadapter="xai_video"',
        '[providers.video]\nadapter="xai_video"\nmodel="unknown-rate"',
    ],
)
def test_entire_budget_validated_before_any_call(rig, tmp_path, config):
    invoke, _, image, video = rig
    (tmp_path / "factory.toml").write_text(config)
    assert invoke("--execute") == 1
    assert not image.requests and not video.submits and not (tmp_path / "runs").exists()


def test_examples_parse_and_have_separate_holdouts(tmp_path):
    base = tmp_path / "inputs"
    shutil.copytree(EXAMPLES, base)
    spec_path = base / "batch.json"
    batch = validate("batch-spec-v1", json.loads(spec_path.read_text()))
    ctx = Context.load(tmp_path, execute=False)
    plan = run_batch(ctx, spec_path)
    assert plan.maxParallel == 2
    assert [c.modelMode for c in plan.characters] == ["TRAIN", "PROMPT_ONLY"]
    for item in batch.characters:
        path = base / item.source_pack
        raw = json.loads(path.read_text())
        validate("source-pack-v1", raw)
        raw["photos"][0]["path"] = "synthetic.png"
        (base / "synthetic.png").write_bytes(solid_png(18, 32, (1, 2, 3)))
        path.write_text(json.dumps(raw))
        pack, _ = run._load_pack(ctx, "demo", path)
        assert not parse.usage_problems(pack)
        msgs, _, _ = run._read_all(pack)
        corpus, holdout = parse.split_holdout(msgs, pack.holdout.fraction)
        assert corpus and holdout
        assert not {m.convId for m in corpus}.intersection(m.convId for m in holdout)


def test_route_example_contains_only_pinned_fields_and_no_key(monkeypatch):
    import os

    name = "RQC_CHARACTER_DIALOGUE_ROUTES"
    monkeypatch.setenv(name, "")
    assert load_env_file(EXAMPLES / "chat-routes.env.example") == [name]
    route = json.loads(os.environ[name])["public-demo"]
    assert route == dict(
        model="public-demo-adapter",
        apiKeyEnv="TWIN_SERVING_API_KEY",
        baseUrl="https://serving.invalid/v1",
    )


def test_official_image_precheck_executes_with_explicit_estimate(rig, tmp_path):
    invoke, _, image, video = rig
    (tmp_path / "factory.toml").write_text(
        '[providers.image]\nadapter="openai_images"\nestimated_cost_usd=1.0\n'
    )
    assert invoke("--execute", "--image-only") == 0
    assert len(image.requests) == 1 and not video.submits
    _, steps = read_report(tmp_path)
    assert steps[0]["status"] == "SUCCESS" and steps[0]["estimatedUsd"] == 1.0
