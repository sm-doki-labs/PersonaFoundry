"""S3 choice-first recipe and G3's pinned, explicit selection lifecycle."""

import json

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.choice_design import (
    ChoiceArtifactRef,
    ChoiceDesign,
    ChoiceReview,
    PlanSelectionV2,
    PlanVariantsOutputV2,
    PlanVariantsV2,
    SeedRequirements,
    SeedRequirementsDraft,
)
from character_factory_poc.contracts.planning import EDITABLE_FIELDS, CharacterPlanV2
from character_factory_poc.pipeline.formation_step import run_typed_step
from character_factory_poc.pipeline.gates import write_gate_record
from character_factory_poc.stages.s3_plan.choice_design import (
    body_hash,
    check_choice_design,
    load_approved_choice_design,
    require_choice_pass,
    verified_ref,
    verify_choice_selection,
)


def source_ref(root, path, kind):
    return ChoiceArtifactRef(
        kind=kind, path=path.relative_to(root).as_posix(), sha256=sha256_file(path)
    )


def run_choice_variants(ctx, cid):
    from character_factory_poc.stages.s3_plan.page import render_g3_page
    from character_factory_poc.stages.s3_plan.variants import _config, _fix_plan, _preflight

    if not ctx.execute:
        raise ValueError("choice generation requires execute=True")
    seed, appearance, guard = _preflight(ctx, cid)
    root = ctx.character_dir(cid)
    stage = ctx.state(cid).stage("s3")
    rev = (
        stage.currentRev
        if stage.status == "RUNNING" and stage.currentRev
        else next_rev(root / "s3-plan", "pr")
    )
    folder = root / "s3-plan" / rev
    if (folder / "failure.json").exists():
        raise ValueError("previous semantic failure; create a new revision")
    ctx.state(cid).transition("s3", "RUNNING", rev=rev)
    budget = ctx.formation_budget()
    try:
        seed_path = root / "s3-plan/seeds" / f"{seed.seedRev}.json"
        raw_seed = dump(seed)
        edits = (
            read_json(folder / "edit-request.json")
            if (folder / "edit-request.json").exists()
            else None
        )
        fixed = read_json(folder / "fixed-plan.json") if edits else None
        prior_requirements = None
        if edits:
            prior_folder = root / "s3-plan" / edits["priorPlanRev"]
            prior_requirements = SeedRequirements.model_validate(
                read_json(prior_folder / "requirements.json")
            )
            prior_seed_ref = ChoiceArtifactRef.model_validate(
                read_json(prior_folder / "seed-ref.json")
            )
            raw_seed = read_json(verified_ref(root, prior_seed_ref))
            raw_seed["schemaVersion"] = "choice-effective-seed-v1"
            raw_seed["userEdits"] = (
                raw_seed.get("userEdits", "")
                + "\n"
                + json.dumps(edits["edits"], ensure_ascii=False, sort_keys=True)
            )
            seed_path = folder / "effective-seed.json"
            write_once_json(seed_path, raw_seed)
        inventory = run_typed_step(
            ctx=ctx,
            cid=cid,
            folder=folder / "requirements",
            role="seed_requirements",
            contract=SeedRequirementsDraft,
            stage="cv-requirements",
            inputs={
                "seed": raw_seed,
                "previousRequirements": dump(prior_requirements) if prior_requirements else None,
            },
            budget=budget,
        )
        inventory_rows = inventory.requirements
        # Creator selections are fixed requirements even if the inventory writer omits them.
        if seed.selectedTraits:
            from character_factory_poc.contracts.choice_design import SeedRequirement

            inventory_rows = [r for r in inventory_rows if r.field != "selectedTraits"]
            inventory_rows += [
                SeedRequirement(
                    requirementId=f"creator-{t.traitId}",
                    field="selectedTraits",
                    quote=t.behavior,
                    kind="fixed",
                )
                for t in seed.selectedTraits
            ]
        if prior_requirements:
            new_rows = [r for r in inventory_rows if r.field == "userEdits"]
            if not new_rows:
                raise ValueError("edited user requirements were omitted")
            existing_ids = {r.requirementId for r in prior_requirements.requirements}
            new_rows = [
                r.model_copy(update={"requirementId": f"{rev}-edit-{i}"})
                for i, r in enumerate(new_rows, 1)
            ]
            if existing_ids & {r.requirementId for r in new_rows}:
                raise ValueError("edit requirement identifier collision")
            inventory_rows = [*prior_requirements.requirements, *new_rows]
        requirements = SeedRequirements(
            characterId=cid,
            seedRev=seed.seedRev,
            seedSha256=sha256_file(seed_path),
            requirements=inventory_rows,
            supersededRequirementIds=edits.get("supersedesRequirements", []) if edits else [],
            previousRequirements=source_ref(
                root, root / "s3-plan" / edits["priorPlanRev"] / "requirements.json", "requirements"
            )
            if edits
            else None,
        )
        req_path = folder / "requirements.json"
        write_once_json(req_path, dump(requirements))
        count = 1 if fixed else _config(ctx)["variants"]
        situations = ctx.config.stage("s3").get("choice_situations", [])
        if (
            not isinstance(situations, list)
            or any(not isinstance(s, str) or not s.strip() for s in situations)
            or len(set(situations)) != len(situations)
        ):
            raise ValueError("invalid comparison situations")
        draft = run_typed_step(
            ctx=ctx,
            cid=cid,
            folder=folder / "choices",
            role="choice_variants",
            contract=PlanVariantsOutputV2,
            stage="cv-choices",
            budget=budget,
            inputs=dict(
                seed=raw_seed,
                requirements=dump(requirements),
                variantCount=count,
                fixedPlan=fixed,
                appearance=appearance,
                ids=dict(characterId=cid, planRev=rev, seedRev=seed.seedRev),
                userEditRequest=edits,
                comparisonSituations=situations,
            ),
        )
        if len(draft.variants) != count or len(draft.designs) != count:
            raise ValueError("choice candidate count mismatch")
        if situations and any(
            {c.situation for c in p.choices} != set(situations) for p in draft.variants
        ):
            raise ValueError("comparison situations differ from declared catalogue")
        designs = []
        candidates = []
        design_refs = {}
        for i, (plan, spec) in enumerate(zip(draft.variants, draft.designs, strict=True), 1):
            variant = fixed["variantId"] if fixed else f"v{i}"
            plan = _fix_plan(plan, seed, appearance, rev, variant)
            if fixed and dump(plan) != fixed:
                raise ValueError("edited fixed plan was changed by generator")
            from character_factory_poc.stages.s3_plan.check_v2 import check_plan_v2

            problems = check_plan_v2(None if fixed else seed, guard)(plan)
            if problems:
                raise ValueError("; ".join(problems))
            candidate_path = folder / f"candidate-{variant}.json"
            write_once_json(candidate_path, dump(plan))
            # Rule identifiers belong to this approved candidate's stable source, not model labels.
            rules = [
                r.model_copy(update={"choiceRuleId": f"{rev}-{variant}-c{j}"})
                for j, r in enumerate(spec.rules, 1)
            ]
            design = ChoiceDesign(
                **(dump(spec) | dict(variantId=variant, rules=[dump(r) for r in rules])),
                characterId=cid,
                planRev=rev,
                seedSha256=sha256_file(seed_path),
                requirementsSha256=sha256_file(req_path),
                planSha256=sha256_file(candidate_path),
            )
            problems = check_choice_design(raw_seed, plan, design, requirements)
            if problems:
                raise ValueError("; ".join(problems))
            path = folder / f"choice-{variant}.json"
            write_once_json(path, dump(design))
            design_refs[variant] = source_ref(root, path, "choice")
            candidates.append(plan)
            designs.append(design)
        comparison_sets = [{c.situation for c in p.choices} for p in candidates]
        if comparison_sets and any(s != comparison_sets[0] for s in comparison_sets):
            raise ValueError("candidate comparison situations differ")
        review_inputs = dict(
            seed=raw_seed,
            requirements=dump(requirements),
            plans=[dump(p) for p in candidates],
            designs=[dump(d) for d in designs],
            userEditRequest=edits,
        )
        write_once_json(folder / "choice-review-inputs.json", review_inputs)
        review = run_typed_step(
            ctx=ctx,
            cid=cid,
            folder=folder / "review",
            role="choice_review",
            contract=ChoiceReview,
            stage="cv-choice-review",
            inputs=review_inputs,
            judge=True,
            budget=budget,
        )
        if review.inputSha256 not in (None, body_hash(review_inputs)):
            raise ValueError("choice review input hash mismatch")
        review = review.model_copy(update={"inputSha256": body_hash(review_inputs)})
        write_once_json(folder / "choice-review.json", dump(review))
        require_choice_pass(
            review, designs, requirements, body_hash(review_inputs), plans=candidates
        )
        variants = PlanVariantsV2(
            characterId=cid,
            planRev=rev,
            seedRev=seed.seedRev,
            seedSha256=sha256_file(seed_path),
            candidates=candidates,
            axisNote=draft.axisNote,
            requirements=source_ref(root, req_path, "requirements"),
            designs=design_refs,
            review=source_ref(root, folder / "choice-review.json", "review"),
        )
        write_once_json(folder / "variants.json", dump(variants))
        write_once_text(
            folder / "gate-G3.html",
            render_g3_page(variants=variants, choice_evidence={d.variantId: d for d in designs}),
        )
        write_once_json(folder / "seed-ref.json", dump(source_ref(root, seed_path, "seed")))
        write_manifest(folder)
        ctx.state(cid).transition("s3", "AWAITING_HUMAN", rev=rev)
        ctx.state(cid).set_gate("G3", "AWAITING_HUMAN", rev, None)
        return folder
    except Exception as exc:
        write_once_json(folder / "failure.json", {"error": str(exc)})
        ctx.state(cid).transition("s3", "CHECK_FAILED", rev=rev, error=str(exc))
        raise


