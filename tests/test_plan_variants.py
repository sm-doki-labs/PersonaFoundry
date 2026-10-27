"""S3 씨앗·변형·직접 기획·G3 선택을 가짜 공급자로 검증한다."""

from __future__ import annotations

import copy
import json

import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import (
    BudgetExceeded,
    CheckFailed,
    FactoryError,
    GateNotApprovedError,
    NeedsInputError,
)
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import verify_manifest
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.stages.s3_plan.check_v2 import codex_checks
from character_factory_poc.stages.s3_plan.draft import new_character
from character_factory_poc.stages.s3_plan.importer import load_approved_plan_v2
from character_factory_poc.stages.s3_plan.own import plan_calls as own_calls
from character_factory_poc.stages.s3_plan.own import run_s3_own
from character_factory_poc.stages.s3_plan.seed import load_latest_seed, write_seed
from character_factory_poc.stages.s3_plan.variants import plan_calls, run_s3_variants
from tests.support.flow import make_ctx, sample_plan_v2, through_s2
from tests.support.synthetic import RANKING

SEED = {"personality": "조용하지만 단단함", "job": "책방 직원", "age": 24}
MOVES = [
    ["서가에서 책을 고르며 기다린다", "무엇을 보고 한 말인지 되묻는다", "지금 마음을 나눠 말한다"],
    ["도착 시간을 물어 일정을 조정한다", "칭찬의 이유를 기억해 둔다", "다음 만남을 먼저 정한다"],
    ["근처에서 할 일을 찾아 시간을 쓴다", "상대의 장점을 되돌려 말한다", "더 필요한 시간을 말한다"],
]


def output(cid, n=3):
    plans = []
    for i in range(n):
        p = sample_plan_v2(cid, variant=f"v{i + 1}", notes="")
        for choice, move in zip(p["choices"], MOVES[i], strict=True):
            choice["firstMove"] = move
        plans.append(p)
    return {"variants": plans, "axisNote": "기다림·조율·자기 시간의 우선순위가 다르다"}


