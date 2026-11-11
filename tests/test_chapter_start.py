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


def test_fan_frame_survives_three_full_boundaries_and_other_templates_keep_bytes():
    from character_factory_poc.stages.s8_prompts.chapter_start import _fan_call_frame

    for template in ("FAMILY_CALL", None):
        candidate = _start()
        before = candidate.model_dump_json()
        assert _fan_call_frame(candidate, template, "나리").model_dump_json() == before

    for name, subject in (("나리", "나리가"), ("새봄", "새봄이")):
        candidate = _start()
        for ch in candidate.chapters:
            ch.sceneBoundaries = [
                "통화 안에 머문다.",
                "장소를 정하지 않는다.",
                "지문을 쓰지 않는다.",
            ]
        for ch in _fan_call_frame(candidate, "FAN_CALL", name).chapters:
            assert "첫인사 때 한 번" in ch.relationship.initiativePolicy
            assert "지문을 쓰지 않는다." in ch.sceneBoundaries[-2]
            assert ch.sceneBoundaries[-1] == (
                f"지금부터 너의 출력은 {subject} 영상통화에서 소리 내어 하는 말 그 자체다. "
                "계획, 메모, 규칙 요약, 따옴표로 묶은 초안은 쓰지 않고 "
                f"첫 글자부터 {name}의 말로 시작한다."
            )


def test_source_template_selects_fan_frame_in_saved_chapters(tmp_path):
    from character_factory_poc.common.store import read_json
    from character_factory_poc.pipeline.approve import approve_gate
    from character_factory_poc.stages.s3_plan.twin import run_s3_twin
    from character_factory_poc.stages.s7_traits.sheet import run_s7
    from character_factory_poc.stages.s8_prompts.chapter_start import run_chapter_start
    from tests.support.web_gates import trait_sheet_for
    from tests.test_twin_s3 import _ready

    ctx, model, cid = _ready(tmp_path, template="FAN_CALL")
    run_s3_twin(ctx, cid)
    approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "시험"})
    model.add("AGENT", lambda req: trait_sheet_for(ctx, cid))
    run_s7(ctx, cid)
    model.add("AGENT", _start().model_dump() | {"characterId": cid})
    chapters = read_json(run_chapter_start(ctx, cid))["chapters"]
    assert all(ch["sceneBoundaries"][-1].startswith("지금부터 너의 출력은") for ch in chapters)
    assert all("첫인사 때 한 번" in ch["relationship"]["initiativePolicy"] for ch in chapters)
