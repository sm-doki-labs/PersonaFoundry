"""S8 text standard follows the source's turn shape; the scene keeps its own job.

All dialogue here is synthetic.
"""

from __future__ import annotations

import json

import pytest

from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.s0_source.run import run_s0
from character_factory_poc.stages.s3_plan.twin import run_s3_twin
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts import evidence_pipeline as ep
from character_factory_poc.stages.s8_prompts import source_shape
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.support.interview import interview_author, interview_judge
from tests.support.web_gates import trait_sheet_for
from tests.test_source_s0 import _good_digest, _twin, _write_pack
from tests.test_twin_s3 import _ready

PACK = {"texts": [{"textId": "i1", "kind": "INTERVIEW"}, {"textId": "k1", "kind": "KAKAO_EXPORT"}]}
LONG = "질문을 받으면 먼저 상황을 정리하고 그다음에 이유를 차근차근 설명해요."


def _qa(text_id, n, answer=LONG):
    rows = []
    for i in range(n):
        conv = f"{text_id}-c{i:04d}"
        rows.append(
            dict(textId=text_id, convId=conv, speaker="USER", name="진행", text=f"{i}번 질문은?")
        )
        rows.append(dict(textId=text_id, convId=conv, speaker="SUBJECT", name="대상", text=answer))
    return rows


def _chat(text_id, n):
    rows = []
    for i in range(n):
        conv = f"{text_id}-c{i:04d}"
        rows.append(dict(textId=text_id, convId=conv, speaker="USER", name="나", text="뭐 해"))
        for bubble in ("응 지금 일어남", f"{i}시에 밥 먹어", "너는 뭐 해?"):
            rows.append(
                dict(textId=text_id, convId=conv, speaker="SUBJECT", name="엄마", text=bubble)
            )
    return rows


def test_interview_turns_are_interview_and_chat_bubbles_are_conversation():
    interview = source_shape.analyze(PACK, _qa("i1", 12))
    assert interview["shape"] == "interview"
    assert interview["label"] == "원문 모양: 인터뷰형(질문-답 100%)"
    pool = next(p for p in interview["pools"] if p["kind"] == "INTERVIEW")
    assert pool["basis"] == "structure" and pool["qaRatio"] == 1.0

    chat = source_shape.analyze(PACK, _chat("k1", 12))
    assert chat["shape"] == "conversation"
    assert chat["qaRatio"] == pytest.approx(0.333)
    assert chat["label"].startswith("원문 모양: 대화형(한 차례 평균 ")


def test_structure_overrides_declared_kind_and_says_so():
    # A chat export that is really one long answer per question reads as an interview.
    result = source_shape.analyze(PACK, _qa("k1", 12))
    pool = next(p for p in result["pools"] if p["kind"] == "KAKAO_EXPORT")
    assert result["shape"] == "interview"
    assert pool["basis"] == "structure" and "KAKAO_EXPORT" in pool["reason"]
    # Strict alternation with short turns is still a conversation.
    short = source_shape.analyze(PACK, _qa("k1", 30, answer="응 그래 알겠어"))
    assert short["shape"] == "conversation"


def test_in_between_structure_follows_declared_kind():
    rows = []
    for i in range(12):
        conv = f"i1-c{i:04d}"
        rows.append(dict(textId="i1", convId=conv, speaker="USER", name="진행", text="질문?"))
        rows.append(dict(textId="i1", convId=conv, speaker="SUBJECT", name="대상", text="가" * 30))
        if i % 3 == 0:  # A short second bubble now and then puts the pool in between.
            rows.append(
                dict(textId="i1", convId=conv, speaker="SUBJECT", name="대상", text="나" * 5)
            )
    result = source_shape.analyze(PACK, rows)
    pool = result["pools"][0]
    assert source_shape.CONVERSATION_QA <= pool["qaRatio"] < source_shape.INTERVIEW_QA
    assert pool["basis"] == "kind" and result["shape"] == "interview"


def test_mixed_source_follows_subject_characters_and_records_share():
    rows = _qa("i1", 12) + _chat("k1", 12)
    result = source_shape.analyze(PACK, rows)
    interview_chars = 12 * len(LONG)
    chat_chars = sum(len(r["text"]) for r in _chat("k1", 12) if r["speaker"] == "SUBJECT")
    assert result["shape"] == "interview"
    assert result["shares"]["interview"] == round(
        interview_chars / (interview_chars + chat_chars), 3
    )
    assert result["qaRatio"] == 1.0  # Measured on the pools that share the chosen shape.
    assert "· 인터뷰형 발화 " in result["label"]


def test_small_or_quote_only_sources_are_not_judged():
    small = source_shape.analyze(PACK, _qa("i1", 3))
    assert small["shape"] is None
    assert small["label"] == "원문 모양: 판정 보류(장면 유형 기준)"
    article = {"texts": [{"textId": "a1", "kind": "ARTICLE"}]}
    quotes = [
        dict(textId="a1", convId="a1-c0001", speaker=s, name="", text=LONG)
        for s in ("OTHER", "SUBJECT") * 20
    ]
    assert source_shape.analyze(article, quotes)["shape"] is None


def _approved_source(tmp, template, lines):
    ctx = Context.load(tmp, execute=True)
    model = FakeTextModel()
    model.add("AGENT", _good_digest)
    ctx.use_models(model)
    cid = _twin(ctx)
    path = _write_pack(tmp)
    pack = read_json(path)
    pack["chapterTemplate"] = template
    path.write_text(json.dumps(pack), encoding="utf-8")
    path.with_name("mom.txt").write_text("\n".join(lines), encoding="utf-8")
    run_s0(ctx, cid, path)
    approve_gate(ctx, cid, "G0", {"decision": "APPROVE", "reviewer": "u"})
    return ctx, cid


