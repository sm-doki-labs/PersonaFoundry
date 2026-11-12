"""Bounded interview editing. Machine retention is only a candidate for G6."""

from __future__ import annotations

import fcntl
import json
import re
from collections import defaultdict, deque
from importlib.resources import files
from pathlib import Path
from statistics import median

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import canonical_bytes, sha256_file, sha256_of
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.providers.base import ChatRequest, Message
from character_factory_poc.stages.s8_prompts.evidence_compiler import (
    SECTIONS,
    _text,
    compile_prompt,
)
from character_factory_poc.stages.s8_prompts.evidence_source import _UNSAFE, validate_card

VERSION = "interview-editor-v2"
REVIEW_SCHEMA = "interview-editor-review-v2"
LABELS = ("확인", "단순선택", "이유과정", "소감평가", "사실회상", "조건정정", "기타")
AUTHOR_SCOPES = ("LOCAL", "REPEATED", "REPORTED")
TRIGGERS = (
    "전제나 가능 여부를 확인하는 질문을 받으면",
    "이유 없이 대상 하나만 골라 달라는 질문을 받으면",
    "이유나 판단 과정을 묻는 질문을 받으면",
    "소감이나 평가를 묻는 질문을 받으면",
    "이미 확인된 경험의 구체적인 내용을 묻는 질문을 받으면",
    "새 조건을 주거나 앞선 말의 범위를 좁혀 달라는 질문을 받으면",
)
MAX_QUESTIONS = 180
MAX_AUTHOR_RECORDS = 55
MAX_CARDS = 18
MAX_PRIORITY = 8
MAX_AUTHOR_REFS = 6
MIN_GROUP_COUNT = 5
MIN_GROUP_SOURCES = 3
SHORT_CHARS = 80  # Audit threshold, never a runtime character budget.
QUESTION_BODY_CAP = 48_000
AUTHOR_RECORD_CAP = 50_000
AUTHOR_CARD_CAP = 900
EDITOR_BODY_CAP = 70_000
PROSE_BOUNDS = {"trigger": 100, "first": 145, "shift": 80, "stop": 80, "limit": 120}
AUTHOR_KEYS = {"section", "scope", "evidence", *PROSE_BOUNDS}
_UNGROUNDED_METRICS = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:[%％]|글자|자(?![가-힣])|문장|줄(?![가-힣])|토큰|단어|턴)"
)
PHASES = {
    "classify": ("질문만 분류", 4096),
    "author": ("인터뷰 관찰 카드 추출", 10000),
    "judge": ("독립 근거 심사", 4096),
}
QUESTION_ARTIFACT = "evidence-interview-questions.json"
DECISION_ARTIFACT = "evidence-interview-decisions.json"


def _compact(text):
    return re.sub(r"[\W_]+", "", text.casefold())


def _eligible(source):
    """Use the immediate USER turn on the same side of every source barrier."""
    excluded = set(source["holdoutIds"]) | {item["id"] for item in source["coverage"]["excluded"]}
    eligible = []
    for record in source["records"]:
        rid, question, answer = record["id"], record["context"], record["target"]
        history = record["history"]
        if (
            rid not in excluded
            and history
            and history[-1] == {"speaker": "USER", "text": question}
            and 3 <= len(question) <= 460
            and 1 <= len(answer) <= 2000
            and not (_UNSAFE.search(question) or _UNSAFE.search(answer))
            and _compact(question)
            and _compact(answer)
        ):
            eligible.append(dict(id=rid, unit=record["unit"], question=question, answer=answer))
    return eligible


def _sample(rows, maximum, body_cap, project, *, priority=()):
    """Round robin across text sources; never count exact reposts as new pairs."""
    buckets = defaultdict(list)
    for row in rows:
        buckets[row["unit"][0]].append(row)
    priority = set(priority)
    queues = [
        deque(sorted(buckets[key], key=lambda r: (r["id"] not in priority, sha256_of(r["id"]))))
        for key in sorted(
            buckets,
            key=lambda key: (not any(r["id"] in priority for r in buckets[key]), sha256_of(key)),
        )
    ]
    active, chosen, seen = deque(queues), [], set()
    remaining = body_cap
    while active and len(chosen) < maximum:
        queue = active.popleft()
        while queue:
            row = queue.popleft()
            identity = (_compact(row["question"]), _compact(row["answer"]))
            size = len(canonical_bytes(project(row)).decode("utf-8")) + 1
            if identity not in seen and size <= remaining:
                chosen.append(row)
                seen.add(identity)
                remaining -= size
                break
        if queue:
            active.append(queue)
    return chosen


