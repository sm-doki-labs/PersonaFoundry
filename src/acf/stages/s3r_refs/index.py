"""저작 페르소나·Stanford·합성 JSONL에서 불변 참고 자료 인덱스를 만든다."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from acf.common.schema import dump, validate
from acf.common.store import write_once_json
from acf.contracts.refs import IndexItem, ReferenceIndex, Source
from acf.providers.embed import Embedder


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(f"{key}: {_text(part)}" for key, part in value.items())
    if isinstance(value, list):
        return "\n".join(_text(part) for part in value)
    return "" if value is None else str(value)


def _check_index(index: ReferenceIndex) -> None:
    seen: set[str] = set()
    for item in index.items:
        if item.itemId in seen:
            raise ValueError(f"인덱스 itemId가 중복됐다: {item.itemId}")
        seen.add(item.itemId)
        if len(item.vector) != index.dim:
            raise ValueError(f"{item.itemId}: vector 차원이 dim과 다르다")
        if not all(math.isfinite(v) for v in item.vector):
            raise ValueError(f"{item.itemId}: vector에 비유한 값이 있다")
        if len(set(item.uses)) != len(item.uses):
            raise ValueError(f"{item.itemId}: uses가 중복됐다")


def build_index(
    index_id: str,
    *,
    stanford_catalog: dict | None = None,
    personas_dir: Path | None = None,
    jsonl: list[tuple[Path, Source]] | None = None,
    embedder: Embedder,
) -> ReferenceIndex:
    """로컬 파일만 읽는다. JSONL ID는 출처 접두사를 붙여 서로 충돌하지 않게 한다."""
    rows: list[dict[str, Any]] = []
    if stanford_catalog is not None:
        fields = ("summary", "stance", "values", "speech", "expression_focus", "utterance_examples")
        for preset in stanford_catalog.get("presets", []):
            rows.append(
                {
                    "itemId": f"STANFORD:{preset['preset_id']}",
                    "source": "STANFORD",
                    "version": str(stanford_catalog.get("schema_version", "")),
                    "label": preset.get("name", ""),
                    "uses": ["TRAITS", "VOICE"],
                    "text": _text({key: preset[key] for key in fields if key in preset}),
                }
            )
    if personas_dir is not None:
        for path in sorted(Path(personas_dir).rglob("*.json")):
            persona = json.loads(path.read_text("utf-8"))
            if (
                not isinstance(persona, dict)
                or persona.get("schemaVersion") != "character-persona-v6"
            ):
                continue
            revision = persona["revision"]
            for suffix, use, fields in (
                (
                    "traits",
                    "TRAITS",
                    ("disposition", "wantsAndFears", "readingAndTension", "choices"),
                ),
                ("voice", "VOICE", ("voice",)),
            ):
                rows.append(
                    {
                        "itemId": f"AUTHORED:{revision}:{suffix}",
                        "source": "AUTHORED",
                        "version": revision,
                        "label": persona.get("displayName", persona.get("personaId", revision)),
                        "uses": [use],
                        "text": _text({key: persona[key] for key in fields if key in persona}),
                    }
                )
    for path, source in jsonl or []:
        if source not in {"SNS14", "NIKL", "OTHER"}:
            raise ValueError(f"JSONL 출처는 SNS14/NIKL/OTHER여야 한다: {source}")
        for line_no, line in enumerate(Path(path).read_text("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                raw_id = str(row["id"])
                if not raw_id.strip():
                    raise ValueError("id가 비었다")
                rows.append(
                    {
                        "itemId": raw_id
                        if raw_id.startswith(f"{source}:")
                        else f"{source}:{raw_id}",
                        "source": source,
                        "version": "",
                        "label": row.get("label", ""),
                        "uses": row.get("uses", ["DATA"]),
                        "text": row["text"],
                    }
                )
            except (KeyError, TypeError, ValueError) as e:
                raise ValueError(f"{path}:{line_no}: JSONL 항목이 잘못됐다: {e}") from e
    vectors = embedder.embed([row["text"] for row in rows])
    if len(vectors) != len(rows):
        raise ValueError("임베더 응답 수가 입력 수와 다르다")
    index = ReferenceIndex(
        indexId=index_id,
        embedder=embedder.name,
        dim=embedder.dim,
        sources=sorted({row["source"] for row in rows}),
        items=[IndexItem(**row, vector=vec) for row, vec in zip(rows, vectors, strict=True)],
    )
    _check_index(index)
    return index


def write_index(path: Path, index: ReferenceIndex) -> Path:
    """원문이 있는 인덱스는 실행 자료 영역에 보관하고 기존 파일을 바꾸지 않는다."""
    index = validate("reference-index-v1", dump(index))
    _check_index(index)
    write_once_json(path, dump(index))
    return Path(path)


def load_index(path: Path) -> tuple[ReferenceIndex, str]:
    """검증한 인덱스와 실제로 읽은 파일 바이트의 SHA-256을 돌려준다."""
    data = Path(path).read_bytes()
    index = validate("reference-index-v1", json.loads(data))
    _check_index(index)
    return index, hashlib.sha256(data).hexdigest()