@pytest.fixture
def ready(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    cid = through_s2(ctx)
    write_seed(ctx, cid, SEED)
    agents.set("s3-variants", lambda req: output(cid))
    agents.set("s3-own", lambda req: sample_plan_v2(cid))
    return ctx, agents, cid


def test_seed_revision_and_gender_prefill(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    cid = through_s2(ctx)
    assert load_latest_seed(ctx, cid) is None
    seed = write_seed(ctx, cid, SEED)
    path = ctx.character_dir(cid) / "s3-plan/seeds/sd1.json"
    before = path.read_bytes()
    assert seed.gender == "female"
    assert seed.seedRev == "sd1"
    second = write_seed(ctx, cid, SEED | {"gender": "other"})
    assert second.seedRev == "sd2"
    assert load_latest_seed(ctx, cid) == second
    assert path.read_bytes() == before
    assert json.loads(before) == dump(seed)


@pytest.mark.parametrize("runner", [run_s3_variants, lambda c, i: run_s3_own(c, i, "상세 기획")])
def test_requires_s2_and_seed(tmp_path, runner):
    ctx, agents = make_ctx(tmp_path)
    cid = new_character(ctx, "not-ready")
    with pytest.raises(GateNotApprovedError, match="s2"):
        runner(ctx, cid)
    cid = through_s2(ctx)
    calls = len(agents.calls)
    with pytest.raises(NeedsInputError, match="cfp plan seed"):
        runner(ctx, cid)
    assert len(agents.calls) == calls
    assert not (ctx.character_dir(cid) / "s3-plan/pr1").exists()


def test_variants_select_and_edit(ready):
    ctx, _, cid = ready
    folder = run_s3_variants(ctx, cid)
    variants = json.loads((folder / "variants.json").read_text())
    assert variants["mode"] == "variants"
    assert len(variants["candidates"]) == 3
    assert variants["seedSha256"] == sha256_file(folder.parent / "seeds/sd1.json")
    assert ctx.state(cid).stage("s3").status == "AWAITING_HUMAN"
    assert ctx.state(cid).gate("G3").status == "AWAITING_HUMAN"
    assert not (folder / "plan.json").exists()
    assert verify_manifest(folder) == []
    page = (folder / "gate-G3.html").read_text()
    assert 'type="radio"' in page and 'id="edits"' in page
    assert all(field in page for field in variants["candidates"][0])
    before = (folder / "variants.json").read_bytes()
    approve_gate(
        ctx,
        cid,
        "G3",
        {
            "decision": "SELECT",
            "selections": ["v2"],
            "edits": {"tagline": "고른 책은 끝까지 읽는다"},
            "reviewer": "tester",
            "minutes": 2.5,
            "reasons": "조율을 먼저 하는 선택이 맞는다",
        },
    )
    plan, path = load_approved_plan_v2(ctx, cid)
    assert plan.variantId == "v2" and plan.tagline == "고른 책은 끝까지 읽는다"
    assert path == folder / "plan.json"
    assert (folder / "variants.json").read_bytes() == before
    assert json.loads((folder / "selection.json").read_text()) == {
        "schemaVersion": "plan-selection-v1",
        "planRev": "pr1",
        "selected": "v2",
        "editedFields": ["tagline"],
    }
    assert ctx.state(cid).gate("G3").status == "APPROVED"
    assert ctx.ledger(cid).human()[-1]["minutes"] == 2.5
    assert verify_manifest(folder) == []


def test_retry_then_pass(ready):
    ctx, agents, cid = ready
    calls = []

    def respond(req):
        calls.append(req)
        raw = output(cid)
        if len(calls) == 1:
            raw["variants"][1]["choices"][0]["firstMove"] = MOVES[0][0]
        return raw

    agents.set("s3-variants", respond)
    run_s3_variants(ctx, cid)
    assert len(calls) == 2
    assert "firstMove" in calls[1].messages[-1].content


@pytest.mark.parametrize("bad", ["move", "situation", "count", "job", "age", "gender", "bare"])
def test_failed_checks_set_state(ready, bad):
    ctx, agents, cid = ready
    raw = output(cid)
    if bad == "move":
        raw["variants"][1]["choices"][0]["firstMove"] = MOVES[0][0]
    elif bad == "situation":
        raw["variants"][1]["choices"][0]["situation"] = "다른 상황"
    elif bad == "count":
        raw["variants"].pop()
    elif bad == "bare":
        raw["variants"][0]["coreTraits"] = ["차분함, 다정함"]
    else:
        raw["variants"][0][bad] = {"job": "사진가", "age": 25, "gender": "male"}[bad]
    agents.set("s3-variants", lambda req: copy.deepcopy(raw))
    with pytest.raises(CheckFailed):
        run_s3_variants(ctx, cid)
    assert agents.calls.count("s3-variants") == 4
    assert ctx.state(cid).stage("s3").status == "CHECK_FAILED"
    assert ctx.state(cid).gate("G3").status != "AWAITING_HUMAN"
    assert not (ctx.character_dir(cid) / "s3-plan/pr1/variants.json").exists()


def test_own_and_new_revision(ready):
    ctx, agents, cid = ready
    text = "윤하린은 24세 여성 책방 직원이다. 말보다 먼저 상대를 기다린다."
    raw = sample_plan_v2(cid)
    raw["evidence"] = {
        "name": [{"kind": "USER", "ref": "user-text.md", "quote": "윤하린"}],
        "coreTraits": [{"kind": "AGENT", "ref": "보완", "quote": ""}],
    }
    agents.set("s3-own", lambda req: copy.deepcopy(raw))
    folder = run_s3_own(ctx, cid, text)
    assert (folder / "user-text.md").read_text() == text
    data = json.loads((folder / "variants.json").read_text())
    assert data["mode"] == "own" and data["candidates"][0]["variantId"] == "u1"
    assert data["candidates"][0]["evidence"]["name"][0]["kind"] == "USER"
    approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["u1"], "reviewer": "u"})
    assert load_approved_plan_v2(ctx, cid)[0].variantId == "u1"
    before = (folder / "plan.json").read_bytes()
    next_folder = run_s3_variants(ctx, cid)
    assert next_folder.name == "pr2"
    assert (folder / "plan.json").read_bytes() == before


def test_approve_picks_first(ready):
    ctx, _, cid = ready
    run_s3_variants(ctx, cid)
    approve_gate(ctx, cid, "G3", {"decision": "APPROVE", "reviewer": "u"})
    assert load_approved_plan_v2(ctx, cid)[0].variantId == "v1"


def test_ids_and_arc_metadata_are_owned_by_code(ready):
    ctx, agents, cid = ready
    raw = output(cid)
    for plan in raw["variants"]:
        plan.update(
            characterId="ignored",
            planRev="pr99",
            seedRev="sd99",
            variantId="u9",
            appearanceRev="ar99",
        )
        for arc in plan["chapterArc"]:
            arc["title"] = "모델이 쓴 잘못된 제목"
    agents.set("s3-variants", lambda req: raw)
    folder = run_s3_variants(ctx, cid)
    data = json.loads((folder / "variants.json").read_text())
    for i, plan in enumerate(data["candidates"], 1):
        assert (
            plan["characterId"],
            plan["planRev"],
            plan["seedRev"],
            plan["variantId"],
            plan["appearanceRev"],
        ) == (cid, "pr1", "sd1", f"v{i}", "ar1")
        assert [arc["title"] for arc in plan["chapterArc"]] == ["친해지기", "썸타기", "고백하기"]


