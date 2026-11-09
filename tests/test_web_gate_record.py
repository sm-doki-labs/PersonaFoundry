"""검토 기록 화면(QA 3차 L 묶음): 기록은 읽기 전용, 자동 진행은 그렇다고 밝히고, 표시용 필드는 원본을 바꾸지 않는다.

합성 흐름과 가짜 공급자만 쓴다. 관문 화면 스크립트는 문장과 표시 규칙을 정적으로 확인한다.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from character_factory_poc.web import create_app
from character_factory_poc.web.gate_items import split_stat_sentences
from tests.support.web_gates import build

STATIC = Path(__file__).resolve().parents[1] / "src" / "character_factory_poc" / "web" / "static"
SCRIPT = (STATIC / "shared" / "gate.js").read_text("utf-8")
STYLE = (STATIC / "shared" / "gate.css").read_text("utf-8")
STAT = "승인 원문의 대상 발화 종결형은 높임 459, 반말 0, 미분류 379였다."


def _view(root: Path, cid: str, gate: str) -> dict:
    with TestClient(create_app(root)) as client:
        res = client.get(f"/api/characters/{cid}/gates/{gate}")
    assert res.status_code == 200, res.text
    return res.json()


def test_stat_sentences_leave_the_character_text():
    voice, stats = split_stat_sentences(
        f"듣는 사람에게 존댓말을 쓴다. {STAT} '되게', '너무'를 자주 붙인다."
    )
    assert voice == "듣는 사람에게 존댓말을 쓴다. '되게', '너무'를 자주 붙인다."
    assert stats == [STAT]
    # 연도·경력 숫자는 통계가 아니다.
    career = "2015~2025년 토트넘에서 10년을 뛰었다. 2018 아시안게임 금메달을 땄다."
    assert split_stat_sentences(career) == (career, [])
    assert split_stat_sentences(None) == ("", [])
    # 마침표가 없어 나눌 수 없으면 설명을 숨기지 않는다.
    joined = f"감탄사를 아낀다 {STAT}"
    assert split_stat_sentences(joined) == (joined, [])


def test_g3_plan_display_splits_voice_stats_without_touching_candidate(tmp_path):
    _ctx, cid = build(tmp_path, "G3")
    view = _view(tmp_path, cid, "G3")
    assert view["items"]["planDisplay"] == {}
    path = tmp_path / view["stageDir"] / "variants.json"
    data = json.loads(path.read_text("utf-8"))
    original = data["candidates"][0]["voiceSummary"].rstrip(".") + "."
    data["candidates"][0]["voiceSummary"] = f"{original} {STAT}"
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    items = _view(tmp_path, cid, "G3")["items"]
    first = items["candidates"][0]
    assert items["planDisplay"] == {
        first["variantId"]: {"voiceSummary": original, "voiceStats": [STAT]}
    }
    # 고칠 칸의 원래 값(결정에 실리는 값)은 그대로다.
    assert first["voiceSummary"] == f"{original} {STAT}"


def test_g6_same_prompt_flag(tmp_path):
    _ctx, cid = build(tmp_path, "G6")
    view = _view(tmp_path, cid, "G6")
    assert view["items"]["samePrompt"] is False
    path = tmp_path / view["stageDir"] / "prompt-pair.json"
    pair = json.loads(path.read_text("utf-8"))
    pair["short"] = dict(pair["long"])
    path.write_text(json.dumps(pair, ensure_ascii=False), "utf-8")
    assert _view(tmp_path, cid, "G6")["items"]["samePrompt"] is True


def test_record_mode_is_read_only_and_names_auto_decisions():
    # 승인·반려한 관문은 기록으로 연다. 자동 진행 기록은 사람이 보지 않았다고 밝힌다(QA F05·F06).
    assert "function isRecord()" in SCRIPT
    assert "'자동 진행으로 승인됐어요'" in SCRIPT and "' · 사람 확인 없음'" in SCRIPT
    assert "나중에 볼 것 " in SCRIPT
    assert "사람만 결정해요" not in SCRIPT
    # 기록에서는 결정 버튼·메모·검토한 사람·단축키 안내를 숨긴다.
    hidden = STYLE[STYLE.index("body.gate-record .side-hint") :].split("{", 1)[0]
    for part in ("side-actions", "side-keys", "side-more", "side-status"):
        assert f"body.gate-record .{part}" in hidden
    # 기록 시트에서는 주 버튼 단축키가 결정을 보내지 않는다.
    common = SCRIPT[SCRIPT.index("function onCommonKey") :]
    assert common.index("if (isRecord()) return;") < common.index("primary.click()")


def test_review_text_drops_comparison_and_internal_words_for_one_plan():
    # 후보가 하나면 비교 문구·숫자 키 안내가 없고, 빈 칸은 '없음'으로 보이지 않는다(QA F07·F12).
    assert "숫자 키(1~" not in SCRIPT
    assert "'<span class=\"plan-none\">없음</span>'" not in SCRIPT
    assert "row.empty = plans.every" in SCRIPT
    # G6: 내부 빈칸 목록과 '표본 응답을 먼저 보고'를 표본이 없을 때 쓰지 않는다(QA F10·F11).
    assert "아직 비어 있는 칸" not in SCRIPT and "성격 5요인 메모" not in SCRIPT
    assert "표본 응답이 아직 없어요" not in SCRIPT
    assert "아직 대화 표본이 없어요." in SCRIPT
    # 화면 이름은 '대화해 보기'로 통일한다(약속 4).
    assert "직접 대화해 보기" not in SCRIPT and "대화 테스트" not in SCRIPT
    # 위치 줄과 창 제목에 관문 코드를 붙이지 않는다.
    assert "esc(state.gate + ' '" not in SCRIPT
    assert "'캐릭터 공장 · ' + state.gate" not in SCRIPT
