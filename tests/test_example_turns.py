from character_factory_poc.stages.s8_prompts.example_turns import (
    BRIDGE,
    build,
    exchanges,
    pick,
    system_text,
)


def rows(sources=3, per=10, long_every=5):
    out = []
    for s in range(sources):
        for i in range(per):
            reply = "가" * (200 if i % long_every == 0 else 10 + i)
            for j, (speaker, text) in enumerate(
                (("USER", f"질문 {s}-{i}"), ("SUBJECT", reply + f"{s}{i}"))
            ):
                out.append(
                    dict(
                        textId=f"src{s}",
                        convId=f"c{i}",
                        msgId=f"{s}-{i}-{j}",
                        speaker=speaker,
                        text=text,
                    )
                )
    return out


def test_one_exchange_per_source_before_any_repeat_and_short_replies_for_other_medium():
    cap, chosen = pick(rows(), set(), 5, same_medium=False, seed="s")
    assert len(chosen) == 5 and {p["source"] for p in chosen[:3]} == {"src0", "src1", "src2"}
    assert cap < 200 and all(len(p["reply"]) <= cap for p in chosen)
    again = pick(rows(), set(), 5, same_medium=False, seed="s")[1]
    assert [p["msgId"] for p in chosen] == [p["msgId"] for p in again]
    assert [p["msgId"] for p in pick(rows(), set(), 5, same_medium=False, seed="t")[1]] != [
        p["msgId"] for p in chosen
    ]


def test_same_medium_keeps_long_replies_and_single_source_samples_without_repeats():
    data = rows(sources=1, per=12, long_every=2)
    cap, chosen = pick(data, set(), 12, same_medium=True, seed="s")
    assert cap == 450 and len({p["msgId"] for p in chosen}) == 12
    assert any(len(p["reply"]) > 100 for p in chosen)


def test_flagged_third_party_media_and_time_gaps_never_form_an_exchange():
    data = [
        dict(
            textId="t", convId="c", msgId="1", speaker="USER", text="처음", at="2026-01-01T10:00:00"
        ),
        dict(
            textId="t",
            convId="c",
            msgId="2",
            speaker="OTHER",
            text="끼어듦",
            at="2026-01-01T10:00:10",
        ),
        dict(
            textId="t",
            convId="c",
            msgId="3",
            speaker="SUBJECT",
            text="답1",
            at="2026-01-01T10:00:20",
        ),
        dict(
            textId="t", convId="c", msgId="4", speaker="USER", text="둘째", at="2026-01-01T10:01:00"
        ),
        dict(
            textId="t",
            convId="c",
            msgId="5",
            speaker="SUBJECT",
            text="사진",
            at="2026-01-01T10:01:10",
        ),
        dict(
            textId="t", convId="c", msgId="6", speaker="USER", text="셋째", at="2026-01-01T10:02:00"
        ),
        dict(
            textId="t",
            convId="c",
            msgId="7",
            speaker="SUBJECT",
            text="늦은 답",
            at="2026-01-01T12:00:00",
        ),
        dict(
            textId="t", convId="c", msgId="8", speaker="USER", text="넷째", at="2026-01-01T12:00:10"
        ),
        dict(
            textId="t",
            convId="c",
            msgId="9",
            speaker="SUBJECT",
            text="비공개",
            at="2026-01-01T12:00:20",
        ),
        dict(
            textId="t",
            convId="c",
            msgId="10",
            speaker="USER",
            text="다섯째",
            at="2026-01-01T12:00:30",
        ),
        dict(
            textId="t",
            convId="c",
            msgId="11",
            speaker="USER",
            text="이어서",
            at="2026-01-01T12:00:40",
        ),
        dict(
            textId="t",
            convId="c",
            msgId="12",
            speaker="SUBJECT",
            text="답2",
            at="2026-01-01T12:00:50",
        ),
        dict(
            textId="t",
            convId="c",
            msgId="13",
            speaker="SUBJECT",
            text="덧붙임",
            at="2026-01-01T12:00:55",
        ),
    ]
    found = exchanges(data, {"9"})
    assert [(p["user"], p["reply"]) for p in found] == [("다섯째 이어서", "답2 덧붙임")]


def test_system_keeps_identity_paragraph_and_facts_but_drops_behaviour_guidance():
    text = system_text("정체성과 경계.\n\n행동 지침은 길다.", "사실 한 줄")
    assert text.startswith("정체성과 경계.") and "행동 지침" not in text
    assert BRIDGE in text and text.endswith("[확인된 설정과 정보]\n사실 한 줄")
    assert build([], set(), "a\n\nb", "f", 5, same_medium=True, seed="s") is None
