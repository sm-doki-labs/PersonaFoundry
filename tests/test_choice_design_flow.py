import json
import re

import pytest

from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.stages.s3_plan.choice_design import load_approved_choice_design
from character_factory_poc.stages.s3_plan.seed import write_seed
from character_factory_poc.stages.s3_plan.variants import run_s3_variants
from tests.support.flow import make_ctx, sample_plan_v2, through_s2


def payload(req):
    return json.loads(
        re.search(r'<input name="payload">\n(.*?)\n</input>', req.messages[-1].content, re.S)[1]
    )


def setup_choices(tmp_path, review_status="PASS", extra=""):
    ctx, agents = make_ctx(
        tmp_path, '[stages.s7]\nformation_profile="ko-text-choice-voice-long-v2"\n' + extra
    )
    cid = through_s2(ctx)
    write_seed(
        ctx,
        cid,
        dict(personality="조용하지만 부탁을 무조건 수락하지 않는다", job="책방 직원", age=24),
    )

    def inventory(req):
        seed = payload(req)["seed"]
        return {
            "requirements": [
                dict(requirementId=f"r{i}", field=k, quote=str(v), kind="fixed")
                for i, (k, v) in enumerate(seed.items())
                if k in {"personality", "job", "age", "gender", "notes", "background", "userEdits"}
                and v not in (None, "")
            ]
        }

    def plans(req):
        p = payload(req)
        rows = []
        designs = []
        for i in range(p["variantCount"]):
            plan = sample_plan_v2(cid, variant=f"v{i + 1}")
            plan["choices"][0]["firstMove"] += f". {i + 1}분의 여유를 둔다"
            if p.get("fixedPlan"):
                plan = p["fixedPlan"]
            rows.append(plan)
            rs = [r["requirementId"] for r in p["requirements"]["requirements"]]
            designs.append(
                dict(
                    variantId=plan["variantId"],
                    coverage={r: "implemented" for r in rs},
                    rules=[
                        dict(
                            choiceRuleId=f"c{j}",
                            traitId="t1",
                            requirementIds=rs,
                            situation=c["situation"],
                            firstMove=c["firstMove"],
                            attention="조건",
                            priority="자기 시간",
                            acceptedCost="실망",
                            activateWhen="부탁을 받으면",
                            doNotActivateWhen="인사",
                            switchWhen="여유가 생기면",
                            alternative="다른 시간",
                            wrongTransformation="무조건 수락",
                            classification="contrast",
                            classificationReason="우선순위 충돌",
                        )
                        for j, c in enumerate(plan["choices"], 1)
                    ],
                )
            )
        return dict(variants=rows, designs=designs, axisNote="시간 우선순위")

    def review(req):
        p = payload(req)
        return dict(
            status=review_status,
            inventoryComplete=True,
            contrastStatus=review_status,
            sharedStatus="PASS",
            items=[
                dict(
                    variantId=d["variantId"],
                    requirementId=r["requirementId"],
                    status=review_status,
                    quote=d["rules"][0]["firstMove"],
                    reason="원문 요구 확인",
                )
                for d in p["designs"]
                for r in p["requirements"]["requirements"]
            ],
            evidence=[p["designs"][0]["rules"][0]["firstMove"]],
        )

    agents.set("cv-requirements", inventory)
    agents.set("cv-choices", plans)
    agents.set("cv-choice-review", review)
    return ctx, agents, cid


def test_v2_approve_requires_explicit_selection_and_pins_sources(tmp_path):
    ctx, _, cid = setup_choices(tmp_path)
    folder = run_s3_variants(ctx, cid)
    assert json.loads((folder / "variants.json").read_text())["schemaVersion"] == "plan-variants-v2"
    with pytest.raises(ValueError, match="SELECT"):
        approve_gate(ctx, cid, "G3", dict(decision="APPROVE", reviewer="tester"))
    approve_gate(ctx, cid, "G3", dict(decision="SELECT", selections=["v2"], reviewer="tester"))
    assert load_approved_choice_design(ctx, cid).variantId == "v2"
    selected = json.loads((folder / "selection.json").read_text())
    selected["choice"] = json.loads((folder / "variants.json").read_text())["designs"]["v1"]
    (folder / "selection.json").write_text(json.dumps(selected))
    with pytest.raises(ValueError, match="mixed|mismatch"):
        load_approved_choice_design(ctx, cid)


def test_semantic_failure_has_no_api_redraw(tmp_path):
    ctx, agents, cid = setup_choices(tmp_path, "FAIL")
    with pytest.raises(ValueError, match="review"):
        run_s3_variants(ctx, cid)
    assert agents.calls.count("cv-choices") == 1
    assert agents.calls.count("cv-choice-review") == 1
    assert ctx.state(cid).stage("s3").status == "CHECK_FAILED"


