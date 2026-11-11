"""Whole-source turn chunks with auditable exclusions and continuity barriers."""

import json
from collections import defaultdict
from datetime import datetime

from character_factory_poc.stages.s8_prompts.evidence_source import _UNSAFE, MAX_TURN_CHARS, _index


def prepare_full_source(train, holdout, flagged, *, max_chunk_chars=24000, max_gap_seconds=1800):
    if (
        type(max_chunk_chars) is not int
        or max_chunk_chars < 1000
        or type(max_gap_seconds) is not int
        or max_gap_seconds < 0
    ):
        raise ValueError("invalid full-source chunk bounds")
    train_ids, train_units = _index(train, "train")
    held_ids, held_units = _index(holdout, "holdout")
    if train_ids & held_ids:
        raise ValueError("cross-split message ID")
    groups = defaultdict(list)
    excluded = []
    for row in train:
        unit = (row["textId"], row["convId"])
        if unit in held_units:
            excluded.append(dict(id=row["msgId"], reason="shared_evaluation_unit"))
        else:
            groups[unit].append(row)
    segments = []
    boundaries = 0
    for unit, rows in groups.items():
        turns = []
        previous = None
        have_previous = False

        def flush(unit=unit):
            nonlocal turns
            if turns:
                segments.append(dict(unit=list(unit), turns=turns))
                turns = []

        for row in rows:
            raw = row.get("at")
            try:
                stamp = datetime.fromisoformat(raw) if raw is not None else None
            except (TypeError, ValueError):
                flush()
                previous = None
                have_previous = False
                excluded.append(dict(id=row["msgId"], reason="invalid_time"))
                continue
            gap = False
            if have_previous:
                if (previous is None) != (stamp is None):
                    gap = True
                elif stamp is not None:
                    try:
                        gap = not 0 <= (stamp - previous).total_seconds() <= max_gap_seconds
                    except TypeError:
                        gap = True
            if gap:
                flush()
                boundaries += 1
            previous = stamp
            have_previous = True
            text = row.get("text")
            speaker = row.get("speaker")
            reason = None
            if row["msgId"] in flagged:
                reason = "flagged_private"
            elif (
                not isinstance(text, str) or not text.strip() or speaker not in ("USER", "SUBJECT")
            ):
                reason = "invalid_message"
            elif len(text.strip()) <= MAX_TURN_CHARS and _UNSAFE.search(text):
                reason = "private_or_media"
            if reason:
                flush()
                excluded.append(dict(id=row["msgId"], reason=reason))
                continue
            text = text.strip()
            if turns and turns[-1]["speaker"] == speaker:
                t = turns[-1]
                t["text"] += " " + text
                t["messageIds"].append(row["msgId"])
            else:
                turns.append(
                    dict(id=row["msgId"], speaker=speaker, text=text, messageIds=[row["msgId"]])
                )
        flush()
    # Oversized merged turns are barriers, never cut into fabricated replies.
    safe = []
    for segment in segments:
        current = []
        for t in segment["turns"]:
            if len(t["text"]) > MAX_TURN_CHARS:
                if current:
                    safe.append(dict(unit=segment["unit"], turns=current))
                    current = []
                excluded.extend(dict(id=i, reason="oversized_turn") for i in t["messageIds"])
            else:
                current.append(t)
        if current:
            safe.append(dict(unit=segment["unit"], turns=current))
    records = []
    for segment in safe:
        turns = segment["turns"]
        for i, t in enumerate(turns):
            if t["speaker"] != "SUBJECT":
                continue
            records.append(
                dict(
                    id=t["id"],
                    unit=segment["unit"],
                    target=t["text"],
                    context=turns[i - 1]["text"] if i else "",
                    next=turns[i + 1]["text"] if i + 1 < len(turns) else None,
                    followup=turns[i + 2]["text"] if i + 2 < len(turns) else None,
                    history=[
                        dict(speaker=q["speaker"], text=q["text"]) for q in turns[max(0, i - 5) : i]
                    ],
                )
            )

    def chunk(parts, n=999999):
        return dict(
            id=f"chunk-{n:04d}",
            segments=parts,
            recordIds=list(
                dict.fromkeys(
                    t["id"] for s in parts for t in s["turns"] if t["speaker"] == "SUBJECT"
                )
            ),
        )

    def fits(parts):
        return len(json.dumps(chunk(parts), ensure_ascii=False)) <= max_chunk_chars

    pieces = []
    for s in safe:
        turns = s["turns"]
        start = 0
        while start < len(turns):
            end = start
            while end < len(turns) and fits([dict(unit=s["unit"], turns=turns[start : end + 1])]):
                end += 1
            if end == start:
                raise ValueError("한 말차례를 보존할 수 없는 chunk 상한이다. 상한을 늘린다")
            pieces.append(dict(unit=s["unit"], turns=turns[start:end]))
            if end == len(turns):
                break
            # Context overlap is best-effort within the hard transport bound.
            following = max(start + 1, end - 5)
            while following < end and not fits(
                [dict(unit=s["unit"], turns=turns[following : end + 1])]
            ):
                following += 1
            start = following
    chunks = []
    parts = []
    for piece in pieces:
        if parts and not fits(parts + [piece]):
            chunks.append(chunk(parts, len(chunks) + 1))
            parts = []
        parts.append(piece)
    if parts:
        chunks.append(chunk(parts, len(chunks) + 1))
    included = {
        mid for c in chunks for s in c["segments"] for t in s["turns"] for mid in t["messageIds"]
    }
    omitted = {e["id"] for e in excluded}
    if included & omitted or included | omitted != train_ids or len(excluded) != len(omitted):
        raise ValueError("전체 메시지 coverage 누락 또는 중복 제외")
    coverage = dict(
        inputMessageCount=len(train),
        includedMessageIds=sorted(included),
        excluded=excluded,
        complete=True,
    )
    return dict(
        records=records,
        chunks=chunks,
        holdoutIds=sorted(held_ids),
        coverage=coverage,
        stats=dict(
            train_messages=len(train),
            holdout_messages=len(holdout),
            holdout_units=len(held_units),
            included_messages=len(included),
            excluded_messages=len(excluded),
            time_boundaries=boundaries,
            eligible_turns=len(records),
            eligible_units=len({tuple(r["unit"]) for r in records}),
            sampled_records=len(records),
            sampled_units=len({tuple(r["unit"]) for r in records}),
            chunks=len(chunks),
            unsampled_records=0,
            full_source=True,
        ),
    )
