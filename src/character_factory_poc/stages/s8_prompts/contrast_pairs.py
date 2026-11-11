"""비슷한 상황의 두 선택을 찾고, 다음 답을 가린 예측을 독립적으로 판정한다."""

from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.stages.s8_prompts.focus_pairs import RES, references
from character_factory_poc.stages.s8_prompts.response_traits import sample, verification_pool

DISC, ROUTE, CONFIRM = (
    RES.joinpath(f"contrast-{k}-v1.md").read_text("utf-8") for k in ("disc", "route", "confirm")
)
SIDES = ("A", "B")
FIELDS = ("situation", *(k + side for side in SIDES for k in ("cue", "focus", "move")))


def keyed(raw, expected):
    if not isinstance(raw, list) or any(not isinstance(r, dict) for r in raw):
        raise ValueError("특질별 검토 응답 형식 오류")
    result = {str(r.get("key")): r for r in raw}
    if len(result) != len(raw) or set(result) != set(expected):
        raise ValueError("특질별 검토 응답 누락 또는 중복")
    return result


def blind_shortlist(candidates, discover, reservoir):
    # No reply text, reply length or reply message IDs participate in ranking.
    def mask(pool):
        return {k: {**s, "turns": s["turns"][:1], "refs": s["refs"][:1]} for k, s in pool.items()}

    queries = {
        (i, side): ({}, c["discovery"][side]) for i, c in candidates.items() for side in SIDES
    }
    ids = verification_pool(queries, mask(discover), mask(reservoir))
    return {k: reservoir[k] for k in ids}


def analyze_pairs(rows, flagged, call):
    d, v = sample(rows, flagged, cap=160, pair=True, reservoir=True)
    idx = {str(i): s for i, s in enumerate(d.values())}
    out = dict(
        version="contrast-pairs-v2",
        eligibleScenes=len(v),
        routedScenes=[],
        rulesSha256=sha256_of([DISC, ROUTE, CONFIRM]),
        discoveryScenes=list(d),
        confirmScenes=[],
        patterns=[],
        rejected=[],
    )
    if len({s["conversation"] for s in d.values()}) < 3 or not v:
        return out
    found = call("discover", DISC, [dict(id=int(i), turns=s["turns"]) for i, s in idx.items()])[
        "patterns"
    ]
    if not isinstance(found, list):
        raise ValueError("후보 목록이 필요하다")
    cand = {}
    for n, item in enumerate(found[:3]):
        if not isinstance(item, dict) or not all(
            isinstance(item.get(k), str) and 0 < len(item[k].strip()) <= 180 for k in FIELDS
        ):
            continue
        refs = {k: references(item.get(k), idx) for k in SIDES}
        sets = [{e["id"] for e in refs[k]} for k in SIDES]
        unit = dict(trait={k: item[k].strip() for k in FIELDS}, discovery=refs)
        if (
            not all(sets)
            or sets[0] & sets[1]
            or len({d[x]["conversation"] for x in sets[0] | sets[1]}) < 3
        ):
            out["rejected"].append(dict(**unit, reason="insufficient_contrast"))
            continue
        cand[str(n)] = unit
    if not cand:
        return out
    v = blind_shortlist(cand, d, v)
    val = {str(i): s for i, s in enumerate(v.values())}
    out["routedScenes"] = list(v)
    routes = keyed(
        call(
            "route",
            ROUTE,
            dict(
                rules={
                    i: {k: t["trait"][k] for k in ("situation", "cueA", "cueB")}
                    for i, t in cand.items()
                },
                scenes=[dict(id=int(i), user=s["turns"][0]) for i, s in val.items()],
            ),
        )["routes"],
        cand,
    )
    trials = {}
    tasks = {}
    for i, c in cand.items():
        votes = {}
        for side in SIDES:
            raw = routes[i].get(side, [])
            for r in raw[:4] if isinstance(raw, list) else []:
                if not isinstance(r, dict):
                    continue
                j = str(r.get("id"))
                mark = r.get("marker")
                if (
                    j in val
                    and isinstance(mark, str)
                    and mark.strip()
                    and any(mark in t for t in val[j]["turns"][0])
                ):
                    votes.setdefault(j, {})[side] = mark
        picked = {j: next(iter(m.items())) for j, m in votes.items() if len(m) == 1}
        c["predictions"] = [dict(id=val[j]["id"], side=s, marker=m) for j, (s, m) in picked.items()]
        if {x[0] for x in picked.values()} != set(SIDES):
            out["rejected"].append(dict(**c, reason="insufficient_blind_routes"))
            continue
        trials[i] = picked
        tasks[i] = dict(
            actions={s: [c["trait"]["focus" + s], c["trait"]["move" + s]] for s in SIDES},
            scenes=[dict(id=int(j), turns=val[j]["turns"]) for j in sorted(picked, key=int)],
        )
    if not trials:
        return out
    out["confirmScenes"] = sorted({val[j]["id"] for group in trials.values() for j in group})
    checks = keyed(call("confirm", CONFIRM, tasks)["reviews"], tasks)
    for i, picked in trials.items():
        c = cand[i]
        items = checks[i].get("items")
        seen = set()
        results = []
        if not isinstance(items, list):
            raise ValueError("장면 판정 누락")
        for row in items:
            if not isinstance(row, dict):
                raise ValueError("잘못된 장면 판정")
            j = str(row.get("id"))
            actual = row.get("actual")
            if j not in picked or j in seen or actual not in (*SIDES, "neither"):
                raise ValueError("장면 번호 또는 판정 종류 오류")
            seen.add(j)
            ref = references([row], val)
            results.append(
                dict(
                    id=val[j]["id"],
                    predicted=picked[j][0],
                    actual=actual,
                    evidence=ref[0] if ref else None,
                    hit=bool(ref and actual == picked[j][0]),
                )
            )
        if set(picked) != seen:
            raise ValueError("장면 판정 누락")
        c["checks"] = results
        wins = [
            {v[r["id"]]["conversation"] for r in results if r["predicted"] == s and r["hit"]}
            for s in SIDES
        ]

        # At least one branch must travel to a different topic than a discovery scene
        # (within the same branch); neither or ungrounded labels count as misses.
        def crosses(side, c=c, results=results):
            ds = {e["topic"] for e in c["discovery"][side]} - {"기타"}
            vs = {
                r["evidence"]["topic"] for r in results if r["hit"] and r["predicted"] == side
            } - {"기타"}
            return any(x != y for x in ds for y in vs)

        if (
            not all(wins)
            or len(wins[0] | wins[1]) < 2
            or not any(crosses(s) for s in SIDES)
            or any(
                2 * sum(r["hit"] for r in results if r["predicted"] == s)
                <= sum(r["predicted"] == s for r in results)
                for s in SIDES
            )
        ):
            out["rejected"].append(dict(**c, reason="blind_contrast_not_reproduced"))
            continue
        out["patterns"].append(c)
    return out
