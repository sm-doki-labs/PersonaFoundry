"""Deterministic, covered compilation for the approved choice/voice recipe."""

from itertools import combinations
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import next_rev, read_json, write_once_json, write_once_text
from character_factory_poc.contracts.choice_design import PROFILE_ID, ChoiceDesign
from character_factory_poc.contracts.dialogue_beats import FormationBeats
from character_factory_poc.contracts.formation import (
    PersonaBlueprintV2,
    TraitSheet,
    load_quality_profile,
)
from character_factory_poc.contracts.rendered_dialogues import PreservationReport, RenderedDialogues
from character_factory_poc.contracts.voice import VoiceBinding
from character_factory_poc.contracts.voice_bundle import CoveragePolicy, PersonaBundleV2
from character_factory_poc.stages.s3_plan.choice_design import body_hash
from character_factory_poc.stages.s7_traits.voice import verify_voice_binding
from character_factory_poc.stages.s7_traits.voice_render import check_render_preservation
from character_factory_poc.stages.s8_prompts.actor_persona import (
    VERSION as ACTOR_VERSION,
)
from character_factory_poc.stages.s8_prompts.actor_persona import (
    compose_actor_runtime,
    load_actor_rules,
    project_actor_persona,
    verify_actor_runtime,
)
from character_factory_poc.stages.s8_prompts.compiler import render
from character_factory_poc.stages.s8_prompts.source import (
    canonical_sections,
    project_plan,
    with_creator_traits,
)


def select_covered_examples(dialogues, policy: CoveragePolicy) -> list[str]:
    ids = sorted(d.dialogueId for d in dialogues.dialogues)
    for selected in combinations(ids, policy.examples):
        if not all(i in policy.coverage for i in selected):
            continue
        tags = {tag for i in selected for tag in policy.coverage[i].tags}
        rules = {rule for i in selected for rule in policy.coverage[i].ruleIds}
        if set(policy.requiredTags) <= tags and set(policy.requiredRuleIds) <= rules:
            return list(selected)
    raise ValueError("COVERAGE_GAP: four examples cannot cover required choices/contexts")


