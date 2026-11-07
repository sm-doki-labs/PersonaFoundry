"""Human packets hide model/recipe identity and contain no LLM judgments."""

from __future__ import annotations

from pathlib import Path

from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.stages.persona_quality.protocol import Cohort, canonical_hash


def export_review_packet(run: Path) -> Path:
    run = Path(run)
    if read_json(run / "cohort.json").get("schemaVersion") == "persona-development-cohort-v2":
        from character_factory_poc.stages.persona_quality.development import (
            export_development_packet,
        )

        return export_development_packet(run)
    cohort = Cohort.model_validate(read_json(run / "cohort.json"))
    packet = []
    mapping = {}
    template = dict(cohortHash=canonical_hash(cohort), scenes={}, blueprintFaithful={})
    # Stable IDs do not contain old/new labels. Mapping remains separate from the packet.
    for index, slot in enumerate(sorted(cohort.slots, key=lambda s: s.id), 1):
        blind = f"A{index:03}"
        mapping[blind] = slot.id
        template["blueprintFaithful"][blind] = None
        for scene in slot.scenes:
            turns = []
            for n, user in enumerate(scene.turns, 1):
                path = run / "dialogues" / slot.id / scene.id / f"{n:02}.json"
                if path.exists():
                    obj = read_json(path)
                    turns.append(dict(turn=n, user=obj["user"], assistant=obj["assistant"]))
                else:
                    turns.append(dict(turn=n, user=user.user, assistant=None))
            key = f"{blind}/{scene.id}"
            entry = dict(id=key, turns=turns, expectedChoices=scene.expectedChoices)
            if cohort.profile.get("profileId") == "ko-text-choice-voice-long-v2":
                from character_factory_poc.stages.persona_quality.development import (
                    qualification_standard,
                )

                entry.update(qualification_standard(run, slot))
            packet.append(entry)
            template["scenes"][key] = dict(
                reviewer="",
                sawLLMCandidatesFirst=False,
                naturalness=None,
                collapse=None,
                turns=[
                    dict(turn=t["turn"], voiceOK=None, majorTypes=None, evidence="", choiceOK=None)
                    for t in turns
                ],
                second=None,
                adjudication=None,
            )
    out = run / "human-review-packet.json"
    write_once_json(out, dict(cohortHash=canonical_hash(cohort), scenes=packet))
    write_once_json(run / "private-review-map.json", mapping)
    write_once_json(run / "human-review-template.json", template)
    return out
