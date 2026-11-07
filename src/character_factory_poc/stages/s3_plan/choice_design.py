"""Choice checks and approved-source loading; never redraw semantic failures."""

import json
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.choice_design import (
    ChoiceDesign,
    ChoiceReview,
    PlanSelectionV2,
    PlanVariantsV2,
    SeedRequirements,
)


def body_hash(body) -> str:
    return sha256_text(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def check_choice_design(
    seed, plan, design: ChoiceDesign, requirements: SeedRequirements
) -> list[str]:
    seed = dump(seed) if hasattr(seed, "model_dump") else seed
    plan = dump(plan) if hasattr(plan, "model_dump") else plan
    errors = []
    reqs = {r.requirementId: r for r in requirements.requirements}
    if len(reqs) != len(requirements.requirements):
        errors.append("duplicate requirementId")
    for r in requirements.requirements:
        if r.quote not in str(seed.get(r.field, "")):
            errors.append(f"requirement {r.requirementId} has no seed quote")
        if (
            r.kind == "fixed"
            and r.requirementId not in requirements.supersededRequirementIds
            and design.coverage.get(r.requirementId) != "implemented"
        ):
            errors.append(f"required {r.requirementId} is missing or unresolved")
    if set(design.coverage) != set(reqs):
        errors.append("requirement coverage differs from inventory")
    for field in ("personality", "background", "notes", "job", "age", "gender", "userEdits"):
        if seed.get(field) not in (None, "") and not any(r.field == field for r in reqs.values()):
            errors.append(f"seed field {field} omitted from requirements")
    if design.characterId != plan["characterId"] or design.planRev != plan["planRev"]:
        errors.append("choice identity/revision mismatch")
    if design.variantId != plan["variantId"]:
        errors.append("choice variant mismatch")
    choices = {(c["situation"], c["firstMove"]) for c in plan["choices"]}
    if {(r.situation, r.firstMove) for r in design.rules} != choices:
        errors.append("choice rules differ from plan choices")
    ids = [r.choiceRuleId for r in design.rules]
    if len(set(ids)) != len(ids):
        errors.append("duplicate choiceRuleId")
    for rule in design.rules:
        if not set(rule.requirementIds) <= set(reqs):
            errors.append("choice rule references unknown requirement")
    if plan.get("selectedTraits", []) != seed.get("selectedTraits", []):
        errors.append("creator selectedTraits differ from seed")
    for trait in seed.get("selectedTraits", []):
        matching = [
            r
            for r in reqs.values()
            if r.field == "selectedTraits" and r.quote == trait["behavior"] and r.kind == "fixed"
        ]
        if not matching:
            errors.append(f"creator trait {trait['traitId']} omitted from requirements")
        elif not any(
            r.requirementId in rule.requirementIds for r in matching for rule in design.rules
        ):
            errors.append(f"creator trait {trait['traitId']} has no linked behavioral rule")
    return errors


def require_choice_pass(
    review: ChoiceReview, designs, requirements, input_hash: str, *, plans=None
) -> None:
    expected = {(d.variantId, r.requirementId) for d in designs for r in requirements.requirements}
    actual = {(i.variantId, i.requirementId) for i in review.items}
    if (
        review.inputSha256 != input_hash
        or not review.inventoryComplete
        or review.status != "PASS"
        or review.contrastStatus != "PASS"
        or review.sharedStatus != "PASS"
        or expected != actual
        or len(actual) != len(review.items)
        or any(i.status != "PASS" for i in review.items)
    ):
        raise ValueError("choice review missing, failed, unresolved, or bound to different inputs")

    def scalar_texts(value):
        if isinstance(value, dict):
            return [s for child in value.values() for s in scalar_texts(child)]
        if isinstance(value, list):
            return [s for child in value for s in scalar_texts(child)]
        return [value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)]

    supplied = {d.variantId: scalar_texts(dump(d)) for d in designs}
    for plan in plans or []:
        raw = dump(plan) if hasattr(plan, "model_dump") else plan
        if raw["variantId"] not in supplied:
            raise ValueError("choice review plan differs from supplied designs")
        supplied[raw["variantId"]].extend(scalar_texts(raw))
    if any(
        not any(i.quote in text for text in supplied.get(i.variantId, [])) for i in review.items
    ):
        raise ValueError("choice review quote is not in its supplied candidate plan/design")
    creator_ids = {
        r.requirementId for r in requirements.requirements if r.field == "selectedTraits"
    }
    behavioral_fields = (
        "situation",
        "firstMove",
        "attention",
        "priority",
        "acceptedCost",
        "activateWhen",
        "doNotActivateWhen",
        "switchWhen",
        "alternative",
        "wrongTransformation",
    )
    plans_by_id = {
        (dump(p) if hasattr(p, "model_dump") else p)["variantId"]: (
            dump(p) if hasattr(p, "model_dump") else p
        )
        for p in plans or []
    }
    for item in review.items:
        if item.requirementId not in creator_ids:
            continue
        design = next(d for d in designs if d.variantId == item.variantId)
        linked = [r for r in design.rules if item.requirementId in r.requirementIds]
        actual_behavior = [getattr(rule, field) for rule in linked for field in behavioral_fields]
        plan = plans_by_id.get(item.variantId, {})
        for field in (
            "coreTraits",
            "contrastTrait",
            "lifeAndTastes",
            "wantsAndFears",
            "misreadings",
        ):
            actual_behavior.extend(scalar_texts(plan.get(field, [])))
        if not linked or not any(item.quote in text for text in actual_behavior):
            raise ValueError("creator trait evidence must cite behavioral design, not metadata")


