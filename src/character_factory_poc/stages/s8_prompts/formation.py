"""Long-only bundle lifecycle and pinned source verification (spec §16)."""

from __future__ import annotations

import json
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
from character_factory_poc.common.textstats import section_names
from character_factory_poc.contracts.formation import (
    FormationDialogues,
    PersonaBlueprint,
    PersonaBundle,
    load_quality_profile,
)
from character_factory_poc.contracts.persona import PromptPairV2, TraitSheet, load_prompt_pair
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import render_gate_page
from character_factory_poc.stages.s3_plan.importer import load_approved_plan
from character_factory_poc.stages.s8_prompts.compiler import compile_persona


def pinned_path(root: Path, *parts: str) -> Path:
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("bundle source path escapes character folder")
    return path


def verify_bundle(ctx: Context, cid: str, rev_dir: Path) -> tuple[PersonaBundle, TraitSheet, Path]:
    """Never substitute the current S7 for the revision G6 actually showed."""
    raw = read_json(rev_dir / "persona-bundle.json")
    if raw.get("schemaVersion") == "persona-bundle-v2":
        from character_factory_poc.contracts.voice_bundle import PersonaBundleV2
        from character_factory_poc.stages.s8_prompts.choice_voice import verify_bundle_v2

        bundle = PersonaBundleV2.model_validate(raw)
        char = ctx.character_dir(cid)
        roots = {
            name: Path(asset.path)
            if Path(asset.path).is_absolute()
            else pinned_path(char, asset.path)
            for name, asset in bundle.sourceAssets.items()
        }
        verify_bundle_v2(bundle, roots)
        gate = ctx.state(cid).gate("G6")
        if gate.status == "AWAITING_HUMAN" and gate.rev == rev_dir.name:
            from character_factory_poc.stages.s7_traits.choice_voice import recipe

            recorded = read_json(roots["recipe"])
            if recorded["recipe"] != recipe(ctx):
                raise ValueError("formation recipe changed; rerun S7 before approval")
            from character_factory_poc.contracts.voice import VoiceBinding
            from character_factory_poc.stages.s7_traits.choice_voice import voice_inputs

            current_voice, _ = voice_inputs(ctx, read_json(roots["plan"]))
            if current_voice != VoiceBinding.model_validate(read_json(roots["voiceBinding"])):
                raise ValueError(
                    "voice policy/pack configuration changed; rerun S7 before approval"
                )
            configured = ctx.config.stage("s7").get("quality_profile")
            profile_source = (
                (ctx.config.root / str(configured)).resolve()
                if configured
                else Path(recorded["profileSource"])
            )
            if not profile_source.is_file() or sha256_file(profile_source) != recorded["profile"]:
                raise ValueError("quality profile recipe changed; rerun S7 before approval")
        pair = load_prompt_pair(rev_dir / "prompt-pair.json")
        if (
            not isinstance(pair, PromptPairV2)
            or pair.shortStatus != "UNAVAILABLE"
            or pair.short is not None
            or bundle.characterId != cid
            or bundle.personaVersion != rev_dir.name
            or pair.characterId != cid
            or pair.long != bundle.long
            or pair.traitSheetSha256 != bundle.traitSheetSha256
            or pair.systemRulesSha256 != bundle.systemRulesSha256
            or pair.systemRulesRef != bundle.systemRulesRef
            or pair.personaVersion is not None
            or (rev_dir / "long.md").read_text("utf-8") != bundle.long.text
        ):
            raise ValueError("bundle prompt identity/content mismatch")
        return bundle, TraitSheet.model_validate(read_json(roots["trait"])), roots["trait"]
    bundle = PersonaBundle.model_validate(raw)
    char = ctx.character_dir(cid)
    if bundle.characterId != cid or bundle.personaVersion != rev_dir.name:
        raise ValueError("bundle identity/revision mismatch")
    trait_dir = pinned_path(char, "s7-traits", bundle.traitRevision)
    paths = dict(
        plan=pinned_path(char, "s3-plan", bundle.planRev, "plan.json"),
        trait=trait_dir / "trait-sheet.json",
        blueprint=trait_dir / "blueprint.json",
        dialogues=trait_dir / "formation-dialogues.json",
        profile=trait_dir / "profile.json",
    )
    expected = dict(
        plan=bundle.planSha256,
        trait=bundle.traitSheetSha256,
        blueprint=bundle.blueprintSha256,
        dialogues=bundle.dialoguesSha256,
        profile=bundle.profileSha256,
    )
    for name, path in paths.items():
        if sha256_file(path) != expected[name]:
            raise ValueError(f"bundle {name} source hash mismatch")
    pair = load_prompt_pair(rev_dir / "prompt-pair.json")
    if not isinstance(pair, PromptPairV2) or pair.long != bundle.long:
        raise ValueError("bundle prompt-pair mismatch")
    if (
        pair.characterId != bundle.characterId
        or pair.personaVersion is not None
        or pair.systemRulesRef != bundle.systemRulesRef
        or pair.systemRulesSha256 != bundle.systemRulesSha256
        or pair.shortStatus != "UNAVAILABLE"
    ):
        raise ValueError("bundle prompt metadata/identity mismatch")
    if pair.traitSheetSha256 != bundle.traitSheetSha256:
        raise ValueError("bundle prompt trait hash mismatch")
    if (rev_dir / "long.md").read_text("utf-8") != bundle.long.text:
        raise ValueError("bundle long text mismatch")
    sheet = TraitSheet.model_validate(read_json(paths["trait"]))
    if sheet.characterId != cid or sheet.planRev != bundle.planRev:
        raise ValueError("bundle trait identity mismatch")
    return bundle, sheet, paths["trait"]


