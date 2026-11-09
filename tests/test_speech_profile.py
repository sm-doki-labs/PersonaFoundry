"""D-0145 모티브 말버릇 정의: 원문 통계 → 말투 칸. 모든 발화는 합성 자료다."""

from __future__ import annotations

from character_factory_poc.stages.s3_plan.speech_profile import (
    _josa,
    build_speech_profile,
    render_voice_definition,
)
from character_factory_poc.stages.s8_prompts.twin import voice_lines

QUESTIONS = ("오늘 훈련 어땠어요?", "요즘 뭐 먹어요?", "주말엔 뭐 해요?", "힘들지 않아요?")
POLITE_ANSWERS = (
    "네, 뭐 오늘은 좀 괜찮았던 것 같아요.",
    "아 진짜 맛있는 거 먹었죠.",
    "저는 그냥 집에서 쉬는 편이에요.",
    "그렇죠, 좀 힘들긴 한데 괜찮아요.",
    "제가 사실 운동을 좋아하거든요.",
)
CASUAL_ANSWERS = (
    "응 밥 먹었어 ㅋㅋ",
    "나 오늘 일찍 잘 거야",
    "내가 내일 전화할게",
    "그냥 집에 있어 ㅋㅋ",
    "뭐 별일 없지",
)


def _corpus(answers, *, kind="TRANSCRIPT", text_id="t1", n=40):
    rows, kinds = [], {text_id: kind}
    for i in range(n):
        conv = f"{text_id}-c{i:04d}"
        rows.append(
            dict(
                msgId=f"{text_id}-{2 * i + 1:05d}",
                convId=conv,
                speaker="USER",
                text=QUESTIONS[i % 4],
            )
        )
        rows.append(
            dict(
                msgId=f"{text_id}-{2 * i + 2:05d}",
                convId=conv,
                speaker="SUBJECT",
                text=answers[i % len(answers)],
            )
        )
    return rows, kinds


def test_polite_spoken_source_becomes_a_definition_without_quotes():
    rows, kinds = _corpus(POLITE_ANSWERS)
    profile = build_speech_profile(rows, kinds)
    assert profile["politeShare"] == 1.0
    assert profile["answers"]["scope"] == "CONVERSATION"
    assert profile["answers"]["gunaOpenings"] == 0
    assert profile["gunaSentenceEndings"] == 0
    lines = render_voice_definition(profile)
    text = "\n".join(lines)
    assert lines[0].startswith("상대높임 등급: 해요체")
    assert "담화 표지:" in text and "'좀'" in text
    assert "'-구나'로 되받는 일은 드물다" in text and "발화 길이:" in text
    assert "표기: 웃음 표기와 이모티콘은 일상 발화의 0%" in text
    # 견본 후보가 여섯 개 미만이면 원문을 넣지 않는다.
    assert all(a not in text for a in POLITE_ANSWERS)
    assert "말투 예시" not in text


def test_casual_chat_with_laughter():
    rows, kinds = _corpus(CASUAL_ANSWERS, kind="KAKAO_EXPORT")
    lines = render_voice_definition(build_speech_profile(rows, kinds))
    text = "\n".join(lines)
    assert lines[0].startswith("상대높임 등급: 반말")
    assert "표기: 웃음 표기와 이모티콘은 일상 발화의 40%" in text


def test_articles_are_not_counted():
    rows, kinds = _corpus(("감사하다는 말을 전하고 싶다.",), kind="ARTICLE", text_id="a1")
    profile = build_speech_profile(rows, kinds)
    assert profile["subjectMessages"] == 0
    # 통계를 낼 수 없으면 사람이 승인한 말투 요약과 공통 끝 문장만 쓴다.
    closing = render_voice_definition(profile)[-1]
    assert render_voice_definition(profile, "해요체로 말한다.") == ["해요체로 말한다.", closing]


def test_small_source_falls_back_to_the_approved_summary():
    rows, kinds = _corpus(POLITE_ANSWERS, n=3)
    profile = build_speech_profile(rows, kinds)
    voice = {
        "speechProfile": profile,
        "speechEndings": {"politeEnding": 3, "casualEnding": 0, "unclassified": 0},
    }
    lines = voice_lines("한 문장으로 먼저 제안한다.", voice)
    assert lines[0] == "기본 말높임: 존댓말."
    assert lines[1] == "한 문장으로 먼저 제안한다."
    assert len(lines) == 3


