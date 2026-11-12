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
from character_factory_poc.common.canonical import (
    canonical_bytes,
    sha256_file,
    sha256_of,
    sha256_text,
)
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.providers.base import ChatRequest, Message
from character_factory_poc.stages.s8_prompts.evidence_compiler import (
    FACTS_GUARD_CARD,
    FACTS_GUARD_SCOPE,
    SECTIONS,
    _text,
    compile_prompt,
)
from character_factory_poc.stages.s8_prompts.evidence_source import _UNSAFE, validate_card

VERSION = "interview-editor-v2"
REVIEW_SCHEMA = "interview-editor-review-v2"
# Instruction text revisions. VERSION stays the packet and compiler format, and its
# resource file is hash-bound by approved bindings, so it is never edited. New builds
# use INSTRUCTIONS (limit made explicitly required, plus one bounded format repair).
# Builds started before revisions were recorded resume on LEGACY_INSTRUCTIONS.
LEGACY_INSTRUCTIONS = VERSION
INSTRUCTIONS = "interview-editor-v3"
INSTRUCTION_REVISIONS = (LEGACY_INSTRUCTIONS, INSTRUCTIONS)
INSTRUCTION_ARTIFACT = "analysis/interview-instructions.json"
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
# Current sampling: several pairs from each chosen text source, so the same question
# situation can be compared across independent sources (REPEATED evidence).
# v2 also merges text sources that repost or re-edit the same interview into one source
# group, and adds the compiler-owned facts guard card to new reviews.
CLUSTER_V1 = "source-cluster-v1"
SAMPLING_VERSION = "source-cluster-v2"
SAMPLING_VERSIONS = (None, CLUSTER_V1, SAMPLING_VERSION)
MAX_AUTHOR_RECORDS = 120
PAIRS_PER_SOURCE = 4
MIN_CLUSTER_PAIRS = 3  # Sources with at least this many pairs are chosen first.
# Near-duplicate answers: character 4-grams of the normalized answer. Two answers from
# different text sources match when they share enough 4-grams in absolute terms and as a
# share of the shorter answer, so stock greetings alone never merge two sources.
SHINGLE = 4
REPOST_MIN_SHARED = 12
REPOST_MIN_CONTAINMENT = 0.6
# Reviews saved before SAMPLING_VERSION used one round-robin pass of at most 55 pairs.
LEGACY_AUTHOR_RECORDS = 55
MAX_CARDS = 18
MAX_PRIORITY = 8
MAX_AUTHOR_REFS = 6
MIN_GROUP_COUNT = 5
MIN_GROUP_SOURCES = 3
SHORT_CHARS = 80  # Audit threshold, never a runtime character budget.
QUESTION_BODY_CAP = 48_000
AUTHOR_RECORD_CAP = 50_000
AUTHOR_CARD_CAP = 900
EDITOR_BODY_CAP = 80_000  # Records, up to MAX_CARDS candidates and the repost groups.
LABEL_SLOT = max(LABELS, key=len)  # Reserve the longest label while sizing author records.
PROSE_BOUNDS = {"trigger": 100, "first": 145, "shift": 80, "stop": 80, "limit": 120}
OPTIONAL_PROSE = ("shift", "stop")
AUTHOR_KEYS = {"section", "scope", "evidence", *PROSE_BOUNDS}
_UNGROUNDED_METRICS = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:[%％]|글자|자(?![가-힣])|문장|줄(?![가-힣])|토큰|단어|턴)"
)
# Questions about factual content are answered from FACTS, never governed by a card.
_FACT_TRIGGER = re.compile(r"수치|숫자|통계|데이터|기록|날짜|연도|이름|명칭|성적|경력|이력")
FACTS_GUARD_ID = "facts-guard"
FACTS_GUARD_REASON = "사실표의 값을 그대로 보존하는 고정 규칙이다."
PHASES = {
    "classify": ("질문만 분류", 4096),
    "author": ("인터뷰 관찰 카드 추출", 10000),
    # At most one call, only for authored cards held by a field-format check.
    "repair": ("형식 보류 카드의 빠진 칸 수선(최대 1회)", 6000),
    "judge": ("독립 근거 심사", 4096),
}
LEGACY_PHASES = ("classify", "author", "judge")
# Phases whose invalid response is recorded once instead of failing the build.
TOLERANT_PHASES = ("classify", "repair")
QUESTION_ARTIFACT = "evidence-interview-questions.json"
DECISION_ARTIFACT = "evidence-interview-decisions.json"
CLASSIFICATION_FAILURE = "invalid_structured_response"
FORMAT_HOLD = "형식 보류"


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


def _sample(rows, maximum, body_cap, project, *, priority=(), seen=None):
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
    active, chosen = deque(queues), []
    seen = set() if seen is None else seen
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


def _question(row, wire_id=None):
    return {"id": row["id"] if wire_id is None else wire_id, "question": row["question"]}


def _question_keys(count):
    return [f"q{i}" for i in range(1, count + 1)]


def _identity(row):
    return row


def _author_record(row, label=None, group=None):
    record = dict(
        id=row["id"],
        unit=row["unit"],
        questionType=label,
        question=row["question"],
        answer=row["answer"],
    )
    if group is not None:
        record["sourceGroup"] = group
    return record


