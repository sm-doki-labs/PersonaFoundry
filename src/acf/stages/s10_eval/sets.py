"""S10 평가 세트 (LLD §8.9).

문장은 `resources/eval-sets-v1.json`에 두고 캐릭터 기획서의 이름과 관계로 채운다. 고정 이력
질문(OE), 서운함(SE), 무례·사과 대본(APOLOGY), 200턴 대화(LONG200)를 만든다. 각 세트는
정규화 JSON의 sha256으로 고정한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from acf.common.canonical import sha256_of
from acf.common.errors import FactoryError
from acf.common.schema import register, validate
from acf.common.store import write_once_json
from acf.contracts.common import Strict
from acf.contracts.training import SetId

SET_IDS: tuple[SetId, ...] = ("OE", "SE", "APOLOGY", "LONG200")
OE_ITEMS = 12
SE_ITEMS = 12
APOLOGY_ITEMS = 6
LONG_PERSONAS = 4
LONG_TURNS = 200
APOLOGY_MIN_TURNS, APOLOGY_MAX_TURNS = 10, 14

RELATION_LABELS = {
    "STRANGER": "처음 만난 사이",
    "ACQUAINTANCE": "친해진 사이",
    "FLIRTING": "썸을 타는 사이",
    "DATING": "연애 중",
}

_PLACEHOLDER = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_]*)\}")


@register("eval-set-v1")
class EvalSetDoc(Strict):
    """한 세트의 렌더링 결과. items 모양은 setId마다 다르고 check_set_doc이 검사한다."""

    schemaVersion: Literal["eval-set-v1"] = "eval-set-v1"
    setId: SetId
    characterId: str
    relation: str
    items: list[dict[str, Any]] = Field(min_length=1)


@dataclass(frozen=True)
class RenderedSet:
    doc: dict[str, Any]
    sha256: str


def relationship_label(plan: Any) -> str:
    """기획서의 마지막 챕터 목표 관계를 평가 대화의 관계 말로 쓴다."""
    arcs = plan.get("chapterArc") if isinstance(plan, dict) else getattr(plan, "chapterArc", [])
    if not arcs:
        return "가까운 사이"
    target = arcs[-1].get("targetStage") if isinstance(arcs[-1], dict) else arcs[-1].targetStage
    return RELATION_LABELS.get(str(target), "가까운 사이")


def load_resource() -> dict[str, Any]:
    path = resources.files("acf.resources").joinpath("eval-sets-v1.json")
    doc = json.loads(path.read_text("utf-8"))
    if doc.get("schemaVersion") != "eval-sets-v1":
        raise FactoryError("eval-sets-v1.json의 schemaVersion이 eval-sets-v1이 아니다")
    return doc


def _fill(value: Any, values: dict[str, str], where: str) -> Any:
    if isinstance(value, str):
        out = value
        for key, replacement in values.items():
            out = out.replace("{" + key + "}", str(replacement))
        left = _PLACEHOLDER.findall(out)
        if left:
            raise FactoryError(f"{where}: 채우지 않은 자리표시자 {sorted(set(left))}")
        return out
    if isinstance(value, list):
        return [_fill(v, values, where) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, values, f"{where}.{k}") for k, v in value.items()}
    return value


def _fill_item(item: dict[str, Any], values: dict[str, str], where: str) -> dict[str, Any]:
    return _fill(item, values, where)


def _fixed_set(
    resource: dict[str, Any], key: str, cid: str, relation: str, name: str, expected: int
) -> dict[str, Any]:
    block = resource[key]
    items = []
    for i, raw in enumerate(block["items"], start=1):
        where = f"{key}.items[{i}]"
        item = _fill_item(raw, {"name": name, "relation": relation}, where)
        if not item.get("itemId") or not item.get("question"):
            raise FactoryError(f"{where}: itemId와 question이 필요하다")
        items.append(item)
    if len(items) != expected:
        raise FactoryError(f"{key} 문항은 {expected}개여야 한다(현재 {len(items)})")
    return {
        "schemaVersion": "eval-set-v1",
        "setId": key,
        "characterId": cid,
        "relation": relation,
        "items": items,
    }


def _apology_set(resource: dict[str, Any], cid: str, relation: str, name: str) -> dict[str, Any]:
    block = resource["APOLOGY"]
    items = []
    for i, raw in enumerate(block["items"], start=1):
        where = f"APOLOGY.items[{i}]"
        item = _fill_item(raw, {"name": name, "relation": relation}, where)
        turns = item.get("turns") or []
        if not APOLOGY_MIN_TURNS <= len(turns) <= APOLOGY_MAX_TURNS:
            raise FactoryError(
                f"{where}: 사과 대본은 {APOLOGY_MIN_TURNS}~{APOLOGY_MAX_TURNS}턴이다"
                f"(현재 {len(turns)})"
            )
        phases = [t.get("phase") for t in turns]
        for phase in ("rude", "hollow", "sincere"):
            if phase not in phases:
                raise FactoryError(f"{where}: {phase} 구간이 없다")
        if any(t.get("phase") == "sincere" for t in turns[: len(turns) // 2]):
            raise FactoryError(f"{where}: 진지한 사과는 대본 뒤쪽에 와야 한다")
        recovery = item.get("recoveryTurns") or []
        if not recovery:
            raise FactoryError(f"{where}: recoveryTurns가 필요하다")
        items.append(item)
    if len(items) != APOLOGY_ITEMS:
        raise FactoryError(f"APOLOGY 대본은 {APOLOGY_ITEMS}개여야 한다(현재 {len(items)})")
    return {
        "schemaVersion": "eval-set-v1",
        "setId": "APOLOGY",
        "characterId": cid,
        "relation": relation,
        "items": items,
    }


def _long_set(resource: dict[str, Any], cid: str, relation: str, name: str) -> dict[str, Any]:
    block = resource["LONG200"]
    templates = block["turns"]
    if len(templates) != LONG_TURNS:
        raise FactoryError(f"LONG200 turns는 {LONG_TURNS}개여야 한다(현재 {len(templates)})")
    by_turn = {int(t["turn"]): t for t in templates}
    if sorted(by_turn) != list(range(1, LONG_TURNS + 1)):
        raise FactoryError("LONG200 turns의 turn 번호가 1~200 연속이 아니다")
    personas = block["personas"]
    if len(personas) != LONG_PERSONAS:
        raise FactoryError(f"LONG200 페르소나는 {LONG_PERSONAS}명이어야 한다")
    items = []
    for persona in personas:
        pid = persona["personaId"]
        probes = {p["id"]: p for p in persona["probes"]}
        if set(probes) != {"c1", "c2", "c3"}:
            raise FactoryError(f"LONG200 {pid}: 확인 질문은 c1·c2·c3 세 개다")
        values = {
            "name": name,
            "relation": relation,
            **{k: str(v) for k, v in persona["facts"].items()},
            **{k: str(v) for k, v in persona["changes"].items()},
        }
        turns = []
        for n in range(1, LONG_TURNS + 1):
            raw = by_turn[n]
            kind = raw.get("kind", "chat")
            text = raw["user"]
            check_id = raw.get("checkId", "")
            answer_keys: list[str] = []
            if kind == "check":
                probe = probes.get(check_id)
                if probe is None:
                    raise FactoryError(f"LONG200 {pid}: {check_id} 확인 질문이 없다")
                text = probe["question"]
                answer_keys = [str(k) for k in probe["answerKeys"]]
                if not answer_keys:
                    raise FactoryError(f"LONG200 {pid}.{check_id}: answerKeys가 비었다")
            filled = _fill(text, values, f"LONG200 {pid} turn {n}")
            turns.append(
                {
                    "turn": n,
                    "user": filled,
                    "kind": kind,
                    "checkId": check_id,
                    "answerKeys": answer_keys,
                }
            )
        items.append(
            {
                "itemId": f"long-{pid}",
                "personaId": pid,
                "persona": persona["label"],
                "turns": turns,
            }
        )
    return {
        "schemaVersion": "eval-set-v1",
        "setId": "LONG200",
        "characterId": cid,
        "relation": relation,
        "items": items,
    }


def render_sets(
    plan: Any, character_id: str, *, relationship: str | None = None
) -> dict[SetId, RenderedSet]:
    """기획서의 이름·관계로 네 세트를 렌더링한다. 파일을 쓰지 않는다."""
    name = plan.get("name") if isinstance(plan, dict) else plan.name
    if not name:
        raise FactoryError("평가 세트를 채우려면 기획서의 name이 필요하다")
    relation = relationship or relationship_label(plan)
    resource = load_resource()
    docs = {
        "OE": _fixed_set(resource, "OE", character_id, relation, str(name), OE_ITEMS),
        "SE": _fixed_set(resource, "SE", character_id, relation, str(name), SE_ITEMS),
        "APOLOGY": _apology_set(resource, character_id, relation, str(name)),
        "LONG200": _long_set(resource, character_id, relation, str(name)),
    }
    rendered: dict[SetId, RenderedSet] = {}
    for sid, doc in docs.items():
        check_set_doc(doc)
        rendered[sid] = RenderedSet(doc=doc, sha256=sha256_of(doc))
    return rendered


def check_set_doc(doc: dict[str, Any]) -> None:
    """세트별 개수와 필수 칸. 렌더링 뒤·읽을 때 모두 부른다."""
    validate("eval-set-v1", doc)
    sid = doc["setId"]
    items = doc["items"]
    if sid == "OE" and len(items) != OE_ITEMS:
        raise FactoryError(f"OE 문항은 {OE_ITEMS}개여야 한다")
    if sid == "SE" and len(items) != SE_ITEMS:
        raise FactoryError(f"SE 문항은 {SE_ITEMS}개여야 한다")
    if sid in {"OE", "SE"}:
        for item in items:
            if not item.get("itemId") or not item.get("question"):
                raise FactoryError(f"{sid}: itemId와 question이 필요하다")
            for h in item.get("history", []):
                if h.get("role") not in {"user", "assistant"} or not h.get("content"):
                    raise FactoryError(f"{item['itemId']}: history 역할·내용이 잘못됐다")
    if sid == "APOLOGY":
        if len(items) != APOLOGY_ITEMS:
            raise FactoryError(f"APOLOGY 대본은 {APOLOGY_ITEMS}개여야 한다")
        for item in items:
            turns = item.get("turns") or []
            if not APOLOGY_MIN_TURNS <= len(turns) <= APOLOGY_MAX_TURNS:
                raise FactoryError(f"{item.get('itemId')}: 사과 대본 턴 수가 범위를 벗어난다")
            if not item.get("recoveryTurns"):
                raise FactoryError(f"{item.get('itemId')}: recoveryTurns가 없다")
    if sid == "LONG200":
        if len(items) != LONG_PERSONAS:
            raise FactoryError(f"LONG200 페르소나는 {LONG_PERSONAS}명이어야 한다")
        for item in items:
            turns = item.get("turns") or []
            if len(turns) != LONG_TURNS:
                raise FactoryError(f"{item.get('itemId')}: LONG200은 {LONG_TURNS}턴이다")
            checks = [t for t in turns if t.get("kind") == "check"]
            if len(checks) != 3:
                raise FactoryError(f"{item.get('itemId')}: 확인 질문은 3개다")
            if not item.get("personaId"):
                raise FactoryError(f"{item.get('itemId')}: personaId가 없다")


def set_path(char_dir: Path, rev: str, set_id: SetId) -> Path:
    return char_dir / "s10-eval" / rev / "sets" / f"{set_id}.json"


def write_sets(char_dir: Path, rev: str, rendered: dict[SetId, RenderedSet]) -> dict[str, Any]:
    """세트 파일을 revision 폴더에 한 번만 쓰고 ref·sha 목록을 돌려준다."""
    out: dict[str, Any] = {}
    for sid in SET_IDS:
        rs = rendered[sid]
        path = set_path(char_dir, rev, sid)
        write_once_json(path, rs.doc)
        out[sid] = {
            "ref": path.relative_to(char_dir).as_posix(),
            "sha256": rs.sha256,
        }
    return out


def load_set(char_dir: Path, ref: str, expected_sha: str) -> dict[str, Any]:
    """사전 등록에 적힌 세트를 읽고 정규화 JSON sha256을 확인한다."""
    rel = Path(ref)
    if rel.is_absolute() or ".." in rel.parts:
        raise FactoryError(f"세트 경로가 캐릭터 폴더 밖을 가리킨다: {ref}")
    path = char_dir / rel
    if not path.exists():
        raise FactoryError(f"평가 세트 파일이 없다: {ref}")
    doc = json.loads(path.read_text("utf-8"))
    actual = sha256_of(doc)
    if actual != expected_sha:
        raise FactoryError(
            f"평가 세트 sha256이 사전 등록과 다르다: {ref}\n  등록 {expected_sha}\n  실제 {actual}"
        )
    check_set_doc(doc)
    return doc
