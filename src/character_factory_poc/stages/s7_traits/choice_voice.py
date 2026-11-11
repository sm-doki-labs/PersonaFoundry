"""Choice/voice formation profile; historical recipes remain opt-in and intact."""

from dataclasses import asdict
from importlib.resources import files
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.choice_design import PROFILE_ID, ChoiceArtifactRef
from character_factory_poc.contracts.formation import (
    FormationDesignV2,
    FormationDraftV2,
    PersonaBlueprintV2,
    SourceRef,
    load_quality_profile,
)
from character_factory_poc.pipeline.formation_step import run_typed_step
from character_factory_poc.stages.s3_plan.choice_design import (
    body_hash,
    load_approved_choice_design,
)
from character_factory_poc.stages.s3_plan.importer import load_approved_plan
from character_factory_poc.stages.s7_traits.beats import build_formation_beats
from character_factory_poc.stages.s7_traits.check import check_matches_plan, check_trait_sheet
from character_factory_poc.stages.s7_traits.voice import bind_voice, load_voice_pack
from character_factory_poc.stages.s7_traits.voice_render import render_formation_dialogues

ROLES = (
    "persona_choice_formation",
    "persona_beats",
    "persona_voice_render",
    "persona_voice_preservation",
)


def recipe(ctx):
    from character_factory_poc.pipeline.agent import load_role_prompt

    base = Path(__file__).parents[2]
    paths = [
        *base.joinpath("contracts").glob("*.py"),
        base / "pipeline/formation_step.py",
        *Path(__file__).parent.glob("*.py"),
        base / "stages/s8_prompts/choice_voice.py",
        base / "stages/s8_prompts/actor_persona.py",
        base / "resources/actor-system-rules-v1.md",
        base / "resources/actor-system-rules-v2.md",
        base / "resources/actor-system-rules-v3.md",
        base / "resources/actor-system-rules-v4.md",
        base / "resources/actor-system-rules-v4-motif.md",
    ]
    return dict(
        code={str(p.relative_to(base)): sha256_file(p) for p in sorted(paths) if p.exists()},
        roles={r: body_hash(load_role_prompt(r)) for r in ROLES},
        textDeck=[
            ctx.config.text_binding(task)
            for task in ("personality", "voice", "scenarios", "consistency")
        ]
        if ctx.text_deck_enabled
        else None,
        generator=asdict(ctx.config.provider("text")),
        reviewer=asdict(ctx.config.provider("judge")),
        agent=ctx.config.agent,
        profile=PROFILE_ID,
        runtimeCompiler="actor-tendencies-compiler-v3",
    )


def voice_inputs(ctx, plan):
    cfg = ctx.config.stage("s7")

    def path(value):
        return (ctx.config.root / str(value)).resolve()

    if (
        not cfg.get("voice_packs")
        or not cfg.get("voice_approval_index")
        or not cfg.get("voice_policy")
    ):
        raise ValueError(
            "VOICE_SOURCE_MISSING: voice_packs, voice_approval_index, voice_policy가 필요하다"
        )
    policy_path = path(cfg["voice_policy"])
    policy = read_json(policy_path)
    packs = [
        load_voice_pack(path(p), approval_index=path(cfg["voice_approval_index"]))
        for p in cfg["voice_packs"]
    ]
    binding = bind_voice(plan, packs, policy)
    if binding.status != "READY":
        raise ValueError("VOICE_SOURCE_MISSING: " + binding.reason)
    return binding, policy_path


