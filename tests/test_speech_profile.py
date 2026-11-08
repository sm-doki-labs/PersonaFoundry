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
    assert lines[0].startswith("말높임: 상대에게는 존댓말을 기본으로 쓴다.")
    assert "'~다'로 끝나는 글말 문장은 쓰지 않는다." in lines[0]
    assert "'~것 같아요'" in text and "담화 표지:" in text and "'좀'" in text
    assert "'~구나'로 받지 않는다" in text and "길이: 일상 대화에서는" in text
    assert "첫마디 다음 문장에서도" in text
    assert "웃음 표기(ㅋㅋ)나 이모티콘은 거의 쓰지 않는다" in text
    # 원문 문장을 그대로 옮기지 않는다.
    assert all(a not in text for a in POLITE_ANSWERS)
    assert "말투 예시" not in text


def test_casual_chat_with_laughter():
    rows, kinds = _corpus(CASUAL_ANSWERS, kind="KAKAO_EXPORT")
    lines = render_voice_definition(build_speech_profile(rows, kinds))
    text = "\n".join(lines)
    assert lines[0] == "말높임: 상대에게 반말을 기본으로 쓴다."
    assert "자기 지칭: '나', '내가'를 쓴다." in text
    assert "표기: 웃음 표기나 이모티콘을 메시지" in text


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
    assert "길이에 따라 다르다" in text
    assert "짧은 답(40자 미만)에서는 열에 하나도 안 되게" in text
    assert "(150자 이상)에서는 거의 모두 정도다" in text


def test_guna_rule_is_skipped_when_the_source_uses_it():
    rows, kinds = _corpus(("아 그러셨구나.", "네, 저도 그래요."), n=40)
    profile = build_speech_profile(rows, kinds)
    assert profile["gunaSentenceEndings"] == 20
    assert "'~구나'로 받지 않는다" not in "\n".join(render_voice_definition(profile))


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
    assert "말결:" in text and "한두 마디 짧은 답이 0~1번" in text
    assert "고쳐 잇는 일이 거의 모두 정도 있다" in text
    assert "바로 답할 수 있는 짧은 말에는 표지를 붙이지 않는다" not in text
