"""이미지 자동 검사와 사람 관문 연결을 합성 이미지·가짜 공급자로 검증한다."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from character_factory_poc.cli import main
from character_factory_poc.common.errors import BudgetExceeded, CheckFailed
from character_factory_poc.common.schema import dump
from character_factory_poc.contracts.qa import QaSummary
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.providers.base import ImageRequest, VisionRequest
from character_factory_poc.providers.fake_image import FakeImageModel, solid_png
from character_factory_poc.providers.fake_vision import FakeVisionModel, all_pass
from character_factory_poc.providers.openai_compat import OpenAICompatVisionModel
from character_factory_poc.stages.image_qa import (
    RUBRICS,
    QaSettings,
    generate_checked,
    parse_verdict,
)
from character_factory_poc.stages.s4_frames.run import run_s4
from character_factory_poc.stages.s4a_backgrounds.run import plan_calls as background_calls
from character_factory_poc.stages.s4a_backgrounds.run import run_s4a
from character_factory_poc.stages.s4b_poses.run import run_s4b
from tests.support.flow import approve_plan_v2, make_ctx, through_s2
from tests.test_scene_flow import backgrounds, choose_bg, flow, poses, read, scenes, through_pose

# flow fixture를 이 모듈에서도 쓴다.
__all__ = ["flow"]


def verdict(req, failed=(), unsure=()):
    result = all_pass(req)
    for item in result["items"]:
        item["verdict"] = (
            "FAIL" if item["id"] in failed else "UNSURE" if item["id"] in unsure else "PASS"
        )
        item["reason"] = f"확인 <{item['id']}>"
    result["fixHint"] = "Remove the person, preserve the place." if failed else ""
    return result


def checked(tmp_path, *, responder=None, settings=None, refs=()):
    image = FakeImageModel()
    vision = FakeVisionModel(responder=responder)
    request = ImageRequest(
        stage="s4a",
        prompt="Empty courtyard.",
        ref="unit/plate",
        size="1024x1536",
        reference_images=refs,
    )
    outcome = generate_checked(
        image_model=image,
        vision=vision,
        request=request,
        ratio=(9, 16),
        rubric=RUBRICS["plate-v1"],
        context="저녁의 마당",
        judge_refs=[],
        out_dir=tmp_path,
        image_id="plate",
        settings=settings or QaSettings(),
    )
    return outcome, image, vision


def test_first_pass(tmp_path):
    outcome, image, vision = checked(tmp_path)
    assert len(image.requests) == len(vision.requests) == 1
    assert outcome.report.status == "PASS" and outcome.report.finalAttempt == 1
    assert outcome.data == (tmp_path / "attempts/plate-a1.png").read_bytes()


@pytest.mark.parametrize("mode", ["edit", "regenerate"])
def test_fix_once(tmp_path, mode):
    calls = []

    def responder(req):
        calls.append(req)
        return verdict(req, failed=("no_people",) if len(calls) == 1 else ())

    outcome, image, vision = checked(
        tmp_path, responder=responder, settings=QaSettings(fix_mode=mode), refs=("identity.png",)
    )
    assert len(image.requests) == len(vision.requests) == 2
    assert outcome.report.status == "PASS" and outcome.report.finalAttempt == 2
    second = image.requests[1]
    assert "Fix: Remove the person" in second.prompt
    if mode == "edit":
        assert second.prompt.startswith("Edit the last attached image")
        assert second.reference_images == ("identity.png", str(tmp_path / "attempts/plate-a1.png"))
    else:
        assert second.reference_images == ("identity.png",)
        assert second.prompt.startswith("Empty courtyard.")
    assert outcome.data == (tmp_path / "attempts/plate-a2.png").read_bytes()


@pytest.mark.parametrize("counts,selected", [([1, 2, 3], 1), ([2, 1, 2], 2), ([2, 1, 1], 3)])
def test_exhausted_selects_fewest_failures_latest_tie(tmp_path, counts, selected):
    rounds = iter(counts)
    outcome, image, vision = checked(
        tmp_path, responder=lambda req: verdict(req, RUBRICS["plate-v1"].ids[: next(rounds)])
    )
    assert len(image.requests) == len(vision.requests) == 3
    assert outcome.report.status == "FAIL" and outcome.report.finalAttempt == selected
    assert outcome.data == (tmp_path / f"attempts/plate-a{selected}.png").read_bytes()
    assert image.requests[2].reference_images[-1] == str(tmp_path / "attempts/plate-a2.png")


def test_malformed_verdict_retried_once_then_fails(tmp_path):
    vision = FakeVisionModel(responder=lambda req: "invalid json")
    with pytest.raises(CheckFailed, match="판정 실패"):
        generate_checked(
            image_model=FakeImageModel(),
            vision=vision,
            request=ImageRequest(stage="s4a", prompt="Empty", ref="unit", size="1024x1536"),
            ratio=(9, 16),
            rubric=RUBRICS["plate-v1"],
            context="",
            judge_refs=[],
            out_dir=tmp_path,
            image_id="bad",
            settings=QaSettings(),
        )
    assert len(vision.requests) == 2
    assert list((tmp_path / "attempts").glob("*.png")) == [tmp_path / "attempts/bad-a1.png"]


def test_malformed_verdict_recovers_without_regeneration(tmp_path):
    calls = []

    def responder(req):
        calls.append(req)
        return "invalid json" if len(calls) == 1 else all_pass(req)

    outcome, image, vision = checked(tmp_path, responder=responder)
    assert outcome.report.status == "PASS"
    assert len(image.requests) == 1 and len(vision.requests) == 2


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate"])
def test_verdict_ids_must_match(change):
    ids = RUBRICS["plate-v1"].ids.copy()
    if change == "missing":
        ids.pop()
    elif change == "extra":
        ids.append("invented")
    else:
        ids[-1] = ids[0]
    raw = json.dumps({"items": [{"id": i, "verdict": "PASS"} for i in ids]})
    with pytest.raises(ValueError, match="기준표"):
        parse_verdict(raw, RUBRICS["plate-v1"])


def test_disabled_has_no_vision_or_attempts(tmp_path):
    outcome, image, vision = checked(tmp_path, settings=QaSettings(enabled=False))
    assert len(image.requests) == 1 and vision.requests == []
    assert outcome.report is None and outcome.final_path is None
    assert not (tmp_path / "attempts").exists()


def test_s4a_retry_and_vision_ledger(flow):
    ctx, _, cid, _ = flow

    def responder(req):
        return verdict(req, failed=("no_people",) if "ch2-b1#qa1" in req.ref else ())

    vision = FakeVisionModel(responder=responder)
    ctx.use_vision(vision)
    out = run_s4a(ctx, cid)
    candidate = read(out / "background-candidates.json")["chapters"][1]["candidates"][0]
    assert candidate["qa"]["status"] == "PASS" and candidate["qa"]["attempts"] == 2
    report = read(out / candidate["qa"]["report"])
    assert report["finalAttempt"] == 2
    assert (out / candidate["plate"]["path"]).read_bytes() == (
        out / "attempts/ch2-b1-a2.png"
    ).read_bytes()
    assert "자동 검사 통과 (2회째)" in (out / "gate-G4a.html").read_text()
    calls = [c for c in ctx.ledger(cid).calls() if c["kind"] == "VISION"]
    assert len(calls) == 10 and all(c["stage"] == "s4a" for c in calls)
    assert "ch2" in vision.requests[3].prompt
    assert len(vision.requests[0].images) == 1


def test_s4a_exhausted_still_waits_for_human(flow):
    ctx, _, cid, _ = flow
    ctx.use_vision(
        FakeVisionModel(
            responder=lambda req: verdict(
                req, failed=("no_people",) if "ch1-b1#qa" in req.ref else ()
            )
        )
    )
    out = run_s4a(ctx, cid)
    candidate = read(out / "background-candidates.json")["chapters"][0]["candidates"][0]
    assert candidate["qa"]["status"] == "FAIL" and candidate["qa"]["attempts"] == 3
    assert ctx.state(cid).stage("s4a").status == "AWAITING_HUMAN"
    page = (out / "gate-G4a.html").read_text()
    assert "자동 검사 미통과 — 사람 확인 필요" in page and "사람 없음" in page
    assert "&lt;no_people&gt;" in page and "<no_people>" not in page
    assert 'href="qa/ch1-b1.json"' in page


def test_s4b_custom_and_copied_plate_qa(flow):
    ctx, _, cid, _ = flow
    bg = choose_bg(ctx, cid, custom=True)
    ctx.use_vision(
        FakeVisionModel(
            responder=lambda req: verdict(
                req, failed=("no_people",) if "ch3#qa1" in req.ref else ()
            )
        )
    )
    out = run_s4b(ctx, cid)
    chapters = read(out / "scene-plan.json")["chapters"]
    assert chapters[2]["qa"]["attempts"] == 2
    assert (out / "plates/ch3.png").read_bytes() == (out / "attempts/ch3-a2.png").read_bytes()
    assert read(out / chapters[2]["qa"]["report"])["stage"] == "s4b"
    for ch in chapters[:2]:
        qa = ch["qa"]
        assert (out / qa["report"]).read_bytes() == (bg / qa["report"]).read_bytes()
        for attempt in read(out / qa["report"])["rounds"]:
            assert (out / attempt["filePath"]).read_bytes() == (
                bg / attempt["filePath"]
            ).read_bytes()
    assert "자동 검사 통과 (2회째)" in (out / "gate-G4b.html").read_text()
    assert (
        len([c for c in ctx.ledger(cid).calls() if c["kind"] == "VISION" and c["stage"] == "s4b"])
        == 2
    )


@pytest.mark.parametrize("mode", ["face", "full"])
def test_s4_reference_order_badge_and_carry(flow, monkeypatch, mode):
    import character_factory_poc.stages.s4_frames.run as runner

    ctx, _, cid, image = flow
    through_pose(ctx, cid)
    if mode == "face":
        monkeypatch.setattr(
            runner, "crop_face", lambda data, scale: (solid_png(30, 30, (1, 2, 3)), (1, 2, 30))
        )
    else:
        ctx.config.stages["s4"] = {"reference_crop": "full"}
    vision = FakeVisionModel()
    ctx.use_vision(vision)
    out = run_s4(ctx, cid)
    assert len(vision.requests) == 3
    for request in vision.requests:
        assert [lab for lab, _ in request.images] == [
            "candidate image",
            f"identity reference ({mode})",
            "background plate",
        ]
        assert "Scene facts:" in request.prompt and "Outfit:" in request.prompt
        for _, path in request.images:
            assert Path(path).is_file()
    page = (out / "gate-G4.html").read_text()
    assert "자동 검사 통과 (1회째)" in page and 'href="qa/ch1-f1.json"' in page
    approve_gate(
        ctx,
        cid,
        "G4",
        {
            "decision": "REQUEST_CHANGES",
            "reviewer": "u",
            "requestedChanges": [{"field": "ch2", "note": "가방을 왼쪽으로 옮긴다"}],
        },
    )
    ctx.use_vision(
        FakeVisionModel(
            responder=lambda req: verdict(req, failed=("hands_ok",) if "#qa1" in req.ref else ())
        )
    )
    image.requests.clear()
    ctx.max_calls = 9  # 수정하는 한 챕터의 이미지 최대 3회, 판정 최대 6회만 예약한다.
    second = run_s4(ctx, cid)
    assert len(image.requests) == 2
    assert image.requests[1].prompt.startswith("Edit the last attached image")
    assert all("Revision note: 가방을 왼쪽으로 옮긴다" in req.prompt for req in image.requests)
    before, after = read(out / "frames.json"), read(second / "frames.json")
    for i in (0, 2):
        assert before[i]["qa"] == after[i]["qa"]
        report = after[i]["qa"]["report"]
        assert (out / report).read_bytes() == (second / report).read_bytes()
        for attempt in read(second / report)["rounds"]:
            path = attempt["filePath"]
            assert (out / path).read_bytes() == (second / path).read_bytes()
    assert "자동 검사 통과 (2회째)" in (second / "gate-G4.html").read_text()


@pytest.mark.parametrize("stage", ["s4a", "s4b", "s4"])
def test_disabled_stages_preserve_generation_without_qa(flow, stage):
    ctx, _, cid, _ = flow
    ctx.config.stages["image_qa"] = {"enabled": False}
    vision = FakeVisionModel(responder=lambda req: pytest.fail("판정하면 안 된다"))
    ctx.use_vision(vision)
    if stage == "s4a":
        out, filename = run_s4a(ctx, cid), "background-candidates.json"
        items = [c for ch in read(out / filename)["chapters"] for c in ch["candidates"]]
    elif stage == "s4b":
        choose_bg(ctx, cid, custom=True)
        out, filename = run_s4b(ctx, cid), "scene-plan.json"
        items = read(out / filename)["chapters"]
    else:
        through_pose(ctx, cid)
        out, filename = run_s4(ctx, cid), "frames.json"
        items = read(out / filename)
    assert all(item["qa"] is None for item in items)
    assert not (out / "attempts").exists() and not (out / "qa").exists()
    assert not vision.requests
    assert (
        "자동 검사"
        not in (
            out / {"s4a": "gate-G4a.html", "s4b": "gate-G4b.html", "s4": "gate-G4.html"}[stage]
        ).read_text()
    )


@pytest.mark.parametrize("stage", ["s4a", "s4b", "s4"])
@pytest.mark.parametrize("allow", [None, False, True])
def test_judge_configuration_checked_before_writes(tmp_path, stage, allow):
    extra = '[providers.image]\nadapter="codex_image"\nmodel="gpt-6.1-sol"\n'
    if allow is not None:
        extra += '[providers.vision]\nadapter="openai_compat"\nbase_url="http://unused.invalid/v1"\nmodel="gpt-6.1-sol"\n'
    ctx, agents = make_ctx(tmp_path)
    agents.set("s4a", backgrounds)
    agents.set("s4b-scene", scenes)
    agents.set("s4b-pose", poses)
    cid = through_s2(ctx)
    approve_plan_v2(ctx, cid)
    if stage == "s4b":
        choose_bg(ctx, cid, custom=True)
    elif stage == "s4":
        through_pose(ctx, cid)
    # 승인된 입력을 먼저 준비하고 검사 대상 단계에만 실제 공급자 설정을 적용한다.
    (tmp_path / "factory.toml").write_text(extra)
    from character_factory_poc.pipeline.context import Context

    ctx.config = Context.load(tmp_path, execute=False).config
    if allow is not None:
        ctx.use_vision(FakeVisionModel())
    else:
        ctx._vision = None
    ctx.config.stages["image_qa"] = {"allow_same_family": bool(allow)}
    run, folder = {
        "s4a": (run_s4a, "s4a-backgrounds"),
        "s4b": (run_s4b, "s4b-poses"),
        "s4": (run_s4, "s4-frames"),
    }[stage]
    before = dump(ctx.state(cid).stage(stage))
    if allow:
        out = run(ctx, cid)
        assert out.exists()
        reports = [read(path) for path in (out / "qa").glob("*.json")]
        assert any(report["sameFamilyWarning"] for report in reports if report["stage"] == stage)
    else:
        with pytest.raises(CheckFailed):
            run(ctx, cid)
        assert not (ctx.character_dir(cid) / folder).exists()
        assert dump(ctx.state(cid).stage(stage)) == before


def test_budget_reserves_qa_before_writes(flow):
    ctx, _, cid, image = flow
    ctx.max_calls = 54
    assert [p.calls for p in background_calls(ctx)] == [1, 27, 54]
    with pytest.raises(BudgetExceeded):
        run_s4a(ctx, cid)
    assert not image.requests and not (ctx.character_dir(cid) / "s4a-backgrounds").exists()


def test_s4a_cli_plan_defaults(flow, capsys):
    ctx, _, cid, image = flow
    assert main(["--root", str(ctx.config.root), "scene", "backgrounds", cid]) == 0
    text = capsys.readouterr().out
    assert "9장 (자동 검사 포함 최대 27장)" in text
    assert "비전" in text and "54회" in text and "합계 82회" in text
    assert not image.requests and not (ctx.character_dir(cid) / "s4a-backgrounds").exists()


@pytest.mark.parametrize("status", ["PASS", "FAIL"])
def test_badge_escapes_reasons_and_lists_unsure(status):
    from character_factory_poc.stages.s4a_backgrounds.page import render_qa

    qa = QaSummary(
        status=status,
        attempts=2,
        failed=["no_people"] if status == "FAIL" else [],
        unsure=["no_text"],
        reasons=["사람 없음: <script>bad</script>", "글자·로고 없음: <logo>"],
        report='qa/a"b.json',
    )
    page = render_qa(qa, RUBRICS["plate-v1"])
    assert "판단 보류" in page and "글자·로고 없음" in page
    assert "&lt;logo&gt;" in page and "<logo>" not in page
    assert "<script>" not in page and "&quot;b.json" in page
    if status == "FAIL":
        assert "자동 검사 미통과 — 사람 확인 필요" in page and "&lt;script&gt;" in page
    else:
        assert "자동 검사 통과 (2회째)" in page
    assert render_qa(None, RUBRICS["plate-v1"]) == ""


@pytest.mark.parametrize("retry", [False, True])
def test_vision_http_body_order_parse_and_retry(tmp_path, retry):
    refs = []
    for i, label in enumerate(("candidate image", "identity reference (face)", "background plate")):
        path = tmp_path / f"{i}.png"
        path.write_bytes(solid_png(2, 2, (i, 2, 3)))
        refs.append((label, str(path)))
    request = VisionRequest(
        stage="s4", ref="test", prompt="judge", images=tuple(refs), system="rules"
    )
    bodies, sleeps = [], []
    raw = json.dumps({"items": [{"id": "same_identity", "verdict": "PASS"}]})

    def handler(req):
        bodies.append(json.loads(req.content))
        if retry and len(bodies) == 1:
            return httpx.Response(500, json={"error": "retry"})
        return httpx.Response(
            200,
            json={
                "model": "judge-response",
                "choices": [{"message": {"content": raw}}],
                "usage": {"prompt_tokens": 42, "completion_tokens": 12},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = OpenAICompatVisionModel(
            base_url="https://judge.invalid/v1",
            model="judge",
            client=client,
            sleep=sleeps.append,
            max_retries=1,
        )
        response = model.judge(request)
    assert response.text == raw and response.model == "judge-response"
    assert response.input_tokens == 42 and response.output_tokens == 12
    assert len(bodies) == (2 if retry else 1) and sleeps == ([1.0] if retry else [])
    assert bodies[0]["messages"][0] == {"role": "system", "content": "rules"}
    parts = bodies[0]["messages"][1]["content"]
    assert [p["text"] for p in parts[1::2]] == [f"[{label}]" for label, _ in refs]
    urls = [p["image_url"]["url"] for p in parts[2::2]]
    assert urls == [
        "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()
        for _, path in refs
    ]


def test_s4_failed_custom_pose_and_unsure_still_reach_gate(flow):
    ctx, _, cid, _ = flow
    choose_bg(ctx, cid)
    run_s4b(ctx, cid)
    custom = "난간 옆에 서서 두 손을 허리 아래에 모으고 남색 재킷을 입는다."
    approve_gate(
        ctx,
        cid,
        "G4b",
        {
            "decision": "SELECT",
            "reviewer": "u",
            "picks": {"ch1": "ch1-p1", "ch2": "ch2-p1"},
            "custom": {"ch3": custom},
        },
    )
    vision = FakeVisionModel(
        responder=lambda req: verdict(
            req, failed=("hands_ok",) if "ch3-f1#qa" in req.ref else (), unsure=("same_identity",)
        )
    )
    ctx.use_vision(vision)
    out = run_s4(ctx, cid)
    frames = read(out / "frames.json")
    assert frames[2]["qa"]["status"] == "FAIL" and frames[2]["qa"]["attempts"] == 3
    assert frames[0]["qa"]["unsure"] == ["same_identity"]
    assert all(custom in req.prompt for req in vision.requests if "ch3-f1#qa" in req.ref)
    assert ctx.state(cid).stage("s4").status == "AWAITING_HUMAN"
    assert ctx.state(cid).gate("G4").status == "AWAITING_HUMAN"
    page = (out / "gate-G4.html").read_text()
    assert "자동 검사 미통과 — 사람 확인 필요" in page and "손:" in page
    assert "판단 보류 · 같은 얼굴:" in page


def test_s4b_failed_custom_plate_still_reaches_gate(flow):
    ctx, _, cid, _ = flow
    choose_bg(ctx, cid, custom=True)
    ctx.use_vision(FakeVisionModel(responder=lambda req: verdict(req, failed=("no_people",))))
    out = run_s4b(ctx, cid)
    custom = read(out / "scene-plan.json")["chapters"][2]
    assert custom["qa"]["status"] == "FAIL" and custom["qa"]["attempts"] == 3
    assert ctx.state(cid).stage("s4b").status == "AWAITING_HUMAN"
    page = (out / "gate-G4b.html").read_text()
    assert "자동 검사 미통과 — 사람 확인 필요" in page and "사람 없음:" in page


@pytest.mark.parametrize("enabled,expected", [(True, (27, 54)), (False, (9, 0))])
def test_plate_plan_counts_with_qa_toggle(flow, enabled, expected):
    ctx, _, _, _ = flow
    ctx.config.stages["image_qa"] = {"enabled": enabled}
    plans = background_calls(ctx)[1:]
    assert plans[0].calls == expected[0]
    assert sum(plan.calls for plan in plans[1:]) == expected[1]
    assert all(plan.stage == "s4a" for plan in plans)
    ctx.config.stages["s4a"] = {"plates": False}
    assert [plan.calls for plan in background_calls(ctx)] == [1]