def finish_bundle(ctx: Context, cid: str, folder: Path, bundle: PersonaBundle) -> Path:
    """Restore derived files from the frozen bundle, then consistently open G6."""
    char = ctx.character_dir(cid)
    trait_dir = pinned_path(char, "s7-traits", bundle.traitRevision)
    pair = PromptPairV2(
        characterId=cid,
        traitSheetSha256=bundle.traitSheetSha256,
        sections=section_names(bundle.long.text)
        or [line[3:] for line in bundle.long.text.splitlines() if line.startswith("## ")],
        long=bundle.long,
        shortStatus="UNAVAILABLE",
        systemRulesRef=bundle.systemRulesRef,
        systemRulesSha256=bundle.systemRulesSha256,
    )
    write_once_json(folder / "prompt-pair.json", dump(pair))
    write_once_text(folder / "long.md", bundle.long.text)
    write_once_json(
        folder / "prompt-probe.json",
        dict(
            schemaVersion="prompt-probe-v1",
            characterId=cid,
            promptPairSha256=sha256_file(folder / "prompt-pair.json"),
            probes=[],
            judgeModel="NOT_RUN",
            note="long-only; quality qualification is separate",
        ),
    )
    if not (folder / "gate-G6.html").exists():
        name = read_json(pinned_path(char, "s3-plan", bundle.planRev, "plan.json"))["name"]
        page = render_gate_page(
            title=f"G6 페르소나 검토 · {name} · {folder.name}",
            subject_id=cid,
            gate="G6",
            rev=folder.name,
            sections=[
                (
                    "특질 시트",
                    json.dumps(read_json(trait_dir / "trait-sheet.json"), ensure_ascii=False),
                ),
                (
                    "행동·목소리 설계",
                    json.dumps(read_json(trait_dir / "blueprint.json"), ensure_ascii=False),
                ),
                (
                    "형성 대화12개",
                    json.dumps(
                        read_json(trait_dir / "formation-dialogues.json"), ensure_ascii=False
                    ),
                ),
                (f"긴 프롬프트 ({bundle.long.chars}자)", bundle.long.text),
                ("지원 범위", "한국어 문자·긴 프롬프트. 실제 품질은 아직 미검증이다."),
            ],
        )
        write_once_text(folder / "gate-G6.html", page)
    verify_bundle(ctx, cid, folder)
    write_manifest(folder)
    state = ctx.state(cid)
    if state.stage("s8").status == "RUNNING":
        state.transition("s8", "AWAITING_HUMAN", rev=folder.name)
    if state.gate("G6").status != "AWAITING_HUMAN" or state.gate("G6").rev != folder.name:
        state.set_gate("G6", "AWAITING_HUMAN", folder.name, None)
    return folder


