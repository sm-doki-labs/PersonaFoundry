"""같은 첫 행동 뒤, 후속 단서 유무에 따라 다음 행동 빈도가 달라지는지 두 대화 묶음에서 잰다."""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import mean

from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.stages.s3_plan.tendencies import MOVES
from character_factory_poc.stages.s8_prompts.response_traits import sample

CUES = {
    "question": "상대의 다음 말에 물음표가 있을 때",
    "laugh": "상대의 다음 말에 웃음 표기(ㅋ·ㅎ)가 있을 때",
    "number": "상대의 다음 말에 숫자가 있을 때",
}


def records(pool, tags):
    used = set()
    result = []

    def moves(ids):
        return {v for m in ids for v in tags.get(m, []) if v in MOVES and v != "OTHER"}

    for s in sorted(pool.values(), key=lambda x: sha256_of(x["id"])):
        mids = {mid for turn in s["refs"] for mid in turn}
        if used & mids:
            continue
        used.update(mids)
        a, b = moves(s["refs"][1]), moves(s["refs"][3])
        text = " ".join(s["turns"][2])
        cues = {
            k
            for k, p in [("question", r"\?"), ("laugh", r"[ㅋㅎ]{2,}"), ("number", r"\d")]
            if re.search(p, text)
        }
        result.append((s["conversation"], s["id"], a, cues, b))
    return result


def contrast(records, first, cue, last):
    cells = [defaultdict(list), defaultdict(list)]
    refs = []
    for conv, mid, a, cues, b in records:
        if first not in a:
            continue
        hit = last in b
        cells[int(cue in cues)][conv].append(hit)
        if cue in cues and hit:
            refs.append((conv, mid))
    # A prolific speaker on a single day must not dominate the estimate.
    if (
        any(len(c) < 4 or sum(map(len, c.values())) < 12 for c in cells)
        or len({k for k, _ in refs}) < 3
    ):
        return None

    def stats(c):
        return {
            "conversations": len(c),
            "total": sum(map(len, c.values())),
            "hits": sum(sum(v) for v in c.values()),
            "rate": round(mean(mean(v) for v in c.values()), 3),
        }

    off, on = map(stats, cells)
    return dict(
        withCue=on,
        withoutCue=off,
        lift=round(on["rate"] - off["rate"], 3),
        evidence=list(dict(refs).values())[:6],
    )


def measure(rows, flagged, labels):
    tags = {r["id"]: r["moves"] for r in labels}
    discovery, validation = [records(pool, tags) for pool in sample(rows, flagged, all_scenes=True)]
    moves = sorted(MOVES.keys() - {"OTHER"})
    hypotheses = []
    for first in moves:
        for cue in CUES:
            for last in moves:
                d = contrast(discovery, first, cue, last)
                if d and d["lift"] >= 0.15 and d["withCue"]["rate"] >= 0.3:
                    hypotheses.append((d["lift"], first, cue, last, d))
    out = []
    # Freeze the shortlist using discovery only; do not search the validation set for winners.
    for _, first, cue, last, d in sorted(hypotheses, reverse=True)[:4]:
        v = contrast(validation, first, cue, last)
        if not v or v["lift"] < 0.15 or v["withCue"]["rate"] < 0.3:
            continue
        summary = (
            f"처음에 ‘{MOVES[first]}’는 반응을 보인 뒤, {CUES[cue]}에는 "
            f"‘{MOVES[last]}’는 다음 반응이 더 잦았다. 그 표지가 있는 경우와 없는 경우 "
            f"대화별 평균은 발견 {d['withCue']['rate']:.0%}/{d['withoutCue']['rate']:.0%}, "
            f"별도 검토 {v['withCue']['rate']:.0%}/{v['withoutCue']['rate']:.0%}. "
            "표기 자체가 원인이라는 뜻은 아니다."
        )
        out.append(
            dict(first=first, cue=cue, last=last, discovery=d, confirmation=v, summary=summary)
        )
    return out
