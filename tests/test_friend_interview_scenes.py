"""Scene selection survives intake, planning and evidence S8 using synthetic data only."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from character_factory_poc.common.canonical import sha256_file, sha256_of, sha256_text
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import read_json, verify_manifest
from character_factory_poc.contracts.release import TwinRelease
from character_factory_poc.contracts.source import SourcePack
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.stages.s3_plan.twin import _chapters, run_s3_twin
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.build import run_s8
from character_factory_poc.stages.s8_prompts.chapter_start import (
    _fan_call_frame,
    run_chapter_start,
)
from character_factory_poc.web.app import create_app
from character_factory_poc.web.sources import Draft
from tests.support.interview import interview_author, interview_judge
from tests.support.web_gates import trait_sheet_for
from tests.test_chapter_start import _start
from tests.test_evidence_pipeline import candidate
from tests.test_source_intake import META, put
from tests.test_twin_s3 import _ready


@pytest.mark.parametrize("template", ["FRIEND_CHAT", "INTERVIEW", "FAN_CALL", "FAMILY_CALL"])
def test_web_intake_preserves_scene_in_source_pack(tmp_path, template):
    with TestClient(create_app(tmp_path, runner=lambda job, stream: None)) as client:
        response = client.post(
            "/api/sources/drafts",
            json=dict(
                displayName="선수",
                subjectKind="PRIVATE_PERSON",
                chapterTemplate=template,
                autoReview=False,
            ),
        )
        assert response.status_code == 200, response.text
        cid = response.json()["characterId"]
        url = "/api/sources/" + cid
        assert client.post(put(client, url) + "/complete", json=META).is_success
        assert client.post(url + "/finalize").is_success
        pack = SourcePack.model_validate(
            read_json(tmp_path / "runs/characters" / cid / "source-pack.json")
        )
        assert pack.chapterTemplate == template


@pytest.mark.parametrize("template", ["FRIEND_CHAT", "INTERVIEW"])
def test_release_contract_keeps_new_scene_value(template):
    release = TwinRelease(
        sourcePackSha256="a" * 64,
        subjectKind="PRIVATE_PERSON",
        usageScope="합성 시험",
        consentRecorded=True,
        modelMode="PROMPT_ONLY",
        chapterTemplate=template,
        startButtonLabel="대화 시작",
    )
    assert TwinRelease.model_validate_json(release.model_dump_json()).chapterTemplate == template


@pytest.mark.parametrize(
    "template,titles,scene_tokens",
    [
        ("FRIEND_CHAT", ["친구의 안부", "일상 수다", "속마음 나누기"], ["오래된 친구", "메신저"]),
        ("INTERVIEW", ["인터뷰 시작", "주제 탐색", "인터뷰 마무리"], ["질문자", "인터뷰"]),
        ("FAN_CALL", ["첫 통화", "친해지기", "단골 팬"], ["처음 만나는 팬", "해요체"]),
        ("FAMILY_CALL", ["안부", "일상", "속마음"], ["가족과 통화", "말높임"]),
    ],
)
def test_scene_survives_approved_plan_final_prompt_and_chapter_start(
    tmp_path,
    template,
    titles,
    scene_tokens,
):
    ctx, model, cid = _ready(tmp_path, template=template)
    root = ctx.character_dir(cid)
    source_file = root / "s0-source/sp1/source-pack.json"
    source_hash = sha256_file(source_file)
    plan_dir = run_s3_twin(ctx, cid)
    assert read_json(plan_dir / "workspace/inputs/source.json")["chapterTemplate"] == template
    approve_gate(ctx, cid, "G3", dict(decision="SELECT", selections=["v1"], reviewer="test"))
    assert [c["title"] for c in read_json(plan_dir / "plan.json")["chapterArc"]] == titles
    assert read_json(plan_dir / "variants.json")["seedSha256"] == source_hash
    model.add("AGENT", lambda req: trait_sheet_for(ctx, cid))
    run_s7(ctx, cid)
    if template == "INTERVIEW":
        model.add("AGENT", interview_author)
        model.add("JUDGE", interview_judge)
        expected_compiler = "builtin:interview-editor-v2"
    else:
        model.add("AGENT", candidate)
        expected_compiler = "builtin:evidence-pipeline-v4"
    prompt_dir = run_s8(ctx, cid, [])
    pair = read_json(prompt_dir / "prompt-pair.json")
    packet = read_json(prompt_dir / "evidence-packet.json")
    binding = read_json(prompt_dir / "evidence-binding.json")
    assert pair["systemRulesRef"] == expected_compiler
    assert all(token in packet["scene"] for token in scene_tokens)
    if template == "FAN_CALL":
        assert packet["scene"] == "처음 만나는 팬과 통화한다. 해요체를 쓴다."
    elif template == "FAMILY_CALL":
        assert packet["scene"] == "가족과 통화한다. 원문의 관계와 말높임을 따른다."
    assert binding["scene"] == packet["scene"]
    assert packet["scene"] in pair["long"]["text"]
    assert sha256_text(pair["long"]["text"]) == pair["long"]["sha256"]
    assert not (prompt_dir / "example-turns.json").exists()
    prompt_hash = sha256_file(prompt_dir / "prompt-pair.json")
    # A generic call draft must not turn the selected new scene back into a fan call.
    model.add("AGENT", _start().model_dump() | {"characterId": cid})
    chapter_path = run_chapter_start(ctx, cid)
    chapters = validate("chapter-start-v1", read_json(chapter_path)).chapters
    if template in {"FRIEND_CHAT", "INTERVIEW"}:
        scene_input = read_json(chapter_path.parent / "workspace/inputs/scene-template.json")
        assert scene_input["chapterTemplate"] == template
        for ch in chapters:
            assert ch.relationship.speechLevel == "POLITE"
            assert all(token in " ".join(ch.sceneFacts) for token in scene_tokens)
            assert "첫인사 때 한 번" not in ch.relationship.initiativePolicy
            if template == "FRIEND_CHAT":
                assert "메신저" in ch.relationship.presenceReason
                assert "영상통화" not in " ".join(ch.sceneFacts + ch.relationship.entryPosture)
                assert "친구" in ch.relationship.addresseeStance
            else:
                assert "질문자" in ch.relationship.initiativePolicy
                assert "답한다" in ch.relationship.initiativePolicy
    assert sha256_file(source_file) == source_hash
    assert sha256_file(prompt_dir / "prompt-pair.json") == prompt_hash
    assert read_json(chapter_path.parent / "inputs.json")["promptPairSha256"] == prompt_hash
    assert verify_manifest(chapter_path.parent) == []
    approve_gate(ctx, cid, "G6", dict(decision="APPROVE", reviewer="test", evidenceReviewed=True))
    assert read_json(prompt_dir / "persona-version.json")["long"] == pair["long"]


@pytest.mark.parametrize(
    "kind,template,pack_hash,arc_hash,start_hash",
    [
        (
            "PUBLIC_FIGURE",
            "FAN_CALL",
            "bebdb44915d64df352aee084ee9062b60f77b8ba6dba340a8283aae93f78a8ee",
            "3836803ad1a32802e0c75b16306476bfc650782c3a71324996723a7f885c5800",
            "2e602cd09f7ab2905bf9c6d1810577e8028724306e8b4b9234d53016dfb8c836",
        ),
        (
            "PRIVATE_PERSON",
            "FAMILY_CALL",
            "52db52cd58564538f4a75030afae8355ca58d802bb96060685e03404490d8cdc",
            "de38757763045484e990c0f4789dab508a7fe4b2d863336105aa89a478fc2376",
            "3f2274cc68b9c45184b21530c2d0528f5eb7c78116973d428b3ec78daf2e242d",
        ),
    ],
)
def test_legacy_defaults_and_artifact_hashes_stay_compatible(
    kind,
    template,
    pack_hash,
    arc_hash,
    start_hash,
):
    pack = SourcePack(
        subject=dict(displayName="합성인물", kind=kind),
        texts=[dict(textId="t1", kind="TRANSCRIPT", path="synthetic.txt")],
    )
    assert pack.chapterTemplate == template
    assert sha256_of(dump(pack)) == pack_hash
    assert sha256_of(_chapters(template)) == arc_hash
    assert sha256_of(dump(_fan_call_frame(_start(), template, "나리"))) == start_hash


def test_unknown_scene_is_rejected_at_intake_and_source_contract():
    with pytest.raises(ValidationError):
        Draft(displayName="합성인물", subjectKind="PRIVATE_PERSON", chapterTemplate="UNKNOWN")
    with pytest.raises(ValidationError):
        SourcePack(
            subject=dict(displayName="합성인물", kind="PRIVATE_PERSON"),
            texts=[dict(textId="t1", kind="TRANSCRIPT", path="synthetic.txt")],
            chapterTemplate="UNKNOWN",
        )


@pytest.mark.parametrize("kind", ["KAKAO_EXPORT", "INTERVIEW", "TRANSCRIPT"])
@pytest.mark.parametrize("template", ["FRIEND_CHAT", "INTERVIEW", "FAN_CALL", "FAMILY_CALL"])
def test_opt_in_v3_respects_new_scenes_and_preserves_legacy(tmp_path, monkeypatch, kind, template):
    from character_factory_poc.stages.s0_source.run import load_approved_source
    from character_factory_poc.stages.s3_plan.importer import load_approved_plan
    from character_factory_poc.stages.s8_prompts import motif_v3
    from character_factory_poc.stages.s8_prompts.build import load_latest_trait_sheet
    from character_factory_poc.stages.s8_prompts.twin import approved_voice
    from tests.test_evidence_pipeline import ready

    ctx, _, cid = ready(tmp_path)
    plan, _ = load_approved_plan(ctx, cid)
    sheet, _ = load_latest_trait_sheet(ctx, cid)
    voice = approved_voice(ctx, cid, plan)
    pack, index, corpus = load_approved_source(ctx, cid)
    # V3 consumes normalized records; vary only the selected scene and source format.
    pack = SourcePack.model_validate(
        dump(pack)
        | {
            "chapterTemplate": template,
            "texts": [dump(text) | {"kind": kind} for text in pack.texts],
        }
    )
    monkeypatch.setattr(motif_v3, "load_approved_source", lambda *args: (pack, index, corpus))
    scene = motif_v3.packet(ctx, cid, plan, sheet, voice, None, {})["scene"]
    if template == "FRIEND_CHAT":
        assert "오래된 친구" in scene and "메신저" in scene
        assert "가족과 통화" not in scene
    elif template == "INTERVIEW":
        assert "질문자" in scene and "인터뷰" in scene
        assert "가족과 통화" not in scene
    else:
        expected = (
            "익숙한 상대와 카톡으로 대화. 말높임과 거리는 원문에 맞춘다."
            if kind == "KAKAO_EXPORT"
            else "처음 만나는 팬과 통화. 해요체."
            if template == "FAN_CALL"
            else "가족과 통화. 원문의 관계와 말높임."
        )
        assert scene == expected + " 화면에 AI 모티브임이 표시된다."