def test_josa_follows_the_final_consonant():
    assert _josa("사실", "을", "를") == "을"
    assert _josa("진짜", "을", "를") == "를"
    assert _josa("그래서", "으로", "로") == "로"
    assert _josa("근데", "이", "가") == "가"
    assert _josa("일단은", "으로", "로") == "으로"
    assert _josa("마을", "으로", "로") == "로"


def test_hedging_is_written_per_length_band():
    short = "네, 괜찮아요."
    medium = "저는 그냥 집에서 쉬는 편인데, 요즘은 날이 좋아서 좀 걷는 게 제일 좋은 것 같아요."
    assert 40 <= len(medium) < 150 and len(short) < 40
    long = (
        "사실 경기 끝나고 나면 이제 몸이 진짜 무겁고 생각이 많아지는데, 그래도 또 다음 경기가 "
        "있으니까 회복하는 데 제일 신경을 쓰고 있고, 그렇게 하루하루 버티다 보면 "
        "결국에는 좋은 결과가 따라오는 것 같아요. 그래서 저는 요즘 잠도 일찍 자고 "
        "먹는 것도 많이 신경을 쓰고 있어요."
    )
    assert len(long) >= 150
    rows, kinds = _corpus((short, medium, long), n=90)
    profile = build_speech_profile(rows, kinds)
    bands = profile["hedgeByLength"]
    assert bands["short"]["share"] == 0.0 and bands["long"]["share"] == 1.0
    text = "\n".join(render_voice_definition(profile))
    assert "완화 표현: 생각이나 느낌을 길게 풀 때" in text
    assert "긴 발화의 100%" in text


def test_guna_rule_is_skipped_when_the_source_uses_it():
    rows, kinds = _corpus(("아 그러셨구나.", "네, 저도 그래요."), n=40)
    profile = build_speech_profile(rows, kinds)
    assert profile["gunaSentenceEndings"] == 20
    assert "'-구나'로 받는 답은 50%" in "\n".join(render_voice_definition(profile))


def test_texture_line_writes_filler_counts_per_length_band():
    short = "네, 괜찮아요."
    medium = "뭐 저는 그냥 집에서 쉬는 편인데, 요즘은 날이 좋아서 좀 걷는 게 제일 좋은 것 같아요."
    long = (
        "뭐 사실 경기 끝나고 나면 이제 몸이 진짜 무겁고 생각이 많아지는데, 그래도 또 다음 경기가 "
        "있으니까 이제 회복하는 데 제일 신경을 쓰고 있고, 그렇게 그렇게 하루하루 버티다 보면 "
        "뭐 결국에는 좋은 결과가 따라오는 것 같아요. 그래서 저는 요즘 잠도 좀 일찍 자고 "
        "먹는 것도 많이 신경을 쓰고 있어요."
    )
    rows, kinds = _corpus((short, medium, long), n=90)
    profile = build_speech_profile(rows, kinds)
    bands = profile["fillerByLength"]
    assert bands["short"]["avgPerAnswer"] == 0 and bands["long"]["avgPerAnswer"] >= 5
    assert bands["long"]["repeatShare"] == 1.0
    text = "\n".join(render_voice_definition(profile))
    assert "담화 표지:" in text and "짧은 답의 군말은 0~1번" in text
    assert "150자 넘게 풀어 말할 때 군말은" in text and "반복:" in text
    assert "바로 답할 수 있는 짧은 말에는 표지를 붙이지 않는다" not in text


