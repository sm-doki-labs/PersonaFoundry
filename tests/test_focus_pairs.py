from character_factory_poc.stages.s8_prompts.focus_pairs import analyze_pairs


def corpus():
    return [
        dict(textId="s", convId=str(n), msgId=f"{n}/{j}", speaker=role, text=f"{role} {n}")
        for n in range(12)
        for j, role in enumerate(["USER", "SUBJECT"])
    ]


def extract(vtopic="기술", wrong=False, conflicting=False):
    def proof(scene, topic):
        return dict(id=scene["id"], at=[0, 0], topic={"식생활": 5, "기술": 0, "기타": 12}[topic])

    def model(step, rules, payload):
        if step == "discover":
            return dict(
                patterns=[
                    dict(
                        cue="기준이 모호할 때",
                        focus="기준",
                        move="비교해서 확인",
                        boundary="관찰된 대화",
                        support=[proof(s, "식생활") for s in payload[:2]],
                    )
                ]
            )
        p = proof(payload["scenes"][0], vtopic)
        if wrong:
            p["at"][1] = 99
        return dict(reviews=[dict(key="0", support=[p], counter=[p] if conflicting else [])])

    return analyze_pairs(corpus(), set(), model)


def test_cross_topic_pattern_even_when_all_source_dialogues_have_only_two_turns():
    r = extract()
    assert r["patterns"][0]["discoveryTopics"] == ["식생활"]
    assert r["patterns"][0]["confirmationTopics"] == ["기술"]
    assert len(set(r["discoveryScenes"]) & set(r["confirmScenes"])) == 0


def test_no_generalizing_same_topic_or_unverified_alignment():
    for r in (extract("식생활"), extract("기타"), extract(wrong=True), extract(conflicting=True)):
        assert not r["patterns"] and r["rejected"]


def test_flagged_answer_removes_pair():
    r = analyze_pairs(corpus(), {f"{i}/1" for i in range(12)}, lambda *a: 1 / 0)
    assert not r["discoveryScenes"] and not r["confirmScenes"]


def test_discovery_and_confirmation_never_share_interview_file():
    from character_factory_poc.stages.s8_prompts.response_traits import sample

    data = [{**r, "textId": "file-" + str(int(r["convId"]) // 3)} for r in corpus()]
    d, v = sample(data, set(), pair=True)
    assert d and v
    assert {s["conversation"][0] for s in d.values()}.isdisjoint(
        {s["conversation"][0] for s in v.values()}
    )