def _question(row):
    return {"id": row["id"], "question": row["question"]}


def _identity(row):
    return row


def _samples(source, binding):
    if not source.get("coverage", {}).get("complete"):
        raise ValueError("인터뷰 원문 범위가 미완료다")
    rows = _eligible(source)
    priority = binding.get("interviewPriorityIds", [])
    if not isinstance(priority, list) or not all(isinstance(rid, str) for rid in priority):
        raise ValueError("인터뷰 우선 근거 ID 형식이 다르다")
    eligible_ids = {row["id"] for row in rows}
    priority = list(dict.fromkeys(rid for rid in priority if rid in eligible_ids))[:MAX_PRIORITY]
    questions = _sample(rows, MAX_QUESTIONS, QUESTION_BODY_CAP - 100, _question)
    author = _sample(rows, MAX_AUTHOR_RECORDS, AUTHOR_RECORD_CAP, _identity, priority=priority)
    sampling = dict(
        eligiblePairCount=len(rows),
        questionIds=[row["id"] for row in questions],
        authorIds=[row["id"] for row in author],
        priorityIds=[row["id"] for row in author if row["id"] in priority],
        sourceIdentity="textId",
    )
    return questions, author, sampling


def plan_calls(source) -> list[CallPlan]:
    """Upper bound; no judge is needed when no admissible authored cards survive."""
    count = int(bool(_eligible(source))) if source.get("coverage", {}).get("complete") else 0
    return [CallPlan("s8", description, count, None) for description, _ in PHASES.values()]


def _labels(out, rows):
    if (
        not isinstance(out, dict)
        or set(out) != {"labels"}
        or not isinstance(out["labels"], list)
        or len(out["labels"]) != len(rows)
        or any(label not in LABELS for label in out["labels"])
    ):
        raise ValueError("질문 분류 응답의 개수나 분류값이 다르다")
    return out["labels"]


def _measure(rows, labels):
    evidence = []
    groups = {label: [] for label in LABELS}
    for row, label in zip(rows, labels, strict=True):
        pair = dict(
            id=row["id"],
            questionType=label,
            textId=row["unit"][0],
            convId=row["unit"][1],
            answerChars=len(row["answer"]),
        )
        groups[label].append(pair)
        evidence.append(pair)
    stats = {}
    for label, group in groups.items():
        sizes = [pair["answerChars"] for pair in group]
        source_count = len({pair["textId"] for pair in group})
        stats[label] = dict(
            count=len(sizes),
            sourceCount=source_count,
            medianChars=median(sizes) if sizes else None,
            atMost80Count=sum(size <= SHORT_CHARS for size in sizes),
            measurable=label != "기타"
            and len(sizes) >= MIN_GROUP_COUNT
            and source_count >= MIN_GROUP_SOURCES,
        )
    return evidence, stats


def _measured_cards(evidence, stats):
    for i, (label, trigger) in enumerate(zip(LABELS[:-1], TRIGGERS, strict=True), 1):
        group = stats[label]
        if not group["measurable"]:
            continue
        if group["medianChars"] <= SHORT_CHARS:
            first = "묻는 핵심 위주로 짧게 답한다."
            stop = "요청받은 내용을 답했으면 차례를 넘긴다."
            limit = "추가로 설명을 요청하면 짧게 끝내려 하지 않는다."
        else:
            first = "질문이 요구한 판단 근거나 세부가 빠지지 않게 설명한다."
            stop = "요청받은 설명이 끝나면 차례를 넘긴다."
            limit = "필요하지 않은 부연이나 확인되지 않은 경험은 덧붙이지 않는다."
        refs = [pair["id"] for pair in evidence if pair["questionType"] == label]
        card = dict(
            section="VOICE",
            scope="MEASURED",
            trigger=trigger,
            first=first,
            shift="",
            stop=stop,
            limit=limit,
            rule=first,
            evidence=refs,
        )
        yield f"measure-{i:02}", card


def _all_speech(source):
    # Chunk overlap and repeated merged turns must not inflate validation work.
    return tuple(
        dict.fromkeys(
            turn["text"]
            for chunk in source["chunks"]
            for segment in chunk["segments"]
            for turn in segment["turns"]
        )
    )


