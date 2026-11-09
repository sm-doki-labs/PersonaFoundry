"""캐릭터의 출신(갈래) 기록 (D-0116, D-0127, D-0128).

출신은 캐릭터 폴더의 origin.json에 한 번 쓰고 바꾸지 않는다. 파일이 없으면 오리지널(CREATED)이다.
state.json 형식은 바꾸지 않는다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.pipeline.graph import (
    CREATED,
    MODES,
    ORIGINS,
    SOURCE,
    TRAIN,
    Stage,
    stages_for,
)

ORIGIN_FILE = "origin.json"
SCHEMA = "character-origin-v1"
MODE_FILE = "model-mode.json"
MODE_SCHEMA = "model-mode-v1"
MODE_EVENTS = "model-mode-events.jsonl"
LABELS = {CREATED: "오리지널", SOURCE: "모티브"}
# 명령 인자 이름 → 코드 값. twin은 D-0144 이전 이름이라 당분간 같은 뜻으로 받는다.
CLI_NAMES = {"original": CREATED, "motif": SOURCE, "twin": SOURCE}
MODE_CLI_NAMES = {"train": "TRAIN", "bind": "BIND_EXISTING", "prompt": "PROMPT_ONLY"}

__all__ = [
    "CREATED",
    "SOURCE",
    "graph_for_dir",
    "origin_label",
    "read_model_mode",
    "read_origin",
    "stage_def",
    "write_model_mode",
    "write_origin",
]


def origin_label(origin: str) -> str:
    return LABELS[origin]


def read_origin(char_dir: Path) -> str:
    path = Path(char_dir) / ORIGIN_FILE
    if not path.exists():
        return CREATED
    data = json.loads(path.read_text("utf-8"))
    origin = data.get("origin")
    if data.get("schemaVersion") != SCHEMA or origin not in ORIGINS:
        raise FactoryError(f"{path}: 출신 기록 형식이 아니다")
    return origin


def read_archived(char_dir: Path) -> bool:
    return (char_dir / ".archived").is_file()


def set_archived(char_dir: Path, archived: bool) -> None:
    marker = char_dir / ".archived"
    if archived:
        marker.touch(exist_ok=True)
    else:
        marker.unlink(missing_ok=True)


def is_twin(char_dir: Path) -> bool:
    """모티브(실존 인물 기반) 캐릭터인가. 이미지·영상 프롬프트가 '가상 인물' 문구를 뺄 때 쓴다."""
    return read_origin(char_dir) == SOURCE


def read_auto_review(char_dir: Path) -> bool:
    path = Path(char_dir) / ORIGIN_FILE
    if not path.is_file():
        return False
    data = json.loads(path.read_text("utf-8"))
    return data.get("origin") == SOURCE and data.get("autoReview") is True


def write_origin(char_dir: Path, origin: str, *, auto_review: bool = False) -> None:
    """출신을 처음 한 번 쓴다. 같은 값이면 그대로 두고, 다른 값이면 거절한다."""
    if origin not in ORIGINS:
        raise FactoryError(f"알 수 없는 출신: {origin}")
    path = Path(char_dir) / ORIGIN_FILE
    if path.exists():
        current = read_origin(char_dir)
        if current != origin:
            raise FactoryError(
                f"출신은 바꿀 수 없다({origin_label(current)} → {origin_label(origin)})"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schemaVersion": SCHEMA,
        "origin": origin,
        "label": origin_label(origin),
        "setAt": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if origin == SOURCE:
        record["autoReview"] = auto_review
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stage_def(char_dir: Path, sid: str) -> Stage:
    """그 캐릭터 갈래의 단계 정의. 갈래에 없는 단계는 오리지널 정의를 돌려준다."""
    from character_factory_poc.pipeline.graph import STAGES

    return graph_for_dir(char_dir).get(sid) or STAGES[sid]


def graph_for_dir(char_dir: Path) -> dict[str, Stage]:
    """그 캐릭터의 갈래·모델 준비 방식에 맞는 단계 그래프."""
    return stages_for(read_origin(char_dir), read_model_mode(char_dir))


def read_model_mode(char_dir: Path) -> str:
    """모델 준비 방식(D-0118). 기록이 없으면 TRAIN이다."""
    path = Path(char_dir) / MODE_FILE
    if not path.exists():
        return TRAIN
    data = json.loads(path.read_text("utf-8"))
    mode = data.get("mode")
    if data.get("schemaVersion") != MODE_SCHEMA or mode not in MODES:
        raise FactoryError(f"{path}: 모델 준비 방식 기록 형식이 아니다")
    return mode


def write_model_mode(char_dir: Path, mode: str, *, reason: str = "") -> None:
    """모델 준비 방식을 정한다. 바꿀 때마다 원장에 한 줄을 남긴다.

    오리지널은 지금 TRAIN만 받는다. 학습 없이 가는 길은 G8 결정(D-0048)으로 고른다.
    """
    if mode not in MODES:
        raise FactoryError(f"알 수 없는 모델 준비 방식: {mode}")
    char_dir = Path(char_dir)
    if mode != TRAIN and read_origin(char_dir) != SOURCE:
        raise FactoryError(
            "오리지널 캐릭터는 TRAIN만 정한다. 학습 없이 가려면 G8에서 고른다(D-0048)"
        )
    previous = read_model_mode(char_dir)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    char_dir.mkdir(parents=True, exist_ok=True)
    record = {"schemaVersion": MODE_SCHEMA, "mode": mode, "setAt": now, "reason": reason}
    (char_dir / MODE_FILE).write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    events = char_dir / "ledger" / MODE_EVENTS
    events.parent.mkdir(parents=True, exist_ok=True)
    with events.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"at": now, "from": previous, "to": mode, "reason": reason}, ensure_ascii=False
            )
            + "\n"
        )
