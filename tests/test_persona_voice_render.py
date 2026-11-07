import copy

import pytest

from character_factory_poc.contracts.rendered_dialogues import PreservationReport, RenderedDialogues
from character_factory_poc.stages.s7_traits.voice_render import check_render_preservation
from tests.test_persona_beats import beats_fixture


def rendered_fixture(beats=None):
    beats = beats or beats_fixture()
    return RenderedDialogues(
        characterId=beats.characterId,
        traitRevision=beats.traitRevision,
        beatsSha256="1" * 64,
        voiceBindingSha256="2" * 64,
        dialogues=[
            dict(
                dialogueId=d.dialogueId,
                turns=[
                    dict(
                        turnId=t.turnId,
                        role=t.role,
                        content="부탁해" if t.role == "user" else "그건 어려워",
                    )
                    for t in d.turns
                ],
            )
            for d in beats.dialogues
        ],
    )


def preservation_fixture(dialogues):
    return dict(
        status="PASS",
        items=[
            dict(
                turnId=t.turnId,
                quote=t.content,
                actPreserved="PASS",
                factsPreserved="PASS",
                ownerPreserved="PASS",
                statePreserved="PASS",
                toneAppropriate="PASS",
                noUnplannedClaims="PASS",
                coverageFaithful="PASS",
                reason="전체 주장과 원문 조건을 대조함",
            )
            for d in dialogues.dialogues
            for t in d.turns
        ],
    )


@pytest.mark.parametrize(
    "field", ["actPreserved", "ownerPreserved", "noUnplannedClaims", "toneAppropriate"]
)
def test_semantic_failure_is_not_redrawn(field):
    beats = beats_fixture()
    rendered = rendered_fixture(beats)
    report = preservation_fixture(rendered)
    report["items"][1][field] = "FAIL"
    before = copy.deepcopy(rendered)
    with pytest.raises(ValueError, match="preservation"):
        check_render_preservation(
            beats, rendered, reviewer=lambda _: PreservationReport.model_validate(report)
        )
    assert rendered == before


def test_polite_refusal_cannot_become_acceptance():
    beats = beats_fixture()
    rendered = rendered_fixture(beats)
    raw = rendered.model_dump()
    raw["dialogues"][0]["turns"][1]["content"] = "웅 내가 해줄게"
    altered = RenderedDialogues.model_validate(raw)
    report = preservation_fixture(altered)
    report["items"][1]["actPreserved"] = "FAIL"
    with pytest.raises(ValueError):
        check_render_preservation(
            beats, altered, reviewer=lambda _: PreservationReport.model_validate(report)
        )


def test_voice_source_fact_cannot_be_added_even_as_example_local():
    beats = beats_fixture()
    rendered = rendered_fixture(beats)
    raw = rendered.model_dump()
    raw["dialogues"][0]["turns"][1]["content"] = "그건 어려워. 오늘 합주를 마쳤거든"
    altered = RenderedDialogues.model_validate(raw)
    report = preservation_fixture(altered)
    report["items"][1]["noUnplannedClaims"] = "FAIL"
    with pytest.raises(ValueError):
        check_render_preservation(
            beats, altered, reviewer=lambda _: PreservationReport.model_validate(report)
        )


def test_undeclared_or_deleted_claim_is_rejected():
    beats = beats_fixture()
    rendered = rendered_fixture(beats)
    report = preservation_fixture(rendered)
    report["items"].pop()
    with pytest.raises(ValueError, match="coverage"):
        check_render_preservation(
            beats, rendered, reviewer=lambda _: PreservationReport.model_validate(report)
        )


def test_exact_number_and_role_integrity():
    beats = beats_fixture()
    raw = rendered_fixture(beats).model_dump()
    raw["dialogues"][0]["turns"][0]["content"] = "새로운 7시 약속"
    with pytest.raises(ValueError, match="number"):
        check_render_preservation(
            beats, RenderedDialogues.model_validate(raw), reviewer=lambda _: None
        )


def test_time_realization_and_inherited_state_do_not_force_number_repetition():
    beats = beats_fixture()
    raw = beats.model_dump()
    row = raw["dialogues"][0]
    row["turns"][0].update(
        act="오늘 6시부터 6시 반까지 만남을 제안한다",
        facts=[
            dict(
                id="f",
                text="사용자가 18:00부터 18:30까지의 만남을 제안했다",
                owner="user",
                scope="example-local",
                sourceRef=None,
            )
        ],
    )
    row["turns"][1].update(
        act="그 시간을 수락한다",
        facts=[
            dict(
                id="a",
                text="18:00부터 18:30까지 만나기로 합의했다",
                owner="shared",
                scope="example-local",
                sourceRef=None,
            )
        ],
    )
    from character_factory_poc.contracts.dialogue_beats import FormationBeats

    beats = FormationBeats.model_validate(raw)
    rendered = rendered_fixture(beats).model_dump()
    rendered["dialogues"][0]["turns"][0]["content"] = "오늘 6시부터 6시 반까지 볼까?"
    rendered["dialogues"][0]["turns"][1]["content"] = "응, 그 시간 좋아"
    rendered = RenderedDialogues.model_validate(rendered)
    report = PreservationReport.model_validate(preservation_fixture(rendered))
    check_render_preservation(beats, rendered, reviewer=lambda _: report)
    bad = report.model_dump()
    bad["items"][1]["statePreserved"] = "FAIL"
    with pytest.raises(ValueError, match="preservation"):
        check_render_preservation(
            beats, rendered, reviewer=lambda _: PreservationReport.model_validate(bad)
        )
