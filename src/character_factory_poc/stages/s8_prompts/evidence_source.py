"""Pure, bounded S8 evidence intake and mechanical provenance checks.

Source order within a (textId, convId) unit is authoritative; never sort it by
timestamp. Records are private review inputs, not persona examples. This module
does not infer facts, approve a linguistic tendency, or resolve unknown history.
The caller must expose only returned record IDs to the author/compiler.
"""

import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

# Character budgets include all text fields (including context repeated in history).
# Whole turns/windows are discarded on overflow: no ellipsis or synthetic adjacency.
MAX_TURN_CHARS = 4_000
MAX_RECORD_CHARS = 16_000
_HISTORY_TURNS = 5
_COPY_SPAN = 12
_CARD_FIELDS = ("trigger", "first", "shift", "stop", "limit", "rule")
_SOURCE_FIELDS = ("context", "target", "next", "followup")

# Conservative lexical exclusions supplement upstream piiFlags, not an anonymizer.
_UNSAFE = re.compile(
    r"https?://|www\.|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
    r"|(?<!\d)(?:\+82[-\s.]?)?0\d{1,2}[-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)"
    r"|(?<!\d)\d{2,6}-\d{2,6}-\d{2,8}(?!\d)"
    r"|송금(?:\s*받기|\s*요청)|원을\s*(?:보냈어요|받았어요)|^샵검색:"
    r"|참여자\d+"
    r"|[\[<](?:전화번호|이메일|번호|계좌(?:번호)?|이름|주소|개인정보|가림|마스킹|"
    r"REDACTED|MASKED|MASK|PII|PHONE|EMAIL|ACCOUNT|NAME|ADDRESS)(?:[_\s:-][^\]>]*)?[\]>]"
    r"|^\s*[\[(]?(?:사진(?:\s*\d+장)?|이모티콘|동영상|음성메시지|"
    r"삭제된 메시지입니다\.?|보이스톡 해요\.?|페이스톡 해요\.?)\s*[\])]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_QUESTION_CUES = (
    ("reason_method_cue", re.compile(r"왜|어떻게|어케|어캐|이유|어떤 식|\bwhy\b|\bhow\b", re.I)),
    ("possibility_check_cue", re.compile(r"가능|되냐|되나|ㄱㄴ|맞지|맞나|되는지")),
    ("question_mark", re.compile(r"[?？]")),
    ("laughter_marks", re.compile(r"[ㅋㅎ]{2,}")),
)


def _identity(value, name):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name}: expected a nonblank, unpadded string")
    return value


def _index(rows, split):
    if not isinstance(rows, list):
        raise ValueError(f"{split}: expected a list")
    ids, units = set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{split}: expected message objects")
        message_id = _identity(row.get("msgId"), "msgId")
        unit = tuple(_identity(row.get(k), k) for k in ("textId", "convId"))
        if message_id in ids:
            raise ValueError(f"{split}: duplicate message ID")
        ids.add(message_id)
        units.add(unit)
    return ids, units


@dataclass
class _Turn:
    speaker: str
    first_id: str
    # None marks an oversized turn. Keep its speaker to discard its entire tail.
    text: str | None


def _turns(rows, flagged, max_gap_seconds, stats):
    turns = []
    previous = None
    have_previous = False
    for row in rows:
        raw_stamp = row.get("at")
        try:
            stamp = datetime.fromisoformat(raw_stamp) if raw_stamp is not None else None
        except (ValueError, TypeError):
            turns.append(None)
            previous, have_previous = None, False
            stats["discarded_messages"] += 1
            continue

        discontinuous = False
        if have_previous:
            if (previous is None) != (stamp is None):
                discontinuous = True
            elif previous is not None and stamp is not None:
                try:
                    discontinuous = not 0 <= (stamp - previous).total_seconds() <= max_gap_seconds
                except TypeError:  # naive/aware clocks cannot establish continuity
                    discontinuous = True
        if discontinuous:
            turns.append(None)
            stats["time_boundaries"] += 1
        previous, have_previous = stamp, True

        text, speaker = row.get("text"), row.get("speaker")
        if (
            not isinstance(text, str)
            or not text.strip()
            or speaker not in ("USER", "SUBJECT")
            or row["msgId"] in flagged
        ):
            turns.append(None)
            stats["discarded_messages"] += 1
            continue
        text = text.strip()
        # Bound regex work as well as emitted text. Oversized data remains a barrier.
        if len(text) <= MAX_TURN_CHARS and _UNSAFE.search(text):
            turns.append(None)
            stats["discarded_messages"] += 1
            continue
        if turns and turns[-1] is not None and turns[-1].speaker == speaker:
            turn = turns[-1]
            if turn.text is not None:
                turn.text = (
                    turn.text + " " + text
                    if len(turn.text) + 1 + len(text) <= MAX_TURN_CHARS
                    else None
                )
        else:
            turns.append(
                _Turn(speaker, row["msgId"], text if len(text) <= MAX_TURN_CHARS else None)
            )
    stats["discarded_oversized_turns"] += sum(t is not None and t.text is None for t in turns)
    return turns


