"""Offline checks for the curated interview authoring stage. All dialogue is synthetic."""

import json
from types import SimpleNamespace

import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.store import read_json
from character_factory_poc.stages.s8_prompts import interview_authoring as editor
from character_factory_poc.stages.s8_prompts.evidence_full_source import prepare_full_source


def row(mid, text_id, conv_id, speaker, text):
    return dict(msgId=mid, textId=text_id, convId=conv_id, speaker=speaker, text=text)


def corpus(extra=0):
    rows = []
    for i, size in enumerate((20, 40, 80, 80, 100, 160, 111, 113, 115, 117, 119)):
        tid = f"source-{i % 3}"
        rows.extend(
            [
                row(f"q{i}", tid, f"session-{i}", "USER", f"합성 질문 {i}번 확인해요?"),
                row(f"a{i}", tid, f"session-{i}", "SUBJECT", f"가상응답{i} " + "나" * (size - 6)),
            ]
        )
    for i in range(extra):
        tid = f"extra-{i % 30}"
        rows.extend(
            [
                row(f"eq{i}", tid, f"extra-{i}", "USER", f"추가 합성 질문 {i}번 맞아요?"),
                row(f"ea{i}", tid, f"extra-{i}", "SUBJECT", f"추가 합성 응답 표지 {i}번입니다."),
            ]
        )
    rows.extend(
        [
            row("unpaired", "spare", "solo", "SUBJECT", "공중우편함에는무지갯빛나사가숨어있다"),
            row("flag", "spare", "flagged", "USER", "FLAGGED_SENTINEL"),
            row("after-flag", "spare", "flagged", "SUBJECT", "단절된 답변"),
            row("private", "spare", "private", "USER", "확인 번호 private@example.test"),
            row("after-private", "spare", "private", "SUBJECT", "사용 불가 질문 뒤 답변"),
            row("same-unit", "spare", "held", "SUBJECT", "SHARED_UNIT_SENTINEL"),
        ]
    )
    held = [row("eval-id", "spare", "held", "USER", "HOLDOUT_SENTINEL")]
    return prepare_full_source(rows, held, {"flag"})


def packet(source):
    return dict(
        formatVersion=editor.VERSION,
        role="합성 인물을 바탕으로 답한다.",
        scene="공개 인터뷰",
        facts="승인된 합성 사실표 원문",
        trainIds=[r["id"] for r in source["records"]],
        holdoutIds=source["holdoutIds"],
        sections=[],
    )


def authored(scope, refs, **changes):
    return dict(
        dict(
            section="CHOICES",
            scope=scope,
            trigger="질문자가 이미 정한 조건의 충족 여부를 물을 때",
            first="판단할 수 있는 범위에서 성립 여부를 먼저 밝힌다.",
            shift="",
            stop="",
            limit="동기를 묻는 경우까지 단순 확인으로 처리하지 않는다.",
            evidence=refs,
        ),
        **changes,
    )


