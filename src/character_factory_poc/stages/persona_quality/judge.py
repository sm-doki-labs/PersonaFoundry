"""Independent-family defect triage. Candidate labels never qualify a recipe."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object
from character_factory_poc.stages.persona_quality.protocol import canonical_hash


def family(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else model.split("-", 1)[0]


def triage_scene(model, dialogue_model: str, turns: list[dict], dest: Path) -> dict:
    if family(model.model) == family(dialogue_model):
        raise ValueError("triage must use a different model family")
    if Path(dest).exists():
        return read_json(dest)
    instruction = (
        "한국어 대화 결함 후보만 분류한다. "
        "각 턴의 실제 이력을 읽고 책임·합의·변경 전제를 확인한다. "
        "새 일정 제안을 틀린 회상으로 분류하지 않는다. 감정 공감과 책임 날조를 구분한다. "
        '점수나 합격을 내리지 않는다. json {"defects":[{"turn":1,"type":"...",'
        '"evidence":"assistant의 정확한 부분문자열","reason":"..."}]}만 출력한다.'
    )
    # One optional format retry, both raw responses preserved. No brace repair or silent drop.
    for attempt in (1, 2):
        request = ChatRequest(
            "JUDGE",
            "persona-quality-triage",
            (
                Message("system", instruction),
                Message("user", json.dumps(turns, ensure_ascii=False)),
            ),
            ref=str(dest),
            max_output_tokens=6000,
            temperature=0.1,
            response_json=True,
        )
        raw_path = Path(str(dest) + f".attempt-{attempt}.json")
        request_path = Path(str(dest) + f".attempt-{attempt}.request.json")
        if raw_path.exists():
            cached = read_json(raw_path)
            if canonical_hash(cached["request"]) != canonical_hash(dataclasses.asdict(request)):
                raise ValueError("judge checkpoint request changed")
            text = cached["response"]["text"]
        elif request_path.exists():
            result = dict(
                status="INVALID", reason="prior judge outcome unknown; redraw forbidden", defects=[]
            )
            write_once_json(dest, result)
            return result
        else:
            write_once_json(request_path, dataclasses.asdict(request))
            response = model.complete(request)
            write_once_json(
                raw_path,
                dict(request=dataclasses.asdict(request), response=dataclasses.asdict(response)),
            )
            text = response.text
        try:
            result = extract_json_object(text)
            defects = result["defects"]
            if not isinstance(defects, list):
                raise ValueError("defects must be a list")
            by_turn = {t["turn"]: t for t in turns}
            for defect in defects:
                raw = by_turn[defect["turn"]]["assistant"]
                if not defect.get("evidence") or defect["evidence"] not in raw:
                    raise ValueError("defect quote does not match original assistant")
                if not defect.get("type") or not defect.get("reason"):
                    raise ValueError("defect type/reason missing")
            result.update(status="CANDIDATES_ONLY", attempt=attempt)
            write_once_json(dest, result)
            return result
        except (KeyError, TypeError, ValueError) as exc:
            if attempt == 2:
                result = dict(status="INVALID", reason=str(exc), defects=[])
                write_once_json(dest, result)
                return result
    raise AssertionError("unreachable")
