"""모티브 시연 선택의 근거와 행동을 검사한다."""

from character_factory_poc.stages.s7_traits.ledger import check_ledger
from tests.test_trait_ledger import _ledger


def demo_ledger(cid, ref="근거1"):
    rows = [
        ("TEASE", "별명을 붙여 놀릴 때", "농담을 비틀어 되묻고 받아친 한마디로 맺는다."),
        ("WORRY", "실패한 일을 털어놓을 때", "먼저 공감하고 경험을 들려준 뒤 응원한다."),
        ("CRITICISM", "악플 이야기를 꺼낼 때", "실수를 인정하고 고칠 점을 밝힌다."),
        ("UNKNOWN", "처음 듣는 기록을 물을 때", "모른다고 밝히고 어느 대회를 뜻하는지 확인한다."),
        ("PRIVATE", "누구와 사귀는지 캐물을 때", "사적인 질문을 거절하고 공개한 소식으로 돌린다."),
    ]
    return _ledger(
        characterId=cid,
        traits=[
            dict(
                id=f"t{i}",
                kind="choice",
                basis="INFERRED",
                demoSituation=sit,
                sourceRef=ref,
                trigger=trigger,
                nearMiss="내일 일정만 궁금해할 때",
                behavior=behavior,
                rarity="sometimes",
            )
            for i, (sit, trigger, behavior) in enumerate(rows, 1)
        ],
    )


def test_uses_available_joke_cell_and_checks_coverage_and_action():
    ledger = demo_ledger("인물")
    check = check_ledger("인물", {"tendencies": [{"cell": "JOKE/JOKE_BACK"}]}, {"근거1"})
    assert any("추론은" in p for p in check(ledger))
    tease = ledger.traits[0]
    tease.basis, tease.demoSituation, tease.sourceRef = "JOKE/JOKE_BACK", None, None
    assert check(ledger) == []
    ledger.traits[1].demoSituation = "PRIVATE"
    ledger.traits[1].sourceRef = "없는 근거"
    tease.behavior = "부드럽고 차분한 말투로 대답한다."
    problems = " ".join(check(ledger))
    assert all(key in problems for key in ("말투만", "WORRY", "같은 상황(PRIVATE)", "sourceRef"))


def test_demo_temperature_reaches_only_motif_speech_requests(tmp_path):
    from types import SimpleNamespace

    from character_factory_poc.common.schema import validate
    from character_factory_poc.pipeline.context import Context
    from character_factory_poc.pipeline.origin import SOURCE, write_origin
    from character_factory_poc.stages.s8_prompts.build import run_probes
    from tests.support.synthetic import trait_sheet
    from tests.test_persona_pipeline import _fake_models

    ctx = Context.load(tmp_path, execute=True)
    cid = "cf-20260101-test"
    sheet = validate("trait-sheet-v1", trait_sheet(cid, "pr1"))
    prompt = SimpleNamespace(text="합성 대화 지시")
    pair = SimpleNamespace(long=prompt, short=prompt)
    talk, judge = _fake_models(cid)
    ctx.use_models(talk, judge)
    ctx.config.stages["s8"] = {"motif_demo_chat_temperature": 0.4}
    for motif, expected in ((False, 0.8), (True, 0.4), (True, 0.8)):
        if motif:
            write_origin(ctx.character_dir(cid), SOURCE)
        if motif and expected == 0.8:
            ctx.config.stages["s8"].clear()
        run_probes(ctx, cid, ctx.budget(), pair, sheet, ["오늘은 어때요?"], True)
        assert [r.temperature for r in talk.requests[-2:]] == [expected, expected]
        assert judge.requests[-1].temperature == 0.0