def verify_bundle_v2(bundle: PersonaBundleV2, roots) -> None:
    if set(roots) != set(bundle.sourceAssets):
        raise ValueError("bundle asset set mismatch")
    for name, asset in bundle.sourceAssets.items():
        if not Path(roots[name]).is_file() or sha256_file(Path(roots[name])) != asset.sha256:
            raise ValueError(f"bundle {name} source hash mismatch")
    from character_factory_poc.contracts.choice_design import PlanSelectionV2
    from character_factory_poc.stages.s3_plan.choice_design import verify_choice_selection

    char_root = Path(roots["plan"]).parents[2]
    selected = PlanSelectionV2.model_validate(read_json(roots["choiceSelection"]))
    verified_choice = verify_choice_selection(char_root, Path(roots["plan"]).parent, selected)
    approval = read_json(roots["choiceApproval"])
    if approval.get("decision") != "SELECT" or approval.get("selections") != [selected.selected]:
        raise ValueError("bundle choice approval mismatch")
    for row in approval["shownArtifacts"]:
        p = (char_root / row["ref"]).resolve()
        if (
            not p.is_relative_to(char_root.resolve())
            or not p.is_file()
            or sha256_file(p) != row["sha256"]
        ):
            raise ValueError("bundle approved choice source hash mismatch")
    bp = PersonaBlueprintV2.model_validate(read_json(roots["blueprint"]))
    choice = ChoiceDesign.model_validate(read_json(roots["choice"]))
    if choice != verified_choice or bp.approvedChoiceRef.sha256 != sha256_file(roots["choice"]):
        raise ValueError("bundle blueprint points to a different approved choice")
    expected_rules = [
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
    ]
    if [dump(r) for r in bp.decisionRules] != expected_rules:
        raise ValueError("bundle blueprint changed the approved choice")
    beats = FormationBeats.model_validate(read_json(roots["beats"]))
    dialogues = RenderedDialogues.model_validate(read_json(roots["dialogues"]))
    report = PreservationReport.model_validate(read_json(roots["preservation"]))
    voice = VoiceBinding.model_validate(read_json(roots["voiceBinding"]))
    policy = CoveragePolicy.model_validate(read_json(roots["coveragePolicy"]))
    plan = read_json(roots["plan"])
    if (
        plan["characterId"] != bundle.characterId
        or plan["planRev"] != bundle.planRev
        or bp.planSha256 != bundle.planSha256
        or bp.traitSheetSha256 != bundle.traitSheetSha256
        or choice.planSha256 != bundle.planSha256
        or choice.characterId != bundle.characterId
        or beats.planSha256 != bundle.planSha256
        or beats.choiceSha256 != sha256_file(roots["choice"])
        or beats.blueprintSha256 != sha256_file(roots["blueprint"])
        or dialogues.beatsSha256 != sha256_file(roots["beats"])
        or dialogues.voiceBindingSha256 != sha256_file(roots["voiceBinding"])
        or bundle.recipeSha256 != sha256_file(roots["recipe"])
        or bundle.coveragePolicySha256 != sha256_file(roots["coveragePolicy"])
    ):
        raise ValueError("bundle source relationship mismatch")
    semantic = read_json(roots["preservationInputs"])
    if (
        semantic.get("beats") != dump(beats)
        or semantic.get("dialogues") != dump(dialogues)
        or semantic.get("voice") != dump(voice)
        or semantic.get("blueprint") != dump(bp)
        or report.inputSha256 != body_hash(semantic)
    ):
        raise ValueError("bundle preservation source mismatch")
    check_render_preservation(beats, dialogues, reviewer=lambda _: report)
    verify_voice_binding(voice, plan, read_json(roots["voicePolicy"]))
    receipt = read_json(roots["formationReceipt"])
    recipe_compiler = read_json(roots["recipe"])["recipe"].get("runtimeCompiler")
    if recipe_compiler is not None and recipe_compiler != bundle.compilerVersion:
        raise ValueError("bundle compiler differs from its pinned formation recipe")
    trait_root = Path(roots["trait"]).parent
    for name, digest in receipt["files"].items():
        p = (trait_root / name).resolve()
        if (
            not p.is_relative_to(trait_root.resolve())
            or not p.is_file()
            or sha256_file(p) != digest
        ):
            raise ValueError("bundle formation checkpoint hash mismatch")
    if select_covered_examples(dialogues, policy) != bundle.selectedDialogueIds:
        raise ValueError("bundle selected examples differ from policy")
    if bundle.compilerVersion == ACTOR_VERSION:
        from character_factory_poc.contracts.actor_persona import RuntimePersona

        sheet = TraitSheet.model_validate(read_json(roots["trait"]))
        if bundle.examplesUsage != "review-only" or "actorProfile" not in roots:
            raise ValueError("actor bundle must keep examples outside the runtime prompt")
        projected = project_actor_persona(plan, sheet, bp)
        if RuntimePersona.model_validate(read_json(roots["actorProfile"])) != projected:
            raise ValueError("actor profile differs from approved source projection")
        rules_text = Path(roots["systemRules"]).read_text("utf-8")
        verify_actor_runtime(bundle.long.text, plan, sheet, bp, rules_text=rules_text)
    elif bundle.compilerVersion != "choice-voice-long-compiler-v2":
        raise ValueError("unsupported bundle compiler version")
    elif bundle.examplesUsage != "injected":
        raise ValueError("legacy bundle examples usage mismatch")
    else:
        if "actorProfile" in roots:
            raise ValueError("legacy compiler cannot claim actor profile assets")
        legacy_text, _ = compose_choice_voice_text(
            validate(plan["schemaVersion"], plan),
            TraitSheet.model_validate(read_json(roots["trait"])),
            bp,
            dialogues,
            voice,
            bundle.selectedDialogueIds,
            plan_sha=sha256_file(roots["plan"]),
            rules_text=Path(roots["systemRules"]).read_text("utf-8"),
            long_max=load_quality_profile(roots["profile"]).thresholds.longMaxChars,
        )
        if legacy_text != bundle.long.text:
            raise ValueError("legacy compiler/body reproduction mismatch")


