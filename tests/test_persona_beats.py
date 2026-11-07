from character_factory_poc.contracts.dialogue_beats import FormationBeats
from character_factory_poc.stages.s7_traits.beats import check_beats


def beats_fixture():
    rows = []
    for i in range(12):
        category = "ordinary" if i < 8 else "boundary" if i < 10 else "change"
        rows.append(
            dict(
                dialogueId=f"d{i:02}",
                category=category,
                coverageTags=["ordinary", "emotion", "decision", "change"],
                relationship="close",
                scene="부탁의 조건을 확인한다",
                turns=[
                    dict(
                        turnId=f"d{i}-u",
                        role="user",
                        act="부탁한다",
                        facts=[],
                        tone="평온",
                        decisionRuleIds=[],
                        stateBefore={},
                        stateAfter={},
                    ),
                    dict(
                        turnId=f"d{i}-a",
                        role="assistant",
                        act="조건을 보고 거절한다",
                        facts=[],
                        tone="차분",
                        decisionRuleIds=["c1"],
                        stateBefore={},
                        stateAfter={"request": "refused"},
                    ),
                ],
            )
        )
    for i, row in enumerate(rows):
        for j in range(1, 6 if i < 2 else 2):
            for role in ("user", "assistant"):
                row["turns"].append(
                    dict(
                        turnId=f"d{i}-{role}-{j}",
                        role=role,
                        act="추가 조건을 확인한다" if role == "user" else "확인한 조건에 답한다",
                        facts=[],
                        tone="차분",
                        decisionRuleIds=[],
                        stateBefore={},
                        stateAfter={},
                    )
                )
    return FormationBeats(
        characterId="cf-a",
        traitRevision="tr1",
        planSha256="1" * 64,
        blueprintSha256="2" * 64,
        choiceSha256="3" * 64,
        dialogues=rows,
    )


def test_beats_preserve_approved_choice():
    beats = beats_fixture()
    assert not check_beats(beats, character_id="cf-a", rule_ids={"c1"})
    assert check_beats(beats, character_id="cf-other", rule_ids={"c1"})
    assert check_beats(beats, character_id="cf-a", rule_ids={"c9"})


def test_local_facts_keep_owner_and_scope():
    raw = beats_fixture().model_dump()
    raw["dialogues"][0]["turns"][0]["facts"] = [
        dict(id="f1", text="오늘은 바쁘다", owner="user", scope="example-local", sourceRef=None)
    ]
    parsed = FormationBeats.model_validate(raw)
    fact = parsed.dialogues[0].turns[0].facts[0]
    assert fact.owner == "user" and fact.scope == "example-local"
    raw["dialogues"][0]["turns"][0]["facts"][0]["scope"] = "canon"
    assert check_beats(FormationBeats.model_validate(raw), character_id="cf-a", rule_ids={"c1"})


def test_untriggered_rule_does_not_force_boundary():
    raw = beats_fixture().model_dump()
    raw["dialogues"][0]["turns"][1]["decisionRuleIds"] = []
    raw["dialogues"][0]["turns"][1]["act"] = "인사에 짧게 답한다"
    assert not check_beats(FormationBeats.model_validate(raw), character_id="cf-a", rule_ids={"c1"})


def test_bad_role_order_or_duplicate_turn_id_is_rejected():
    raw = beats_fixture().model_dump()
    raw["dialogues"][0]["turns"][1]["role"] = "user"
    assert check_beats(FormationBeats.model_validate(raw), character_id="cf-a", rule_ids={"c1"})


def test_canon_fact_cannot_self_assert_its_source():
    raw = beats_fixture().model_dump()
    raw["dialogues"][0]["turns"][0]["facts"] = [
        dict(
            id="f",
            text="자작 원본 사실",
            owner="character",
            scope="canon",
            sourceRef=dict(
                kind="plan",
                ref="fake.json",
                version="pr1",
                sha256="1" * 64,
                fieldPath="job",
                quote="자작 사실",
            ),
        )
    ]
    assert check_beats(FormationBeats.model_validate(raw), character_id="cf-a", rule_ids={"c1"})


def test_beats_require_two_pairs_and_two_six_pair_scenes():
    raw = beats_fixture().model_dump()
    raw["dialogues"][0]["turns"] = raw["dialogues"][0]["turns"][:2]
    assert check_beats(FormationBeats.model_validate(raw), character_id="cf-a", rule_ids={"c1"})
    raw = beats_fixture().model_dump()
    for dialogue in raw["dialogues"]:
        dialogue["turns"] = dialogue["turns"][:4]
    assert check_beats(FormationBeats.model_validate(raw), character_id="cf-a", rule_ids={"c1"})