def _check_prose(value, key, limit, *, optional=False):
    if value == "" and optional:
        return
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > limit
        or any(not ch.isprintable() for ch in value)
        or _UNSAFE.search(value)
    ):
        raise ValueError(f"{key}: 비어 있거나 범위 밖 문장이다")
    _text(value, key)


def _check_card(card, by_id, speech, *, measured=False):
    if not isinstance(card, dict) or set(card) != AUTHOR_KEYS | {"rule"}:
        raise ValueError("인터뷰 카드 구조가 다르다")
    scopes = ("MEASURED",) if measured else AUTHOR_SCOPES
    if card["section"] not in SECTIONS[1:] or card["scope"] not in scopes:
        raise ValueError("허용하지 않는 카드 섹션이나 근거 범위다")
    for field, limit in PROSE_BOUNDS.items():
        _check_prose(card[field], field, limit, optional=field in ("shift", "stop"))
    if card["rule"] != card["first"]:
        raise ValueError("규칙은 검토한 첫 반응과 같아야 한다")
    refs = card["evidence"]
    if (
        not isinstance(refs, list)
        or not refs
        or len(refs) > (MAX_QUESTIONS if measured else MAX_AUTHOR_REFS)
        or any(not isinstance(ref, str) or ref not in by_id for ref in refs)
        or len(set(refs)) != len(refs)
    ):
        raise ValueError("카드가 허용된 문답 표본 밖의 근거를 인용했다")
    scope = card["scope"]
    if not measured:
        if len(canonical_bytes(card).decode("utf-8")) > AUTHOR_CARD_CAP:
            raise ValueError("저작 카드 전송 상한을 넘었다")
        if any(_UNGROUNDED_METRICS.search(card[field]) for field in PROSE_BOUNDS):
            raise ValueError("저작 카드에 측정하지 않은 수치 규칙이 있다")
    if scope == "LOCAL" and len(refs) != 1:
        raise ValueError("LOCAL 카드는 하나의 장면 근거만 인용한다")
    if scope == "REPEATED":
        pairs = {(_compact(by_id[ref]["context"]), _compact(by_id[ref]["target"])) for ref in refs}
        if len({by_id[ref]["unit"][0] for ref in refs}) < 2 or len(pairs) != len(refs):
            raise ValueError("REPEATED 카드는 재전재를 제외한 서로 다른 출처가 필요하다")
    validate_card(card, [by_id[ref] for ref in refs], min_units=1, extra_speech=speech)


def _author_output(out):
    if (
        not isinstance(out, dict)
        or set(out) != {"cards", "unresolved"}
        or not isinstance(out["cards"], list)
        or len(out["cards"]) > MAX_CARDS
        or not isinstance(out["unresolved"], list)
        or len(out["unresolved"]) > len(SECTIONS) - 1
    ):
        raise ValueError("인터뷰 카드 추출 응답의 형식이나 개수가 다르다")
    return out


def _judge_output(out, expected_ids):
    if (
        not isinstance(out, dict)
        or set(out) != {"decisions"}
        or not isinstance(out["decisions"], list)
        or len(out["decisions"]) != len(expected_ids)
    ):
        raise ValueError("독립 심사 결과의 형식이나 개수가 다르다")
    decisions = {}
    for item in out["decisions"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "decision", "reason"}
            or not isinstance(item["id"], str)
            or item["id"] not in expected_ids
            or item["id"] in decisions
            or item["decision"] not in ("APPROVE", "HOLD")
        ):
            raise ValueError("독립 심사 결과의 후보 ID나 판정값이 다르다")
        _check_prose(item["reason"], "reason", 240)
        decisions[item["id"]] = item
    return decisions


def _prose_or_blank(value):
    try:
        _check_prose(value, "검토 메모", 240)
    except ValueError:
        return ""
    return value


def _hold(card_id, reason, raw=None, sampled=None):
    claim = {}
    if isinstance(raw, dict):
        refs = raw.get("evidence")
        if isinstance(refs, list):
            claim["evidence"] = [
                ref for ref in refs[:MAX_AUTHOR_REFS] if isinstance(ref, str) and ref in sampled
            ]
        for src, dst in (("first", "rule"), ("trigger", "trigger"), ("limit", "exclusion")):
            if prose := _prose_or_blank(raw.get(src)):
                claim[dst] = prose
    return dict(id=card_id, reason=reason, claim=claim)


