"""G0 생성용 원문에서 네 말차례를 복원하고 다른 대화에서 재관찰된 행동만 채택한다."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from importlib.resources import files
from itertools import groupby

from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.common.store import read_json
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object
from character_factory_poc.stages.s0_source.run import load_approved_source

VERSION = "response-traits-v1"
ROLES = ["USER", "SUBJECT", "USER", "SUBJECT"]
FIELDS = ("cue", "firstMove", "newCue", "nextMove", "limit")
SKIP = re.compile(r"https?://|[\w.+-]+@[\w.-]+\.\w+|\d{2,3}-\d{3,4}-\d{4}|송금 받기|원을 보냈어요")


def _rules(step):
    return (
        files("character_factory_poc.resources")
        .joinpath(f"response-traits-{step}-v1.md")
        .read_text("utf-8")
    )


DISCOVER = _rules("discover")
CONFIRM = _rules("confirm")


def sample(rows, flagged, cap=128, *, reservoir=False, all_scenes=False, pair=False):
    """주제·평가 질문을 보지 않는다. 같은 대화는 발견/검토 중 한쪽에만 들어간다."""
    groups = defaultdict(list)
    seen = set()

    def windows(block, key):
        turns = [list(g) for _, g in groupby(block, key=lambda r: r["speaker"])]
        roles = ROLES[:2] if pair else ROLES
        for i in range(len(turns) - len(roles) + 1):
            four = turns[i : i + len(roles)]
            if [t[0]["speaker"] for t in four] != roles:
                continue
            utterances = [[r["text"].strip() for r in t] for t in four]
            if any(len(t) > 8 or sum(map(len, t)) > 480 for t in utterances):
                continue
            digest = sha256_of(utterances)
            if digest in seen:
                continue
            seen.add(digest)
            groups[key].append(
                dict(
                    id=four[0][0]["msgId"],
                    turns=utterances,
                    conversation=key,
                    refs=[[r["msgId"] for r in t] for t in four],
                )
            )

    for key, group in groupby(rows, key=lambda r: (r["textId"], r["convId"])):
        block = []
        last = None
        for r in group:
            text = r["text"].strip()
            at = datetime.fromisoformat(r["at"]) if r.get("at") else None
            gap = at and last and not 0 <= (at - last).total_seconds() <= 1800
            skip = (
                r["speaker"] not in ROLES
                or r["msgId"] in flagged
                or not text
                or SKIP.search(text)
                or text in {"사진", "이모티콘", "동영상", "삭제된 메시지입니다."}
            )
            if gap or skip:
                windows(block, key)
                block = []
            if not skip:
                block.append(r)
            last = at
        windows(block, key)
    keys = sorted(groups, key=sha256_of)
    # 발견과 검토는 대화 단위로 나눈다. 각 대화에서 원문이 겹치지 않는
    # 창을 최대 네 개 뽑되, 첫 창부터 대화 사이에 고르게 배분한다.
    pools = []
    sides = (keys[::2], keys[1::2])
    sources = sorted({k[0] for k in keys}, key=sha256_of)
    if pair and len(sources) > 1:
        first = set(sources[::2])
        sides = ([k for k in keys if k[0] in first], [k for k in keys if k[0] not in first])
    for which, side in enumerate(sides):
        if all_scenes or (reservoir and which == 1):
            pools.append({s["id"]: s for k in side for s in groups[k]})
            continue
        batches = []
        for key in side:
            chosen, used = [], set()
            for scene in sorted(groups[key], key=lambda s: sha256_of(s["id"])):
                mids = {m for turn in scene["refs"] for m in turn}
                if not used.intersection(mids):
                    chosen.append(scene)
                    used.update(mids)
                if len(chosen) == 4:
                    break
            batches.append(chosen)
        ordered = [batch[n] for n in range(4) for batch in batches if n < len(batch)]
        # Keep long transcripts within the reader's input budget.
        pool = {}
        chars = 0
        for scene in ordered[:cap]:
            size = sum(len(t) for turn in scene["turns"] for t in turn)
            if chars + size <= 36000:
                pool[scene["id"]] = scene
                chars += size
        pools.append(pool)
    return pools


def _cue_features(scene):
    # Rank by cues only. Never use the reply whose agreement is being tested.
    features = set()
    for i, turn in enumerate(scene["turns"][:3]):
        text = " ".join(turn).lower()
        for word in re.findall(r"[가-힣a-z0-9]+", text):
            features.add((i, word))
            features.update((i, word[j : j + 2]) for j in range(len(word) - 1))
        if "?" in text:
            features.add((i, "?"))
        for n, forms in enumerate(
            (
                "어디 어디서 어디임 어디노",
                "왜 뭐 뭘 뭐임 어떤 무슨 누구 ㄴㄱ",
                "얼마 몇 언제 얼마나",
                "아니 ㄴㄴ 아닌",
                "불가 못 안됨 안돼 안되",
                "괜찮 ㄱㅊ 됨 가능",
                "ㅋㅋ ㅎㅎ",
            )
        ):
            if any(x in text for x in forms.split()):
                features.add((i, "act" + str(n)))
    return features


def verification_pool(candidates, discover, reservoir):
    feats = {k: _cue_features(s) for k, s in reservoir.items()}
    df = Counter(f for fs in feats.values() for f in fs)
    weights = {f: min(5, 1 + math.log((len(feats) + 1) / (n + 1))) for f, n in df.items()}

    def sim(x, y):
        return sum(weights.get(v, 1) for v in x & y) / max(1, sum(weights.get(v, 1) for v in x | y))

    orders = []
    for _, support in candidates.values():
        examples = [_cue_features(discover[e["id"]]) for e in support]
        orders.append(
            sorted(feats, key=lambda k: (-max(sim(feats[k], v) for v in examples), sha256_of(k)))
        )
    # Mix with a fixed sample that was not retrieved as similar.
    orders.append(sorted(feats, key=sha256_of))
    pool, used, count, chars = {}, set(), Counter(), 0
    for group in zip(*orders, strict=True):
        for k in group:
            scene = reservoir[k]
            mids = {m for t in scene["refs"] for m in t}
            if used & mids or count[scene["conversation"]] >= 5:
                continue
            size = sum(len(x) for t in scene["turns"] for x in t)
            if chars + size > 36000:
                continue
            pool[k] = scene
            used.update(mids)
            count[scene["conversation"]] += 1
            chars += size
            if len(pool) >= 128:
                return pool
    return pool


def _refs(proposals, pool, start=0):
    evidence = {}
    for raw in proposals if isinstance(proposals, list) else []:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            continue
        scene = pool.get(raw["id"])
        quotes = raw.get("quotes")
        if not scene or not isinstance(quotes, list) or len(quotes) != 4 - start:
            continue
        refs = []
        for quote, texts, ids in zip(
            quotes, scene["turns"][start:], scene["refs"][start:], strict=True
        ):
            if not isinstance(quote, str) or not quote.strip():
                break
            match = next((mid for text, mid in zip(texts, ids, strict=True) if quote in text), None)
            if match is None:
                break
            refs.append(match)
        if len(refs) == 4 - start:
            evidence[scene["id"]] = {"id": scene["id"], "msgIds": refs, "quotes": quotes}
    return list(evidence.values())


def extract(rows, flagged, call):
    discover, reservoir = sample(rows, flagged, reservoir=True)
    result = dict(
        version=VERSION,
        rulesSha256=sha256_of([DISCOVER, CONFIRM]),
        discoveryScenes=list(discover),
        confirmScenes=[],
        confirmationCandidates=len(reservoir),
        rejected=[],
        patterns=[],
    )
    if len(discover) < 2 or not reservoir:
        return result

    def public(pool):
        return [{"id": k, "turns": s["turns"]} for k, s in pool.items()]

    raw = call("discover", DISCOVER, public(discover)).get("patterns")
    if not isinstance(raw, list):
        raise ValueError("특질 발견 응답에 patterns가 없다")
    candidates = {}
    for n, item in enumerate(raw[:4]):
        if not isinstance(item, dict) or not all(
            isinstance(item.get(k), str) and 0 < len(item[k].strip()) <= 220 for k in FIELDS
        ):
            continue
        support = _refs(item.get("support"), discover)
        if len({discover[x["id"]]["conversation"] for x in support}) >= 2:
            candidates[str(n)] = ({k: item[k].strip() for k in FIELDS}, support)
        else:
            result["rejected"].append(
                dict(
                    trait={k: item[k] for k in FIELDS},
                    discovery=support,
                    reason="insufficient_discovery",
                )
            )
    if not candidates:
        return result
    confirm = verification_pool(candidates, discover, reservoir)
    result["confirmScenes"] = list(confirm)
    reviews = call(
        "confirm",
        CONFIRM,
        {"patterns": {k: v[0] for k, v in candidates.items()}, "scenes": public(confirm)},
    ).get("reviews")
    if (
        not isinstance(reviews, list)
        or any(not isinstance(r, dict) for r in reviews)
        or sorted(str(r.get("key")) for r in reviews) != sorted(candidates)
    ):
        raise ValueError("특질 후보마다 독립 검토 결과 하나가 필요하다")
    for review in reviews:
        trait, support = candidates[str(review["key"])]
        positive = _refs(review.get("support"), confirm)
        counters = review.get("counter")
        # 반례 인용의 형식이 잘못돼도 반례 없음으로 취급하지 않는다.
        if not positive or counters != []:
            tails = _refs(review.get("tailSupport"), confirm, start=2)
            if tails and review.get("tailCounter") == [] and counters == []:
                result["patterns"].append(
                    dict(
                        scope="followup_only",
                        trait={"newCue": trait["newCue"], "nextMove": trait["nextMove"]},
                        discovery=[
                            {"id": x["id"], "msgIds": x["msgIds"][2:], "quotes": x["quotes"][2:]}
                            for x in support
                        ],
                        confirmation=tails,
                    )
                )
                continue
            result["rejected"].append(
                dict(
                    trait=trait,
                    discovery=support,
                    confirmation=positive,
                    counter=_refs(counters, confirm),
                )
            )
            continue
        result["patterns"].append(dict(trait=trait, discovery=support, confirmation=positive))
    return result


def analyze(ctx, cid, budget, rev, plan_rev):
    _, index, rows = load_approved_source(ctx, cid)
    digest = read_json(ctx.character_dir(cid) / "s0-source" / index.sourceRev / "digest.json")
    flagged = {f["msgId"] for f in digest["piiFlags"]}

    def call(step, rules, payload):
        judge = step == "confirm"
        model = ctx.judge_model(cid, budget) if judge else ctx.text_model(cid, budget)
        response = model.complete(
            ChatRequest(
                kind="JUDGE" if judge else "AGENT",
                stage="s8",
                ref=f"{cid}/{rev}/response-traits/{step}",
                temperature=0.0,
                max_output_tokens=6000,
                response_json=True,
                messages=(
                    Message("system", rules),
                    Message("user", json.dumps(payload, ensure_ascii=False)),
                ),
            )
        )
        return extract_json_object(response.text)

    if ctx.config.stage("s8").get("trait_method", "focus") == "contrast":
        from character_factory_poc.stages.s8_prompts.contrast_pairs import analyze_pairs
    else:
        from character_factory_poc.stages.s8_prompts.focus_pairs import analyze_pairs

    return {**analyze_pairs(rows, flagged, call), "sourceRev": index.sourceRev}
