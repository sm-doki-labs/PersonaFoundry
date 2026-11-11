from character_factory_poc.stages.s8_prompts.response_traits import extract, sample


def rows():
    out = []
    for i in range(12):
        for n, (speaker, text) in enumerate(
            [
                ("USER", f"처음 단서 {i}"),
                ("SUBJECT", "짧게"),
                ("SUBJECT", "되묻기"),
                ("USER", "조건 변경"),
                ("SUBJECT", f"다시 판단 {i}"),
            ]
        ):
            out.append(
                dict(msgId=f"{i}-{n}", convId=f"c{i}", textId="t", speaker=speaker, text=text)
            )
    return out


def proof(s):
    return {"id": s["id"], "quotes": [t[-1] for t in s["turns"]]}


def test_never_bridge_flagged_or_third_party_and_keep_bursts():
    data = rows()
    data[8]["speaker"] = "OTHER"
    a, b = sample(data, {"0-3"})
    assert len(a) + len(b) == 10 and not set(a) & set(b)
    for s in [*a.values(), *b.values()]:
        assert s["turns"][1] == ["짧게", "되묻기"]
        assert s["id"] not in {"0-0", "1-0"}


def test_only_independently_grounded_sequences_promoted():
    fields = dict(cue="단서", firstMove="첫 반응", newCue="변화", nextMove="전환", limit="범위")

    def mock(step, rules, payload):
        if step == "discover":
            return {
                "patterns": [
                    {**fields, "support": [proof(payload[0]), proof(payload[1])]} for _ in range(4)
                ]
            }
        good = proof(payload["scenes"][0])
        mixed = dict(good, quotes=[*good["quotes"][:3], "여기에 없는 해석"])
        reused = proof(next(iter(sample(rows(), set())[0].values())))
        return {
            "reviews": [
                dict(key=k, support=[e], counter=c)
                for k, e, c in [
                    ("0", good, []),
                    ("1", mixed, []),
                    ("2", good, [good]),
                    ("3", reused, []),
                ]
            ]
        }

    r = extract(rows(), set(), mock)
    assert len(r["patterns"]) == 1 and len(r["rejected"]) == 3
    ok = r["patterns"][0]
    assert ok["discovery"][0]["id"] != ok["confirmation"][0]["id"]
    assert len(ok["confirmation"][0]["msgIds"]) == 4


def test_single_conversation_is_not_recurrence():
    def fail(*_):
        raise AssertionError("근거가 모자라면 모델을 부르지 않는다")

    assert not extract(rows()[:5], set(), fail)["patterns"]


def test_many_clips_from_one_chat_or_repeating_a_reference_never_qualify():
    def mock(step, rules, payload):
        assert step == "discover"
        one = proof(payload[0])
        fields = dict(
            cue="첫 질문", firstMove="확인", newCue="설명", nextMove="수정", limit="이 관계에서"
        )
        return {"patterns": [{**fields, "support": [one, one]}]}

    r = extract(rows(), set(), mock)
    assert not r["patterns"] and r["rejected"][0]["reason"] == "insufficient_discovery"


def test_no_conversation_or_overlapping_turn_appears_on_both_sides():
    data = rows() + [{**r, "msgId": r["msgId"] + "x", "text": r["text"] + "!"} for r in rows()]
    a, b = sample(data, set())
    assert {s["conversation"] for s in a.values()}.isdisjoint(s["conversation"] for s in b.values())
    all_refs = [m for pool in (a, b) for s in pool.values() for t in s["refs"] for m in t]
    assert len(all_refs) == len(set(all_refs))


def test_retrieval_does_not_consult_withheld_response():
    from copy import deepcopy

    from character_factory_poc.stages.s8_prompts.response_traits import verification_pool

    a, b = sample(rows(), set(), reservoir=True)
    candidates = {"0": ({}, [{"id": next(iter(a))}])}
    changed = deepcopy(b)
    for scene in changed.values():
        scene["turns"][3] = ["완전히 딴 말"]
    assert list(verification_pool(candidates, a, b)) == list(
        verification_pool(candidates, a, changed)
    )


def test_confirming_only_last_exchange_never_promotes_first_move_or_out_of_turn_quote():
    fields = dict(cue="단서", firstMove="초반", newCue="새 질문", nextMove="새 답", limit="조건")

    def mock(step, rules, payload):
        if step == "discover":
            return {"patterns": [{**fields, "support": [proof(s) for s in payload[:2]]}] * 2}
        scene = payload["scenes"][0]
        quotes = proof(scene)["quotes"]
        return {
            "reviews": [
                dict(
                    key=k,
                    support=[],
                    counter=[],
                    tailCounter=[],
                    tailSupport=[{"id": scene["id"], "quotes": sample_quotes}],
                )
                for k, sample_quotes in [("0", quotes[2:]), ("1", quotes[:2])]
            ]
        }

    r = extract(rows(), set(), mock)
    assert len(r["patterns"]) == len(r["rejected"]) == 1
    p = r["patterns"][0]
    assert p["scope"] == "followup_only" and set(p["trait"]) == {"newCue", "nextMove"}
    assert len(p["confirmation"][0]["msgIds"]) == 2


def test_frequency_requires_replication_across_conversations(monkeypatch):
    from character_factory_poc.stages.s8_prompts import transition_rates as rates

    def make_pool(prefix, reversed_outcome=False):
        result = {}
        tags = []
        for i in range(48):
            scene_id = f"{prefix}-{i}"
            on = i % 2 == 1
            result[scene_id] = dict(
                id=scene_id,
                conversation=f"{prefix}-{i // 8}",
                refs=[[scene_id + str(j)] for j in range(4)],
                turns=[["시작"], ["첫 반응"], ["질문?" if on else "알림"], ["후속 반응"]],
            )
            tags.extend(
                [
                    dict(id=scene_id + "1", moves=["ASK_BACK"]),
                    dict(
                        id=scene_id + "3",
                        moves=["OWN_EXPERIENCE"] if on != reversed_outcome else [],
                    ),
                ]
            )
        return result, tags

    for flipped in (False, True):
        a, t = make_pool("a")
        b, u = make_pool("b", flipped)
        monkeypatch.setattr(rates, "sample", lambda *args, pools=(a, b), **kwargs: pools)
        results = rates.measure([], set(), t + u)
        assert bool(results) is not flipped
        if results:
            assert results[0]["confirmation"]["withCue"]["conversations"] == 6
