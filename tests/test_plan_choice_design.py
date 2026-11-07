import copy

import pytest

from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.contracts.choice_design import (
    ChoiceDesign,
    ChoiceReview,
    SeedRequirements,
)
from character_factory_poc.stages.s3_plan.choice_design import (
    check_choice_design,
    require_choice_pass,
    select_by_content,
)
from tests.support.flow import sample_plan_v2


def choice_fixture(cid="cf-choice"):
    plan = sample_plan_v2(cid)
    seed = {"personality": "조용하지만 부당한 부탁은 바로 거절한다", "notes": "마감을 지킨다"}
    requirements = SeedRequirements(
        characterId=cid,
        seedRev="sd1",
        seedSha256="1" * 64,
        requirements=[
            dict(requirementId="r1", field="personality", quote=seed["personality"], kind="fixed"),
            dict(requirementId="r2", field="notes", quote=seed["notes"], kind="fixed"),
        ],
    )
    rules = [
        dict(
            choiceRuleId=f"c{i}",
            traitId="t1",
            requirementIds=["r1", "r2"],
            situation=row["situation"],
            firstMove=row["firstMove"],
            attention="요구와 남은 시간을 본다",
            priority="기한과 자기 선택권",
            acceptedCost="상대의 실망",
            activateWhen="요구가 충돌할 때",
            doNotActivateWhen="평범한 인사일 때",
            switchWhen="조건이 달라질 때",
            alternative="시간 조정",
            wrongTransformation="무조건 수락",
            classification="contrast",
            classificationReason="기한과 부탁이 충돌한다",
        )
        for i, row in enumerate(plan["choices"], 1)
    ]
    design = ChoiceDesign(
        characterId=cid,
        planRev=plan["planRev"],
        variantId=plan["variantId"],
        seedSha256="1" * 64,
        requirementsSha256="2" * 64,
        planSha256="3" * 64,
        coverage={"r1": "implemented", "r2": "implemented"},
        rules=rules,
    )
    return seed, plan, requirements, design


def review_fixture(design):
    return ChoiceReview(
        inputSha256="4" * 64,
        status="PASS",
        inventoryComplete=True,
        items=[
            dict(
                variantId=design.variantId,
                requirementId=r,
                status="PASS",
                quote=design.rules[0].firstMove,
                reason="고정 요구와 일치",
            )
            for r in design.coverage
        ],
        contrastStatus="PASS",
        sharedStatus="PASS",
        evidence=[design.rules[0].firstMove],
    )


def test_seed_required_clause_cannot_be_omitted():
    seed, plan, req, design = choice_fixture()
    missing = design.model_copy(update={"coverage": {"r1": "implemented"}})
    assert any("r2" in p for p in check_choice_design(seed, plan, missing, req))


def test_seed_quote_and_plan_choice_must_match():
    seed, plan, req, design = choice_fixture()
    assert not check_choice_design(seed, plan, design, req)
    plan["choices"][0]["firstMove"] = "무조건 수락한다"
    assert check_choice_design(seed, plan, design, req)


@pytest.mark.parametrize("status", ["FAIL", "UNRESOLVED"])
def test_same_action_paraphrases_do_not_establish_contrast(status):
    _, _, req, design = choice_fixture()
    review = review_fixture(design).model_copy(update={"contrastStatus": status})
    with pytest.raises(ValueError, match="review"):
        require_choice_pass(review, [design], req, "4" * 64)


def test_shared_action_is_allowed_with_reason():
    seed, plan, req, design = choice_fixture()
    rules = [
        r.model_copy(
            update={"classification": "shared", "classificationReason": "명시적 경청 요청"}
        )
        for r in design.rules
    ]
    shared = design.model_copy(update={"rules": rules})
    assert not check_choice_design(seed, plan, shared, req)
    require_choice_pass(review_fixture(shared), [shared], req, "4" * 64)


def test_shared_cannot_hide_seed_conflict():
    _, _, req, design = choice_fixture()
    bad = review_fixture(design).model_copy(update={"sharedStatus": "FAIL"})
    with pytest.raises(ValueError, match="review"):
        require_choice_pass(bad, [design], req, "4" * 64)


def test_g3_rejects_review_missing_failed_or_unresolved():
    _, _, req, design = choice_fixture()
    review = review_fixture(design)
    for change in ({"items": []}, {"inventoryComplete": False}, {"status": "UNRESOLVED"}):
        with pytest.raises(ValueError):
            require_choice_pass(review.model_copy(update=change), [design], req, "4" * 64)
    with pytest.raises(ValueError):
        require_choice_pass(review, [design], req, "5" * 64)


def test_selection_is_invariant_to_candidate_order_and_id():
    a = sample_plan_v2("cf-choice")
    b = copy.deepcopy(a)
    b["background"] = "다른 생활을 한다"
    first = select_by_content([a, b])
    a["variantId"], b["variantId"] = "v9", "v8"
    second = select_by_content([b, a])
    assert first["background"] == second["background"]
    assert len(sha256_text(str(first))) == 64


def test_review_can_cite_own_plan_identity_without_inventing_a_choice_rule():
    _, plan, req, design = choice_fixture()
    plan["background"] = "독립 서점에서 혼자 일한다"
    review = review_fixture(design)
    items = [i.model_copy(update={"quote": plan["background"]}) for i in review.items]
    require_choice_pass(
        review.model_copy(update={"items": items}), [design], req, "4" * 64, plans=[plan]
    )


def test_review_cannot_use_another_candidates_quote():
    _, plan, req, design = choice_fixture()
    other_plan = dict(plan, variantId="v-other", background="다른 후보만 가진 고유 원문")
    other_design = design.model_copy(update={"variantId": "v-other"})
    review = review_fixture(design)
    items = [i.model_copy(update={"quote": other_plan["background"]}) for i in review.items]
    items += [
        i.model_copy(update={"variantId": "v-other", "quote": other_plan["background"]})
        for i in review.items
    ]
    with pytest.raises(ValueError, match="quote"):
        require_choice_pass(
            review.model_copy(update={"items": items}),
            [design, other_design],
            req,
            "4" * 64,
            plans=[plan, other_plan],
        )