def select_by_content(plans):
    def key(plan):
        raw = dump(plan) if hasattr(plan, "model_dump") else plan
        return body_hash({k: v for k, v in raw.items() if k not in {"variantId", "planRev"}})

    return min(plans, key=key)


def verified_ref(root: Path, ref) -> Path:
    path = (root / ref.path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("choice reference escapes character root or is missing")
    if sha256_file(path) != ref.sha256:
        raise ValueError("choice reference hash mismatch")
    return path


def load_approved_choice_design(ctx, cid: str) -> ChoiceDesign:
    gate = ctx.state(cid).gate("G3")
    if gate.status != "APPROVED" or not gate.rev:
        raise ValueError("G3 choice design is not approved")
    root = ctx.character_dir(cid)
    folder = root / "s3-plan" / gate.rev
    if not gate.recordRef:
        raise ValueError("G3 approval record is missing")
    record = read_json(root / gate.recordRef)
    for artifact in record["shownArtifacts"]:
        path = (root / artifact["ref"]).resolve()
        if not path.is_relative_to(root.resolve()) or sha256_file(path) != artifact["sha256"]:
            raise ValueError("G3 approved artifact hash mismatch")
    selection = PlanSelectionV2.model_validate(read_json(folder / "selection.json"))
    if record.get("selections") != [selection.selected]:
        raise ValueError("G3 approval selection mismatch")
    return verify_choice_selection(root, folder, selection)


def verify_choice_selection(root, folder, selection):
    cid = root.name
    refs = {
        name: getattr(selection, name)
        for name in ("seed", "requirements", "plan", "choice", "review")
    }
    bodies = {name: read_json(verified_ref(root, ref)) for name, ref in refs.items()}
    variants = PlanVariantsV2.model_validate(read_json(folder / "variants.json"))
    plan = bodies["plan"]
    design = ChoiceDesign.model_validate(bodies["choice"])
    requirements = SeedRequirements.model_validate(bodies["requirements"])
    if requirements.supersededRequirementIds:
        if requirements.previousRequirements is None:
            raise ValueError("replaced seed requirements lack the original source")
        prior = SeedRequirements.model_validate(
            read_json(verified_ref(root, requirements.previousRequirements))
        )
        if not set(requirements.supersededRequirementIds) <= {
            r.requirementId for r in prior.requirements
        }:
            raise ValueError("unknown replaced seed requirement")
    review = ChoiceReview.model_validate(bodies["review"])
    all_designs = [
        ChoiceDesign.model_validate(read_json(verified_ref(root, ref)))
        for ref in variants.designs.values()
    ]
    review_inputs = read_json(folder / "choice-review-inputs.json")
    if (
        selection.characterId != cid
        or selection.planRev != folder.name
        or plan["characterId"] != cid
        or plan["planRev"] != folder.name
        or plan["variantId"] != selection.selected
        or design.planSha256 != refs["plan"].sha256
        or design.seedSha256 != refs["seed"].sha256
        or requirements.seedSha256 != refs["seed"].sha256
        or design.requirementsSha256 != refs["requirements"].sha256
        or variants.designs.get(selection.selected) != refs["choice"]
        or variants.requirements != refs["requirements"]
        or variants.review != refs["review"]
        or review_inputs["designs"] != [dump(d) for d in all_designs]
        or review_inputs["seed"] != bodies["seed"]
        or review_inputs["requirements"] != bodies["requirements"]
    ):
        raise ValueError("mixed choice candidate or approval source relationship mismatch")
    problems = check_choice_design(bodies["seed"], plan, design, requirements)
    if problems:
        raise ValueError("; ".join(problems))
    require_choice_pass(
        review, all_designs, requirements, body_hash(review_inputs), plans=review_inputs["plans"]
    )
    return design
