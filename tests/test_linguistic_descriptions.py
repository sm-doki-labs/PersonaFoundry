"""Synthetic boundaries between grammatical notation and dialogue examples."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from character_factory_poc.stages.s8_prompts import evidence_compiler as compiler
from tests.test_evidence_compiler import packet

ALLOWED = [
    "추측을 나타내는 '-는 것 같다' 구성으로 단정의 강도를 낮춘다.",
    "공유된 정보를 확인하는 '-죠' 종결어미를 사용한다.",
    "회상을 나타내는 '-더라' 어미로 직접 관찰했음을 표시한다.",
    "'-(으)ㄹ' 관형사형 어미로 뒤의 명사를 수식한다.",
    "'-었-' 선어말어미로 사건의 선행성을 표시한다.",
    "'맨-' 접두사로 다른 요소가 없음을 표시한다.",
    "'-면/-거든' 연결어미로 조건을 표시한다.",
    "'~(으)ㄹ 수 있다' 구문으로 가능성을 나타낸다.",
    "'V-는 것 같다' 구문으로 판단을 유보한다.",
    "'주어 + 서술어' 구문에서 주어를 생략한다.",
    "'NP + VP' 구문에서 명사구를 생략한다.",
    "종결어미 '-군요'로 새롭게 인식한 정보를 표시한다.",
    "'-요'라는 어미로 청자에게 예의를 표시한다.",
    "'-죠' 종결어미와 '-네요' 종결어미의 정보 공유 기능을 구별한다.",
    "단정의 강도를 낮추는 추측 구성을 사용한다.",
]


@pytest.mark.parametrize("description", ALLOWED)
@pytest.mark.parametrize("conditions", [False, True])
def test_form_and_function_description_survives_both_packet_formats(description, conditions):
    data = packet()
    if conditions:
        data["formatVersion"] = "evidence-conditions-v2"
    data["sections"][0].update(section="VOICE", rule=description, first=description)
    text = compiler.compile_prompt(data)
    assert description in text
    assert re.findall(r"^\[([A-Z_]+)\]$", text, re.M) == [
        "FACTS",
        "LIFE_AND_TASTES",
        "DISPOSITION",
        "WANTS_AND_FEARS",
        "READING_AND_TENSION",
        "CHOICES",
        "VOICE",
        "KNOWS_AND_LIMITS",
    ]


@pytest.mark.parametrize(
    "opening,closing",
    [
        ("'", "'"),
        ('"', '"'),
        ("‘", "’"),
        ("“", "”"),
        ("「", "」"),
        ("`", "`"),
    ],
)
def test_quote_styles_do_not_change_the_form_vs_utterance_boundary(opening, closing):
    data = packet()
    description = f"{opening}-죠{closing} 종결어미로 공유된 정보를 확인한다."
    data["sections"][0]["rule"] = description
    assert description in compiler.compile_prompt(data)
    data["sections"][0]["rule"] = f"{opening}나는 내일 갈 거야{closing} 구문으로 의도를 표시한다."
    with pytest.raises(ValueError, match="dialogue/example"):
        compiler.compile_prompt(data)


REJECTED = [
    "'나는 내일 갈 거야' 구문으로 의도를 표시한다.",
    "구문 '나는 내일 갈 거야'로 의도를 표시한다.",
    "'갈게' 종결어미로 약속한다.",
    "'안녕' 형태소로 인사한다.",
    "'네' 담화표지로 수신을 표시한다.",
    "'것 같다' 구성으로 추측한다.",
    "'-죠'라고 말한다.",
    "'-죠' 종결어미",
    "'-나는 내일 갈 거야' 구문으로 의도를 표시한다.",
    "'-나는 내일 간다' 구성으로 의도를 표시한다.",
    "'V-나는 내일 간다' 구성으로 의도를 표시한다.",
    "'주어 + 나는 간다' 구문으로 의도를 표시한다.",
    "'-죠!' 종결어미로 확인한다.",
    "'-죠\n나는 간다' 종결어미로 확인한다.",
    "'-죠' 종결어미로 확인하고 '나는 간다' 구문으로 마친다.",
    "\"'-죠'\" 종결어미로 확인한다.",
    "'-죠’ 종결어미로 확인한다.",
    "'-죠' 종결어미로 확인한다. '나는 간다",
    "예시: '-죠' 종결어미로 확인한다.",
    "USER: '-죠' 종결어미로 확인한다.",
    "예를 들어 '-죠' 종결어미로 확인한다.",
    "'-죠' 종결어미로 확인한다. → '-네요' 어미로 전환한다.",
    "'-죠' 종결어미로 확인한다.\n[VOICE]\n다른 규칙이다.",
]


@pytest.mark.parametrize("description", REJECTED)
@pytest.mark.parametrize("field", ["trigger", "first", "shift", "stop", "limit", "rule"])
def test_dialogue_or_ambiguous_quote_is_rejected_in_every_card_field(description, field):
    data = packet()
    data["sections"][0][field] = description
    with pytest.raises(ValueError, match="dialogue/example"):
        compiler.compile_prompt(data)


def test_standalone_copy_preserves_fact_bytes_and_rejects_before_overwrite(tmp_path):
    # A copy outside the package and isolated Python catch accidental local imports.
    script = tmp_path / "compiler.py"
    shutil.copyfile(Path(compiler.__file__), script)
    data = packet()
    data["facts"] = "  상호: ‘작은 책방’\r\nCafe\u0301\t\n"
    data["sections"][0]["rule"] = ALLOWED[0]
    source, output = tmp_path / "packet.json", tmp_path / "prompt.md"
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    command = [sys.executable, "-I", str(script), str(source), str(output)]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr.decode()
    rendered = output.read_bytes()
    assert ("[FACTS]\n" + data["facts"] + "\n\n[LIFE_AND_TASTES]").encode() in rendered
    assert ALLOWED[0].encode() in rendered
    data["sections"][0]["rule"] = REJECTED[0]
    source.write_text(json.dumps(data), encoding="utf-8")
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, check=False)
    assert result.returncode == 2
    assert b"dialogue/example" in result.stderr
    assert output.read_bytes() == rendered