def _report_entry(card_id, card, reason):
    reported = card["scope"] == "REPORTED"
    return dict(
        id=card_id,
        cardSha256=sha256_of(card),
        decision="CANDIDATE_FOR_G6",
        reason=reason,
        claimScope="bounded_self_report" if reported else "expression_only",
        allowedPersonalClaim=card["first"] if reported else "",
        experienceLimit=card["limit"],
    )


def _phase_paths(folder, phase):
    base = folder / "analysis"
    name = f"{VERSION}-{phase}.json"
    return base / name, base / "receipts" / name, base / "attempts" / name


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("인터뷰 분석 JSON에 중복 필드가 있다")
        result[key] = value
    return result


def _call(ctx, cid, folder, budget, phase, payload, input_hash, validator):
    cache, receipt, attempt = _phase_paths(folder, phase)
    all_instructions = files("character_factory_poc.resources").joinpath(VERSION + ".md")
    phase_instructions = all_instructions.read_text("utf-8").split(f"<!-- {phase} -->", 1)[1]
    system = phase_instructions.split("<!-- end -->", 1)[0].strip()
    body = canonical_bytes({"phase": phase, **payload}).decode("utf-8")
    is_judge = phase == "judge"
    kind = "JUDGE" if is_judge else "AGENT"
    cap = QUESTION_BODY_CAP if phase == "classify" else EDITOR_BODY_CAP
    if len(body) > cap:
        raise ValueError("인터뷰 분석 전송 상한을 넘었다")
    tokens = PHASES[phase][1]
    digest = sha256_of(
        dict(
            version=VERSION,
            phase=phase,
            system=system,
            body=body,
            inputSha256=input_hash,
            kind=kind,
            maxOutputTokens=tokens,
        )
    )
    if cache.exists() and receipt.exists():
        saved = read_json(cache)
        if saved.get("requestSha256") != digest or read_json(receipt) != {
            "cacheSha256": sha256_file(cache)
        }:
            raise ValueError("저장된 인터뷰 분석의 무결성이나 원천이 다르다")
        validator(saved["output"])
        return saved["output"], saved["model"]
    if cache.exists() or receipt.exists() or attempt.exists():
        raise ValueError("인터뷰 단계의 호출 상한을 이미 썼다. 새 revision이 필요하다")
    provider = ctx.judge_model(cid, budget) if is_judge else ctx.text_model(cid, budget)
    write_once_json(attempt, dict(requestSha256=digest))
    response = provider.complete(
        ChatRequest(
            kind=kind,
            stage="s8",
            ref=f"{cid}/{folder.name}/{VERSION}/{phase}",
            max_output_tokens=tokens,
            temperature=0.0,
            response_json=True,
            messages=(Message("system", system), Message("user", body)),
        )
    )
    try:
        if response.finish_reason not in (None, "stop", "STOP") or len(response.text) > 32_000:
            raise ValueError("응답이 중간에 끝났거나 상한을 넘었다")
        out = json.loads(response.text, object_pairs_hook=_unique_keys)
        # Reject invalid Unicode before caching it in a local UTF-8 file.
        canonical_bytes(out)
        validator(out)
    except (ValueError, RecursionError) as exc:
        write_once_json(
            attempt.parent / f"{VERSION}-{phase}-failure.json",
            dict(requestSha256=digest, reason="invalid structured response"),
        )
        raise ValueError(f"인터뷰 {phase} 단계의 구조화 응답을 검증할 수 없다") from exc
    write_once_json(cache, dict(requestSha256=digest, output=out, model=response.model))
    write_once_json(receipt, dict(cacheSha256=sha256_file(cache)))
    return out, response.model