def test_g3_edit_reopens_new_revision_before_s7(tmp_path):
    ctx, _, cid = setup_choices(tmp_path)
    folder = run_s3_variants(ctx, cid)
    before = (folder / "variants.json").read_bytes()
    approve_gate(
        ctx,
        cid,
        "G3",
        dict(
            decision="SELECT",
            selections=["v2"],
            edits={"tagline": "수정한 소개"},
            reviewer="tester",
        ),
    )
    assert (folder / "variants.json").read_bytes() == before
    assert ctx.state(cid).gate("G3").status == "AWAITING_HUMAN"
    assert ctx.state(cid).gate("G3").rev == "pr2"
    with pytest.raises(ValueError, match="approved"):
        load_approved_choice_design(ctx, cid)
    approve_gate(ctx, cid, "G3", dict(decision="SELECT", selections=["v2"], reviewer="tester"))
    assert load_approved_choice_design(ctx, cid).planRev == "pr2"


def test_approval_record_prevents_rebinding_selection(tmp_path):
    from character_factory_poc.common.canonical import sha256_file

    ctx, _, cid = setup_choices(tmp_path)
    folder = run_s3_variants(ctx, cid)
    approve_gate(ctx, cid, "G3", dict(decision="SELECT", selections=["v1"], reviewer="tester"))
    selection = json.loads((folder / "selection.json").read_text())
    variants = json.loads((folder / "variants.json").read_text())
    (folder / "plan.json").write_bytes((folder / "candidate-v2.json").read_bytes())
    selection.update(selected="v2", choice=variants["designs"]["v2"])
    selection["plan"]["sha256"] = sha256_file(folder / "plan.json")
    (folder / "selection.json").write_text(json.dumps(selection))
    with pytest.raises(ValueError, match="approved|approval"):
        load_approved_choice_design(ctx, cid)


def test_user_edit_preserves_explicit_requirement_replacement(tmp_path):
    ctx, _, cid = setup_choices(tmp_path)
    folder = run_s3_variants(ctx, cid)
    req = json.loads((folder / "requirements.json").read_text())
    original = next(r["requirementId"] for r in req["requirements"] if r["field"] == "personality")
    approve_gate(
        ctx,
        cid,
        "G3",
        dict(
            decision="SELECT",
            selections=["v2"],
            edits={"coreTraits": ["부탁을 받으면 먼저 가능 조건을 확인하고 적극적으로 수락한다"]},
            supersedesRequirements=[original],
            reviewer="tester",
        ),
    )
    new = folder.parent / "pr2"
    changed = json.loads((new / "requirements.json").read_text())
    assert original in changed["supersededRequirementIds"]
    assert any(r["field"] == "userEdits" for r in changed["requirements"])


def test_semantic_failure_has_no_codex_redraw(tmp_path):
    from types import SimpleNamespace

    from character_factory_poc.providers.base import Message
    from character_factory_poc.providers.fake_codex import FakeCodexAgent

    ctx, agents, cid = setup_choices(tmp_path, "FAIL")

    def writer(workspace, prompt, attempt):
        data = json.loads((workspace / "inputs/payload.json").read_text())
        stage = "cv-requirements" if workspace.parent.name == "requirements" else "cv-choices"
        req = SimpleNamespace(
            messages=[
                Message(
                    "user",
                    '<input name="payload">\n'
                    + json.dumps(data, ensure_ascii=False)
                    + "\n</input>",
                )
            ]
        )
        return agents.by_stage[stage](req)

    backend = FakeCodexAgent(writer=writer)
    ctx.use_codex(backend)
    with pytest.raises(ValueError, match="review"):
        run_s3_variants(ctx, cid)
    assert len(backend.calls) == 2
    assert agents.calls.count("cv-choice-review") == 1


def test_candidates_must_use_the_same_comparison_situations(tmp_path):
    ctx, agents, cid = setup_choices(tmp_path)
    original = agents.by_stage["cv-choices"]

    def unrelated(req):
        result = original(req)
        result["variants"][1]["choices"][0]["situation"] = "다른 조건의 상황"
        result["designs"][1]["rules"][0]["situation"] = "다른 조건의 상황"
        return result

    agents.set("cv-choices", unrelated)
    with pytest.raises(ValueError, match="situations"):
        run_s3_variants(ctx, cid)


def test_explicit_comparison_situations_cannot_be_silently_replaced(tmp_path):
    ctx, _, cid = setup_choices(tmp_path)
    ctx.config.stages.setdefault("s3", {})["choice_situations"] = ["공통으로 검사할 상황"]
    with pytest.raises(ValueError, match="comparison situation"):
        run_s3_variants(ctx, cid)
