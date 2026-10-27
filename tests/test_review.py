"""관문 사전 검토 (LLD §6.8·§5.19, 명세 §7.2, FR-45, D-0049).

가짜 판정 모델·가짜 비전 모델만 쓴다. 네트워크도 실제 공급자도 부르지 않는다. 검토는 상태·산출물을
바꾸지 않고, 관문 기록(reviewRef·followedReview)과 화면(review)에만 붙는지 확인한다.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.cli import main
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.errors import FactoryError, ValidationFailed
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.pipeline.review import (
    load_review,
    plan_review_calls,
    review_gate,
    review_on_open,
    review_path,
)
from character_factory_poc.providers.fake_vision import FakeVisionModel
from character_factory_poc.stages.s3_plan.draft import new_character
from character_factory_poc.web import create_app
from tests.support.flow import make_ctx
from tests.support.synthetic import RANKING
from tests.support.web_gates import SEED, build
from tests.test_plan_variants import output as plan_variants

G3_ANSWER = {
    "items": [
        {
            "candidateId": "v2",
            "rank": 1,
            "verdict": "RECOMMEND",
            "reasons": ["같은 상황에서 조율을 먼저 고른다"],
        },
        {"candidateId": "v1", "rank": 2, "verdict": "OK", "reasons": []},
        {"candidateId": "v3", "rank": 3, "verdict": "OK", "reasons": []},
    ],
    "summary": "v2를 먼저 권한다",
}


def enable_review(ctx, gates: list[str], *, vision: bool = False) -> None:
    """factory.toml의 [review]를 이미 읽은 Context에 같은 값을 넣는다."""
    ctx.config = replace(
        ctx.config, review={"enabled": True, "vision": vision, "gates": list(gates)}
    )


def _add_text_review(ctx, response) -> None:
    ctx._judge.add("REVIEW", response)  # noqa: SLF001  가짜 판정 모델에 검토 답을 준비한다


def _vision_answer(request) -> dict:
    """요청의 <input>에서 후보 ID를 읽어 순위 답을 만든다(가짜 비전)."""
    match = re.search(r"<input>(.*?)</input>", request.prompt, re.S)
    assert match, "검토 입력이 없다"
    payload = json.loads(match.group(1))
    ids = [c["candidateId"] for c in payload["candidates"]]
    return {
        "items": [
            {
                "candidateId": candidate_id,
                "rank": index + 1,
                "verdict": "RECOMMEND" if index == 0 else "OK",
                "reasons": ["가짜 비전 검토 근거"],
            }
            for index, candidate_id in enumerate(ids)
        ],
        "summary": "가짜 비전 검토",
    }


def _state_bytes(root: Path, cid: str) -> bytes:
    return (root / "runs" / "characters" / cid / "state.json").read_bytes()


def _record(root: Path, cid: str, gate: str, rev: str) -> dict:
    path = root / "runs" / "characters" / cid / "gates" / f"{gate}-{rev}.json"
    return json.loads(path.read_text("utf-8"))


def test_review_contract_and_old_gate_record() -> None:
    review = validate(
        "gate-review-v1",
        {
            "subjectId": "cf-1",
            "gate": "G3",
            "rev": "pr1",
            "reviewer": {"provider": "fake", "model": "fake-judge", "family": "fake"},
            "mode": "llm",
            "shownArtifacts": [],
            "items": [
                {
                    "candidateId": "v1",
                    "chapterId": "ch1",
                    "rank": 1,
                    "verdict": "RECOMMEND",
                    "reasons": ["근거"],
                    "defects": [{"field": "tagline", "note": "짧다"}],
                }
            ],
            "summary": "요약",
            "createdAt": "2026-10-28T00:00:00+00:00",
        },
    )
    assert dump(review)["items"][0]["rank"] == 1
    with pytest.raises(ValidationFailed):
        validate("gate-review-v1", {**dump(review), "items": [{"candidateId": "v1"}]})

    old = validate(
        "gate-record-v1",
        {
            "subjectId": "cf-1",
            "gate": "G3",
            "rev": "pr1",
            "shownArtifacts": [],
            "decision": "APPROVE",
            "reviewer": "user",
            "decidedAt": "2026-10-28T00:00:00+00:00",
        },
    )
    assert old.reviewRef is None
    assert old.followedReview is None


def test_review_ranks_are_recorded_and_exposed_without_state_change(tmp_path) -> None:
    ctx, cid = build(tmp_path, "G3")
    enable_review(ctx, ["G3"])
    _add_text_review(ctx, G3_ANSWER)
    before = _state_bytes(tmp_path, cid)
    rev = ctx.state(cid).gate("G3").rev

    out = review_on_open(ctx, cid, "G3")
    assert out is not None and out.name == f"G3-{out.stem.split('-', 1)[1]}.json"
    assert out.parent.name == "reviews"
    assert _state_bytes(tmp_path, cid) == before
    review = load_review(ctx.character_dir(cid), "G3", rev)
    assert review is not None
    assert review.mode == "llm"
    assert review.reviewer.model == "fake-judge"
    assert [item.candidateId for item in review.items if item.rank == 1] == ["v2"]
    assert review.summary == "v2를 먼저 권한다"
    assert review.shownArtifacts == [] or all(a.ref for a in review.shownArtifacts)
    before_review = out.read_bytes()
    assert review_gate(ctx, cid, "G3") == out
    assert out.read_bytes() == before_review
    assert len(ctx._judge.requests) == 1  # noqa: SLF001  이미 있으면 다시 부르지 않는다

    with TestClient(create_app(tmp_path)) as client:
        view = client.get(f"/api/characters/{cid}/gates/G3").json()
    assert view["review"]["rev"] == rev
    assert view["review"]["items"][0]["candidateId"] in {"v1", "v2", "v3"}


def test_plan_calls_and_human_only_gates_are_rejected(tmp_path) -> None:
    ctx, cid = build(tmp_path, "G3")
    plans = plan_review_calls(ctx, cid, "G3")
    assert len(plans) == 1
    assert plans[0].calls == 1
    with pytest.raises(FactoryError, match="사전 검토"):
        plan_review_calls(ctx, cid, "G7a")
    with pytest.raises(FactoryError, match="사전 검토"):
        review_gate(ctx, cid, "G8")


def test_format_errors_twice_leave_no_review_and_state(tmp_path) -> None:
    ctx, cid = build(tmp_path, "G3")
    enable_review(ctx, ["G3"])
    _add_text_review(ctx, ["형식이 아니다", "여전히 형식이 아니다"])
    rev = ctx.state(cid).gate("G3").rev
    before = _state_bytes(tmp_path, cid)

    assert review_on_open(ctx, cid, "G3") is None
    assert not review_path(ctx.character_dir(cid), "G3", rev).exists()
    assert _state_bytes(tmp_path, cid) == before
    assert ctx.state(cid).gate("G3").status == "AWAITING_HUMAN"
    calls = ctx.ledger(cid).calls()
    assert any(c["kind"] == "REVIEW" and c["ok"] is False for c in calls)
    assert calls[-1]["ok"] is False
    assert len([c for c in calls if c["kind"] == "REVIEW"]) == 3


@pytest.mark.parametrize("decision,expected", [("v2", True), ("v1", False)])
def test_followed_review_true_and_false(tmp_path, decision, expected) -> None:
    ctx, cid = build(tmp_path, "G3")
    enable_review(ctx, ["G3"])
    _add_text_review(ctx, G3_ANSWER)
    rev = ctx.state(cid).gate("G3").rev
    assert review_gate(ctx, cid, "G3") is not None

    approve_gate(
        ctx,
        cid,
        "G3",
        {"decision": "SELECT", "selections": [decision], "reviewer": "tester"},
    )
    record = _record(tmp_path, cid, "G3", rev)
    assert record["reviewRef"] == f"reviews/G3-{rev}.json"
    assert record["followedReview"] is expected


def test_old_review_is_hidden_after_new_revision(tmp_path) -> None:
    ctx, cid = build(tmp_path, "G3")
    enable_review(ctx, ["G3"])
    _add_text_review(ctx, G3_ANSWER)
    rev = ctx.state(cid).gate("G3").rev
    assert review_gate(ctx, cid, "G3") is not None

    char_dir = ctx.character_dir(cid)
    new_rev = "pr2"
    shutil.copytree(char_dir / "s3-plan" / rev, char_dir / "s3-plan" / new_rev)
    assert not (char_dir / "reviews" / f"G3-{new_rev}.json").exists()  # 검토는 rev 폴더 밖에 있다
    state_path = char_dir / "state.json"
    state = json.loads(state_path.read_text("utf-8"))
    state["gates"]["G3"]["rev"] = new_rev
    state["gates"]["G3"]["status"] = "AWAITING_HUMAN"
    state["gates"]["G3"]["recordRef"] = None
    state["stages"]["s3"]["currentRev"] = new_rev
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with TestClient(create_app(tmp_path)) as client:
        view = client.get(f"/api/characters/{cid}/gates/G3").json()
    assert view["rev"] == new_rev
    assert view["review"] is None


def test_same_family_text_reviewer_is_rejected(tmp_path) -> None:
    ctx, cid = build(tmp_path, "G3")
    enable_review(ctx, ["G3"])
    _add_text_review(ctx, G3_ANSWER)
    same = ProviderConfig(
        adapter="openai_compat",
        base_url="http://127.0.0.1:9/v1",
        model="vendor/same-model",
    )
    ctx.config = replace(
        ctx.config, providers={**ctx.config.providers, "text": same, "judge": same}
    )
    with pytest.raises(FactoryError, match="계열"):
        review_gate(ctx, cid, "G3")


def test_same_family_vision_reviewer_is_rejected(tmp_path) -> None:
    ctx, cid = build(tmp_path, "G4a")
    enable_review(ctx, ["G4a"], vision=True)
    ctx.use_vision(FakeVisionModel(responder=_vision_answer))
    ctx.config = replace(
        ctx.config,
        providers={
            **ctx.config.providers,
            "image": ProviderConfig(adapter="codex_image", model="gpt-6.1-sol"),
            "vision": ProviderConfig(adapter="openai_compat", model="gpt-6.1-sol"),
        },
    )
    with pytest.raises(FactoryError, match="계열"):
        review_gate(ctx, cid, "G4a")


def test_vision_off_skips_image_gate_review(tmp_path) -> None:
    ctx, cid = build(tmp_path, "G1")
    enable_review(ctx, ["G1"], vision=False)
    vision = FakeVisionModel(responder=_vision_answer)
    ctx.use_vision(vision)
    rev = ctx.state(cid).gate("G1").rev

    assert review_on_open(ctx, cid, "G1") is None
    assert not review_path(ctx.character_dir(cid), "G1", rev).exists()
    assert vision.requests == []
    assert ctx.state(cid).gate("G1").status == "AWAITING_HUMAN"


def test_vision_review_runs_once_per_chapter_for_g4a(tmp_path) -> None:
    ctx, cid = build(tmp_path, "G4a")
    enable_review(ctx, ["G4a"], vision=True)
    vision = FakeVisionModel(responder=_vision_answer)
    ctx.use_vision(vision)
    rev = ctx.state(cid).gate("G4a").rev

    out = review_on_open(ctx, cid, "G4a")
    assert out is not None
    assert len(vision.requests) == 3
    review = load_review(ctx.character_dir(cid), "G4a", rev)
    assert review is not None and review.mode == "vision"
    for chapter in ("ch1", "ch2", "ch3"):
        ranks = sorted(
            item.rank for item in review.items if item.chapterId == chapter and item.rank
        )
        assert ranks == [1, 2, 3]


def test_g9_review_is_deterministic_and_needs_no_model(tmp_path) -> None:
    ctx, _agents = make_ctx(tmp_path)
    cid = "cf-g9"
    rev_dir = ctx.character_dir(cid) / "s11-release" / "pk1"
    (rev_dir / "chapters" / "ch1").mkdir(parents=True)
    (rev_dir / "chapters" / "ch1" / "frame.png").write_bytes(b"png")
    package = {
        "files": [{"path": "chapters/ch1/frame.png"}, {"path": "missing.txt"}],
        "chapters": [{"chapterId": "ch1"}],
        "videos": [],
    }
    (rev_dir / "package.json").write_text(json.dumps(package), encoding="utf-8")
    ctx.state(cid).set_gate("G9", "AWAITING_HUMAN", "pk1", None)
    ctx._judge.requests.clear()  # noqa: SLF001

    out = review_gate(ctx, cid, "G9")
    review = load_review(ctx.character_dir(cid), "G9", "pk1")
    assert out is not None and review is not None
    assert review.mode == "deterministic"
    assert "빠진 파일 1개" in review.summary
    assert ctx._judge.requests == []  # noqa: SLF001  모델 호출 없음


def test_run_until_opening_gate_writes_review(tmp_path) -> None:
    ctx, agents = make_ctx(tmp_path, extra_toml='[review]\nenabled = true\ngates = ["G3"]\n')
    cid = new_character(ctx, "run-review")
    agents.set("s3-variants", lambda req: plan_variants(cid))
    _add_text_review(ctx, G3_ANSWER)

    log = run_until(
        ctx,
        cid,
        RunOptions(
            until="G3",
            ranking=RANKING,
            auto_approve={"G1"},
            seed=dict(SEED),
        ),
    )
    assert "G3" in log.waiting
    rev = ctx.state(cid).gate("G3").rev
    assert review_path(ctx.character_dir(cid), "G3", rev).is_file()
    assert load_review(ctx.character_dir(cid), "G3", rev) is not None


def test_cli_review_is_dry_run_by_default(tmp_path, capsys) -> None:
    _ctx, cid = build(tmp_path, "G3")
    rc = main(["--root", str(tmp_path), "review", cid, "G3"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "--execute" in out
    assert "G3" in out