def actor_compiler_hash():
    from character_factory_poc.stages.s3_plan.choice_design import body_hash

    return body_hash(
        {
            name: sha256_file(Path(__file__).with_name(name))
            for name in ("choice_voice.py", "actor_persona.py")
        }
    )


def run_choice_voice_s8(ctx, cid, voice_probes):
    from character_factory_poc.stages.s3_plan.importer import load_approved_plan
    from character_factory_poc.stages.s8_prompts.formation import finish_bundle

    if not ctx.execute or voice_probes:
        raise ValueError("choice-voice long compilation requires execute and no probes")
    state = ctx.state(cid)
    state.require_deps("s8")
    root = ctx.character_dir(cid)
    plan, pp = load_approved_plan(ctx, cid)
    tr = state.stage("s7").currentRev
    folder = root / "s7-traits" / tr
    if not (folder / "formed.json").exists():
        raise ValueError("choice voice formation incomplete")
    from character_factory_poc.stages.s7_traits.choice_voice import recipe

    if read_json(folder / "recipe.json")["recipe"] != recipe(ctx):
        raise ValueError("formation recipe changed; rerun S7 before compiling")
    sheet = TraitSheet.model_validate(read_json(folder / "trait-sheet.json"))
    bp = PersonaBlueprintV2.model_validate(read_json(folder / "blueprint.json"))
    beats = FormationBeats.model_validate(read_json(folder / "formation-beats.json"))
    ds = RenderedDialogues.model_validate(read_json(folder / "rendered-dialogues.json"))
    voice = VoiceBinding.model_validate(read_json(folder / "voice-binding.json"))
    profile = load_quality_profile(folder / "profile.json")
    policy = CoveragePolicy(
        requiredRuleIds=[r.choiceRuleId for r in bp.decisionRules],
        coverage={
            d.dialogueId: dict(
                tags=d.coverageTags, ruleIds=sorted({r for t in d.turns for r in t.decisionRuleIds})
            )
            for d in beats.dialogues
        },
    )
    write_once_json(folder / "coverage-policy.json", dump(policy))
    selected = select_covered_examples(ds, policy)
    rules_text, rules_ref = load_actor_rules(ctx)
    text, _ = compose_actor_runtime(
        plan,
        sheet,
        bp,
        rules_text=rules_text,
        long_max=profile.thresholds.longMaxChars,
    )
    rules_path = folder / "compiled-system-rules.md"
    write_once_text(rules_path, rules_text)
    selection = read_json(root / "s3-plan" / plan.planRev / "selection.json")
    assets = dict(
        plan=pp,
        trait=folder / "trait-sheet.json",
        blueprint=folder / "blueprint.json",
        dialogues=folder / "rendered-dialogues.json",
        beats=folder / "formation-beats.json",
        voiceBinding=folder / "voice-binding.json",
        voicePolicy=folder / "voice-policy.json",
        voicePack=Path(voice.packPath),
        voiceApprovalIndex=Path(voice.approvalIndexPath),
        preservation=folder / "preservation-report.json",
        preservationInputs=folder / "preservation-inputs.json",
        profile=folder / "profile.json",
        coveragePolicy=folder / "coverage-policy.json",
        systemRules=rules_path,
        recipe=folder / "recipe.json",
        formationReceipt=folder / "formed.json",
        choiceSelection=root / "s3-plan" / plan.planRev / "selection.json",
        choiceApproval=root / "gates" / f"G3-{plan.planRev}.json",
    )
    for key in ("seed", "requirements", "choice", "review"):
        assets["choiceReview" if key == "review" else key] = root / selection[key]["path"]
    current = state.stage("s8")
    if current.status == "AWAITING_HUMAN":
        old = root / "s8-prompts" / current.currentRev
        if (old / "persona-bundle.json").exists():
            saved = PersonaBundleV2.model_validate(read_json(old / "persona-bundle.json"))
            if (
                saved.traitRevision == tr
                and saved.compilerVersion == ACTOR_VERSION
                and saved.compilerSha256 == actor_compiler_hash()
                and saved.systemRulesSha256 == sha256_text(rules_text)
            ):
                verify_bundle_v2(
                    saved,
                    {
                        k: Path(v.path) if Path(v.path).is_absolute() else root / v.path
                        for k, v in saved.sourceAssets.items()
                    },
                )
                return old
        state.transition("s8", "REJECTED", rev=current.currentRev)
    rev = next_rev(root / "s8-prompts", "pv")
    out = root / "s8-prompts" / rev
    state.transition("s8", "RUNNING", rev=rev)
    write_once_json(out / "actor-persona.json", dump(project_actor_persona(plan, sheet, bp)))
    assets["actorProfile"] = out / "actor-persona.json"
    bundle = PersonaBundleV2(
        characterId=cid,
        personaVersion=rev,
        planRev=plan.planRev,
        traitRevision=tr,
        planSha256=sha256_file(pp),
        traitSheetSha256=sha256_file(assets["trait"]),
        blueprintSha256=sha256_file(assets["blueprint"]),
        dialoguesSha256=sha256_file(assets["dialogues"]),
        profileId=PROFILE_ID,
        profileSha256=sha256_file(assets["profile"]),
        compilerVersion=ACTOR_VERSION,
        compilerSha256=actor_compiler_hash(),
        systemRulesRef=rules_ref,
        systemRulesSha256=sha256_text(rules_text),
        selectedDialogueIds=selected,
        examplesUsage="review-only",
        long=dict(text=text, sha256=sha256_text(text), chars=len(text)),
        recipeSha256=sha256_file(assets["recipe"]),
        coveragePolicySha256=sha256_file(assets["coveragePolicy"]),
        sourceAssets={
            k: dict(
                path=p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p),
                sha256=sha256_file(p),
            )
            for k, p in assets.items()
        },
    )
    verify_bundle_v2(bundle, assets)
    write_once_json(out / "persona-bundle.json", dump(bundle))
    return finish_bundle(ctx, cid, out, bundle)


