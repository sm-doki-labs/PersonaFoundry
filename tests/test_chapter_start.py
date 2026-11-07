"""D-0089: 챕터 시작 설정 계약·검사와 서비스 내보내기 연결."""

from character_factory_poc.common.schema import validate
from character_factory_poc.stages.export.doki_app.chat_svc import _chapter_asset, _profile
from character_factory_poc.stages.s8_prompts.chapter_start import _example, check_chapter_start


def _start(level="POLITE", posture="골목 빵집 작업대에서 반죽을 정리하다 통화를 받았다."):
    raw = _example("cf-20260101-x", "pr1")
    for ch in raw["chapters"]:
        ch["sceneFacts"] = [
            "인물은 마감 뒤 작업대 앞에 있다.",
            "상대는 다른 곳에서 영상통화를 걸었다.",
        ]
        ch["sceneBoundaries"] = ["장소 이동이나 행동 지문을 만들지 않는다."]
        rel = ch["relationship"]
        rel.update(
            speechLevel=level,
            addresseeStance="인물은 해요체로 상대를 대하고 호칭을 생략한다.",
            entryPosture=[posture],
            presenceReason="마감을 마친 뒤 걸려 온 통화를 받았다.",
            initiativePolicy="인물은 빵 이야기를 먼저 꺼낼 수 있다.",
            expressionDelta=["인물은 자기 하루를 조금 더 길게 이야기한다."],
            sceneWant="인물은 상대의 하루를 조용히 듣고 싶다.",
            moodRange={k: "인물은 차분하다." for k in ("down", "start", "middle", "top")},
        )
    return validate("chapter-start-v1", raw)


def test_check_follows_the_plan_speech_level_and_rejects_quotes():
    check = check_chapter_start("말끝을 정갈하게 맺는 해요체.")
    assert check(_start()) == []
    assert any("speechLevel" in p for p in check(_start(level="CASUAL")))
    quoted = _start(posture="인물은 \u201c어서 와요\u201d라고 말할 준비를 한다.")
    assert any("따옴표" in p for p in check(quoted))


def test_export_uses_generated_start_instead_of_template():
    from character_factory_poc.common.schema import dump
    from character_factory_poc.contracts.release import Chapter

    start = dump(_start())["chapters"][0]
    chapter = Chapter(
        chapterNo=1,
        chapterId="ch1",
        title="친해지기",
        relationshipStage="STRANGER",
        facts="chapters/ch1/facts.json",
        frame="chapters/ch1/frame.png",
    )
    facts = {"chapterStart": start, "sceneFacts": ["틀 문장"]}
    profile = _profile("x", chapter, "K", "x-ch1-r1", {"entry": "STRANGER"}, facts, {}, "인물")
    asset = _chapter_asset("x-ch1-context-v1", "K", chapter, facts)
    assert profile["speechLevel"] == "POLITE"
    assert profile["sceneWant"] == start["relationship"]["sceneWant"]
    assert asset["sceneFacts"] == start["sceneFacts"]
