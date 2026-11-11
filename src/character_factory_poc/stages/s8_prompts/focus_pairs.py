"""두 말차례에서 무엇을 집었고 어떤 대응을 했는지 발견하고 독립 대화에서 검토한다."""

from importlib.resources import files

from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.stages.s8_prompts.response_traits import sample

TOPICS = (
    "기술 일·진로 학습 돈·소비 옷·외모 식생활 문화·놀이 건강·운동 "
    "관계·감정 이동·장소 일정·약속 생활 기타"
).split()
FIELDS = ("cue", "focus", "move", "boundary")
RES = files("character_factory_poc.resources")
DISC = RES.joinpath("focus-pairs-disc-v2.md").read_text("utf-8")
CONF = RES.joinpath("focus-pairs-conf-v2.md").read_text("utf-8")


def references(raw, pool):
    refs = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id"))
        ti = item.get("topic")
        pos = item.get("at")
        if key not in pool or type(ti) is not int or not 0 <= ti < len(TOPICS):
            continue
        if not isinstance(pos, list) or len(pos) != 2:
            continue
        scene = pool[key]
        if not all(
            type(j) is int and 0 <= j < len(turn)
            for j, turn in zip(pos, scene["turns"], strict=True)
        ):
            continue
        refs[key] = dict(
            id=scene["id"],
            topic=TOPICS[ti],
            quotes=[t[j] for j, t in zip(pos, scene["turns"], strict=True)],
            msgIds=[t[j] for j, t in zip(pos, scene["refs"], strict=True)],
        )
    return list(refs.values())


def analyze_pairs(rows, flagged, call):
    d, v = sample(rows, flagged, cap=160, pair=True)
    out = dict(
        version="focus-pairs-v2",
        rulesSha256=sha256_of([DISC, CONF]),
        discoveryScenes=list(d),
        confirmScenes=list(v),
        patterns=[],
        rejected=[],
    )

    def payload(pool):
        return [dict(id=i, turns=s["turns"]) for i, s in enumerate(pool.values())]

    def chats(refs, pool):
        return {pool[e["id"]]["conversation"] for e in refs}

    if len({s["conversation"] for s in d.values()}) < 2 or not v:
        return out
    candidates = {}
    proposals = call("discover", DISC, payload(d))["patterns"]
    if not isinstance(proposals, list):
        raise ValueError("분석 후보 형식 오류")
    for i, p in enumerate(proposals[:4]):
        if not isinstance(p, dict) or not all(
            isinstance(p.get(k), str) and 0 < len(p[k].strip()) <= 220 for k in FIELDS
        ):
            continue
        trait = {k: p[k].strip() for k in FIELDS}
        support = references(p.get("support"), {str(i): s for i, s in enumerate(d.values())})
        candidate = dict(trait=trait, discovery=support)
        if len(chats(support, d)) >= 2:
            candidates[str(i)] = candidate
        else:
            out["rejected"].append({**candidate, "reason": "insufficient_discovery"})
    if not candidates:
        return out
    reviews = call(
        "confirm",
        CONF,
        dict(patterns={k: x["trait"] for k, x in candidates.items()}, scenes=payload(v)),
    )["reviews"]
    if not isinstance(reviews, list) or sorted(str(r["key"]) for r in reviews) != sorted(
        candidates
    ):
        raise ValueError("후보별 독립 대조가 필요하다")
    indexed = {str(i): s for i, s in enumerate(v.values())}
    for rev in reviews:
        c = candidates[str(rev["key"])]
        support = references(rev.get("support"), indexed)
        counter = references(rev.get("counter"), indexed)
        dt = {e["topic"] for e in c["discovery"]} - {"기타"}
        vt = {e["topic"] for e in support} - {"기타"}
        # 대화 묶음 양쪽에서 서로 다른 소재가 있어야 한다.
        cross = any(a != b for a in dt for b in vt)
        audited = dict(
            **c,
            confirmation=support,
            counter=counter,
            discoveryTopics=sorted(dt),
            confirmationTopics=sorted(vt),
        )
        if (
            not isinstance(rev.get("counter"), list)
            or len(counter) != len(rev["counter"])
            or not cross
            or not chats(support, v) - chats(counter, v)
            or len(chats(support, v)) <= len(chats(counter, v))
        ):
            out["rejected"].append({**audited, "reason": "insufficient_cross_topic_support"})
        else:
            out["patterns"].append(audited)
    return out