def test_choice_order_does_not_change_same_situation_check(ready):
    ctx, agents, cid = ready
    raw = output(cid)
    raw["variants"][1]["choices"].reverse()
    agents.set("s3-variants", lambda req: raw)
    run_s3_variants(ctx, cid)


@pytest.mark.parametrize("selections", [[], ["v4"], ["v1", "v2"], "v1"])
def test_select_requires_one_candidate(ready, selections):
    ctx, _, cid = ready
    folder = run_s3_variants(ctx, cid)
    with pytest.raises(FactoryError):
        approve_gate(
            ctx,
            cid,
            "G3",
            {
                "decision": "SELECT",
                "selections": selections,
                "reviewer": "u",
            },
        )
    assert not (folder / "selection.json").exists()


def test_configured_count_and_retry_limit(tmp_path):
    ctx, agents = make_ctx(tmp_path, "[stages.s3]\nvariants = 2\nmax_check_retries = 0\n")
    cid = through_s2(ctx)
    write_seed(ctx, cid, SEED)
    agents.set("s3-variants", lambda req: output(cid, 2))
    folder = run_s3_variants(ctx, cid)
    assert len(json.loads((folder / "variants.json").read_text())["candidates"]) == 2
    approve_gate(ctx, cid, "G3", {"decision": "REQUEST_CHANGES", "reviewer": "u"})
    agents.set("s3-variants", lambda req: output(cid))
    with pytest.raises(CheckFailed):
        run_s3_variants(ctx, cid)
    assert agents.calls.count("s3-variants") == 2


def test_exhausted_format_retries_fail_stage(ready):
    ctx, agents, cid = ready
    agents.set("s3-variants", lambda req: {"variants": []})
    with pytest.raises(CheckFailed):
        run_s3_variants(ctx, cid)
    assert agents.calls.count("s3-variants") == 3
    assert ctx.state(cid).stage("s3").status == "CHECK_FAILED"


def test_own_user_evidence_must_quote_source(ready):
    ctx, agents, cid = ready
    raw = sample_plan_v2(cid)
    raw["evidence"] = {"name": [{"kind": "USER", "quote": "원문에 없는 이름"}]}
    agents.set("s3-own", lambda req: raw)
    with pytest.raises(CheckFailed, match="USER quote"):
        run_s3_own(ctx, cid, "상세 기획 원문")
    assert agents.calls.count("s3-own") == 4


def test_edit_name_leak_is_rejected(ready):
    ctx, _, cid = ready
    from character_factory_poc.stages.s1_reference.ranking import all_names, load_ranking

    folder = run_s3_variants(ctx, cid)
    with pytest.raises(CheckFailed, match="이름"):
        approve_gate(
            ctx,
            cid,
            "G3",
            {
                "decision": "SELECT",
                "selections": ["v1"],
                "reviewer": "u",
                "edits": {"name": all_names(load_ranking(RANKING))[0]},
            },
        )
    assert not (folder / "plan.json").exists()


def test_page_escapes_candidate_fields(ready):
    ctx, agents, cid = ready
    raw = output(cid)
    raw["variants"][0]["tagline"] = '<script>alert("x")</script>'
    agents.set("s3-variants", lambda req: raw)
    folder = run_s3_variants(ctx, cid)
    page = (folder / "gate-G3.html").read_text()
    assert '<script>alert("x")</script>' not in page
    assert "&lt;script&gt;" in page


def test_seed_numbering_after_sd9(ready):
    ctx, _, cid = ready
    for _ in range(10):
        write_seed(ctx, cid, SEED)
    assert load_latest_seed(ctx, cid).seedRev == "sd11"


def test_codex_own_check_matches_api(ready):
    ctx, agents, cid = ready
    raw = sample_plan_v2(cid)
    raw["evidence"] = {"name": [{"kind": "USER", "quote": "윤하린"}]}
    agents.set("s3-own", lambda req: raw)
    folder = run_s3_own(ctx, cid, "이름은 윤하린이다")
    contract, checks = codex_checks("s3-own", folder / "workspace")
    assert contract == "character-plan-v2"
    assert not [p for check in checks for p in check(validate(contract, raw))]
    raw["age"] = 25
    assert [p for check in checks for p in check(validate(contract, raw))]