def _candidates(unit, turns, stats):
    for i, turn in enumerate(turns):
        if not turn or turn.speaker != "SUBJECT" or turn.text is None or i == 0:
            continue
        prior = turns[i - 1]
        if not prior or prior.speaker != "USER" or prior.text is None:
            continue
        following = turns[i + 1] if i + 1 < len(turns) else None
        followup = turns[i + 2] if following and i + 2 < len(turns) else None
        if any(t is not None and t.text is None for t in (following, followup)):
            stats["discarded_oversized_records"] += 1
            continue
        history = []
        for earlier in reversed(turns[max(0, i - _HISTORY_TURNS) : i]):
            if earlier is None or earlier.text is None:
                break
            history.append({"speaker": earlier.speaker, "text": earlier.text})
        history.reverse()
        record = {
            "id": turn.first_id,
            "unit": list(unit),
            "context": prior.text,
            "target": turn.text,
            "next": following.text if following else None,
            "followup": followup.text if followup else None,
            "history": history,
        }
        size = sum(len(record[k] or "") for k in _SOURCE_FIELDS)
        size += sum(len(t["text"]) for t in history)
        if size > MAX_RECORD_CHARS:
            stats["discarded_oversized_records"] += 1
            continue
        yield record


def _cue(record):
    return next(
        (label for label, pattern in _QUESTION_CUES if pattern.search(record["context"])), "other"
    )


def _rank(value):
    return sha256(value.encode("utf-8")).digest()


def _sample(candidates, limit):
    """Max-min unit fairness first, then cue diversity; deterministic ID tie-breaks.

    Lexical cues balance surface coverage only; they are not semantic annotations.
    Exhausted units/cues release their share to the remaining candidates.
    """
    buckets = defaultdict(list)
    for record in candidates:
        buckets[(tuple(record["unit"]), _cue(record))].append(record)
    queues = {
        key: deque(sorted(rows, key=lambda r: (_rank(r["id"]), r["id"])))
        for key, rows in buckets.items()
    }
    unit_counts, cue_counts, pair_counts = Counter(), Counter(), Counter()
    sample = []
    while queues and len(sample) < limit:
        key = min(
            queues,
            key=lambda k: (
                unit_counts[k[0]],
                cue_counts[k[1]],
                pair_counts[k],
                _rank("\0".join((*k[0], k[1]))),
                k,
            ),
        )
        sample.append(queues[key].popleft())
        unit_counts[key[0]] += 1
        cue_counts[key[1]] += 1
        pair_counts[key] += 1
        if not queues[key]:
            del queues[key]
    return sample


