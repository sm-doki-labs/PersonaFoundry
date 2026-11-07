"""관문 화면이 검토자에게 쉬운 해요체로 말하는지 본다(D-0104, K-0091)."""

from __future__ import annotations

import re
from pathlib import Path

from character_factory_poc.web.gate_items import _plain_rationale

STATIC = Path(__file__).resolve().parents[1] / "src" / "character_factory_poc" / "web" / "static"
LITERAL = re.compile(r"'((?:[^'\\]|\\.)*)'")
DEV_WORDS = ("revision", "답 JSON", "data-qa", "LLD", "501", "D-00", "S2 기준", "ADOPT일", "FIX일")


def _literals(path: Path) -> list[tuple[int, str]]:
    out = []
    for number, line in enumerate(path.read_text("utf-8").split("\n"), start=1):
        if line.strip().startswith(("//", "/*", "*")):
            continue
        out.extend((number, m.group(1)) for m in LITERAL.finditer(line))
    return out


def test_gate_script_speaks_haeyo_without_developer_words() -> None:
    korean = [
        (n, s) for n, s in _literals(STATIC / "shared" / "gate.js") if re.search("[가-힣]", s)
    ]
    assert korean, "관문 화면 문장을 찾지 못했다"
    plain_da = [
        (n, s) for n, s in korean if re.search(r"[가-힣](다|니다)[.)]?\s*$|[가-힣]다[.,] ", s)
    ]
    assert plain_da == [], plain_da
    dev = [(n, s) for n, s in korean if any(word in s for word in DEV_WORDS)]
    assert dev == [], dev


def test_gate_page_hides_technical_controls_behind_details() -> None:
    page = (STATIC / "gate.html").read_text("utf-8")
    assert "답 JSON" not in page and 'value="user"' not in page
    side = page[page.index('aria-label="결정"') :]
    # 결정 버튼과 상태 줄이 먼저, 미리 보기는 '기술 정보' 안에 있다.
    assert side.index("data-actions") < side.index("기술 정보") < side.index("data-preview")


def test_face_reason_reads_as_plain_words() -> None:
    text = _plain_rationale(
        {"listCount": 2, "memberCount": 4, "popularity": {"medianPercentile": 0.46, "iqr": 0.35}},
        "fallback",
    )
    assert text == (
        "순위 목록 2개에 걸쳐 4명이 함께 가진 특징이에요. "
        "구성원 순위는 중간값으로 목록 위에서 54% 지점이에요. 사람마다 순위 차이가 커요."
    )
    assert "IQR" not in text and "백분위" not in text
    short = _plain_rationale(
        {"listCount": 1, "memberCount": 3, "popularity": {"medianPercentile": None}}, "x"
    )
    assert short.endswith("목록이 짧아 순위를 비교하지 못했어요.")
    assert _plain_rationale({"memberCount": 3}, "원래 근거") == "원래 근거"


def test_every_gate_kind_has_its_screen_functions() -> None:
    """관문 종류마다 적힌 render·build 함수가 실제로 있어야 화면이 열린다."""
    script = (STATIC / "shared" / "gate.js").read_text("utf-8")
    names = set(re.findall(r"(?:render|build): (\w+)", script))
    assert len(names) >= 20, names
    missing = sorted(n for n in names if f"function {n}(" not in script)
    assert missing == [], missing