@pytest.mark.parametrize("stage", ["s3-variants", "s3-own"])
def test_fake_codex_backend_retries_and_approves(ready, stage):
    from character_factory_poc.providers.fake_codex import FakeCodexAgent

    ctx, _, cid = ready

    def writer(workspace, prompt, attempt):
        if stage == "s3-variants":
            raw = output(cid)
            if attempt == 1:
                raw["variants"][1]["choices"][0]["firstMove"] = MOVES[0][0]
            return raw
        raw = sample_plan_v2(cid)
        raw["evidence"] = {"name": [{"kind": "USER", "quote": "윤하린"}]}
        if attempt == 1:
            raw["age"] = 25
        return raw

    backend = FakeCodexAgent(writer=writer)
    ctx.use_codex(backend)
    folder = (
        run_s3_variants(ctx, cid)
        if stage == "s3-variants"
        else run_s3_own(ctx, cid, "이름은 윤하린이다")
    )
    assert len(backend.calls) == 2
    assert "./check.sh" in backend.calls[1][1]
    approve_gate(ctx, cid, "G3", {"decision": "APPROVE", "reviewer": "u"})
    assert load_approved_plan_v2(ctx, cid)[0].variantId == (
        "v1" if stage == "s3-variants" else "u1"
    )
    assert verify_manifest(folder) == []


def test_pending_gate_is_kept_until_human_decides(ready):
    ctx, _, cid = ready
    folder = run_s3_variants(ctx, cid)
    state_before = (ctx.character_dir(cid) / "state.json").read_bytes()
    with pytest.raises(FactoryError, match="REQUEST_CHANGES"):
        run_s3_own(ctx, cid, "새 상세 기획")
    assert (ctx.character_dir(cid) / "state.json").read_bytes() == state_before
    assert folder.exists() and not (folder.parent / "pr2").exists()


@pytest.mark.parametrize("changes", [{"unknown": "x"}, {"planRev": "pr9"}, {"age": 2}])
def test_invalid_edits_do_not_approve(ready, changes):
    ctx, _, cid = ready
    folder = run_s3_variants(ctx, cid)
    with pytest.raises(FactoryError):
        approve_gate(
            ctx,
            cid,
            "G3",
            {
                "decision": "SELECT",
                "selections": ["v1"],
                "edits": changes,
                "reviewer": "u",
            },
        )
    assert ctx.state(cid).gate("G3").status == "AWAITING_HUMAN"
    assert not (folder / "plan.json").exists()


@pytest.mark.parametrize("decision", ["REQUEST_CHANGES", "REJECT"])
def test_decline_writes_no_plan(ready, decision):
    ctx, _, cid = ready
    folder = run_s3_variants(ctx, cid)
    approve_gate(ctx, cid, "G3", {"decision": decision, "reviewer": "u"})
    assert not (folder / "plan.json").exists()
    assert not (folder / "selection.json").exists()
    assert ctx.state(cid).gate("G3").status == "REJECTED"


@pytest.mark.parametrize(
    "runner,stage",
    [(run_s3_variants, "s3-variants"), (lambda c, i: run_s3_own(c, i, "상세 기획"), "s3-own")],
)
def test_name_leak_rejected(ready, runner, stage):
    ctx, agents, cid = ready
    from character_factory_poc.stages.s1_reference.ranking import all_names, load_ranking

    name = all_names(load_ranking(RANKING))[0]
    p = sample_plan_v2(cid, name=" ".join(name))
    raw = output(cid)
    raw["variants"][0] = p
    agents.set(stage, lambda req: copy.deepcopy(raw if stage == "s3-variants" else p))
    with pytest.raises(CheckFailed, match="이름"):
        runner(ctx, cid)
    assert ctx.state(cid).stage("s3").status == "CHECK_FAILED"


def test_codex_checks_match_api(ready):
    ctx, _, cid = ready
    folder = run_s3_variants(ctx, cid)
    contract, checks = codex_checks("s3-variants", folder / "workspace")
    raw = output(cid)
    raw["variants"][1]["choices"][0]["firstMove"] = MOVES[0][0]
    assert contract == "plan-variants-output-v1"
    assert [p for check in checks for p in check(validate(contract, raw))]


@pytest.mark.parametrize(
    "runner,calls",
    [(run_s3_variants, plan_calls), (lambda c, i: run_s3_own(c, i, "기획"), own_calls)],
)
def test_budget_checked_before_writes(ready, runner, calls):
    ctx, _, cid = ready
    assert sum(p.calls for p in calls(ctx)) >= 4
    ctx.max_calls = 0
    state_path = ctx.character_dir(cid) / "state.json"
    before = state_path.read_bytes()
    with pytest.raises(BudgetExceeded):
        runner(ctx, cid)
    assert state_path.read_bytes() == before
    assert not (ctx.character_dir(cid) / "s3-plan/pr1").exists()