def _pair_identity(row):
    return (_compact(row["question"]), _compact(row["answer"]))


def _shingles(text):
    compact = _compact(text)
    return frozenset(compact[i : i + SHINGLE] for i in range(len(compact) - SHINGLE + 1))


def _near_duplicate(a, b):
    common = len(a & b)
    return common >= REPOST_MIN_SHARED and common >= REPOST_MIN_CONTAINMENT * min(len(a), len(b))


def _repost_groups(rows):
    """Text sources linked by a near-duplicate answer are one interview (repost or re-edit).

    Returns only groups with two or more text IDs, each sorted, in sorted order.
    """
    parent = {}

    def find(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    shingled = [
        (row["unit"][0], shingles)
        for row in rows
        if len(shingles := _shingles(row["answer"])) >= REPOST_MIN_SHARED
    ]
    for i, (left, a) in enumerate(shingled):
        for right, b in shingled[i + 1 :]:
            if left != right and find(left) != find(right) and _near_duplicate(a, b):
                parent[find(left)] = find(right)
    members = defaultdict(set)
    for key in list(parent):
        members[find(key)].add(key)
    return sorted(sorted(group) for group in members.values() if len(group) > 1)


def _group_of(groups):
    """Map each merged text ID to its group ID, the smallest member. Others map to self."""
    return {text_id: group[0] for group in groups for text_id in group}


def _cluster_sample(rows, priority, groups=None):
    """Pick whole source clusters: up to PAIRS_PER_SOURCE distinct pairs per source.

    Sources holding a priority pair come first, then sources with enough pairs to show
    more than one question situation, each group in hash order. Deterministic.
    With repost groups (v2) a source is a repost group and near-duplicate answers inside
    it are skipped; without them (v1) a source is a text ID.
    """
    group_of = _group_of(groups) if groups is not None else None

    def source_key(row):
        text_id = row["unit"][0]
        return text_id if group_of is None else group_of.get(text_id, text_id)

    buckets = defaultdict(list)
    for row in rows:
        buckets[source_key(row)].append(row)
    priority = set(priority)
    distinct = {key: len({_pair_identity(r) for r in bucket}) for key, bucket in buckets.items()}
    order = sorted(
        buckets,
        key=lambda key: (
            not any(r["id"] in priority for r in buckets[key]),
            distinct[key] < MIN_CLUSTER_PAIRS,
            sha256_of(key),
        ),
    )
    chosen, seen, remaining = [], set(), AUTHOR_RECORD_CAP
    for key in order:
        taken, kept = 0, []
        for row in sorted(
            buckets[key], key=lambda r: (r["id"] not in priority, sha256_of(r["id"]))
        ):
            if len(chosen) >= MAX_AUTHOR_RECORDS:
                return chosen
            if taken >= PAIRS_PER_SOURCE and row["id"] not in priority:
                break
            identity = _pair_identity(row)
            wire = _author_record(row, LABEL_SLOT, None if group_of is None else key)
            size = len(canonical_bytes(wire).decode("utf-8")) + 1
            if identity in seen or size > remaining:
                continue
            if group_of is not None:
                shingles = _shingles(row["answer"])
                if any(_near_duplicate(shingles, other) for other in kept):
                    continue
                kept.append(shingles)
            chosen.append(row)
            seen.add(identity)
            remaining -= size
            taken += 1
    return chosen


def _question_sample(rows, author):
    """Classify every author pair first, then fill the question sample round robin."""
    project = lambda row: _question(row, f"q{MAX_QUESTIONS}")  # noqa: E731
    remaining = QUESTION_BODY_CAP - 100
    chosen, seen = [], set()
    for row in author:
        size = len(canonical_bytes(project(row)).decode("utf-8")) + 1
        if len(chosen) < MAX_QUESTIONS and size <= remaining:
            chosen.append(row)
            seen.add(_pair_identity(row))
            remaining -= size
    taken = {row["id"] for row in chosen}
    rest = [row for row in rows if row["id"] not in taken]
    return chosen + _sample(rest, MAX_QUESTIONS - len(chosen), remaining, project, seen=seen)


def _samples(source, binding, *, legacy_questions=False, version=SAMPLING_VERSION):
    if not source.get("coverage", {}).get("complete"):
        raise ValueError("인터뷰 원문 범위가 미완료다")
    if version not in SAMPLING_VERSIONS:
        raise ValueError("인터뷰 표본 방식의 버전이 다르다")
    rows = _eligible(source)
    priority = binding.get("interviewPriorityIds", [])
    if not isinstance(priority, list) or not all(isinstance(rid, str) for rid in priority):
        raise ValueError("인터뷰 우선 근거 ID 형식이 다르다")
    eligible_ids = {row["id"] for row in rows}
    priority = list(dict.fromkeys(rid for rid in priority if rid in eligible_ids))[:MAX_PRIORITY]
    groups = None
    if version is None:
        # Reproduce reviews saved before SAMPLING_VERSION exactly.
        # Reserve the longest wire ID while sampling. Old reviews used source IDs for this cap.
        project = _question if legacy_questions else lambda row: _question(row, f"q{MAX_QUESTIONS}")
        questions = _sample(rows, MAX_QUESTIONS, QUESTION_BODY_CAP - 100, project)
        author = _sample(
            rows, LEGACY_AUTHOR_RECORDS, AUTHOR_RECORD_CAP, _identity, priority=priority
        )
    else:
        groups = _repost_groups(rows) if version == SAMPLING_VERSION else None
        author = _cluster_sample(rows, priority, groups)
        questions = _question_sample(rows, author)
    sampling = dict(
        eligiblePairCount=len(rows),
        questionIds=[row["id"] for row in questions],
        authorIds=[row["id"] for row in author],
        priorityIds=[row["id"] for row in author if row["id"] in priority],
        sourceIdentity="textId",
    )
    if version is not None:
        group_of = _group_of(groups or [])
        sampling.update(
            version=version,
            pairsPerSource=PAIRS_PER_SOURCE,
            authorSourceCount=len({group_of.get(row["unit"][0], row["unit"][0]) for row in author}),
        )
    if groups is not None:
        sampling.update(sourceIdentity="repostGroup", repostGroups=groups)
    return questions, author, sampling


def _sampled_groups(sampling):
    """Repost group map for v2 reviews, None for earlier sampling versions."""
    if sampling.get("version") != SAMPLING_VERSION:
        return None
    return _group_of(sampling["repostGroups"])


def _author_records(author_rows, questions, labels, group_of=None):
    """Wire records grouped by question type, then by source, so situations line up."""
    by_id = {row["id"]: label for row, label in zip(questions, labels, strict=True)}

    def source_key(row):
        text_id = row["unit"][0]
        return None if group_of is None else group_of.get(text_id, text_id)

    sources = list(dict.fromkeys(source_key(row) or row["unit"][0] for row in author_rows))

    def key(item):
        position, row = item
        label = by_id.get(row["id"])
        group = LABELS.index(label) if label is not None else len(LABELS)
        return group, sources.index(source_key(row) or row["unit"][0]), position

    return [
        _author_record(row, by_id.get(row["id"]), source_key(row))
        for _, row in sorted(enumerate(author_rows), key=key)
    ]


def plan_calls(source) -> list[CallPlan]:
    """Upper bound; no judge is needed when no admissible authored cards survive."""
    count = int(bool(_eligible(source))) if source.get("coverage", {}).get("complete") else 0
    return [CallPlan("s8", description, count, None) for description, _ in PHASES.values()]


def _labels(out, count):
    if isinstance(out, dict) and set(out) == {"labels"}:
        labels = out["labels"]
        if isinstance(labels, dict):
            keys = _question_keys(count)
            if set(labels) <= set(keys) and all(
                label is None or label in LABELS for label in labels.values()
            ):
                return [labels.get(key) for key in keys]
        # Accept the original fake/positional response only when it is complete.
        if (
            isinstance(labels, list)
            and len(labels) == count
            and all(label in LABELS for label in labels)
        ):
            return labels
    raise ValueError("질문 분류 응답의 ID, 개수 또는 분류값이 다르다")


def _classification_audit(ids, labels, *, invalid=False):
    unobserved = [rid for rid, label in zip(ids, labels, strict=True) if label is None]
    if invalid:
        if not ids or unobserved != ids:
            raise ValueError("검증할 수 없는 분류 응답에 관측 라벨이 있다")
        status, reason = "UNAVAILABLE", CLASSIFICATION_FAILURE
    elif unobserved:
        status, reason = "PARTIAL", "missing_or_uncertain_labels"
    else:
        status, reason = ("COMPLETE" if ids else "NOT_NEEDED"), None
    return dict(
        status=status,
        reason=reason,
        observedCount=len(ids) - len(unobserved),
        unobservedIds=unobserved,
    )


def _measure(rows, labels):
    evidence = []
    groups = {label: [] for label in LABELS}
    complete = None not in labels
    for row, label in zip(rows, labels, strict=True):
        if label is None:
            continue
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
            measurable=complete
            and label != "기타"
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


def _check_card(
    card, by_id, speech, *, measured=False, group_of=None, facts_guard=False, unchecked=()
):
    """group_of and facts_guard apply to v2 reviews only, so older reviews still verify.

    unchecked only serves the repair probe: it names prose fields already known to fail,
    so the remaining checks can show whether rewriting those fields alone could pass.
    """
    if not isinstance(card, dict) or set(card) != AUTHOR_KEYS | {"rule"}:
        raise ValueError("인터뷰 카드 구조가 다르다")
    scopes = ("MEASURED",) if measured else AUTHOR_SCOPES
    if card["section"] not in SECTIONS[1:] or card["scope"] not in scopes:
        raise ValueError("허용하지 않는 카드 섹션이나 근거 범위다")
    for field, limit in PROSE_BOUNDS.items():
        if field not in unchecked:
            _check_prose(card[field], field, limit, optional=field in OPTIONAL_PROSE)
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
        if facts_guard and _FACT_TRIGGER.search(card["trigger"]):
            raise ValueError("사실을 묻는 질문의 답하는 방식은 카드로 정하지 않고 사실표로 답한다")
    if scope == "LOCAL" and len(refs) != 1:
        raise ValueError("LOCAL 카드는 하나의 장면 근거만 인용한다")
    if scope == "REPEATED":
        pairs = {(_compact(by_id[ref]["context"]), _compact(by_id[ref]["target"])) for ref in refs}
        texts = {by_id[ref]["unit"][0] for ref in refs}
        sources = texts if group_of is None else {group_of.get(t, t) for t in texts}
        if len(sources) < 2 or len(pairs) != len(refs):
            raise ValueError("REPEATED 카드는 재전재를 제외한 서로 다른 출처가 필요하다")
    validate_card(card, [by_id[ref] for ref in refs], min_units=1, extra_speech=speech)


def _field_problem(value, field):
    """A plain-language problem when this one authored field fails its own shape checks."""
    if not isinstance(value, str):
        return "문자열이 아니다. 한 문장으로 쓴다"
    if value == "":
        return None if field in OPTIONAL_PROSE else "비어 있다. 반드시 한 문장으로 쓴다"
    try:
        _check_prose(value, field, PROSE_BOUNDS[field])
    except ValueError:
        if len(value) > PROSE_BOUNDS[field]:
            return "너무 길다. 뜻을 유지하며 한 문장으로 줄인다"
        if value != value.strip() or any(not ch.isprintable() for ch in value):
            return "앞뒤 공백, 줄바꿈이나 제어 문자를 뺀다"
        if _UNSAFE.search(value):
            return "주소나 연락처처럼 보이는 표현을 뺀다"
        return "대사, 예시나 섹션 제목처럼 보이는 표현을 뺀다"
    if _UNGROUNDED_METRICS.search(value):
        return "측정하지 않은 수치를 빼고 길이는 짧게나 길게처럼 상대적으로 쓴다"
    return None


def _merge(raw, fixes=None):
    """Authored card with missing prose fields as empty text and only the repaired fields."""
    card = {field: "" for field in PROSE_BOUNDS} | raw | (fixes or {})
    return dict(card, rule=card["first"])


def _repair_plan(raw, by_id, speech, *, group_of, facts_guard):
    """Fields to rewrite when only field formats keep the card out, else None.

    Section, scope and evidence are never repairable, and an empty trigger or first is new
    authoring rather than a repair. Every other check must already pass with the failing
    fields set aside, so rewriting them alone cannot widen the card or its evidence.
    """
    if not isinstance(raw, dict) or set(raw) - AUTHOR_KEYS:
        return None
    if (AUTHOR_KEYS - set(raw)) - set(PROSE_BOUNDS):
        return None
    card = _merge(raw)
    problems = {f: p for f in PROSE_BOUNDS if (p := _field_problem(card[f], f))}
    if not problems or any(
        field in problems and (not isinstance(card[field], str) or not card[field])
        for field in ("trigger", "first")
    ):
        return None
    probe = _merge(raw, {field: "" for field in problems})
    try:
        _check_card(
            probe,
            by_id,
            speech,
            group_of=group_of,
            facts_guard=facts_guard,
            unchecked=set(problems),
        )
    except ValueError:
        return None
    return problems


def _repair_output(out, requested):
    """Exactly the requested fields of a subset of the requested cards, as text."""
    if (
        not isinstance(out, dict)
        or set(out) != {"cards"}
        or not isinstance(out["cards"], list)
        or len(out["cards"]) > len(requested)
    ):
        raise ValueError("형식 수선 응답의 형식이나 개수가 다르다")
    fixes = {}
    for item in out["cards"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or item["id"] not in requested
            or item["id"] in fixes
            or set(item) != {"id", *requested[item["id"]]}
            or any(not isinstance(item[field], str) for field in requested[item["id"]])
        ):
            raise ValueError("형식 수선 응답의 카드 ID나 필드가 다르다")
        fixes[item["id"]] = {field: item[field] for field in requested[item["id"]]}
    return fixes


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
    if card["scope"] == FACTS_GUARD_SCOPE:
        claim = "facts_literal"
    else:
        claim = "bounded_self_report" if reported else "expression_only"
    return dict(
        id=card_id,
        cardSha256=sha256_of(card),
        decision="CANDIDATE_FOR_G6",
        reason=reason,
        claimScope=claim,
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


def _response_failed(saved):
    """True when a tolerant phase committed its one invalid response without output."""
    if "failure" not in saved:
        return False
    if saved["failure"] != CLASSIFICATION_FAILURE or saved["output"] is not None:
        raise ValueError("저장된 인터뷰 분석 실패 기록이 다르다")
    return True


def _block(text, name):
    return text.split(f"<!-- {name} -->", 1)[1].split("<!-- end -->", 1)[0].strip()


def _resource(revision):
    if revision not in INSTRUCTION_REVISIONS:
        raise ValueError("알 수 없는 인터뷰 지시문 버전이다")
    return files("character_factory_poc.resources").joinpath(revision + ".md").read_text("utf-8")


def instruction_record(revision=INSTRUCTIONS):
    """Revision and digest of the whole instruction file a build used."""
    return dict(revision=revision, sha256=sha256_text(_resource(revision)))


def instructions(phase, revision=INSTRUCTIONS):
    """System text for one phase. Author and judge share one scope definition block."""
    text = _resource(revision)
    system = _block(text, phase)
    include = "<!-- include scopes -->"
    if include in system:
        system = system.replace(include, _block(text, "scopes"))
    return system


def _instruction_revision(folder):
    """New builds use INSTRUCTIONS; builds started before revisions were recorded resume
    on the legacy text, so their cached requests keep matching. Writes nothing."""
    marker = folder / INSTRUCTION_ARTIFACT
    if marker.exists():
        saved = read_json(marker)
        if not isinstance(saved, dict) or saved != instruction_record(saved.get("revision")):
            raise ValueError("인터뷰 지시문이 이 revision을 시작할 때와 다르다")
        return saved["revision"]
    started = (folder / "evidence-review.json").exists() or any(
        path.exists() for phase in PHASES for path in _phase_paths(folder, phase)
    )
    if started:
        return LEGACY_INSTRUCTIONS
    return INSTRUCTIONS


def _call(ctx, cid, folder, budget, phase, payload, input_hash, validator, revision):
    cache, receipt, attempt = _phase_paths(folder, phase)
    system = instructions(phase, revision)
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
        if phase not in TOLERANT_PHASES or not _response_failed(saved):
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
    outcome = dict(requestSha256=digest, model=response.model)
    try:
        if response.finish_reason not in (None, "stop", "STOP") or len(response.text) > 32_000:
            raise ValueError("응답이 중간에 끝났거나 상한을 넘었다")
        out = json.loads(response.text, object_pairs_hook=_unique_keys)
        # Reject invalid Unicode before caching it in a local UTF-8 file.
        canonical_bytes(out)
        validator(out)
    except (ValueError, RecursionError) as exc:
        if phase not in TOLERANT_PHASES:
            write_once_json(
                attempt.parent / f"{VERSION}-{phase}-failure.json",
                dict(requestSha256=digest, reason="invalid structured response"),
            )
            raise ValueError(f"인터뷰 {phase} 단계의 구조화 응답을 검증할 수 없다") from exc
        # Commit the failed attempt without storing the response or calling again.
        out = None
        outcome["failure"] = CLASSIFICATION_FAILURE
    write_once_json(cache, dict(outcome, output=out))
    write_once_json(receipt, dict(cacheSha256=sha256_file(cache)))
    return out, response.model


def _saved_call(folder, phase, models):
    cache, receipt, attempt = _phase_paths(folder, phase)
    saved = read_json(cache)
    if (
        saved.get("model") != models[phase]
        or read_json(attempt) != {"requestSha256": saved.get("requestSha256")}
        or read_json(receipt) != {"cacheSha256": sha256_file(cache)}
    ):
        raise ValueError(f"저장된 인터뷰 {phase} 호출 기록이 다르다")
    return saved


def _verify_repair(folder, review, models):
    """Repaired candidates differ from the authored card only in the requested fields."""
    record = review.get("formatRepair")
    decisions = read_json(folder / DECISION_ARTIFACT)
    entries = record.get("cards") if isinstance(record, dict) else None
    if (
        not isinstance(decisions, dict)
        or decisions.get("formatRepair") != record
        or not isinstance(entries, list)
        or record.get("maxCalls") != 1
        or not isinstance(record.get("notRepairable"), list)
        or bool(entries) != ("repair" in models)
        or any(
            not isinstance(e, dict)
            or not isinstance(e.get("id"), str)
            or not re.fullmatch(r"card-(?:0[1-9]|1[0-8])", e["id"])
            or not isinstance(e.get("fields"), list)
            or not e["fields"]
            or not set(e["fields"]) <= set(PROSE_BOUNDS)
            for e in entries
        )
        or len({e["id"] for e in entries}) != len(entries)
    ):
        raise ValueError("형식 수선 기록이 다르다")
    authored = []
    if "author" in models:
        authored = _author_output(_saved_call(folder, "author", models)["output"])["cards"]
    fixes, failed = {}, False
    if entries:
        saved = _saved_call(folder, "repair", models)
        failed = _response_failed(saved)
        if not failed:
            fixes = _repair_output(saved["output"], {e["id"]: e["fields"] for e in entries})
    if record.get("status") != ("UNAVAILABLE" if failed else "DONE" if entries else "NOT_NEEDED"):
        raise ValueError("형식 수선 상태가 기록과 다르다")
    candidates = decisions.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("인터뷰 후보 기록이 다르다")
    requested = {e["id"] for e in entries}
    for candidate in candidates:
        card_id = candidate.get("id") if isinstance(candidate, dict) else None
        index = int(card_id[5:]) - 1 if re.fullmatch(r"card-\d\d", str(card_id)) else -1
        if not 0 <= index < len(authored) or not isinstance(authored[index], dict):
            raise ValueError("인터뷰 후보가 작성 기록에 없다")
        if card_id in requested and card_id not in fixes:
            raise ValueError("수선하지 않은 형식 보류 카드가 후보에 있다")
        if candidate.get("card") != _merge(authored[index], fixes.get(card_id)):
            raise ValueError("후보 카드가 작성 기록이나 수선한 칸 밖에서 바뀌었다")


def verify_analysis_files(folder, review):
    """Verify bounded artifacts without expecting an exhaustive source audit."""
    folder = Path(folder)
    if review.get("schemaVersion") != REVIEW_SCHEMA:
        raise ValueError("인터뷰 검토 버전이 다르다")
    expected = {QUESTION_ARTIFACT, DECISION_ARTIFACT}
    models = review.get("models")
    if not isinstance(models, dict) or not set(models) <= set(PHASES):
        raise ValueError("인터뷰 분석 모델 기록이 다르다")
    revised = "instructions" in review
    if revised:
        expected.add(INSTRUCTION_ARTIFACT)
    elif "repair" in models or "formatRepair" in review:
        raise ValueError("지시문 기록 없이 형식 수선 기록이 있다")
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
    if revised:
        record = review["instructions"]
        if (
            not isinstance(record, dict)
            or record.get("revision") != INSTRUCTIONS
            or record != instruction_record(INSTRUCTIONS)
            or read_json(folder / INSTRUCTION_ARTIFACT) != record
        ):
            raise ValueError("인터뷰 지시문 기록이 현재 지시문과 다르다")
        _verify_repair(folder, review, models)
    question_artifact = read_json(folder / QUESTION_ARTIFACT)
    if not isinstance(question_artifact, dict):
        raise ValueError("저장된 인터뷰 질문 근거 형식이 다르다")
    if "questionClassification" not in review:
        if "classification" in question_artifact:
            raise ValueError("인터뷰 분류 검토 기록이 빠졌다")
        return  # The original review and question artifact recorded only complete labels.

    sampling = review.get("sampling")
    ids = sampling.get("questionIds") if isinstance(sampling, dict) else None
    if (
        not isinstance(ids, list)
        or len(ids) > MAX_QUESTIONS
        or any(not isinstance(rid, str) for rid in ids)
        or len(ids) != len(set(ids))
        or bool(ids) != ("classify" in models)
    ):
        raise ValueError("저장된 인터뷰 질문 표본이 다르다")
    labels, invalid = [], False
    if ids:
        saved = _saved_call(folder, "classify", models)
        invalid = _response_failed(saved)
        labels = [None] * len(ids) if invalid else _labels(saved["output"], len(ids))
    audit = _classification_audit(ids, labels, invalid=invalid)
    evidence = review.get("questionEvidence")
    if (
        review["questionClassification"] != audit
        or question_artifact.get("classification") != audit
        or question_artifact.get("sampling") != sampling
        or question_artifact.get("evidence") != evidence
        or question_artifact.get("stats") != review.get("questionStats")
        or not isinstance(evidence, list)
        or any(not isinstance(pair, dict) for pair in evidence)
        or [(pair.get("id"), pair.get("questionType")) for pair in evidence]
        != [(rid, label) for rid, label in zip(ids, labels, strict=True) if label is not None]
    ):
        raise ValueError("저장된 인터뷰 분류나 검토 기록이 다르다")


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
    legacy = "questionClassification" not in review
    saved_sampling = review.get("sampling")
    if not isinstance(saved_sampling, dict):
        raise ValueError("인터뷰 표본이 변경됐다")
    # Reviews without a sampling version were saved by the original round-robin sampler.
    questions, _, sampling = _samples(
        source,
        review["binding"],
        legacy_questions=legacy,
        version=saved_sampling.get("version"),
    )
    if saved_sampling != sampling:
        raise ValueError("인터뷰 표본이 변경됐다")
    question_evidence = review.get("questionEvidence")
    if not isinstance(question_evidence, list) or any(
        not isinstance(pair, dict)
        or not isinstance(pair.get("id"), str)
        or pair.get("questionType") not in LABELS
        for pair in question_evidence
    ):
        raise ValueError("인터뷰 질문 근거가 다르다")
    if legacy:
        labels = _labels(
            {"labels": [pair["questionType"] for pair in question_evidence]}, len(questions)
        )
    else:
        by_question = {pair["id"]: pair["questionType"] for pair in question_evidence}
        ids = sampling["questionIds"]
        labels = [by_question.get(rid) for rid in ids]
        audit = review["questionClassification"]
        if not isinstance(audit, dict) or audit != _classification_audit(
            ids, labels, invalid=audit.get("status") == "UNAVAILABLE"
        ):
            raise ValueError("인터뷰 질문 분류의 관측 범위가 다르다")
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
    group_of = _sampled_groups(sampling)
    guarded = group_of is not None
    # v2 reviews end with exactly one compiler-owned facts guard; earlier reviews have none.
    guards = [card for card in cards if card.get("scope") == FACTS_GUARD_SCOPE]
    if guards != ([FACTS_GUARD_CARD] if guarded else []) or (guarded and cards[-1] != guards[0]):
        raise ValueError("사실표 보존 카드가 검토 방식과 다르다")
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
        elif card.get("scope") == FACTS_GUARD_SCOPE:
            if card_id != FACTS_GUARD_ID or reason != FACTS_GUARD_REASON:
                raise ValueError("사실표 보존 카드 ID가 다르다")
        else:
            if not re.fullmatch(r"card-(?:0[1-9]|1[0-8])", card_id):
                raise ValueError("독립 검토 카드 ID가 다르다")
            _check_card(card, by_id, speech, group_of=group_of, facts_guard=guarded)
        if card_id in seen or entry != _report_entry(card_id, card, reason):
            raise ValueError("카드별 검토 범위가 바뀌었다")
        seen.add(card_id)


def _format_hold(raw, exc, revision):
    """G6 reason. New builds label field-format holds that the repair could not take."""
    if revision != INSTRUCTIONS or not isinstance(raw, dict):
        return str(exc), False
    card = _merge({k: v for k, v in raw.items() if k in AUTHOR_KEYS})
    if any(_field_problem(card[field], field) for field in PROSE_BOUNDS):
        reason = f"{FORMAT_HOLD} · 수선 대상 아님(핵심 칸이 비었거나 다른 검사도 걸렸다): {exc}"
        return reason, True
    return str(exc), False


def _distinct(card, seen):
    key = _compact(card["first"])
    if key in seen:
        raise ValueError("이미 후보로 남긴 반응과 중복된다")
    seen.add(key)


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
    revision = _instruction_revision(folder)
    revised = revision == INSTRUCTIONS
    phases = PHASES if revised else LEGACY_PHASES
    if budget is not None and questions:
        remaining = sum(not _phase_paths(folder, phase)[1].exists() for phase in phases)
        budget.check_plan([CallPlan("s8", "인터뷰 편집의 남은 최대 호출 수", remaining, None)])
    write_once_json(folder / "evidence-binding.json", binding)
    if revised:
        write_once_json(folder / INSTRUCTION_ARTIFACT, instruction_record(INSTRUCTIONS))
    # Facts and free-form revision notes stay local. The scene is not evidence.
    scene = packet["scene"]
    context = {"scene": scene} if len(scene) <= 600 and not _UNSAFE.search(scene) else {}
    input_hash = sha256_of(dict(binding=binding, packet=packet, rework=rework))
    models, held, unresolved, candidates, decisions = {}, [], [], [], {}
    labels, invalid = [], False
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
            {
                "questions": [
                    _question(row, key)
                    for row, key in zip(questions, _question_keys(len(questions)), strict=True)
                ]
            },
            input_hash,
            lambda out: _labels(out, len(questions)),
            revision,
        )
        invalid = classification is None
        labels = [None] * len(questions) if invalid else _labels(classification, len(questions))
    audit = _classification_audit(sampling["questionIds"], labels, invalid=invalid)
    if audit["unobservedIds"]:
        reason = "질문 분류 응답을 검증할 수 없었다." if invalid else "일부 질문에 분류값이 없었다."
        held.append(
            _hold(
                "question-classification",
                f"{reason} {len(questions)}개 중 {audit['observedCount']}개의 분류만 확인해 "
                "답변 분량 규칙은 보류했다.",
            )
        )
    evidence, stats, measured = _measures(source, questions, labels, speech, held)
    group_of = _sampled_groups(sampling)
    guarded = group_of is not None
    # Machine labels only group the records; cards are still checked against raw pairs.
    records = _author_records(author_rows, questions, labels, group_of)
    if guarded:
        # Name the merged reposts explicitly so neither model counts them twice.
        sampled = {row["unit"][0] for row in author_rows}
        context = dict(
            context,
            repostGroups=[g for g in sampling["repostGroups"] if sampled.intersection(g)],
        )
    format_repair = dict(maxCalls=1, status="NOT_NEEDED", cards=[], notRepairable=[])
    repaired_ids = {}
    if author_rows:
        extracted, models["author"] = _call(
            ctx,
            cid,
            folder,
            budget,
            "author",
            dict(context, records=records),
            input_hash,
            _author_output,
            revision,
        )
        unresolved = [
            reason for item in extracted["unresolved"] if (reason := _prose_or_blank(item))
        ]
        passed, plans, distinct = {}, {}, set()
        for i, raw in enumerate(extracted["cards"], 1):
            card_id = f"card-{i:02}"
            try:
                if not isinstance(raw, dict) or set(raw) != AUTHOR_KEYS:
                    raise ValueError("인터뷰 카드 필드가 다르다")
                card = dict(raw, rule=raw["first"])
                _check_card(card, by_id, speech, group_of=group_of, facts_guard=guarded)
                _distinct(card, distinct)
            except ValueError as exc:
                problems = revised and _repair_plan(
                    raw, by_id, speech, group_of=group_of, facts_guard=guarded
                )
                if problems:
                    plans[card_id] = (raw, problems, str(exc))
                    continue
                reason, formal = _format_hold(raw, exc, revision)
                if formal:
                    format_repair["notRepairable"].append(card_id)
                held.append(_hold(card_id, reason, raw, by_id))
            else:
                passed[card_id] = card
        if plans:
            # One call, same evidence: only the failing fields of the held cards are rewritten.
            requested = {card_id: list(problems) for card_id, (_, problems, _) in plans.items()}
            cited = {ref for raw, _, _ in plans.values() for ref in raw["evidence"]}
            repaired, models["repair"] = _call(
                ctx,
                cid,
                folder,
                budget,
                "repair",
                dict(
                    context,
                    records=[record for record in records if record["id"] in cited],
                    cards=[
                        dict(
                            id=card_id,
                            card={k: v for k, v in _merge(raw).items() if k != "rule"},
                            fix=problems,
                        )
                        for card_id, (raw, problems, _) in plans.items()
                    ],
                ),
                input_hash,
                lambda out: _repair_output(out, requested),
                revision,
            )
            fixes = {} if repaired is None else _repair_output(repaired, requested)
            format_repair["status"] = "UNAVAILABLE" if repaired is None else "DONE"
            for card_id, (raw, _, error) in plans.items():
                entry = dict(id=card_id, fields=requested[card_id])
                format_repair["cards"].append(entry)
                if repaired is None:
                    entry["outcome"] = "UNAVAILABLE"
                    reason = f"{FORMAT_HOLD} · 수선 응답을 검증할 수 없어 고치지 못했다: {error}"
                    held.append(_hold(card_id, reason, raw, by_id))
                    continue
                if card_id not in fixes:
                    entry["outcome"] = "NOT_RETURNED"
                    reason = f"{FORMAT_HOLD} · 수선 응답이 이 카드를 고치지 않았다: {error}"
                    held.append(_hold(card_id, reason, raw, by_id))
                    continue
                card = _merge(raw, fixes[card_id])
                try:
                    _check_card(card, by_id, speech, group_of=group_of, facts_guard=guarded)
                    _distinct(card, distinct)
                except ValueError as exc:
                    entry["outcome"] = "FORMAT_HELD"
                    reason = f"{FORMAT_HOLD} · 수선 1회 뒤에도 검사를 통과하지 못했다: {exc}"
                    held.append(_hold(card_id, reason, card, by_id))
                else:
                    passed[card_id] = card
                    repaired_ids[card_id] = entry
        candidates = [dict(id=card_id, card=passed[card_id]) for card_id in sorted(passed)]
    if candidates:
        expected_ids = {candidate["id"] for candidate in candidates}
        judged, models["judge"] = _call(
            ctx,
            cid,
            folder,
            budget,
            "judge",
            dict(context, records=records, cards=candidates),
            input_hash,
            lambda out: _judge_output(out, expected_ids),
            revision,
        )
        decisions = _judge_output(judged, expected_ids)
    cards, reports = [], []
    for candidate in candidates:
        card_id, card = candidate["id"], candidate["card"]
        decision = decisions[card_id]
        entry = repaired_ids.get(card_id)
        if decision["decision"] == "HOLD":
            reason = decision["reason"]
            if entry is not None:
                entry["outcome"] = "JUDGE_HELD"
                reason = "수선 뒤 심사 보류: " + reason
            held.append(_hold(card_id, reason, card, by_id))
        else:
            if entry is not None:
                entry["outcome"] = "CANDIDATE_FOR_G6"
            cards.append(card)
            reports.append(_report_entry(card_id, card, decision["reason"]))
    for card_id, card in measured:
        cards.append(card)
        reports.append(_report_entry(card_id, card, "문답 표본의 분량 측정 기준을 충족했다."))
    reviewable = bool(cards)
    if guarded:
        cards.append(dict(FACTS_GUARD_CARD, evidence=[]))
        reports.append(_report_entry(FACTS_GUARD_ID, cards[-1], FACTS_GUARD_REASON))

    packet = packet | {"sections": cards}
    text = compile_prompt(packet)
    write_once_json(folder / "evidence-packet.json", packet)
    question_path = folder / QUESTION_ARTIFACT
    write_once_json(
        question_path,
        dict(
            sampling=sampling,
            classification=audit,
            evidence=evidence,
            stats=stats,
            support=dict(
                minPairs=MIN_GROUP_COUNT, minSources=MIN_GROUP_SOURCES, shortChars=SHORT_CHARS
            ),
        ),
    )
    decisions_path = folder / DECISION_ARTIFACT
    decision_record = dict(
        candidates=candidates,
        judgeDecisions=list(decisions.values()),
        cardDecisions=reports,
        held=held,
        unresolved=unresolved,
        reworkSha256=sha256_of(rework) if rework is not None else None,
    )
    if revised:
        decision_record["formatRepair"] = format_repair
    write_once_json(decisions_path, decision_record)
    files = [question_path, decisions_path]
    if revised:
        files.append(folder / INSTRUCTION_ARTIFACT)
    for phase in models:
        files.extend(_phase_paths(folder, phase))
    review = dict(
        schemaVersion=REVIEW_SCHEMA,
        status="AWAITING_HUMAN" if reviewable else "HELD",
        records=source["records"],
        cards=cards,
        held=held,
        unresolved=unresolved,
        stats=source["stats"],
        sampling=sampling,
        questionClassification=audit,
        questionEvidence=evidence,
        questionStats=stats,
        cardDecisions=reports,
        binding=binding,
        packetSha256=sha256_file(folder / "evidence-packet.json"),
        responseModel=models.get("author", "none"),
        models=models,
        analysisArtifacts={p.relative_to(folder).as_posix(): sha256_file(p) for p in files},
    )
    if revised:
        review.update(instructions=instruction_record(INSTRUCTIONS), formatRepair=format_repair)
    write_once_json(review_path, review)
    if not reviewable:
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
