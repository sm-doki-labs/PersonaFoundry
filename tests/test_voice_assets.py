import json

import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import write_once_json
from character_factory_poc.contracts.voice import VoicePack
from character_factory_poc.stages.s3_plan.choice_design import body_hash
from character_factory_poc.stages.s7_traits.voice import bind_voice, load_voice_pack


def voice_asset(tmp_path, author="human-edited"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "source.json"
    write_once_json(source, {"lines": [f"오늘 합주 {i}번 끝났어 ㅋㅋ" for i in range(20)]})
    validation_source = tmp_path / "validation-source.json"
    write_once_json(validation_source, {"line": "응, 알겠어"})
    examples = [
        dict(
            id=f"e{i}",
            situation=["ordinary", "affection", "conflict", "apology"][i % 4],
            relationship="close" if i % 2 else "neutral",
            emotion="serious" if i % 3 == 0 else "light",
            channel="text",
            styleView="응. 그건 좀 생각해 볼게" if i % 3 == 0 else "웅 ㅋㅋ",
            sourceFile="source.json",
            sourceSha256=sha256_file(source),
            fieldPath=f"lines[{i}]",
            sourceQuote=f"오늘 합주 {i}번 끝났어 ㅋㅋ",
            sourceGroupId=f"g{i}",
            originalConversationId=f"voice-conv-{i}",
            material=author,
        )
        for i in range(20)
    ]
    body = dict(
        schemaVersion="voice-pack-v1",
        packId="soft",
        version="v1",
        rules=["짧은 반말", "진지할 때 장난을 줄인다"],
        doNotUseWhen=["통화"],
        tags=["반말", "짧은"],
        examples=examples,
        validationExamples=[
            dict(
                id="heldout",
                styleView="응, 알겠어",
                sourceGroupId="g-other",
                originalConversationId="validation-conv",
                sourceFile="validation-source.json",
                sourceSha256=sha256_file(validation_source),
                fieldPath="line",
                sourceQuote="응, 알겠어",
                material=author,
            )
        ],
        preprocessingVersion="style-view-v1",
    )
    digest = body_hash(body)
    record = tmp_path / "approval.json"
    write_once_json(
        record,
        dict(
            assetSha256=digest,
            reviewer="user",
            decision="APPROVE",
            scope="voice-pack",
            sourceGroupIds=[f"g{i}" for i in range(20)] + ["g-other"],
        ),
    )
    pack = tmp_path / "pack.json"
    write_once_json(
        pack, body | dict(approvalFile="approval.json", approvalSha256=sha256_file(record))
    )
    index = tmp_path / "trusted.json"
    write_once_json(index, {"approvals": {"approval.json": sha256_file(record)}})
    return pack, index


def test_generated_examples_cannot_self_approve(tmp_path):
    path, index = voice_asset(tmp_path, "model-draft")
    with pytest.raises(ValueError, match="draft"):
        load_voice_pack(path, approval_index=index)


def test_missing_source_or_approval_is_not_ready(tmp_path):
    path, index = voice_asset(tmp_path)
    (tmp_path / "approval.json").unlink()
    with pytest.raises(ValueError, match="approval"):
        load_voice_pack(path, approval_index=index)


def test_voice_binding_does_not_import_source_facts(tmp_path):
    path, index = voice_asset(tmp_path)
    pack = load_voice_pack(path, approval_index=index)
    policy = dict(assignments={"cf-a": "soft"}, rules=[], defaultPackId=None)
    result = bind_voice(dict(characterId="cf-a", voiceSummary="짧은 반말"), [pack], policy)
    assert result.status == "READY"
    text = json.dumps(dump(result), ensure_ascii=False)
    assert "합주" not in text
    assert "sourceQuote" not in text
    assert len(result.examples) == 20
    assert result.doNotUseWhen == ["통화"]


def test_voice_pack_hash_change_invalidates_binding(tmp_path):
    path, index = voice_asset(tmp_path)
    obj = json.loads(path.read_text())
    obj["rules"] = ["매번 장난친다"]
    path.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="approval"):
        load_voice_pack(path, approval_index=index)


def test_missing_match_is_explicit(tmp_path):
    path, index = voice_asset(tmp_path)
    pack = load_voice_pack(path, approval_index=index)
    result = bind_voice(
        dict(characterId="cf-a", voiceSummary="존댓말"), [pack], dict(assignments={}, rules=[])
    )
    assert result.status == "VOICE_SOURCE_MISSING"


def test_same_source_group_cannot_be_both_injected_and_validation(tmp_path):
    path, index = voice_asset(tmp_path)
    raw = json.loads(path.read_text())
    raw["validationExamples"][0]["sourceGroupId"] = "g0"
    with pytest.raises(ValueError):
        VoicePack.model_validate(raw).check_split()