def compose_choice_voice_text(
    plan, sheet, bp, ds, voice, selected, *, plan_sha, rules_text, long_max=8000
):
    sections = canonical_sections(project_plan(plan, plan_sha), sheet)
    sections["SYSTEM_RULES"] = rules_text
    sections["PERSONA / DISPOSITION"] = with_creator_traits(render(dump(bp.ordinaryModes)), plan)
    sections["PERSONA / CHOICES"] = render([dump(r) for r in bp.decisionRules])
    sections["PERSONA / VOICE"] = "\n".join(voice.rules) + "\n" + "말투 목표: " + plan.voiceSummary
    sections["PERSONA / VOICE"] += "\n이 말투를 적용하지 않을 조건: " + ", ".join(
        voice.doNotUseWhen
    )
    sections["PERSONA / KNOWS_AND_LIMITS"] = (
        render(dump(bp.factPolicy))
        + "\n예시의 사용자 사실·공동 사건은 실제 기억이 아니다. 최신 실제 상태 변경을 따른다."
    )
    sections["CHARACTER_EXAMPLES"] = "\n".join(
        "\n".join(
            [f"예시 {d.dialogueId} (example-local)", *[f"{t.role}: {t.content}" for t in d.turns]]
        )
        for d in ds.dialogues
        if d.dialogueId in selected
    )
    sections["OUTPUT"] = "캐릭터가 실제로 할 말만 출력한다. 해설·라벨·사용자 대사를 쓰지 않는다."
    order = (
        "ACTOR_IDENTITY",
        "SYSTEM_RULES",
        "PERSONA / FACTS",
        "PERSONA / DISPOSITION",
        "PERSONA / CHOICES",
        "PERSONA / VOICE",
        "PERSONA / KNOWS_AND_LIMITS",
        "CHAPTERS",
        "CHARACTER_EXAMPLES",
        "OUTPUT",
    )
    text = "\n\n".join(f"## {key}\n{sections[key]}" for key in order)
    if len(text) > long_max:
        raise ValueError("long exceeds 8000 characters; no truncation")
    return text, sections