def approve_choice_variants(ctx, cid, answer):
    root = ctx.character_dir(cid)
    gate = ctx.state(cid).gate("G3")
    folder = root / "s3-plan" / gate.rev
    variants = PlanVariantsV2.model_validate(read_json(folder / "variants.json"))
    decision = answer.get("decision")
    if decision in {"REJECT", "REQUEST_CHANGES"}:
        write_gate_record(
            root,
            ctx.state(cid),
            gate="G3",
            rev=gate.rev,
            stage_id="s3",
            shown=[folder / "variants.json"],
            decision=decision,
            reviewer=answer.get("reviewer", "user"),
            reasons=answer.get("reasons", ""),
        )
        return folder
    selected = answer.get("selections", [])
    if decision == "APPROVE" and len(variants.candidates) == 1:
        selected = [variants.candidates[0].variantId]
    elif decision != "SELECT" or len(selected) != 1:
        raise ValueError("복수 후보는 SELECT로 한 안을 명시해야 한다")
    plan = next((p for p in variants.candidates if p.variantId == selected[0]), None)
    if plan is None:
        raise ValueError("unknown choice candidate")
    if answer.get("edits"):
        return prepare_g3_choice_edit(ctx, cid, answer)
    selection = PlanSelectionV2(
        characterId=cid,
        planRev=gate.rev,
        selected=selected[0],
        seed=ChoiceArtifactRef.model_validate(read_json(folder / "seed-ref.json")),
        requirements=variants.requirements,
        plan=source_ref(root, folder / f"candidate-{selected[0]}.json", "plan"),
        choice=variants.designs[selected[0]],
        review=variants.review,
    )
    # Validate source relationships both before approval and at downstream loads.
    req = SeedRequirements.model_validate(read_json(verified_ref(root, selection.requirements)))
    all_designs = [
        ChoiceDesign.model_validate(read_json(verified_ref(root, r)))
        for r in variants.designs.values()
    ]
    inputs = read_json(folder / "choice-review-inputs.json")
    require_choice_pass(
        ChoiceReview.model_validate(read_json(verified_ref(root, selection.review))),
        all_designs,
        req,
        body_hash(inputs),
        plans=inputs["plans"],
    )
    verify_choice_selection(root, folder, selection)
    write_once_json(folder / "plan.json", dump(plan))
    selection = selection.model_copy(
        update={"plan": source_ref(root, folder / "plan.json", "plan")}
    )
    write_once_json(folder / "selection.json", dump(selection))
    shown = [
        folder / "variants.json",
        folder / "selection.json",
        verified_ref(root, selection.requirements),
        verified_ref(root, selection.choice),
        verified_ref(root, selection.review),
        verified_ref(root, selection.plan),
        verified_ref(root, selection.seed),
    ]
    write_manifest(folder)
    shown = sorted(
        set(shown) | {p for p in folder.rglob("*") if p.is_file() and p.name != "manifest.sha256"}
    )
    write_gate_record(
        root,
        ctx.state(cid),
        gate="G3",
        rev=gate.rev,
        stage_id="s3",
        shown=shown,
        decision="SELECT",
        reviewer=answer.get("reviewer", "user"),
        selections=selected,
        reasons=answer.get("reasons", ""),
        minutes=answer.get("minutes", 0),
    )
    load_approved_choice_design(ctx, cid)
    return folder


