"""PoC 계약(D-0044): S9~S11·내보내기 예시가 검증되고 모르는 칸을 거절한다."""

from __future__ import annotations

import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.common.errors import ValidationFailed
from character_factory_poc.common.schema import validate

H = "0" * 64
REF = {"ref": "x.json", "sha256": H}

EXAMPLES = {
    "data-plan-v1": {
        "characterId": "cf-1",
        "personaVersion": "pv1",
        "promptPairSha256": H,
        "targetTrainConversations": 640,
        "clusters": [
            {
                "clusterId": "base",
                "label": "말투·관계·일상 기반",
                "share": 0.56,
                "targetConversations": 358,
                "materials": ["SNS_REWRITE", "SYNTH"],
            }
        ],
        "guideRef": "somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md@2026-10-23",
        "writerModel": "fake-writer",
    },
    "conversation-v1": {
        "conversationId": "c0001",
        "clusterId": "conflict",
        "material": "SYNTH",
        "skeletonId": "sk01",
        "system": "짧은 system",
        "messages": [{"role": "user", "content": "안녕"}, {"role": "assistant", "content": "응"}],
        "provenance": {"writerModel": "fake-writer", "requestRef": "call-1"},
    },
    "dataset-rev-v2": {
        "characterId": "cf-1",
        "datasetRev": "ds1",
        "personaVersion": "pv1",
        "planSha256": H,
        "sampleQaRefs": ["gates/G7a-base.json"],
        "clusterCounts": {"base": {"conversations": 358, "replies": 2000}},
        "files": [{"split": "train", "path": "train.jsonl", "sha256": H, "conversations": 576}],
        "blockingFailures": 0,
        "digest": H,
    },
    "training-run-v2": {
        "characterId": "cf-1",
        "datasetRev": "ds1",
        "datasetDigest": H,
        "provider": "gemma_qlora",
        "baseModel": "unsloth/gemma-4-31B-it-unsloth-bnb-4bit",
        "requestedConfig": {"lora_r": 16, "epochs": 3},
        "dryRun": True,
        "estimate": {"usd": 1.2, "gpuHours": 1.5, "basis": "L40S $0.80/h"},
        "budgetUsd": 10.0,
        "status": "PLANNED",
    },
    "eval-prereg-v2": {
        "characterId": "cf-1",
        "personaVersion": "pv1",
        "arms": [
            {"armId": "LONG_BASE", "promptRef": REF, "model": "service-model"},
            {"armId": "SHORT_GEMMA_SFT", "promptRef": REF, "model": "binding:gemma"},
        ],
        "sets": [
            {"setId": "LONG200", "ref": REF, "seeds": [1, 2], "perTurnSeed": True, "personas": 4}
        ],
        "judge": {"model": "judge-x", "family": "judge"},
        "criteria": [
            {
                "id": "repeat",
                "metric": "repeat_rate_101_200",
                "comparator": "<=",
                "threshold": 0.05,
            }
        ],
        "frozenAt": "2026-10-27T00:00:00+00:00",
    },
    "character-package-v1": {
        "characterId": "cf-1",
        "packageRev": "pk1",
        "builtAt": "2026-10-27T00:00:00+00:00",
        "profile": {"name": "가나", "gender": "female", "age": "24"},
        "appearance": {"appearanceRev": "ar1", "heroImage": "a/hero.png", "spec": "a/spec.json"},
        "chapters": [
            {
                "chapterNo": 1,
                "chapterId": "ch1",
                "title": "첫 만남",
                "relationshipStage": "stranger",
                "facts": "chapters/ch1/facts.json",
                "frame": "chapters/ch1/frame.png",
            }
        ],
        "videos": [
            {
                "videoId": "v1",
                "kind": "INTRO",
                "durationS": 8,
                "file": "videos/v1.mp4",
                "provider": "fake",
                "synthetic": True,
            }
        ],
        "persona": {
            "personaVersion": "pv1",
            "traitSheet": "persona/trait-sheet.json",
            "longPrompt": "persona/long.md",
            "shortPrompt": "persona/short.md",
        },
        "gates": [{"gate": "G9", "rev": "pk1", "decision": "APPROVE", "recordRef": "g.json"}],
        "files": [{"path": "a/hero.png", "sha256": H, "bytes": 10}],
    },
    "export-result-v1": {
        "characterId": "cf-1",
        "package": REF,
        "target": "doki-app",
        "targetVersions": {"chat-svc": "0028_authoring_project_locale"},
        "outputs": [
            {"system": "chat-svc", "kind": "content-tree", "path": "out/chat", "sha256": H}
        ],
        "mapping": [{"source": "profile.name", "target": "api-svc character.name"}],
        "verification": {"status": "NOT_RUN", "disposableDb": True},
    },
}


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_example_validates(name: str) -> None:
    validate(name, EXAMPLES[name])


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_unknown_field_rejected(name: str) -> None:
    with pytest.raises(ValidationFailed):
        validate(name, {**EXAMPLES[name], "surprise": 1})


def test_package_tags_capped_at_four() -> None:
    obj = dict(EXAMPLES["character-package-v1"])
    obj["profile"] = {**obj["profile"], "tags": ["a", "b", "c", "d", "e"]}
    with pytest.raises(ValidationFailed):
        validate("character-package-v1", obj)