class FakeModel:
    def __init__(self, role, calls, cards, *, bad_labels=False):
        self.role = role
        self.calls = calls
        self.cards = cards
        self.bad_labels = bad_labels

    def complete(self, request):
        phase = request.ref.rsplit("/", 1)[-1]
        assert request.ref.endswith(f"/{editor.VERSION}/{phase}")
        assert self.role == ("judge" if phase == "judge" else "text")
        self.calls.append((phase, request))
        payload = json.loads(request.messages[-1].content)
        for sentinel in (
            "FLAGGED_SENTINEL",
            "HOLDOUT_SENTINEL",
            "SHARED_UNIT_SENTINEL",
            "private@example.test",
            "승인된 합성 사실표 원문",
        ):
            assert sentinel not in request.messages[-1].content
        if phase == "classify":
            assert set(payload) == {"phase", "questions"}
            assert all(set(q) == {"id", "question"} for q in payload["questions"])
            assert "가상응답" not in request.messages[-1].content
            assert "추가 합성 응답" not in request.messages[-1].content
            assert request.kind == "AGENT"
            reason_ids = (
                {"a6"} if len(payload["questions"]) > 100 else {"a6", "a7", "a8", "a9", "a10"}
            )
            labels = ["이유과정" if q["id"] in reason_ids else "확인" for q in payload["questions"]]
            out = {"labels": labels[:-1] if self.bad_labels else labels}
        elif phase == "author":
            assert request.kind == "AGENT"
            assert all(set(r) == {"id", "unit", "question", "answer"} for r in payload["records"])
            assert all("합성 질문" in r["question"] for r in payload["records"])
            out = {"cards": self.cards, "unresolved": ["의도에 관한 근거는 부족하다."]}
        else:
            assert request.kind == "JUDGE"
            assert all(
                r["id"] not in {"unpaired", "after-flag", "after-private"}
                for r in payload["records"]
            )
            out = {
                "decisions": [
                    dict(
                        id=candidate["id"],
                        decision="HOLD" if candidate["card"]["scope"] == "REPEATED" else "APPROVE",
                        reason="일반화가 어렵다."
                        if candidate["card"]["scope"] == "REPEATED"
                        else "범위가 근거와 맞는다.",
                    )
                    for candidate in payload["cards"]
                ]
            }
        return SimpleNamespace(
            text=json.dumps(out, ensure_ascii=False),
            finish_reason="stop",
            model=self.role + "-fake",
        )


def context(calls, cards, *, bad_labels=False):
    def judge(cid, budget, allow_same_family=False):
        assert not allow_same_family
        return FakeModel("judge", calls, cards)

    return SimpleNamespace(
        text_model=lambda *_: FakeModel("text", calls, cards, bad_labels=bad_labels),
        judge_model=judge,
    )


def test_build_classifies_questions_then_measures_and_holds_bad_cards(tmp_path):
    source = corpus()
    approved_packet = packet(source)
    cards = [
        authored("LOCAL", ["a0"]),
        authored("REPEATED", ["a0", "a3"]),  # Two conversations, one text source.
        authored(
            "REPORTED",
            ["a1"],
            section="WANTS_AND_FEARS",
            first="그 공개 문답에서 밝힌 판단 기준까지만 설명한다.",
        ),
        authored("LOCAL", ["eval-id"]),
        authored("LOCAL", ["unpaired"]),
        authored("LOCAL", ["a2"], first="공중 우편함에는 무지갯빛 나사가 숨어 있다."),
        authored("LOCAL", ["a2"], first='그대로 "합성 발화"라고 답한다.'),
        authored("MEASURED", ["a2"], section="VOICE"),
        authored("REPEATED", ["a1", "a2"], first="가능한 선택지부터 비교한다."),
        authored("LOCAL", ["a2"], first="답은 25글자로 제한한다."),
    ]
    calls = []
    binding = {"compiler": editor.VERSION}
    assert sum(p.calls for p in editor.plan_calls(source)) == 3
    ctx = context(calls, cards)
    text, assembly = editor.build(
        ctx, "synthetic", approved_packet, source, binding, tmp_path, None
    )
    review = read_json(tmp_path / "evidence-review.json")
    final_packet = read_json(tmp_path / "evidence-packet.json")

    assert [p for p, _ in calls] == ["classify", "author", "judge"]
    assert [c["id"] for c in json.loads(calls[2][1].messages[-1].content)["cards"]] == [
        "card-01",
        "card-03",
        "card-09",
    ]
    assert final_packet["facts"] == approved_packet["facts"]
    assert review["records"] == source["records"]
    assert review["schemaVersion"] == "interview-editor-review-v2"
    assert assembly["status"] == review["status"] == "AWAITING_HUMAN"
    assert assembly["evidenceReviewSha256"] == sha256_file(tmp_path / "evidence-review.json")
    assert review["packetSha256"] == sha256_file(tmp_path / "evidence-packet.json")
    assert review["binding"] == read_json(tmp_path / "evidence-binding.json") == binding
    assert review["cards"] == final_packet["sections"]
    assert [c["scope"] for c in review["cards"]] == ["LOCAL", "REPORTED", "MEASURED", "MEASURED"]
    assert len(review["held"]) == 8
    assert review["cardDecisions"][0]["claimScope"] == "expression_only"
    report = review["cardDecisions"][1]
    assert report["claimScope"] == "bounded_self_report"
    assert report["allowedPersonalClaim"] == review["cards"][1]["first"]
    assert report["experienceLimit"] == review["cards"][1]["limit"]
    stats = review["questionStats"]
    assert (stats["확인"]["count"], stats["확인"]["sourceCount"]) == (6, 3)
    assert (stats["확인"]["medianChars"], stats["확인"]["atMost80Count"]) == (80, 4)
    assert (stats["이유과정"]["medianChars"], stats["이유과정"]["atMost80Count"]) == (115, 0)
    assert stats["조건정정"]["count"] == 0 and stats["조건정정"]["medianChars"] is None
    assert "80" not in text and "115" not in text
    assert "공중우편함" not in text
    assert not (tmp_path / "example-turns.json").exists()
    editor.verify_cards(review["cards"], source, review)
    editor.verify_analysis_files(tmp_path, review)

    with pytest.raises(ValueError):
        editor.verify_cards(
            [
                dict(review["cards"][0], evidence=["a0", "a3"], scope="REPEATED"),
                *review["cards"][1:],
            ],
            source,
            review,
        )
    malformed = [
        {k: v for k, v in review["cards"][0].items() if k != "scope"},
        *review["cards"][1:],
    ]
    with pytest.raises(ValueError):
        editor.verify_cards(malformed, source, dict(review, cards=malformed))
    with pytest.raises(ValueError):
        editor.verify_cards(review["cards"], source, dict(review, questionStats={}))
    with pytest.raises(ValueError):
        editor.verify_cards(
            [*review["cards"][:-1], dict(review["cards"][-1], first="모든 답을 115자로 제한한다.")],
            source,
            review,
        )

    assert editor.build(ctx, "synthetic", approved_packet, source, binding, tmp_path, None) == (
        text,
        assembly,
    )
    assert len(calls) == 3
    artifact = tmp_path / next(iter(review["analysisArtifacts"]))
    artifact.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        editor.verify_analysis_files(tmp_path, review)
    with pytest.raises(ValueError):
        editor.build(ctx, "synthetic", approved_packet, source, binding, tmp_path, None)
    assert len(calls) == 3


