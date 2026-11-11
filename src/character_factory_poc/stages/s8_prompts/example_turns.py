"""대화 앞에 이전 턴으로 넣을 실제 문답을 생성용 원문에서 뽑는다(D-0173).

모델을 부르지 않는다. 같은 사람이 연달아 보낸 메시지를 한 말차례로 묶고, 끊김 없이 이어진
'상대 말차례 → 본인 말차례'만 후보로 삼는다. 원문과 대화 장면의 매체가 다르면(인터뷰 → 통화)
본인 답 길이의 하위 75% 안에서만 뽑는다. 출처가 여럿이면 출처마다 돌아가며 한 문답씩 뽑는다.
"""

from __future__ import annotations

import random
import re
from datetime import datetime
from itertools import groupby

from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.common.store import read_json
from character_factory_poc.stages.s0_source.run import load_approved_source

VERSION = "example-turns-v1"
BRIDGE = (
    "앞선 대화 기록은 이 사람이 실제로 주고받은 문답 모음이다. "
    "서로 이어지는 내용이 아니며 말투, 길이, 반응 방식만 따른다. 답만 출력한다."
)
USER_MAX = 250
REPLY_MAX = 450
GAP_SECONDS = 1800
SKIP = re.compile(
    r"https?://|[\w.+-]+@[\w.-]+\.\w+|\d{2,3}-\d{3,4}-\d{4}|송금 받기|원을 보냈어요|원을 받았어요"
)
MEDIA = re.compile(r"^(사진( \d+장)?|이모티콘|동영상|삭제된 메시지입니다\.)$")


def exchanges(rows: list[dict], flagged: set[str]) -> list[dict]:
    """끊김 없이 이어진 '상대 말차례 → 본인 말차례' 목록."""
    out: list[dict] = []

    def flush(source, seg):
        blocks = [(sp, list(b)) for sp, b in groupby(seg, key=lambda r: r["speaker"])]
        for (a, x), (b, y) in zip(blocks, blocks[1:], strict=False):
            if a == "USER" and b == "SUBJECT":
                out.append(
                    dict(
                        source=source,
                        msgId=y[0]["msgId"],
                        user=" ".join(r["text"].strip() for r in x),
                        reply=" ".join(r["text"].strip() for r in y),
                    )
                )

    for key, group in groupby(rows, key=lambda r: (r["textId"], r["convId"])):
        seg: list[dict] = []
        last = None
        for r in group:
            text = (r.get("text") or "").strip()
            at = datetime.fromisoformat(r["at"]) if r.get("at") else None
            gap = at and last and not 0 <= (at - last).total_seconds() <= GAP_SECONDS
            skip = (
                r["speaker"] not in ("USER", "SUBJECT")
                or r["msgId"] in flagged
                or not text
                or SKIP.search(text)
                or MEDIA.match(text)
            )
            if gap or skip:
                flush(key[0], seg)
                seg = []
            if not skip:
                seg.append(r)
            last = at
        flush(key[0], seg)
    return out


def pick(rows, flagged, count: int, *, same_medium: bool, seed: str) -> tuple[int | None, list]:
    pairs = exchanges(rows, flagged)
    if not pairs or count <= 0:
        return None, []
    lengths = sorted(len(p["reply"]) for p in pairs)
    cap = REPLY_MAX if same_medium else min(REPLY_MAX, lengths[int(len(lengths) * 0.75)])
    pool, seen = [], set()
    for p in pairs:
        if len(p["user"]) <= USER_MAX and len(p["reply"]) <= cap and p["reply"] not in seen:
            seen.add(p["reply"])
            pool.append(p)
    rnd = random.Random(seed)
    by: dict[str, list] = {}
    for p in pool:
        by.setdefault(p["source"], []).append(p)
    if len(by) <= 1:
        return cap, rnd.sample(pool, min(count, len(pool)))
    names = sorted(by)
    rnd.shuffle(names)
    for name in sorted(by):
        rnd.shuffle(by[name])
    chosen: list = []
    depth = 0
    while len(chosen) < count and any(len(by[n]) > depth for n in names):
        chosen += [by[n][depth] for n in names if len(by[n]) > depth][: count - len(chosen)]
        depth += 1
    return cap, chosen


def system_text(frame: str, facts: str) -> str:
    """조립된 지시문의 첫 문단(정체성·경계)만 남긴다. 행동 지침은 실제 문답이 대신한다."""
    first = frame.strip().split("\n\n")[0].strip()
    return f"{first}\n\n{BRIDGE}\n\n[확인된 설정과 정보]\n{facts}"


def build(rows, flagged, frame, facts, count, *, same_medium, seed) -> dict | None:
    cap, chosen = pick(rows, flagged, count, same_medium=same_medium, seed=seed)
    if not chosen:
        return None
    return dict(
        version=VERSION,
        sameMedium=same_medium,
        replyCap=cap,
        system=system_text(frame, facts),
        turns=[dict(msgId=p["msgId"], user=p["user"], reply=p["reply"]) for p in chosen],
    )


def from_source(ctx, cid: str, frame: str, facts: str, count: int) -> dict | None:
    pack, index, rows = load_approved_source(ctx, cid)
    folder = ctx.character_dir(cid) / "s0-source" / index.sourceRev
    flagged = {x["msgId"] for x in read_json(folder / "digest.json")["piiFlags"]}
    same_medium = all(src.kind == "KAKAO_EXPORT" for src in pack.texts)
    seed = sha256_of([VERSION, cid, index.sourceRev])
    return build(rows, flagged, frame, facts, count, same_medium=same_medium, seed=seed)
