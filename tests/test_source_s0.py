"""트윈 s0 출처 묶음과 G0 (D-0120, D-0126, D-0128). 원문은 모두 테스트가 만든 합성 자료다."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from character_factory_poc.common.errors import CheckFailed, FactoryError
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.pipeline.origin import SOURCE, write_origin
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.s0_source import parse
from character_factory_poc.stages.s0_source.run import (
    digest_check,
    load_approved_source,
    load_holdout,
    read_jsonl,
    run_s0,
)

DAYS = [1, 3, 5, 8, 10, 12]


def _kakao_pc() -> str:
    lines = ["엄마 님과 카카오톡 대화", "저장한 날짜 : 2026-11-08 10:00:00", ""]
    for i, d in enumerate(DAYS):
        lines.append(f"--------------- 2026년 10월 {d}일 토요일 ---------------")
        lines.append(f"[나] [오전 9:0{i}] 엄마 오늘 뭐해 {i}")
        lines.append(f"[엄마] [오전 9:1{i}] 밥은 먹었니 우리 아들 {i}번째 이야기")
        lines.append("[엄마] [오전 9:20] 사진")
        if i == 1:
            lines.append("[엄마] [오전 9:21] 이모 번호 010-1234-5678 저장해 둬")
            lines.append("[이모] [오전 9:22] 언니 나 왔어 메일은 aunt@example.com")
    return "\n".join(lines) + "\n"


def _write_pack(tmp: Path, *, consent: bool = True, kind: str = "PRIVATE_PERSON") -> Path:
    src = tmp / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "mom.txt").write_text(_kakao_pc(), encoding="utf-8")
    (src / "mom.jpg").write_bytes(b"jpg")
    basis = {"scope": "SW마에스트로 최종 발표"}
    if consent:
        basis |= {"consentBy": "어머니 본인", "consentDate": "2026-11-08"}
    pack = {
        "schemaVersion": "source-pack-v1",
        "subject": {"displayName": "엄마", "kind": kind},
        "usageBasis": basis,
        "photos": [{"path": "mom.jpg", "origin": "가족 사진"}],
        "texts": [
            {
                "textId": "k1",
                "kind": "KAKAO_EXPORT",
                "path": "mom.txt",
                "subjectSpeaker": "엄마",
                "userSpeaker": "나",
            }
        ],
    }
    path = src / "pack.json"
    path.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    return path


def _subject_ids(req) -> list[str]:
    user = req.messages[1].content
    block = user.split('<input name="corpus-sample.jsonl">', 1)[1].split("</input>", 1)[0]
    rows = [json.loads(line) for line in block.strip().splitlines() if line.strip()]
    return [r["msgId"] for r in rows if r["speaker"] == "SUBJECT"]


def _good_digest(req) -> dict:
    ids = _subject_ids(req)
    return {
        "schemaVersion": "source-digest-v1",
        "speakerCheck": {"confirmed": True, "note": ""},
        "piiFlags": [],
        "representative": [
            {"msgId": i, "category": "DAILY", "why": "끼니부터 묻는다"} for i in ids[:3]
        ],
        "observations": ["안부를 끼니로 먼저 묻는다"],
        "qualityNotes": [],
    }


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    c = Context.load(tmp_path, execute=True)
    text = FakeTextModel()
    text.add("AGENT", _good_digest)
    c.use_models(text)
    return c


def _twin(ctx: Context, cid: str = "mom") -> str:
    ctx.character_dir(cid).mkdir(parents=True, exist_ok=True)
    ctx.state(cid).save()
    write_origin(ctx.character_dir(cid), SOURCE)
    return cid


def test_kakao_formats_and_media() -> None:
    pc = parse.read_kakao("k", _kakao_pc())
    assert all(m.text != "사진" for m in pc)
    assert pc[0].name == "나" and pc[0].at.day == 1
    mobile = parse.read_kakao(
        "m",
        "2026년 11월 1일 오후 12:05, 엄마 : 밥 먹었니\n둘째 줄\n2026. 11. 2. 오전 9:00, 나 : 응\n",
    )
    assert [(m.name, m.at.hour) for m in mobile] == [("엄마", 12), ("나", 9)]
    assert mobile[0].text == "밥 먹었니\n둘째 줄"
    csv = parse.read_kakao("c", "Date,User,Message\n2026-11-01 09:12:00,엄마,밥 먹었니\n")
    assert csv[0].name == "엄마"


def test_speakers_masking_and_holdout(tmp_path: Path) -> None:
    msgs = parse.read_kakao("k1", _kakao_pc())
    from character_factory_poc.contracts.source import SourceText

    spec = SourceText(
        textId="k1", kind="KAKAO_EXPORT", path="x", subjectSpeaker="엄마", userSpeaker="나"
    )
    parse.assign_speakers(msgs, spec, "엄마")
    counts = parse.mask(msgs)
    text = "\n".join(m.text for m in msgs)
    assert "010-1234-5678" not in text and "aunt@example.com" not in text
    assert counts["phone"] == 1 and counts["email"] == 1 and counts["otherParticipants"] == 1
    assert "참여자1" in {m.name for m in msgs} and "이모" not in {m.name for m in msgs}
    assert parse.segment(msgs, spec, 6) == len(DAYS)
    corpus, held = parse.split_holdout(msgs, 0.2)
    assert {m.convId for m in held} == {"k1-c0006"}  # 날짜 가장 뒤쪽 대화 하나
    assert not {m.convId for m in corpus} & {m.convId for m in held}


def test_interview_and_article() -> None:
    from character_factory_poc.contracts.source import SourceText

    msgs = parse.read_dialogue(
        "i1", "기자: 오늘 경기 어땠나요?\n선수: 팀이 잘했어요.\n이어서 한 줄\n", "2026-10-01"
    )
    spec = SourceText(textId="i1", kind="INTERVIEW", path="x", subjectSpeaker="선수")
    parse.assign_speakers(msgs, spec, "선수")
    assert [m.speaker for m in msgs] == ["USER", "SUBJECT"] and "이어서" in msgs[1].text
    art = parse.read_article(
        "a1", "그는 경기 뒤 “끝까지 뛰겠다”고 말했다.\n\n다음 문단", None, "선수"
    )
    spec = SourceText(textId="a1", kind="ARTICLE", path="x")
    parse.assign_speakers(art, spec, "선수")
    assert [(m.speaker, m.text) for m in art if m.speaker == "SUBJECT"] == [
        ("SUBJECT", "끝까지 뛰겠다")
    ]


def test_missing_subject_speaker_fails(ctx: Context, tmp_path: Path) -> None:
    cid = _twin(ctx)
    pack = _write_pack(tmp_path)
    raw = json.loads(pack.read_text("utf-8"))
    raw["texts"][0]["subjectSpeaker"] = "아빠"
    pack.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CheckFailed, match="아빠"):
        run_s0(ctx, cid, pack)


def test_run_s0_keeps_holdout_out_of_agent_and_corpus(ctx: Context, tmp_path: Path) -> None:
    cid = _twin(ctx)
    rev_dir = run_s0(ctx, cid, _write_pack(tmp_path))
    state = ctx.state(cid)
    assert state.stage("s0").status == "AWAITING_HUMAN"
    assert state.gate("G0").status == "AWAITING_HUMAN"
    held = read_jsonl(rev_dir / "holdout.jsonl")
    assert held, "비교 세트가 비었다"
    held_texts = [r["text"] for r in held]
    corpus_text = (rev_dir / "corpus.jsonl").read_text("utf-8")
    workspace = "".join(
        p.read_text("utf-8") for p in (rev_dir / "workspace").rglob("*") if p.is_file()
    )
    for t in held_texts:
        assert t not in corpus_text and t not in workspace
    index = json.loads((rev_dir / "source-index.json").read_text("utf-8"))
    assert index["usageProblems"] == [] and index["holdoutConversations"] == 1
    assert (rev_dir / "gate-G0.html").exists() and (rev_dir / "manifest.sha256").exists()
    assert "010-1234-5678" not in corpus_text


def test_g0_locked_without_consent(ctx: Context, tmp_path: Path) -> None:
    cid = _twin(ctx)
    run_s0(ctx, cid, _write_pack(tmp_path, consent=False))
    with pytest.raises(FactoryError, match="사용 근거"):
        approve_gate(ctx, cid, "G0", {"decision": "APPROVE", "reviewer": "u"})
    approve_gate(
        ctx, cid, "G0", {"decision": "REQUEST_CHANGES", "reviewer": "u", "reasons": "동의 받기"}
    )
    assert ctx.state(cid).gate("G0").status == "REJECTED"


def test_g0_approval_unblocks_twin_front(ctx: Context, tmp_path: Path) -> None:
    cid = _twin(ctx)
    run_s0(ctx, cid, _write_pack(tmp_path))
    approve_gate(ctx, cid, "G0", {"decision": "APPROVE", "reviewer": "u"})
    state = ctx.state(cid)
    assert state.stage("s0").status == "APPROVED"
    state.require_deps("s2")
    state.require_deps("s3")
    pack, index, corpus = load_approved_source(ctx, cid)
    held = load_holdout(ctx, cid)
    assert pack.subject.displayName == "엄마" and corpus and held
    assert not {r["msgId"] for r in corpus} & {r["msgId"] for r in held}


def test_digest_check_catches_bad_picks_and_leaks() -> None:
    from character_factory_poc.contracts.source import SourceDigest

    sample = [
        {"msgId": "k-1", "speaker": "USER", "text": "뭐해"},
        {"msgId": "k-2", "speaker": "SUBJECT", "text": "밥 먹었니"},
    ]
    check = digest_check(sample, ["이건 비교 세트에만 있는 긴 문장이다"], 12)
    bad = SourceDigest.model_validate(
        {
            "speakerCheck": {"confirmed": False, "note": ""},
            "piiFlags": [{"msgId": "zzz", "reason": "주소"}],
            "representative": [{"msgId": "k-1", "category": "DAILY", "why": "x"}],
            "observations": ["이건 비교 세트에만 있는 긴 문장이다"],
        }
    )
    problems = " / ".join(check(bad))
    for needle in ("note", "zzz", "SUBJECT", "비교 세트"):
        assert needle in problems


def test_agent_retry_then_pass(ctx: Context, tmp_path: Path) -> None:
    cid = _twin(ctx)
    bad = {
        "schemaVersion": "source-digest-v1",
        "speakerCheck": {"confirmed": True, "note": ""},
        "representative": [{"msgId": "nope", "category": "DAILY", "why": "x"}],
    }
    ctx._text.add("AGENT", [bad, _good_digest])
    rev_dir = run_s0(ctx, cid, _write_pack(tmp_path))
    assert (rev_dir / "workspace" / "attempt-2.txt").exists()
    assert json.loads((rev_dir / "digest.json").read_text("utf-8"))["representative"]


def test_run_until_twin_runs_s0_and_waits_g0(ctx: Context, tmp_path: Path) -> None:
    cid = _twin(ctx)
    log = run_until(ctx, cid, RunOptions(until="G3"))
    assert any(re.match(r"s0: 사람 입력 대기", s) for s in log.steps)
    log = run_until(ctx, cid, RunOptions(until="G3", source_pack=_write_pack(tmp_path)))
    assert "G0" in log.waiting
    assert ctx.state(cid).gate("G0").status == "AWAITING_HUMAN"
