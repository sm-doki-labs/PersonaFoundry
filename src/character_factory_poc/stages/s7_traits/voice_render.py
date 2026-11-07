"""Render approved style into fixed content, then reject meaning drift."""

import re

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.rendered_dialogues import (
    PreservationReport,
    RenderedDialogues,
    RenderedDraft,
)
from character_factory_poc.pipeline.formation_step import run_typed_step
from character_factory_poc.stages.s3_plan.choice_design import body_hash
from character_factory_poc.stages.s7_traits.formation import revision_dir

NUMBER = re.compile(r"\d+(?:[.:]\d+)*")
CHECKS = (
    "actPreserved",
    "factsPreserved",
    "ownerPreserved",
    "statePreserved",
    "toneAppropriate",
    "noUnplannedClaims",
    "coverageFaithful",
)


def check_render_structure(beats, dialogues):
    if beats.characterId != dialogues.characterId or beats.traitRevision != dialogues.traitRevision:
        raise ValueError("rendered identity/revision mismatch")
    expected = {d.dialogueId: d for d in beats.dialogues}
    actual = {d.dialogueId: d for d in dialogues.dialogues}
    if expected.keys() != actual.keys() or len(actual) != len(dialogues.dialogues):
        raise ValueError("rendered dialogue coverage mismatch")
    for key, scene in expected.items():
        row = actual[key]
        if len(scene.turns) != len(row.turns):
            raise ValueError("rendered turn count mismatch")
        # Numbers can be inherited by reference ("그 시간") and clocks can be
        # realized in 12h or 24h form. Novel values remain a cheap hard guard;
        # omission, ownership and temporal meaning require the full-context judge.
        planned = " ".join(t.act + " " + " ".join(f.text for f in t.facts) for t in scene.turns)
        allowed_numbers = set(NUMBER.findall(planned))
        for hour, minute in re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", planned):
            allowed_numbers.update({str(int(hour)), str(int(hour) % 12 or 12), str(int(minute))})
        for beat, turn in zip(scene.turns, row.turns, strict=True):
            if beat.turnId != turn.turnId or beat.role != turn.role:
                raise ValueError("rendered turn id/role mismatch")
            found = set(NUMBER.findall(turn.content))
            if not found <= allowed_numbers:
                raise ValueError("rendered number preservation failed: unplanned numeric value")


def check_render_preservation(beats, dialogues, *, reviewer):
    check_render_structure(beats, dialogues)
    inputs = dict(beats=dump(beats), dialogues=dump(dialogues))
    report = reviewer(inputs)
    if not isinstance(report, PreservationReport):
        report = PreservationReport.model_validate(report)
    turns = {t.turnId: t for d in dialogues.dialogues for t in d.turns}
    seen = [r.turnId for r in report.items]
    if set(seen) != turns.keys() or len(seen) != len(set(seen)):
        raise ValueError("preservation coverage is incomplete or duplicated")
    if report.status != "PASS" or any(
        getattr(r, c) != "PASS" for r in report.items for c in CHECKS
    ):
        raise ValueError("semantic preservation failed or unresolved")
    if any(r.quote not in turns[r.turnId].content for r in report.items):
        raise ValueError("preservation quote mismatch")
    return report


def render_formation_dialogues(ctx, cid, beats, voice, *, budget=None):
    if voice.status != "READY":
        raise ValueError("VOICE_SOURCE_MISSING")
    root = revision_dir(ctx, cid)
    inputs = dict(
        beats=dump(beats), voice=dump(voice), blueprint=read_json(root / "blueprint.json")
    )
    draft = run_typed_step(
        ctx=ctx,
        cid=cid,
        folder=root / "render",
        role="persona_voice_render",
        contract=RenderedDraft,
        stage="cv-render",
        inputs=inputs,
        budget=budget,
    )
    dialogues = RenderedDialogues(
        characterId=cid,
        traitRevision=root.name,
        beatsSha256=sha256_file(root / "formation-beats.json"),
        voiceBindingSha256=sha256_file(root / "voice-binding.json"),
        **dump(draft),
    )
    write_once_json(root / "rendered-dialogues.json", dump(dialogues))
    check_render_structure(beats, dialogues)
    semantic_inputs = inputs | dict(dialogues=dump(dialogues))
    write_once_json(root / "preservation-inputs.json", semantic_inputs)
    report = run_typed_step(
        ctx=ctx,
        cid=cid,
        folder=root / "preservation",
        role="persona_voice_preservation",
        contract=PreservationReport,
        stage="cv-preservation",
        inputs=semantic_inputs,
        judge=True,
        budget=budget,
    )
    digest = body_hash(semantic_inputs)
    if report.inputSha256 not in (None, digest):
        raise ValueError("preservation input hash mismatch")
    report = report.model_copy(update={"inputSha256": digest})
    write_once_json(root / "preservation-report.json", dump(report))
    try:
        check_render_preservation(beats, dialogues, reviewer=lambda _: report)
    except ValueError as exc:
        write_once_json(root / "preservation/failure.json", {"error": str(exc)})
        raise
    return dialogues