def prepare_g3_choice_edit(ctx, cid, answer):
    root = ctx.character_dir(cid)
    gate = ctx.state(cid).gate("G3")
    old = root / "s3-plan" / gate.rev
    variants = PlanVariantsV2.model_validate(read_json(old / "variants.json"))
    selected = answer["selections"][0]
    plan = next(p for p in variants.candidates if p.variantId == selected)
    edits = answer["edits"]
    if not isinstance(edits, dict) or set(edits) - set(EDITABLE_FIELDS):
        raise ValueError("invalid G3 edit fields")
    previous = SeedRequirements.model_validate(read_json(verified_ref(root, variants.requirements)))
    replaced = answer.get("supersedesRequirements", [])
    if not isinstance(replaced, list) or not set(replaced) <= {
        r.requirementId for r in previous.requirements
    }:
        raise ValueError("unknown G3 requirement replacement")
    semantic_fields = {
        "coreTraits",
        "contrastTrait",
        "choices",
        "wantsAndFears",
        "boundaries",
        "misreadings",
    }
    for requirement in previous.requirements:
        if requirement.requirementId in replaced:
            allowed = requirement.field in edits or (
                requirement.field in {"personality", "userEdits"}
                and bool(set(edits) & semantic_fields)
            )
            if not allowed:
                raise ValueError("G3 edit cannot replace an unrelated seed requirement")
    rev = next_rev(root / "s3-plan", "pr")
    folder = root / "s3-plan" / rev
    raw = dump(plan)
    raw.update(edits)
    raw["planRev"] = rev
    for field, value in edits.items():
        raw["evidence"][field] = [
            dict(kind="USER", ref=f"G3/{gate.rev}", quote=json.dumps(value, ensure_ascii=False))
        ]
    fixed = CharacterPlanV2.model_validate(raw)
    write_once_json(
        folder / "edit-request.json",
        dict(
            priorPlanRev=gate.rev,
            selected=selected,
            edits=edits,
            supersedesRequirements=answer.get("supersedesRequirements", []),
        ),
    )
    write_once_json(folder / "fixed-plan.json", dump(fixed))
    ctx.state(cid).transition("s3", "REJECTED", rev=gate.rev)
    ctx.state(cid).set_gate("G3", "PENDING", rev, None)
    ctx.state(cid).transition("s3", "RUNNING", rev=rev)
    if ctx.execute:
        return run_choice_variants(ctx, cid)
    return folder