def test_register_overrides_kind_and_habit_rate_counts_answers():
    from types import SimpleNamespace

    from character_factory_poc.stages.s3_plan.speech_profile import source_registers

    everyday, k1 = _corpus(
        ("무척 무척 좋아해요.", "그게 좋아요.", "그게 좋아요."), kind="INTERVIEW", n=60
    )
    press, k2 = _corpus(("무척 기쁩니다.",), kind="TRANSCRIPT", text_id="t2", n=40)
    texts = [
        SimpleNamespace(textId="t1", kind="INTERVIEW", register="CASUAL"),
        SimpleNamespace(textId="t2", kind="TRANSCRIPT", register="FORMAL"),
        SimpleNamespace(textId="old", kind="INTERVIEW"),
    ]
    regs = source_registers(texts)
    assert regs["old"] == "FORMAL"
    p = build_speech_profile(press + everyday, k1 | k2, regs, ["무척"])
    assert p["casual"]["answers"]["count"] == 60 and p["formal"]["subjectMessages"] == 40
    rendered = render_voice_definition(p)
    assert next(s for s in rendered if s.startswith("강조 부사:")) == (
        "강조 부사: '무척' 가운데 하나를 골라 서너 답에 한 번꼴로, 한 답에 하나까지 쓴다."
    )
    assert "소감·각오" in rendered[0] and "0%" in rendered[0]


def test_samples_are_distinct_whole_casual_replies():
    good = (
        "네 저는 잘 모르겠어요.",
        "근데 그건 좀 어렵죠.",
        "사실 그게 더 좋아요.",
        "저도 그렇게 생각했어요.",
        "응 그건 좀 괜찮아.",
        "그래도 그게 맞지.",
        "왜 그렇게 했어?",
        "혹시 그건 좀 어렵나요?",
        "그럼 제가 해요.",
        "아 이거 정말 좋네요.",
    )
    rejected = ("오늘 한도윤을 만났어요.", "부산에서 3년 있었어요.", "별빛전자에서 일했어요.")
    rows, kinds = _corpus(good + rejected, n=52)
    press, extra = _corpus(("저는 그게 더 좋네요.",), kind="INTERVIEW", text_id="press")
    pairs = [rows[i : i + 2] for i in range(0, len(rows), 2)]
    samples = build_speech_profile(rows + press, kinds | extra)["samples"]
    assert 6 <= len(samples) == len(set(samples)) <= 8
    assert set(samples) <= set(good)
    assert (
        samples
        == build_speech_profile([r for pair in reversed(pairs) for r in pair], kinds)["samples"]
    )


def test_formal_only_keeps_previous_voice_definition():
    rows, kinds = _corpus(POLITE_ANSWERS, kind="INTERVIEW")
    p = build_speech_profile(rows, kinds)
    lines = render_voice_definition(p)
    assert lines[0].startswith("말높임:") and not p["samples"]
    assert lines == render_voice_definition(
        {k: v for k, v in p.items() if k not in {"casual", "formal", "samples"}}
    )


def test_created_sheet_voice_preserves_approved_text():
    from character_factory_poc.common.schema import validate
    from character_factory_poc.stages.s8_prompts.actor_persona import compose_approved_sheet
    from tests.support.flow import v2_plan
    from tests.support.synthetic import trait_sheet

    cid = "cf-20260101-original"
    plan = v2_plan(cid)
    sheet = validate("trait-sheet-v1", trait_sheet(cid, "pr1"))
    _, sections = compose_approved_sheet(plan, sheet, rules_text="")
    assert sections["PERSONA / VOICE"] == plan["voiceSummary"]


def test_son_approved_source_renders_every_category():
    import json
    from pathlib import Path

    import pytest

    root = Path(
        "/Users/johnhuh619/projects/character-factory-poc/runs/characters/cf-20261109-son-v6"
    )
    if not root.exists():
        pytest.skip("로컬에 손흥민 승인 원문이 없다")
    gate = json.loads((root / "state.json").read_text())["gates"]["G0"]
    assert gate["status"] == "APPROVED"
    folder = root / "s0-source" / gate["rev"]
    texts = json.loads((folder / "source-index.json").read_text())["texts"]
    rows = list(map(json.loads, (folder / "corpus.jsonl").read_text().splitlines()))
    p = build_speech_profile(
        rows,
        {t["textId"]: t["kind"] for t in texts},
        {t["textId"]: t.get("register") for t in texts},
    )
    lines = voice_lines("", {"speechProfile": p})
    assert [s.split(":")[0] for s in lines if ":" in s] == [
        "상대높임 등급",
        "발화 길이",
        "절 연결",
        "완화 표현",
        "담화 표지",
        "강조 부사",
        "반복",
        "발화 개시어",
        "응답 방식",
        "표기",
        "말의 결 견본",
    ]
    assert 6 <= len(p["samples"]) <= 8