def verify_analysis_files(folder, review):
    """Verify bounded artifacts without expecting an exhaustive source audit."""
    folder = Path(folder)
    if review.get("schemaVersion") != REVIEW_SCHEMA:
        raise ValueError("인터뷰 검토 버전이 다르다")
    expected = {QUESTION_ARTIFACT, DECISION_ARTIFACT}
    models = review.get("models")
    if not isinstance(models, dict) or not set(models) <= set(PHASES):
        raise ValueError("인터뷰 분석 모델 기록이 다르다")
    for phase in models:
        expected.update(p.relative_to(folder).as_posix() for p in _phase_paths(folder, phase))
    artifacts = review.get("analysisArtifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != expected:
        raise ValueError("인터뷰 분석 기록이 빠졌거나 형식이 다르다")
    for ref, digest in artifacts.items():
        path = (folder / ref).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file():
            raise ValueError("인터뷰 분석 기록 경로가 다르다")
        if sha256_file(path) != digest:
            raise ValueError("인터뷰 분석 기록이 바뀌었다")


def _measures(source, questions, labels, speech, held):
    by_id = {r["id"]: r for r in source["records"]}
    evidence, stats = _measure(questions, labels)
    measured = []
    for card_id, card in _measured_cards(evidence, stats):
        try:
            _check_card(card, by_id, speech, measured=True)
        except ValueError as exc:
            held.append(_hold(card_id, str(exc)))
        else:
            measured.append((card_id, card))
    return evidence, stats, measured


def verify_cards(cards, source, review):
    """Recompute support, scope and measured guidance from current eligible source."""
    if (
        not isinstance(review, dict)
        or review.get("schemaVersion") != REVIEW_SCHEMA
        or review.get("cards") != cards
        or not isinstance(review.get("binding"), dict)
        or not isinstance(cards, list)
        or any(not isinstance(card, dict) for card in cards)
    ):
        raise ValueError("인터뷰 검토 카드가 다르다")
    questions, _, sampling = _samples(source, review["binding"])
    if review.get("sampling") != sampling:
        raise ValueError("인터뷰 표본이 변경됐다")
    question_evidence = review.get("questionEvidence")
    if not isinstance(question_evidence, list) or any(
        not isinstance(pair, dict) for pair in question_evidence
    ):
        raise ValueError("인터뷰 질문 근거가 다르다")
    labels = _labels(
        {"labels": [pair.get("questionType") for pair in question_evidence]}, questions
    )
    speech = _all_speech(source)
    evidence, stats, measured = _measures(source, questions, labels, speech, [])
    if question_evidence != evidence or review.get("questionStats") != stats:
        raise ValueError("인터뷰 질문 분류나 통계가 원천과 다르다")
    if [card for card in cards if card.get("scope") == "MEASURED"] != [
        card for _, card in measured
    ]:
        raise ValueError("측정 카드가 검토된 질문 통계와 다르다")
    author_ids = set(sampling["authorIds"])
    by_id = {r["id"]: r for r in source["records"] if r["id"] in author_ids}
    entries = review.get("cardDecisions")
    if not isinstance(entries, list) or len(entries) != len(cards):
        raise ValueError("카드별 독립 검토 기록이 다르다")
    seen = set()
    measured_ids = {sha256_of(card): card_id for card_id, card in measured}
    for card, entry in zip(cards, entries, strict=True):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError("카드별 독립 검토 ID가 다르다")
        card_id, reason = entry["id"], entry.get("reason")
        _check_prose(reason, "reason", 240)
        if card.get("scope") == "MEASURED":
            if measured_ids.get(sha256_of(card)) != card_id:
                raise ValueError("측정 근거 ID가 다르다")
        else:
            if not re.fullmatch(r"card-(?:0[1-9]|1[0-8])", card_id):
                raise ValueError("독립 검토 카드 ID가 다르다")
            _check_card(card, by_id, speech)
        if card_id in seen or entry != _report_entry(card_id, card, reason):
            raise ValueError("카드별 검토 범위가 바뀌었다")
        seen.add(card_id)


def _build(ctx, cid, packet, source, binding, folder, budget, rework):
    if (
        packet.get("formatVersion") != VERSION
        or packet.get("sections") != []
        or packet.get("trainIds") != [r["id"] for r in source["records"]]
        or packet.get("holdoutIds") != source["holdoutIds"]
    ):
        raise ValueError("인터뷰 입력 패킷이 승인 원문과 다르다")
    compile_prompt(packet)
    questions, author_rows, sampling = _samples(source, binding)
    review_path = folder / "evidence-review.json"
    if review_path.exists():
        verify_analysis_files(folder, read_json(review_path))
    if budget is not None and questions:
        remaining = sum(not _phase_paths(folder, phase)[1].exists() for phase in PHASES)
        budget.check_plan([CallPlan("s8", "인터뷰 편집의 남은 최대 호출 수", remaining, None)])
    write_once_json(folder / "evidence-binding.json", binding)
    # Facts and free-form revision notes stay local. The scene is not evidence.
    scene = packet["scene"]
    context = {"scene": scene} if len(scene) <= 600 and not _UNSAFE.search(scene) else {}
    input_hash = sha256_of(dict(binding=binding, packet=packet, rework=rework))
    models, held, unresolved, candidates, decisions = {}, [], [], [], {}
    labels = []
    speech = _all_speech(source)
    all_records = {r["id"]: r for r in source["records"]}
    by_id = {r["id"]: all_records[r["id"]] for r in author_rows}
    if questions:
        classification, models["classify"] = _call(
            ctx,
            cid,
            folder,
            budget,
            "classify",
            {"questions": [_question(r) for r in questions]},
            input_hash,
            lambda out: _labels(out, questions),
        )
        labels = _labels(classification, questions)
    evidence, stats, measured = _measures(source, questions, labels, speech, held)
    if author_rows:
        extracted, models["author"] = _call(
            ctx,
            cid,
            folder,
            budget,
            "author",
            dict(context, records=author_rows),
            input_hash,
            _author_output,
        )
        unresolved = [
            reason for item in extracted["unresolved"] if (reason := _prose_or_blank(item))
        ]
        distinct = set()
        for i, raw in enumerate(extracted["cards"], 1):
            card_id = f"card-{i:02}"
            try:
                if not isinstance(raw, dict) or set(raw) != AUTHOR_KEYS:
                    raise ValueError("인터뷰 카드 필드가 다르다")
                card = dict(raw, rule=raw["first"])
                _check_card(card, by_id, speech)
                key = _compact(card["first"])
                if key in distinct:
                    raise ValueError("이미 후보로 남긴 반응과 중복된다")
                distinct.add(key)
            except ValueError as exc:
                held.append(_hold(card_id, str(exc), raw, by_id))
            else:
                candidates.append(dict(id=card_id, card=card))
    if candidates:
        expected_ids = {candidate["id"] for candidate in candidates}
        judged, models["judge"] = _call(
            ctx,
            cid,
            folder,
            budget,
            "judge",
            dict(context, records=author_rows, cards=candidates),
            input_hash,
            lambda out: _judge_output(out, expected_ids),
        )
        decisions = _judge_output(judged, expected_ids)
    cards, reports = [], []
    for candidate in candidates:
        card_id, card = candidate["id"], candidate["card"]
        decision = decisions[card_id]
        if decision["decision"] == "HOLD":
            held.append(_hold(card_id, decision["reason"], card, by_id))
        else:
            cards.append(card)
            reports.append(_report_entry(card_id, card, decision["reason"]))
    for card_id, card in measured:
        cards.append(card)
        reports.append(_report_entry(card_id, card, "문답 표본의 분량 측정 기준을 충족했다."))

    packet = packet | {"sections": cards}
    text = compile_prompt(packet)
    write_once_json(folder / "evidence-packet.json", packet)
    question_path = folder / QUESTION_ARTIFACT
    write_once_json(
        question_path,
        dict(
            sampling=sampling,
            evidence=evidence,
            stats=stats,
            support=dict(
                minPairs=MIN_GROUP_COUNT, minSources=MIN_GROUP_SOURCES, shortChars=SHORT_CHARS
            ),
        ),
    )
    decisions_path = folder / DECISION_ARTIFACT
    write_once_json(
        decisions_path,
        dict(
            candidates=candidates,
            judgeDecisions=list(decisions.values()),
            cardDecisions=reports,
            held=held,
            unresolved=unresolved,
            reworkSha256=sha256_of(rework) if rework is not None else None,
        ),
    )
    files = [question_path, decisions_path]
    for phase in models:
        files.extend(_phase_paths(folder, phase))
    review = dict(
        schemaVersion=REVIEW_SCHEMA,
        status="AWAITING_HUMAN" if cards else "HELD",
        records=source["records"],
        cards=cards,
        held=held,
        unresolved=unresolved,
        stats=source["stats"],
        sampling=sampling,
        questionEvidence=evidence,
        questionStats=stats,
        cardDecisions=reports,
        binding=binding,
        packetSha256=sha256_file(folder / "evidence-packet.json"),
        responseModel=models.get("author", "none"),
        models=models,
        analysisArtifacts={p.relative_to(folder).as_posix(): sha256_file(p) for p in files},
    )
    write_once_json(review_path, review)
    if not cards:
        raise ValueError("G6에서 검토할 인터뷰 근거 후보가 없다")
    return text, dict(
        compiler=VERSION,
        responseModel=review["responseModel"],
        status=review["status"],
        evidenceReviewSha256=sha256_file(review_path),
    )


def build(ctx, cid, packet, source, binding, folder, budget, rework=None):
    """Create a bounded, private authoring record and an unapproved prompt."""
    folder = Path(folder)
    analysis = folder / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    with (analysis / f".{VERSION}.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _build(ctx, cid, packet, source, binding, folder, budget, rework)
