"""Build content first; do not decide personality in the voice renderer."""

from collections import Counter

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.dialogue_beats import FormationBeats, FormationBeatsDraft
from character_factory_poc.pipeline.formation_step import run_typed_step
from character_factory_poc.stages.s7_traits.formation import revision_dir


def check_beats(
    beats: FormationBeats, *, character_id: str, rule_ids: set[str], canon_sources=None
) -> list[str]:
    errors = []
    if beats.characterId != character_id:
        errors.append("beats identity mismatch")
    if len(beats.dialogues) != 12 or Counter(d.category for d in beats.dialogues) != {
        "ordinary": 8,
        "boundary": 2,
        "change": 2,
    }:
        errors.append("beats require 8 ordinary, 2 boundary and 2 change dialogues")
    if len({d.dialogueId for d in beats.dialogues}) != len(beats.dialogues):
        errors.append("duplicate dialogue id")
    if sum(len(d.turns) == 12 for d in beats.dialogues) < 2:
        errors.append("beats require at least two six-pair dialogues")
    seen_turns = set()
    covered = set()
    for dialogue in beats.dialogues:
        if not 4 <= len(dialogue.turns) <= 12 or len(dialogue.turns) % 2:
            errors.append("beats must contain complete user/assistant pairs")
        for i, turn in enumerate(dialogue.turns):
            if turn.role != ("user" if i % 2 == 0 else "assistant"):
                errors.append("beats role order mismatch")
            if turn.turnId in seen_turns:
                errors.append("duplicate turn id")
            seen_turns.add(turn.turnId)
            if set(turn.decisionRuleIds) - rule_ids or (
                turn.role == "user" and turn.decisionRuleIds
            ):
                errors.append("unknown or user-owned decision rule")
            covered.update(turn.decisionRuleIds)
            for fact in turn.facts:
                if fact.scope == "canon" and (
                    fact.sourceRef is None or fact.owner in {"user", "shared"}
                ):
                    errors.append(
                        "canon fact requires approved source and character/external owner"
                    )
                if fact.scope == "canon" and fact.sourceRef is not None:
                    from character_factory_poc.stages.s7_traits.formation import field_text

                    ref = fact.sourceRef
                    source = (canon_sources or {}).get(ref.kind)
                    if source is None:
                        errors.append("canon fact source is not supplied")
                    else:
                        path, body = source
                        if sha256_file(path) != ref.sha256:
                            errors.append("canon fact source hash mismatch")
                        else:
                            try:
                                if field_text(body, ref.fieldPath) != ref.quote:
                                    errors.append("canon fact quote mismatch")
                            except (ValueError, KeyError, IndexError, TypeError):
                                errors.append("canon fact field path mismatch")
    if not rule_ids <= covered:
        errors.append("beats omit approved choice rules")
    return errors


def build_formation_beats(ctx, cid: str, design, *, budget=None) -> FormationBeats:
    root = revision_dir(ctx, cid)
    bp = design.blueprint
    draft = run_typed_step(
        ctx=ctx,
        cid=cid,
        folder=root / "beats",
        role="persona_beats",
        contract=FormationBeatsDraft,
        stage="cv-beats",
        budget=budget,
        inputs=dict(blueprint=dump(bp), traitSheet=dump(design.traitSheet)),
    )
    result = FormationBeats(
        characterId=cid,
        traitRevision=root.name,
        planSha256=bp.planSha256,
        blueprintSha256=sha256_file(root / "blueprint.json"),
        choiceSha256=bp.approvedChoiceRef.sha256,
        **dump(draft),
    )
    problems = check_beats(
        result,
        character_id=cid,
        rule_ids={r.choiceRuleId for r in bp.decisionRules},
        canon_sources={
            ref.kind: (
                ctx.character_dir(cid) / ref.ref,
                read_json(ctx.character_dir(cid) / ref.ref),
            )
            for ref in bp.sourceRefs
            if ref.kind in {"plan", "trait"}
        },
    )
    if problems:
        write_once_json(root / "beats/failure.json", {"error": "; ".join(problems)})
        raise ValueError("; ".join(problems))
    write_once_json(root / "formation-beats.json", dump(result))
    return result
