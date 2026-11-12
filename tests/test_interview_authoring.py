"""Offline checks for the curated interview authoring stage. All dialogue is synthetic."""

import json
from collections import Counter
from importlib.resources import files
from types import SimpleNamespace

import pytest

from character_factory_poc.common.canonical import sha256_file, sha256_text
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
    def __init__(self, role, calls, cards, *, classify=None, approve_repeated=False, repair=None):
        self.role = role
        self.calls = calls
        self.cards = cards
        self.classify = classify
        self.approve_repeated = approve_repeated
        self.repair = repair

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
            if self.classify:
                out = self.classify(payload["questions"])
            else:
                out = {
                    "labels": [
                        fake_label(q, len(payload["questions"])) for q in payload["questions"]
                    ]
                }
        elif phase == "author":
            assert request.kind == "AGENT"
            # Repost groups are named explicitly for the current sampler only.
            grouped = "repostGroups" in payload
            base = {"id", "unit", "questionType", "question", "answer"}
            assert all(
                set(r) == base | ({"sourceGroup"} if grouped else set()) for r in payload["records"]
            )
            assert all("합성 질문" in r["question"] for r in payload["records"])
            order = {label: i for i, label in enumerate(editor.LABELS)}
            groups = [order.get(r["questionType"], len(order)) for r in payload["records"]]
            assert groups == sorted(groups)  # Same question situations sit together.
            out = {"cards": self.cards, "unresolved": ["의도에 관한 근거는 부족하다."]}
        elif phase == "repair":
            assert request.kind == "AGENT"
            assert request.messages[0].content == editor.instructions("repair")
            assert set(payload) - {"scene", "repostGroups"} == {"phase", "records", "cards"}
            assert all(set(c) == {"id", "card", "fix"} for c in payload["cards"])
            # Only the evidence the held cards cite is shown again.
            cited = {ref for c in payload["cards"] for ref in c["card"]["evidence"]}
            assert {r["id"] for r in payload["records"]} == cited
            out = self.repair(payload) if self.repair else {"cards": []}
        else:
            assert request.kind == "JUDGE"
            assert all(
                r["id"] not in {"unpaired", "after-flag", "after-private"}
                for r in payload["records"]
            )
            hold = lambda card: card["scope"] == "REPEATED" and not self.approve_repeated  # noqa: E731
            out = {
                "decisions": [
                    dict(
                        id=candidate["id"],
                        decision="HOLD" if hold(candidate["card"]) else "APPROVE",
                        reason="일반화가 어렵다."
                        if hold(candidate["card"])
                        else "범위가 근거와 맞는다.",
                    )
                    for candidate in payload["cards"]
                ]
            }
        return SimpleNamespace(
            text=out if isinstance(out, str) else json.dumps(out, ensure_ascii=False),
            finish_reason="stop",
            model=self.role + "-fake",
        )


def fake_label(question, count):
    reason_numbers = (6,) if count > 100 else (6, 7, 8, 9, 10)
    return (
        "이유과정"
        if any(question["question"] == f"합성 질문 {i}번 확인해요?" for i in reason_numbers)
        else "확인"
    )


