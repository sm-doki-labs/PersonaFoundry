"""Decide the S8 text standard from the shape of the approved source, not the scene.

The scene (chapterTemplate) keeps driving dialogue scenes and video direction. Only the text
standard asks: does the subject mostly answer one question at a time (interview), or trade
short bubbles in an ongoing chat (conversation)?

Texts are pooled by declared kind. Each pool is judged from its turn structure when that is
clear, from its declared kind when the structure is in between, and left out when it is too
small to judge. Mixed sources follow the side with more subject characters. When nothing can
be judged the caller falls back to the chapterTemplate rule.

Only counts are read from the corpus. Holdout text is never opened.
"""

from __future__ import annotations

import json
from pathlib import Path

VERSION = "source-shape-v1"
INTERVIEW = "interview"
CONVERSATION = "conversation"
NAMES = {INTERVIEW: "인터뷰형", CONVERSATION: "대화형"}

# Declared kinds and what they suggest when the structure itself is in between.
KIND_PRIOR = {"INTERVIEW": INTERVIEW, "TRANSCRIPT": INTERVIEW, "KAKAO_EXPORT": CONVERSATION}
# A pool needs this much subject speech before its structure counts.
MIN_SUBJECT_TURNS = 10
MIN_SUBJECT_CHARS = 200
# Interview: nearly every subject message answers the other side, and answers are long.
INTERVIEW_QA = 0.8
INTERVIEW_TURN_CHARS = 30
# Conversation: the subject often sends several bubbles in a row, or turns are short.
CONVERSATION_QA = 0.6
CONVERSATION_TURN_CHARS = 20


def _ratio(part, whole):
    return round(part / whole, 3) if whole else 0.0


def _percent(value):
    return round(value * 100)


def _structure(qa, turn_chars):
    if qa >= INTERVIEW_QA and turn_chars >= INTERVIEW_TURN_CHARS:
        return INTERVIEW
    if qa < CONVERSATION_QA or turn_chars < CONVERSATION_TURN_CHARS:
        return CONVERSATION
    return None


def _pool(kind, texts, rows):
    """Count turn structure for one declared kind. rows keep corpus order."""
    msgs = chars = turns = answered = answered_chars = 0
    others = set()
    prev = None
    for row in rows:
        if row["speaker"] == "SUBJECT":
            size = len(row["text"])
            msgs += 1
            chars += size
            same = prev is not None and prev["convId"] == row["convId"]
            if not (same and prev["speaker"] == "SUBJECT"):
                turns += 1
            if same and prev["speaker"] == "USER":
                answered += 1
                answered_chars += size
        else:
            others.add((row["speaker"], row.get("name", "")))
        prev = row
    qa = _ratio(answered, msgs)
    turn_chars = round(chars / turns, 1) if turns else 0.0
    out = dict(
        kind=kind,
        texts=len(texts),
        subjectMessages=msgs,
        subjectTurns=turns,
        subjectChars=chars,
        answeredMessages=answered,
        qaRatio=qa,
        qaCharRatio=_ratio(answered_chars, chars),
        charsPerTurn=turn_chars,
        bubblesPerTurn=round(msgs / turns, 2) if turns else 0.0,
        otherSpeakers=len(others),
    )
    prior = KIND_PRIOR.get(kind)
    if prior is None:
        return out | dict(shape=None, basis="excluded", reason="기사 인용은 말차례가 없어 뺀다")
    if turns < MIN_SUBJECT_TURNS or chars < MIN_SUBJECT_CHARS:
        return out | dict(shape=None, basis="excluded", reason="대상 발화가 적어 판정에서 뺀다")
    found = _structure(qa, turn_chars)
    if found is None:
        return out | dict(
            shape=prior, basis="kind", reason="말차례 구조가 중간이라 원문 종류를 따른다"
        )
    reason = (
        "질문 뒤 긴 답이 대부분이다"
        if found == INTERVIEW
        else "말풍선을 이어 보내거나 짧게 주고받는다"
    )
    if found != prior:
        reason += f"(등록 종류 {kind}와 다르다)"
    return out | dict(shape=found, basis="structure", reason=reason)


def analyze(pack, rows):
    """Judge source shape from a source-pack dict and corpus rows (dicts, corpus order)."""
    kinds = {t["textId"]: t["kind"] for t in pack["texts"]}
    rows_by_kind, texts_by_kind = {}, {}
    for row in rows:
        rows_by_kind.setdefault(kinds.get(row["textId"], "UNKNOWN"), []).append(row)
    for text_id, kind in kinds.items():
        texts_by_kind.setdefault(kind, []).append(text_id)
    pools = [
        _pool(kind, texts_by_kind.get(kind, []), rows_by_kind.get(kind, []))
        for kind in sorted(set(texts_by_kind) | set(rows_by_kind))
    ]
    weight = {INTERVIEW: 0, CONVERSATION: 0}
    for pool in pools:
        if pool["shape"]:
            weight[pool["shape"]] += pool["subjectChars"]
    total = sum(weight.values())
    shares = {k: _ratio(v, total) for k, v in weight.items()}
    if not total:
        shape, reason = None, "판정할 만큼의 대상 발화가 없어 장면 유형을 따른다"
    elif weight[INTERVIEW] == weight[CONVERSATION]:
        shape, reason = None, "두 모양의 대상 발화가 같아 장면 유형을 따른다"
    else:
        shape = INTERVIEW if weight[INTERVIEW] > weight[CONVERSATION] else CONVERSATION
        reason = (
            "한 가지 모양의 원문이다"
            if shares[shape] == 1.0
            else f"섞인 원문이라 대상 발화가 많은 {NAMES[shape]}을 따른다"
        )
    judged = [p for p in pools if p["shape"]]
    # Summary numbers describe the pools that share the chosen shape.
    basis = [p for p in judged if p["shape"] == shape] or judged
    turns = sum(p["subjectTurns"] for p in basis)
    result = dict(
        version=VERSION,
        shape=shape,
        shares=shares,
        qaRatio=_ratio(
            sum(p["answeredMessages"] for p in basis), sum(p["subjectMessages"] for p in basis)
        ),
        charsPerTurn=round(sum(p["subjectChars"] for p in basis) / turns, 1) if turns else 0.0,
        reason=reason,
        pools=pools,
    )
    result["label"] = label(result)
    return result


def label(result):
    """Short line for the source summary, e.g. 원문 모양: 인터뷰형(질문-답 82%).

    Interviews show how often the subject answers the other side; conversations show how
    long one subject turn runs, since short chats can also alternate strictly.
    """
    shape = result.get("shape")
    if shape is None:
        return "원문 모양: 판정 보류(장면 유형 기준)"
    if shape == INTERVIEW:
        detail = f"질문-답 {_percent(result['qaRatio'])}%"
    else:
        detail = f"한 차례 평균 {round(result['charsPerTurn'])}자"
    share = result["shares"][shape]
    if share < 1.0:
        detail += f" · {NAMES[shape]} 발화 {_percent(share)}%"
    return f"원문 모양: {NAMES[shape]}({detail})"


def read_corpus_rows(path):
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                rows.append(
                    {k: row.get(k, "") for k in ("textId", "convId", "speaker", "name", "text")}
                )
    return rows


def analyze_folder(folder):
    """Judge an approved s0-source revision folder (source-pack.json + corpus.jsonl)."""
    folder = Path(folder)
    pack = json.loads((folder / "source-pack.json").read_text("utf-8"))
    return analyze(pack, read_corpus_rows(folder / "corpus.jsonl"))