def verify_approved_pair(ctx: Context, cid: str, folder: Path):
    bundle, sheet, sheet_path = verify_bundle(ctx, cid, folder)
    gate = ctx.state(cid).gate("G6")
    if gate.status != "APPROVED" or gate.rev != folder.name or not gate.recordRef:
        raise ValueError("approved G6 record missing")
    record = read_json(pinned_path(ctx.character_dir(cid), gate.recordRef))
    if record.get("decision") != "APPROVE":
        raise ValueError("approved record decision mismatch")
    for artifact in record["shownArtifacts"]:
        if sha256_file(pinned_path(ctx.character_dir(cid), artifact["ref"])) != artifact["sha256"]:
            raise ValueError("approved artifact hash mismatch")
    original = load_prompt_pair(folder / "prompt-pair.json")
    version = load_prompt_pair(folder / "persona-version.json")
    expected = original.model_copy(update={"personaVersion": bundle.personaVersion})
    if version != expected:
        raise ValueError("persona-version differs from approved bundle")
    return version, sheet, sheet_path


def run_formation_s8(ctx: Context, cid: str, voice_probes: list[str]) -> Path:
    if ctx.config.stage("s7").get("formation_profile") == "ko-text-choice-voice-long-v2":
        from character_factory_poc.stages.s8_prompts.choice_voice import run_choice_voice_s8

        return run_choice_voice_s8(ctx, cid, voice_probes)
    from character_factory_poc.stages.s8_prompts.build import load_system_rules

    if not ctx.execute:
        raise ValueError("--execute is required")
    if voice_probes:
        raise ValueError("new long-only profile uses persona qualify, not long/short probes")
    state = ctx.state(cid)
    state.require_deps("s8")
    current = state.stage("s8")
    char = ctx.character_dir(cid)
    if current.currentRev and current.status in ("RUNNING", "AWAITING_HUMAN"):
        rev_dir = char / "s8-prompts" / current.currentRev
        if (rev_dir / "persona-bundle.json").exists():
            bundle = PersonaBundle.model_validate(read_json(rev_dir / "persona-bundle.json"))
            return finish_bundle(ctx, cid, rev_dir, bundle)
    plan, plan_path = load_approved_plan(ctx, cid)
    tr = state.stage("s7").currentRev
    if not tr:
        raise ValueError("S7 formation is missing")
    trait_dir = char / "s7-traits" / tr
    sheet = TraitSheet.model_validate(read_json(trait_dir / "trait-sheet.json"))
    bp = PersonaBlueprint.model_validate(read_json(trait_dir / "blueprint.json"))
    ds = FormationDialogues.model_validate(read_json(trait_dir / "formation-dialogues.json"))
    profile = load_quality_profile(trait_dir / "profile.json")
    hashes = dict(
        plan=sha256_file(plan_path),
        trait=sha256_file(trait_dir / "trait-sheet.json"),
        blueprint=sha256_file(trait_dir / "blueprint.json"),
        dialogues=sha256_file(trait_dir / "formation-dialogues.json"),
    )
    rules, ref = load_system_rules(ctx)
    rev = (
        current.currentRev
        if current.status == "RUNNING" and current.currentRev
        else next_rev(char / "s8-prompts", "pv")
    )
    folder = char / "s8-prompts" / rev
    state.transition("s8", "RUNNING", rev=rev)
    try:
        bundle = compile_persona(
            plan,
            sheet,
            bp,
            ds,
            profile,
            source_hashes=hashes,
            trait_revision=tr,
            persona_version=rev,
            rules_text=rules,
            rules_ref=ref,
        )
    except Exception as exc:
        state.transition("s8", "CHECK_FAILED", rev=rev, error=str(exc))
        raise
    write_once_json(folder / "persona-bundle.json", dump(bundle))
    return finish_bundle(ctx, cid, folder, bundle)