def prepare_records(
    train: list[dict],
    holdout: list[dict],
    flagged: set[str],
    *,
    max_records: int = 80,
    max_gap_seconds: int = 1800,
) -> dict:
    """Return bounded review records, text-free counts, and sorted holdout IDs.

    History contains at most five turns immediately before the target, including
    its USER context. Consecutive same-speaker messages merge with a single space;
    internal whitespace is preserved. Missing timestamps work for wholly undated
    transcripts, but transitions between dated and undated rows break continuity.
    Empty inputs/zero sampling budget return an empty sample after ID validation.
    """
    for name, value in (("max_records", max_records), ("max_gap_seconds", max_gap_seconds)):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name}: expected a nonnegative integer")
    if not isinstance(flagged, set) or any(not isinstance(i, str) for i in flagged):
        raise ValueError("flagged: expected a set of message IDs")
    train_ids, train_units = _index(train, "train")
    held_ids, held_units = _index(holdout, "holdout")
    if train_ids & held_ids:
        raise ValueError("cross-split message ID")
    stats = dict(
        train_messages=len(train),
        holdout_messages=len(holdout),
        holdout_units=len(held_units),
        discarded_shared_units=len(train_units & held_units),
        discarded_messages=0,
        time_boundaries=0,
        discarded_oversized_turns=0,
        discarded_oversized_records=0,
    )
    groups = defaultdict(list)
    for row in train:
        unit = row["textId"], row["convId"]
        if unit not in held_units:
            groups[unit].append(row)
    candidates = []
    for unit, rows in groups.items():
        candidates.extend(_candidates(unit, _turns(rows, flagged, max_gap_seconds, stats), stats))
    sample = _sample(candidates, max_records)
    stats.update(
        eligible_turns=len(candidates),
        eligible_units=len({tuple(r["unit"]) for r in candidates}),
        sampled_records=len(sample),
        sampled_units=len({tuple(r["unit"]) for r in sample}),
        unsampled_records=len(candidates) - len(sample),
        heuristic_labels_semantically_validated=False,
        sampled_heuristic_cues=dict(sorted(Counter(_cue(r) for r in sample).items())),
    )
    return {"records": sample, "stats": stats, "holdoutIds": sorted(held_ids)}


def validate_card(card, records, *, min_units=2, extra_speech=()) -> None:
    """Check provenance/overlap only; the compiler owns the card's full schema.

    Two distinct source units are necessary, not proof of semantic independence
    or a validated tendency. Compare every card prose field to every sample's
    raw speech, including uncited samples and prior history. Error messages never
    echo source text. The caller must pass the sampled records, not the corpus.
    """
    if not isinstance(card, dict) or not isinstance(records, list):
        raise ValueError("expected a card object and sampled records list")
    by_id = {}
    if any(not isinstance(t, str) for t in extra_speech):
        raise ValueError("extra source speech must be text")
    source_texts = list(extra_speech)
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("expected a sampled record object")
        rid = _identity(record.get("id"), "record ID")
        if rid in by_id:
            raise ValueError("duplicate sampled record ID")
        unit = record.get("unit")
        if not isinstance(unit, (list, tuple)) or len(unit) != 2:
            raise ValueError("record unit: expected textId and convId")
        by_id[rid] = tuple(_identity(part, "record unit") for part in unit)
        for field in _SOURCE_FIELDS:
            value = record.get(field)
            if value is None and field in ("next", "followup"):
                continue
            if not isinstance(value, str):
                raise ValueError("record speech must be text")
            source_texts.append(value)
        history = record.get("history", [])
        if not isinstance(history, list):
            raise ValueError("record history must be a list")
        for turn in history:
            if not isinstance(turn, dict) or not isinstance(turn.get("text"), str):
                raise ValueError("history speech must be text")
            source_texts.append(turn["text"])

    refs = card.get("evidence")
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise ValueError("evidence: expected sampled record IDs")
    if len(refs) != len(set(refs)):
        raise ValueError("duplicate evidence reference")
    if any(ref not in by_id for ref in refs):
        raise ValueError("evidence references an unsampled or unknown record")
    if not refs or len({by_id[ref] for ref in refs}) < min_units:
        raise ValueError("evidence requires at least two distinct source units")

    spans = set()
    for field in _CARD_FIELDS:
        value = card.get(field)
        if not isinstance(value, str):
            raise ValueError(f"{field}: expected text")
        compact = re.sub(r"\s+", "", value)
        spans.update(compact[i : i + _COPY_SPAN] for i in range(len(compact) - _COPY_SPAN + 1))
    for speech in source_texts:
        compact = re.sub(r"\s+", "", speech)
        if any(compact[i : i + _COPY_SPAN] in spans for i in range(len(compact) - _COPY_SPAN + 1)):
            raise ValueError("copied raw speech span in card")