def _days(day_lines):
    out = []
    for day, body in enumerate(day_lines, 1):
        out.append(f"--------------- 2026년 10월 {day}일 토요일 ---------------")
        out += body
    return out


QA_DAYS = _days(
    [f"[나] [오전 9:00] {i}번째로 궁금한 건 뭐예요?", f"[엄마] [오전 9:05] {i}번 {LONG}"]
    for i in range(1, 25)
)
CHAT_DAYS = _days(
    [
        f"[나] [오전 9:00] {i}일 뭐 해",
        "[엄마] [오전 9:05] 응 지금 막 일어났어",
        f"[엄마] [오전 9:05] {i}시에 밥 먹으러 가",
        "[엄마] [오전 9:06] 너는 오늘 뭐 해?",
    ]
    for i in range(1, 25)
)


def test_fan_call_scene_with_interview_shaped_source_uses_interview_standard(tmp_path):
    ctx, cid = _approved_source(tmp_path, "FAN_CALL", QA_DAYS)
    version, record = ep.select_standard(ctx, cid)
    assert version == ep.INTERVIEW_FORMAT == record["compiler"]
    assert record["mode"] == "source_shape" and record["basis"] == "source_shape"
    assert record["standard"] == "interview" and record["chapterTemplate"] == "FAN_CALL"
    assert record["label"] == "원문 모양: 인터뷰형(질문-답 100%)"
    assert record["sourceShape"]["version"] == source_shape.VERSION

    ctx.config.stages.setdefault("s8", {})["text_standard"] = "chapter_template"
    version, record = ep.select_standard(ctx, cid)
    assert version == ep.TENDENCY_VERSION
    assert record == dict(
        mode="chapter_template",
        basis="chapter_template",
        standard="conversation",
        compiler=ep.TENDENCY_VERSION,
        chapterTemplate="FAN_CALL",
    )


def test_interview_scene_with_chat_source_uses_conversation_standard(tmp_path):
    ctx, cid = _approved_source(tmp_path, "INTERVIEW", CHAT_DAYS)
    version, record = ep.select_standard(ctx, cid)
    assert version == ep.TENDENCY_VERSION and record["standard"] == "conversation"
    assert record["label"].startswith("원문 모양: 대화형(")
    # The scene still drives the conversation scene text.
    assert ep.version_for(ctx, cid) == ep.TENDENCY_VERSION


def test_settings_are_validated_and_inherit_keeps_shared_compiler(tmp_path):
    ctx, _, cid = _ready(tmp_path, template="INTERVIEW")
    cfg = ctx.config.stages.setdefault("s8", {})
    cfg["text_standard"] = "scene"
    with pytest.raises(ValueError, match="text_standard"):
        ep.select_standard(ctx, cid)
    cfg["text_standard"] = "source_shape"
    cfg["interview_compiler"] = "inherit"
    assert ep.select_standard(ctx, cid) == (ep.TENDENCY_VERSION, None)
    cfg["interview_compiler"] = ep.INTERVIEW_FORMAT
    cfg["motif_compiler"] = "evidence-v5"
    assert ep.select_standard(ctx, cid) == (ep.USAGE_VERSION, None)


def test_saved_record_must_match_saved_compiler():
    with pytest.raises(ValueError, match="텍스트 표준"):
        ep._inputs(
            None,
            "x",
            None,
            None,
            None,
            version=ep.TENDENCY_VERSION,
            text_standard={"compiler": ep.INTERVIEW_FORMAT},
        )


def _interview_s8(ctx, model, cid):
    judge = FakeTextModel(model="fake-interview-judge")
    ctx.use_models(model, judge)
    run_s3_twin(ctx, cid)
    approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "test"})
    model.add("AGENT", lambda req: trait_sheet_for(ctx, cid))
    run_s7(ctx, cid)
    model.add("AGENT", interview_author)
    judge.add("JUDGE", interview_judge)
    folder = run_s8(ctx, cid, [])
    approve_gate(
        ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "test", "evidenceReviewed": True}
    )
    return folder


def test_new_revision_records_choice_and_is_never_rerouted(tmp_path):
    ctx, model, cid = _ready(tmp_path, template="INTERVIEW")
    folder = _interview_s8(ctx, model, cid)
    binding = read_json(folder / "evidence-binding.json")
    record = binding["textStandard"]
    # The tiny synthetic source cannot be judged, so the scene decides and says so.
    assert record["compiler"] == binding["compiler"] == ep.INTERVIEW_FORMAT
    assert record["basis"] == "chapter_template" and record["sourceShape"]["shape"] is None
    assert record["label"] == "원문 모양: 판정 보류(장면 유형 기준)"
    assert read_json(folder / "evidence-review.json")["binding"] == binding

    cfg = ctx.config.stages.setdefault("s8", {})
    cfg["interview_compiler"] = "inherit"
    cfg["text_standard"] = "chapter_template"
    assert ep.version_for(ctx, cid) == ep.TENDENCY_VERSION
    ep.verify_review(ctx, cid, folder, approved=True)
    ep.verify_snapshot(ctx.character_dir(cid), folder)


def test_revision_saved_before_the_record_still_verifies(tmp_path, monkeypatch):
    ctx, model, cid = _ready(tmp_path, template="INTERVIEW")
    real = ep.select_standard
    monkeypatch.setattr(ep, "select_standard", lambda c, i=None: (real(c, i)[0], None))
    folder = _interview_s8(ctx, model, cid)
    monkeypatch.setattr(ep, "select_standard", real)
    assert "textStandard" not in read_json(folder / "evidence-binding.json")
    ep.verify_review(ctx, cid, folder, approved=True)
    ep.verify_snapshot(ctx.character_dir(cid), folder)