def test_bounded_transport_balances_sources_and_records_thin_group_without_rule(tmp_path):
    source = corpus(extra=300)
    calls = []
    # No model cards are needed when a measurement has sufficient support.
    binding = {"interviewPriorityIds": ["ea299", "eval-id", "unpaired"]}
    editor.build(context(calls, []), "synthetic", packet(source), source, binding, tmp_path, None)
    qdata = json.loads(calls[0][1].messages[-1].content)["questions"]
    adata = json.loads(calls[1][1].messages[-1].content)["records"]
    assert len(qdata) == 180 and len(adata) == 55
    assert len({r["unit"][0] for r in adata}) == 33
    assert adata[0]["id"] == "ea299"
    for phase, request in calls:
        assert len(request.messages[-1].content) <= (48_000 if phase == "classify" else 70_000)
    review = read_json(tmp_path / "evidence-review.json")
    assert len(review["questionEvidence"]) == len(qdata)
    assert review["sampling"]["priorityIds"] == ["ea299"]
    assert review["questionStats"]["이유과정"]["count"] == 1
    assert sum(c["scope"] == "MEASURED" for c in review["cards"]) == 1
    assert review["questionStats"]["이유과정"]["measurable"] is False
    assert {phase for phase, _ in calls} == {"classify", "author"}


def test_malformed_classification_never_borrows_lengths_or_retries(tmp_path):
    source = corpus()
    calls = []
    ctx = context(calls, [], bad_labels=True)
    for _ in range(2):
        with pytest.raises(ValueError):
            editor.build(ctx, "synthetic", packet(source), source, {}, tmp_path, None)
    assert [phase for phase, _ in calls] == ["classify"]
    assert not (tmp_path / "evidence-packet.json").exists()