def context(calls, cards, *, classify=None, approve_repeated=False, repair=None):
    def judge(cid, budget, allow_same_family=False):
        assert not allow_same_family
        return FakeModel("judge", calls, cards, approve_repeated=approve_repeated)

    return SimpleNamespace(
        text_model=lambda *_: FakeModel("text", calls, cards, classify=classify, repair=repair),
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
    # classify, author, at most one format repair, judge.
    assert sum(p.calls for p in editor.plan_calls(source)) == 4
    ctx = context(calls, cards)
    text, assembly = editor.build(
        ctx, "synthetic", approved_packet, source, binding, tmp_path, None
    )
    review = read_json(tmp_path / "evidence-review.json")
    final_packet = read_json(tmp_path / "evidence-packet.json")

    assert [p for p, _ in calls] == ["classify", "author", "repair", "judge"]
    # The quoted and the numeric first fail only a field format, so they go to repair.
    repair = json.loads(calls[2][1].messages[-1].content)
    assert [(c["id"], list(c["fix"])) for c in repair["cards"]] == [
        ("card-07", ["first"]),
        ("card-10", ["first"]),
    ]
    assert [c["id"] for c in json.loads(calls[3][1].messages[-1].content)["cards"]] == [
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
    assert [c["scope"] for c in review["cards"]] == [
        "LOCAL",
        "REPORTED",
        "MEASURED",
        "MEASURED",
        "FACTS_GUARD",
    ]
    assert len(review["held"]) == 8
    held = {h["id"]: h["reason"] for h in review["held"]}
    assert held["card-07"].startswith("형식 보류 · 수선 응답이 이 카드를 고치지 않았다")
    assert held["card-02"] == "REPEATED 카드는 재전재를 제외한 서로 다른 출처가 필요하다"
    assert [(c["id"], c["outcome"]) for c in review["formatRepair"]["cards"]] == [
        ("card-07", "NOT_RETURNED"),
        ("card-10", "NOT_RETURNED"),
    ]
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
            [
                *review["cards"][:-2],
                dict(review["cards"][-2], first="모든 답을 115자로 제한한다."),
                review["cards"][-1],
            ],
            source,
            review,
        )

    assert editor.build(ctx, "synthetic", approved_packet, source, binding, tmp_path, None) == (
        text,
        assembly,
    )
    assert len(calls) == 4
    artifact = tmp_path / next(iter(review["analysisArtifacts"]))
    artifact.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        editor.verify_analysis_files(tmp_path, review)
    with pytest.raises(ValueError):
        editor.build(ctx, "synthetic", approved_packet, source, binding, tmp_path, None)
    assert len(calls) == 4


def test_bounded_transport_clusters_sources_and_records_thin_group_without_rule(tmp_path):
    source = corpus(extra=300)
    calls = []
    # No model cards are needed when a measurement has sufficient support.
    binding = {"interviewPriorityIds": ["ea299", "eval-id", "unpaired"]}

    def classify(questions):
        assert [q["id"] for q in questions] == [f"q{i}" for i in range(1, 181)]
        return {"labels": {q["id"]: fake_label(q, len(questions)) for q in reversed(questions)}}

    ctx = context(calls, [], classify=classify)
    editor.build(ctx, "synthetic", packet(source), source, binding, tmp_path, None)
    qdata = json.loads(calls[0][1].messages[-1].content)["questions"]
    adata = json.loads(calls[1][1].messages[-1].content)["records"]
    assert len(qdata) == 180 and len(adata) == editor.MAX_AUTHOR_RECORDS
    per_source = Counter(r["unit"][0] for r in adata)
    # Several pairs per source, so one question situation can recur across sources.
    # source-2 has three pairs; the record cap cuts the last cluster short.
    assert Counter(per_source.values()) == {editor.PAIRS_PER_SOURCE: 29, 3: 1, 1: 1}
    assert adata[0]["id"] == "ea299"
    assert all(r["questionType"] in editor.LABELS for r in adata)  # Every author pair is labeled.
    for phase, request in calls:
        assert len(request.messages[-1].content) <= (48_000 if phase == "classify" else 80_000)
    review = read_json(tmp_path / "evidence-review.json")
    sampling = review["sampling"]
    assert sampling["version"] == editor.SAMPLING_VERSION
    assert sampling["authorSourceCount"] == 31 and sampling["pairsPerSource"] == 4
    assert sampling["authorIds"][0] == "ea299"
    assert sampling["questionIds"][: len(adata)] == sampling["authorIds"]
    asked = set(sampling["questionIds"])
    assert len({r["unit"][0] for r in source["records"] if r["id"] in asked}) == 33
    assert len(review["questionEvidence"]) == len(qdata)
    assert sampling["priorityIds"] == ["ea299"]
    assert review["questionStats"]["이유과정"]["count"] == 1
    assert sum(c["scope"] == "MEASURED" for c in review["cards"]) == 1
    assert review["questionStats"]["이유과정"]["measurable"] is False
    assert review["questionClassification"] == dict(
        status="COMPLETE", reason=None, observedCount=180, unobservedIds=[]
    )
    editor.verify_cards(review["cards"], source, review)
    editor.verify_analysis_files(tmp_path, review)
    assert {phase for phase, _ in calls} == {"classify", "author"}


def _resource(name):
    return files("character_factory_poc.resources").joinpath(name + ".md").read_text("utf-8")


def test_author_and_judge_share_one_scope_definition():
    for revision, phases in (
        (editor.INSTRUCTIONS, editor.PHASES),
        (editor.LEGACY_INSTRUCTIONS, editor.LEGACY_PHASES),
    ):
        scopes = editor._block(_resource(revision), "scopes")
        shared = [editor.instructions(p, revision) for p in phases if p != "classify"]
        assert scopes and all(scopes in text for text in shared)
        assert scopes not in editor.instructions("classify", revision)
        assert all("<!--" not in editor.instructions(p, revision) for p in phases)


def test_legacy_instructions_stay_byte_identical_and_v3_requires_limit():
    # Approved and awaiting interview bindings hash this whole file (instructionsSha256,
    # systemRulesSha256), so editing it would stop the 8783 review from verifying.
    assert sha256_text(_resource(editor.LEGACY_INSTRUCTIONS)) == (
        "3d00bb43601c16855e5efbfc21384611d78245058c2c6fe63a99f27cd0a30368"
    )
    legacy, current = _resource(editor.LEGACY_INSTRUCTIONS), _resource(editor.INSTRUCTIONS)
    # The classify text is unchanged, so a resumed legacy build keeps its cached labels.
    assert editor._block(legacy, "classify") == editor._block(current, "classify")
    author = editor.instructions("author")
    assert "`limit`을 비우지 않는다" in author and "`shift`와 `stop` 둘뿐이다" in author
    assert "`limit`이 새 반응을 주장하면" not in author  # Read as optional in v2.
    assert "`limit`에는 자료로 확인할 수 없는 부분을 짧게 쓴다" in author
    assert "`fix`에 적힌 필드만 다시 쓴다" in editor.instructions("repair")


def test_cross_source_repeated_card_reaches_g6_with_grouped_records(tmp_path):
    source = corpus()
    calls = []
    cards = [
        authored("REPEATED", ["a1", "a2"], first="가능한 선택지부터 비교한다."),
        authored("LOCAL", ["a0"]),
    ]
    ctx = context(calls, cards, approve_repeated=True)
    editor.build(ctx, "synthetic", packet(source), source, {}, tmp_path, None)
    records = json.loads(calls[1][1].messages[-1].content)["records"]
    assert Counter(r["unit"][0] for r in records) == {"source-0": 4, "source-1": 4, "source-2": 3}
    assert [r["questionType"] for r in records][-5:] == ["이유과정"] * 5
    judged = json.loads(calls[2][1].messages[-1].content)["records"]
    assert judged == records
    review = read_json(tmp_path / "evidence-review.json")
    repeated = [c for c in review["cards"] if c["scope"] == "REPEATED"]
    assert [c["evidence"] for c in repeated] == [["a1", "a2"]]
    editor.verify_cards(review["cards"], source, review)
    editor.verify_analysis_files(tmp_path, review)


def test_review_saved_by_round_robin_sampler_still_verifies(tmp_path, monkeypatch):
    source = corpus(extra=300)
    current = editor._samples
    # Reproduce a review written before sampling carried a version.
    monkeypatch.setattr(
        editor, "_samples", lambda src, binding, **kw: current(src, binding, version=None, **kw)
    )
    ctx = context([], [authored("LOCAL", ["a0"])])
    editor.build(ctx, "synthetic", packet(source), source, {}, tmp_path, None)
    monkeypatch.undo()
    review = read_json(tmp_path / "evidence-review.json")
    sampling = review["sampling"]
    assert "version" not in sampling and len(sampling["authorIds"]) == 55
    assert len({r["unit"][0] for r in source["records"] if r["id"] in sampling["authorIds"]}) == 33
    editor.verify_cards(review["cards"], source, review)
    editor.verify_analysis_files(tmp_path, review)
    for changed in (dict(sampling, version=editor.SAMPLING_VERSION), dict(sampling, version="x")):
        with pytest.raises(ValueError, match="표본"):
            editor.verify_cards(review["cards"], source, dict(review, sampling=changed))


def repost_corpus():
    """'reedit' re-transcribes one answer of 'orig'; the greet sources share only a greeting."""
    answers = {
        "orig": [
            "오래 선수 생활을 할 수 있게 많은 분들이 계속 응원해 주시면 정말 좋겠습니다",
            "가상응답 첫째 출처의 둘째 답은 경기 준비 과정을 차근차근 풀어 설명합니다",
            "가상응답 첫째 출처의 셋째 답은 동료에게 공을 돌리며 짧게 마무리합니다",
        ],
        "reedit": [
            "오래오래 선수 생활할 수 있게 많은 분들이 계속 응원해 주시면 정말 좋겠어요",
            "가상응답 재편집본 고유의 답은 훈련 일정 이야기를 다른 순서로 꺼냅니다",
            "가상응답 재편집본 또 다른 답은 질문의 전제를 부분적으로 바로잡습니다",
        ],
        "other": [
            "가상응답 독립 출처 답은 칭찬을 받으면 먼저 낮추고 나서 감사를 전합니다",
            "가상응답 독립 출처 다른 답은 고를 때 기준부터 밝히고 하나를 고릅니다",
            "가상응답 독립 출처 셋째 답은 모르는 것은 모른다고 짧게 말합니다",
        ],
        "greet-a": ["안녕하세요 합성인물입니다 오늘은 비 오는 날 산책 이야기를 하겠습니다"],
        "greet-b": ["안녕하세요 합성인물입니다 내일은 새 운동화 고르는 이야기를 하겠습니다"],
    }
    rows = []
    for tid, texts in answers.items():
        for i, text in enumerate(texts):
            rows += [
                row(f"{tid}-q{i}", tid, f"{tid}-s{i}", "USER", f"합성 질문 {tid} {i}번이요?"),
                row(f"{tid}-a{i}", tid, f"{tid}-s{i}", "SUBJECT", text),
            ]
    return prepare_full_source(rows, [], set())


def test_reposts_merge_into_one_source_and_facts_cards_are_held(tmp_path):
    source = repost_corpus()
    _, author, sampling = editor._samples(source, {})
    assert sampling["sourceIdentity"] == "repostGroup"
    assert sampling["repostGroups"] == [["orig", "reedit"]]  # The greeting alone never merges.
    sampled = [r["id"] for r in author]
    assert ("orig-a0" in sampled) != ("reedit-a0" in sampled)  # One copy of the repost only.
    same_interview = [
        next(rid for rid in sampled if rid.startswith(tid + "-")) for tid in ("orig", "reedit")
    ]
    cards = [
        authored("REPEATED", same_interview, first="가능한 선택지부터 비교한다."),
        authored("REPEATED", [same_interview[0], "other-a0"], first="가능한 선택지부터 비교한다."),
        authored("LOCAL", ["other-a2"], trigger="정확한 수치나 기록을 묻는 질문을 받을 때"),
    ]
    calls = []
    ctx = context(calls, cards, approve_repeated=True)
    text, _ = editor.build(ctx, "synthetic", packet(source), source, {}, tmp_path, None)
    author_payload = json.loads(calls[1][1].messages[-1].content)
    judge_payload = json.loads(calls[2][1].messages[-1].content)
    assert author_payload["repostGroups"] == judge_payload["repostGroups"] == [["orig", "reedit"]]
    groups = {r["unit"][0]: r["sourceGroup"] for r in author_payload["records"]}
    assert groups["orig"] == groups["reedit"] == "orig" and groups["other"] == "other"
    assert [c["id"] for c in judge_payload["cards"]] == ["card-02"]
    review = read_json(tmp_path / "evidence-review.json")
    held = {h["id"]: h["reason"] for h in review["held"]}
    assert "서로 다른 출처" in held["card-01"] and "사실표" in held["card-03"]
    assert [c["scope"] for c in review["cards"] if c["scope"] != "MEASURED"] == [
        "REPEATED",
        "FACTS_GUARD",
    ]
    assert review["cardDecisions"][-1]["claimScope"] == "facts_literal"
    assert "[KNOWS_AND_LIMITS]\n" + editor.FACTS_GUARD_CARD["first"] + "\n" in text
    editor.verify_cards(review["cards"], source, review)
    for cards_without_guard in (review["cards"][:-1], [*review["cards"], review["cards"][-1]]):
        with pytest.raises(ValueError):
            editor.verify_cards(
                cards_without_guard, source, dict(review, cards=cards_without_guard)
            )


def test_cluster_v1_review_keeps_old_rules_and_layout(tmp_path, monkeypatch):
    """Reviews saved with source-cluster-v1 verify unchanged: no guard, text-ID sources."""
    source = repost_corpus()
    current = editor._samples
    monkeypatch.setattr(
        editor,
        "_samples",
        lambda src, binding, **kw: current(src, binding, version=editor.CLUSTER_V1, **kw),
    )
    fact_card = authored("LOCAL", ["other-a2"], trigger="정확한 수치를 묻는 질문을 받을 때")
    calls = []
    text, _ = editor.build(
        context(calls, [fact_card]), "synthetic", packet(source), source, {}, tmp_path, None
    )
    monkeypatch.undo()
    review = read_json(tmp_path / "evidence-review.json")
    assert review["sampling"]["version"] == editor.CLUSTER_V1
    assert "repostGroups" not in review["sampling"]
    assert "repostGroups" not in json.loads(calls[1][1].messages[-1].content)
    assert [c["scope"] for c in review["cards"] if c["scope"] != "MEASURED"] == ["LOCAL"]
    assert editor.FACTS_GUARD_CARD["first"] not in text
    assert "자료가 부족하므로 이 영역의 인물 특성을 정하지 않는다." in text
    editor.verify_cards(review["cards"], source, review)
    guarded = [*review["cards"], editor.FACTS_GUARD_CARD]
    with pytest.raises(ValueError):
        editor.verify_cards(guarded, source, dict(review, cards=guarded))


def test_partial_keyed_classification_holds_missing_and_uncertain_labels(tmp_path):
    source = corpus()
    calls = []

    def classify(questions):
        labels = {q["id"]: "확인" for q in reversed(questions) if q["id"] != "q2"}
        labels["q4"] = None
        labels["q5"] = "기타"
        return {"labels": labels}

    ctx = context(calls, [authored("LOCAL", ["a0"])], classify=classify)
    text, _ = editor.build(ctx, "synthetic", packet(source), source, {}, tmp_path, None)
    review = read_json(tmp_path / "evidence-review.json")
    ids = review["sampling"]["questionIds"]
    audit = review["questionClassification"]
    assert audit == dict(
        status="PARTIAL",
        reason="missing_or_uncertain_labels",
        observedCount=9,
        unobservedIds=[ids[1], ids[3]],
    )
    observed = {r["id"]: r["questionType"] for r in review["questionEvidence"]}
    assert observed == {
        rid: "기타" if i == 4 else "확인" for i, rid in enumerate(ids) if i not in (1, 3)
    }
    assert review["questionStats"]["확인"]["count"] == 8
    assert review["questionStats"]["확인"]["medianChars"] is not None
    assert review["questionStats"]["확인"]["measurable"] is False
    assert [c["scope"] for c in review["cards"]] == ["LOCAL", "FACTS_GUARD"]
    assert "묻는 핵심 위주로 짧게 답한다." not in text
    assert review["held"][0]["id"] == "question-classification"
    editor.verify_cards(review["cards"], source, review)
    editor.verify_analysis_files(tmp_path, review)
    with pytest.raises(ValueError):
        editor.verify_cards(
            review["cards"],
            source,
            dict(review, questionClassification=dict(audit, observedCount=11)),
        )
    with pytest.raises(ValueError):
        editor.verify_analysis_files(
            tmp_path, {k: v for k, v in review.items() if k != "questionClassification"}
        )


@pytest.mark.parametrize(
    "invalid_output",
    [
        '{"labels":',
        {"labels": ["확인"]},
        '{"labels":{"q1":"확인","q1":"기타"}}',
        {"labels": {"q999": "확인"}},
        {"labels": {"q1": "모르는라벨"}},
    ],
)
def test_invalid_classification_keeps_independently_judged_cards_and_never_retries(
    tmp_path, invalid_output
):
    source = corpus()
    calls = []
    ctx = context(
        calls,
        [authored("LOCAL", ["a0"]), authored("LOCAL", ["a2"], first="답은 25글자로 제한한다.")],
        classify=lambda _: invalid_output,
    )
    args = (ctx, "synthetic", packet(source), source, {}, tmp_path, None)
    built = editor.build(*args)
    assert editor.build(*args) == built
    # The numeric card is offered to the one repair call, which leaves it unchanged.
    assert [phase for phase, _ in calls] == ["classify", "author", "repair", "judge"]
    review = read_json(tmp_path / "evidence-review.json")
    assert built[1]["status"] == review["status"] == "AWAITING_HUMAN"
    assert review["questionClassification"] == dict(
        status="UNAVAILABLE",
        reason="invalid_structured_response",
        observedCount=0,
        unobservedIds=review["sampling"]["questionIds"],
    )
    assert review["questionEvidence"] == []
    assert all(
        stat["count"] == 0 and stat["medianChars"] is None and not stat["measurable"]
        for stat in review["questionStats"].values()
    )
    assert [c["scope"] for c in review["cards"]] == ["LOCAL", "FACTS_GUARD"]
    assert review["cards"][0]["evidence"] == ["a0"]
    editor.verify_cards(review["cards"], source, review)
    editor.verify_analysis_files(tmp_path, review)
    cache = tmp_path / "analysis" / f"{editor.VERSION}-classify.json"
    assert read_json(cache)["output"] is None
    cache.write_bytes(cache.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="바뀌었다"):
        editor.verify_analysis_files(tmp_path, review)
    with pytest.raises(ValueError, match="바뀌었다"):
        editor.build(*args)
    assert len(calls) == 4


def test_invalid_classification_without_valid_authored_cards_stays_held(tmp_path):
    source = corpus()
    calls = []
    ctx = context(calls, [], classify=lambda _: "bad JSON")
    for _ in range(2):
        with pytest.raises(ValueError, match="G6"):
            editor.build(ctx, "synthetic", packet(source), source, {}, tmp_path, None)
    assert [phase for phase, _ in calls] == ["classify", "author"]
    review = read_json(tmp_path / "evidence-review.json")
    assert review["status"] == "HELD" and review["cards"] == [editor.FACTS_GUARD_CARD]


REPAIRED_LIMIT = "같은 조건의 다른 질문 유형까지 넓히지 않는다."
EMPTY_LIMIT = {"limit": "비어 있다. 반드시 한 문장으로 쓴다"}


def test_empty_limits_get_one_repair_with_the_same_evidence_then_the_same_checks(tmp_path):
    source = corpus()
    missing = authored("REPEATED", ["a1", "a2"], first="가능한 선택지부터 비교한다.")
    del missing["limit"]
    cards = [
        authored("LOCAL", ["a0"], limit=""),  # Repaired, then approved.
        missing,  # A missing field counts as empty. Repaired, then held by the judge.
        authored("LOCAL", ["a2"], first="상대가 고른 기준부터 밝힌다.", limit=""),
        authored("LOCAL", ["a0"], first="", limit=""),  # No core reaction: not repairable.
        authored("LOCAL", ["eval-id"], limit=""),  # Evidence outside the sample.
        authored("LOCAL", ["a1"], first="질문의 전제를 먼저 짚는다."),
    ]

    def repair(payload):
        assert [(c["id"], c["fix"]) for c in payload["cards"]] == [
            (card_id, EMPTY_LIMIT) for card_id in ("card-01", "card-02", "card-03")
        ]
        assert payload["cards"][1]["card"] == dict(missing, limit="")
        return {
            "cards": [
                dict(id="card-01", limit=REPAIRED_LIMIT),
                dict(id="card-02", limit="다른 관계의 질문에는 적용하지 않는다."),
                dict(id="card-03", limit=""),  # Still empty: held, never a second call.
            ]
        }

    calls = []
    ctx = context(calls, cards, repair=repair)
    args = (ctx, "synthetic", packet(source), source, {}, tmp_path, None)
    text, assembly = editor.build(*args)
    assert [p for p, _ in calls] == ["classify", "author", "repair", "judge"]
    judged = {c["id"]: c["card"] for c in json.loads(calls[3][1].messages[-1].content)["cards"]}
    assert list(judged) == ["card-01", "card-02", "card-06"]
    assert judged["card-01"] == dict(cards[0], limit=REPAIRED_LIMIT, rule=cards[0]["first"])
    assert (judged["card-02"]["scope"], judged["card-02"]["evidence"]) == ("REPEATED", ["a1", "a2"])
    review = read_json(tmp_path / "evidence-review.json")
    assert review["instructions"] == editor.instruction_record(editor.INSTRUCTIONS)
    assert read_json(tmp_path / editor.INSTRUCTION_ARTIFACT) == review["instructions"]
    assert review["formatRepair"] == dict(
        maxCalls=1,
        status="DONE",
        cards=[
            dict(id="card-01", fields=["limit"], outcome="CANDIDATE_FOR_G6"),
            dict(id="card-02", fields=["limit"], outcome="JUDGE_HELD"),
            dict(id="card-03", fields=["limit"], outcome="FORMAT_HELD"),
        ],
        notRepairable=["card-04", "card-05"],
    )
    assert read_json(tmp_path / editor.DECISION_ARTIFACT)["formatRepair"] == review["formatRepair"]
    held = {h["id"]: h["reason"] for h in review["held"]}
    assert held["card-02"] == "수선 뒤 심사 보류: 일반화가 어렵다."
    assert held["card-03"].startswith("형식 보류 · 수선 1회 뒤에도 검사를 통과하지 못했다: limit")
    assert held["card-04"].startswith("형식 보류 · 수선 대상 아님")
    assert held["card-05"].startswith("형식 보류 · 수선 대상 아님")
    assert [c["evidence"] for c in review["cards"] if c["scope"] == "LOCAL"] == [["a0"], ["a1"]]
    assert REPAIRED_LIMIT in text
    editor.verify_cards(review["cards"], source, review)
    editor.verify_analysis_files(tmp_path, review)
    assert editor.build(*args) == (text, assembly) and len(calls) == 4

    changed = dict(review["formatRepair"], notRepairable=[])
    with pytest.raises(ValueError, match="형식 수선"):
        editor.verify_analysis_files(tmp_path, dict(review, formatRepair=changed))
    # A candidate may differ from the authored card only in the repaired fields.
    decisions_path = tmp_path / editor.DECISION_ARTIFACT
    decisions = read_json(decisions_path)
    decisions["candidates"][0]["card"]["section"] = "VOICE"
    decisions_path.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
    hashes = dict(
        review["analysisArtifacts"], **{editor.DECISION_ARTIFACT: sha256_file(decisions_path)}
    )
    with pytest.raises(ValueError, match="수선한 칸 밖"):
        editor.verify_analysis_files(tmp_path, dict(review, analysisArtifacts=hashes))


def test_invalid_repair_response_is_recorded_once_and_keeps_cards_held(tmp_path):
    source = corpus()
    cards = [
        authored("LOCAL", ["a0"], limit=""),
        authored("LOCAL", ["a1"], first="질문의 전제를 먼저 짚는다."),
    ]
    calls = []
    # Evidence is outside the requested fields, so the whole response is rejected.
    widened = {"cards": [dict(id="card-01", limit=REPAIRED_LIMIT, evidence=["a0", "a3"])]}
    ctx = context(calls, cards, repair=lambda _: widened)
    args = (ctx, "synthetic", packet(source), source, {}, tmp_path, None)
    built = editor.build(*args)
    assert editor.build(*args) == built
    assert [p for p, _ in calls] == ["classify", "author", "repair", "judge"]
    review = read_json(tmp_path / "evidence-review.json")
    assert review["formatRepair"]["status"] == "UNAVAILABLE"
    assert review["formatRepair"]["cards"] == [
        dict(id="card-01", fields=["limit"], outcome="UNAVAILABLE")
    ]
    held = {h["id"]: h["reason"] for h in review["held"]}
    assert held["card-01"] == (
        "형식 보류 · 수선 응답을 검증할 수 없어 고치지 못했다: limit: 비어 있거나 범위 밖 문장이다"
    )
    assert read_json(tmp_path / "analysis" / f"{editor.VERSION}-repair.json")["output"] is None
    assert [c["evidence"] for c in review["cards"] if c["scope"] == "LOCAL"] == [["a1"]]
    editor.verify_cards(review["cards"], source, review)
    editor.verify_analysis_files(tmp_path, review)


def test_build_started_before_instruction_revisions_resumes_on_the_legacy_text(tmp_path):
    source = corpus()
    calls = []
    cards = [
        authored("LOCAL", ["a0"], limit=""),
        authored("LOCAL", ["a1"], first="질문의 전제를 먼저 짚는다."),
    ]
    made = []

    def text_model(*_):
        made.append(1)
        if len(made) == 2:
            raise RuntimeError("공급자 연결이 끊겼다")
        return FakeModel("text", calls, cards)

    ctx = SimpleNamespace(text_model=text_model, judge_model=context(calls, cards).judge_model)
    args = (ctx, "synthetic", packet(source), source, {}, tmp_path, None)
    with pytest.raises(RuntimeError):
        editor.build(*args)
    # Folders written by the earlier code have phase records but no instruction record.
    (tmp_path / editor.INSTRUCTION_ARTIFACT).unlink()
    editor.build(*args)
    assert [p for p, _ in calls] == ["classify", "author", "judge"]
    legacy = editor.LEGACY_INSTRUCTIONS
    assert calls[1][1].messages[0].content == editor.instructions("author", legacy)
    assert calls[2][1].messages[0].content == editor.instructions("judge", legacy)
    review = read_json(tmp_path / "evidence-review.json")
    assert "instructions" not in review and "formatRepair" not in review
    assert "formatRepair" not in read_json(tmp_path / editor.DECISION_ARTIFACT)
    assert not (tmp_path / editor.INSTRUCTION_ARTIFACT).exists()
    held = {h["id"]: h["reason"] for h in review["held"]}
    assert held["card-01"] == "limit: 비어 있거나 범위 밖 문장이다"  # Unchanged wording.
    editor.verify_cards(review["cards"], source, review)
    editor.verify_analysis_files(tmp_path, review)
    with pytest.raises(ValueError, match="지시문 기록 없이"):
        editor.verify_analysis_files(tmp_path, dict(review, formatRepair={}))


def test_instruction_file_edited_after_the_build_started_is_rejected(tmp_path, monkeypatch):
    source = corpus()
    calls = []
    ctx = context(calls, [authored("LOCAL", ["a0"])])
    args = (ctx, "synthetic", packet(source), source, {}, tmp_path, None)
    editor.build(*args)
    review = read_json(tmp_path / "evidence-review.json")
    current = editor._resource
    monkeypatch.setattr(
        editor,
        "_resource",
        lambda revision: current(revision) + ("\n" if revision == editor.INSTRUCTIONS else ""),
    )
    with pytest.raises(ValueError, match="지시문"):
        editor.verify_analysis_files(tmp_path, review)
    with pytest.raises(ValueError, match="지시문"):
        editor.build(*args)
    assert [p for p, _ in calls] == ["classify", "author", "judge"]