def run_choice_voice_s7(ctx, cid):
    if not ctx.execute:
        raise ValueError("--execute is required")
    state = ctx.state(cid)
    state.require_deps("s7")
    plan, plan_path = load_approved_plan(ctx, cid)
    choice = load_approved_choice_design(ctx, cid)
    binding, policy_path = voice_inputs(ctx, plan)
    root = ctx.character_dir(cid)
    selection = read_json(root / "s3-plan" / plan.planRev / "selection.json")
    choice_ref = ChoiceArtifactRef.model_validate(selection["choice"])
    selected_profile = ctx.config.stage("s7").get("quality_profile")
    profile_path = (
        (ctx.config.root / str(selected_profile)).resolve()
        if selected_profile
        else Path(
            str(
                files("character_factory_poc").joinpath(
                    "resources/persona-quality-profile-choice-voice-v2.json"
                )
            )
        )
    )
    if load_quality_profile(profile_path).profileId != PROFILE_ID:
        raise ValueError("quality profile does not match choice-voice formation")
    identity = dict(
        recipe=recipe(ctx),
        plan=sha256_file(plan_path),
        choice=choice_ref.sha256,
        voice=dump(binding),
        policy=sha256_file(policy_path),
        profile=sha256_file(profile_path),
        profileSource=str(profile_path),
    )
    current = state.stage("s7")
    old = root / "s7-traits" / current.currentRev if current.currentRev else None
    reuse = old and (old / "recipe.json").exists() and read_json(old / "recipe.json") == identity
    if reuse and (old / "failure.json").exists():
        raise ValueError("previous semantic failure; create a new recipe/revision")
    if reuse and (old / "formed.json").exists():
        receipt = read_json(old / "formed.json")
        if not receipt.get("files"):
            raise ValueError("formation checkpoint has no complete source hashes")
        for name, digest in receipt["files"].items():
            candidate = (old / name).resolve()
            if (
                not candidate.is_relative_to(old.resolve())
                or not candidate.is_file()
                or sha256_file(candidate) != digest
            ):
                raise ValueError("formation checkpoint hash mismatch")
        return old / "trait-sheet.json"
    rev = old.name if reuse else next_rev(root / "s7-traits", "tr")
    folder = root / "s7-traits" / rev
    if current.status == "AWAITING_HUMAN":
        state.transition("s7", "REJECTED", rev=current.currentRev)
    state.transition("s7", "RUNNING", rev=rev)
    if not reuse and state.gate("G6").status == "AWAITING_HUMAN":
        if state.stage("s8").status == "AWAITING_HUMAN":
            state.transition("s8", "REJECTED", rev=state.stage("s8").currentRev)
        state.set_gate("G6", "PENDING", None, None)
    budget = ctx.formation_budget()
    try:
        write_once_json(folder / "recipe.json", identity)
        write_once_json(folder / "voice-binding.json", dump(binding))
        write_once_json(folder / "voice-policy.json", read_json(policy_path))
        write_once_json(folder / "profile.json", dump(load_quality_profile(profile_path)))
        draft = run_typed_step(
            ctx=ctx,
            cid=cid,
            folder=folder / "design",
            role="persona_choice_formation",
            contract=FormationDraftV2,
            stage="cv-design",
            inputs=dict(
                plan=dump(plan),
                choiceDesign=dump(choice),
                styleEvidence=dict(
                    rules=binding.rules,
                    examples=[
                        dict(
                            situation=e.situation,
                            relationship=e.relationship,
                            emotion=e.emotion,
                            styleView=e.styleView,
                        )
                        for e in binding.examples
                    ],
                ),
            ),
            budget=budget,
        )
        raw_sheet = draft.traitSheet
        expressed = raw_sheet.card.expressedTraits.model_copy(
            update={"core": list(plan.coreTraits)}
        )
        sheet = raw_sheet.model_copy(
            update={"card": raw_sheet.card.model_copy(update={"expressedTraits": expressed})}
        )
        write_once_json(
            folder / "trait-source-binding.json",
            dict(
                sourcePlanSha256=sha256_file(plan_path),
                field="card.expressedTraits.core",
                rawDraftSha256=sha256_file(folder / "design/result.json"),
                generated=list(raw_sheet.card.expressedTraits.core),
                bound=list(plan.coreTraits),
                rule=(
                    "Approved coreTraits are canonical; "
                    "bind rather than ask the writer to paraphrase them."
                ),
            ),
        )
        errors = check_trait_sheet(
            sheet, canonical_core=list(plan.coreTraits)
        ) + check_matches_plan(plan.name, plan.coreTraits)(sheet)
        if sheet.characterId != cid or sheet.planRev != plan.planRev:
            errors.append("trait identity/revision mismatch")
        if errors:
            raise ValueError("; ".join(errors))
        write_once_json(folder / "trait-sheet.json", dump(sheet))
        traits_path = folder / "trait-sheet.json"
        refs = [
            SourceRef(
                kind="plan",
                ref=plan_path.relative_to(root).as_posix(),
                version=plan.planRev,
                sha256=sha256_file(plan_path),
                fieldPath="coreTraits[0]",
                quote=plan.coreTraits[0],
            ),
            SourceRef(
                kind="trait",
                ref=traits_path.relative_to(root).as_posix(),
                version=rev,
                sha256=sha256_file(traits_path),
                fieldPath="choice.attention",
                quote=sheet.choice.attention,
            ),
        ]
        bp = PersonaBlueprintV2(
            characterId=cid,
            planRev=plan.planRev,
            planSha256=sha256_file(plan_path),
            traitSheetSha256=sha256_file(traits_path),
            decisionRules=[
                {
                    k: dump(r)[k]
                    for k in (
                        "choiceRuleId",
                        "situation",
                        "activateWhen",
                        "doNotActivateWhen",
                        "firstMove",
                        "priority",
                        "switchWhen",
                        "wrongTransformation",
                        "attention",
                        "acceptedCost",
                        "alternative",
                    )
                }
                for r in choice.rules
            ],
            voiceProfile=draft.voiceProfile,
            ordinaryModes=draft.ordinaryModes,
            factPolicy=draft.factPolicy,
            sourceRefs=refs,
            approvedChoiceRef=dump(choice_ref),
        )
        write_once_json(folder / "blueprint.json", dump(bp))
        design = FormationDesignV2(traitSheet=sheet, blueprint=bp)
        beats = build_formation_beats(ctx, cid, design, budget=budget)
        rendered = render_formation_dialogues(ctx, cid, beats, binding, budget=budget)
        # Filename compatibility, with explicit rendered-dialogues-v1 schema inside.
        write_once_json(folder / "formation-dialogues.json", dump(rendered))
        write_once_text(
            folder / "system-rules.md",
            "불변 신원은 정본을 따른다. 예시는 실제 기억이 아니다. 최신 실제 합의와 변경을 따른다.",
        )
        write_once_json(
            folder / "formed.json",
            dict(
                recipeSha256=sha256_file(folder / "recipe.json"),
                dialoguesSha256=sha256_file(folder / "rendered-dialogues.json"),
                files={
                    p.relative_to(folder).as_posix(): sha256_file(p)
                    for p in folder.rglob("*")
                    if p.is_file() and p.name not in {"formed.json", "manifest.sha256"}
                },
            ),
        )
        write_manifest(folder)
        state.transition("s7", "AWAITING_HUMAN", rev=rev)
        return folder / "trait-sheet.json"
    except Exception as exc:
        write_once_json(folder / "failure.json", {"error": str(exc)})
        state.transition("s7", "CHECK_FAILED", rev=rev, error=str(exc))
        raise
