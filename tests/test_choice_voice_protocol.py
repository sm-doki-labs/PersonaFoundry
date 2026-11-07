import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.store import write_once_json
from character_factory_poc.stages.persona_quality.choice_voice_protocol import (
    SplitManifest,
    check_controlled_hashes,
    next_neutral_user,
    validate_source_split,
)


def test_source_group_overlap_or_unresolved_audit_blocks_qualification(tmp_path):
    path = tmp_path / "source.json"
    write_once_json(path, {"text": "합성 예시"})
    rows = [
        dict(
            id="a",
            path=str(path),
            sha256=sha256_file(path),
            sourceGroupId="g1",
            originalConversationId="conv1",
            parentSourceIds=[],
            derivedFrom=[],
            sceneFamilyId="scene1",
            split="injection",
        ),
        dict(
            id="b",
            path=str(path),
            sha256=sha256_file(path),
            sourceGroupId="g2",
            originalConversationId="conv1",
            parentSourceIds=[],
            derivedFrom=[],
            sceneFamilyId="scene2",
            split="voice-validation",
        ),
    ]
    manifest = SplitManifest(auditStatus="PASS", rows=rows)
    with pytest.raises(ValueError, match="overlap"):
        validate_source_split(manifest)
    rows[1].update(originalConversationId="conv2", path=str(tmp_path / "missing.json"))
    with pytest.raises(ValueError):
        validate_source_split(SplitManifest(auditStatus="PASS", rows=rows))
    with pytest.raises(ValueError, match="audit"):
        validate_source_split(SplitManifest(auditStatus="UNRESOLVED", rows=[]))


def test_negative_like_phrase_does_not_branch_to_acceptance():
    assert (
        next_neutral_user(
            {"user": "지금 결정하기 어렵다면 다음 얘기로 넘어가도 돼", "branches": []},
            "좋아하는 건 맞지만 약속은 못 잡아",
        )
        == "지금 결정하기 어렵다면 다음 얘기로 넘어가도 돼"
    )
    with pytest.raises(ValueError, match="substring"):
        next_neutral_user(
            {"user": "다음 얘기", "branches": [{"contains": "좋아", "user": "합의했네"}]},
            "좋아하는 건 맞지만 못 해",
        )


def test_voice_comparison_requires_identical_beats():
    shared = {
        "B": dict(choice="1", blueprint="2", beats=None),
        "C": dict(choice="1", blueprint="2", beats="3"),
        "D": dict(choice="1", blueprint="2", beats="4"),
    }
    with pytest.raises(ValueError, match="beats"):
        check_controlled_hashes(shared)
    shared["D"]["beats"] = "3"
    check_controlled_hashes(shared)
    shared["B"]["choice"] = "5"
    with pytest.raises(ValueError, match="choice"):
        check_controlled_hashes(shared)


def test_new_profile_plan_counts_all_formation_steps():
    from types import SimpleNamespace

    from character_factory_poc.stages.persona_quality.run import plan_qualification

    cohort = SimpleNamespace(
        slots=[object(), object()],
        formation=True,
        profile={
            "profileId": "ko-text-choice-voice-long-v2",
            "modelBinding": {"maxOutputTokens": 2400},
        },
    )
    plan = plan_qualification(cohort)
    assert plan["formationCalls"] == 14
    assert plan["maxFormationCalls"] == 42
    assert plan["maxOutputTokens"] == 2400
