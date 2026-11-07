"""체크포인트 선별 요청 만들기 (D-0077).

학습에서 뺀 검증 대화(validation_base·validation_augmented)에서 결정적으로 뽑는다. 한 턴 요청은
대화의 마지막 답변 직전까지를 이력으로 주고, 연속 대화 요청은 사용자 발화만 주고 모델이 자기
답을 이어 쓰게 한다. 머스크 N3b 선별처럼 첫 출력만 쓴다.

연속 대화 장면은 사용자 발화가 max_turns개 이상인 대화에서만 만들고 정확히 max_turns턴을 쓴다.
품질 운영 규격의 개발 비교(단발 24 + 6턴 장면 2 = 조건당 36출력)가 장면마다 같은 길이를 전제하기
때문이다. 조건에 맞는 대화가 모자라면 장면 수가 줄고, 생성 수는 계획에 그대로 드러난다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from character_factory_poc.providers.training.port import DatasetFile

SCREEN_SPLITS = ("validation_base", "validation_augmented")


def _rows(files: list[DatasetFile]) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for item in files:
        if item.split not in SCREEN_SPLITS:
            continue
        for n, line in enumerate(item.path.read_text("utf-8").splitlines()):
            if line.strip():
                row = json.loads(line)
                key = hashlib.sha256(f"{item.relative}:{n}".encode()).hexdigest()
                out.append((key, row))
    return sorted(out, key=lambda kv: kv[0])


def _clean(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"role": str(m["role"]), "content": str(m["content"])} for m in messages]


def build_screen_tasks(
    files: list[DatasetFile],
    *,
    single: int,
    multi: int,
    max_turns: int,
    seed: int,
) -> list[dict[str, Any]]:
    rows = _rows(files)
    tasks: list[dict[str, Any]] = []
    for key, row in rows:
        if len([t for t in tasks if t["kind"] == "single"]) >= single:
            break
        messages = _clean(row.get("messages") or [])
        last = max((i for i, m in enumerate(messages) if m["role"] == "assistant"), default=-1)
        if last <= 0 or messages[last - 1]["role"] != "user":
            continue
        tasks.append(
            {
                "taskId": f"s-{key[:10]}",
                "kind": "single",
                "messages": messages[:last],
                "reference": messages[last]["content"],
                "seed": seed + len(tasks),
            }
        )
    used = {t["taskId"][2:] for t in tasks}
    count = 0
    for key, row in rows:
        if count >= multi:
            break
        messages = _clean(row.get("messages") or [])
        users = [m["content"] for m in messages if m["role"] == "user"]
        if len(users) < max_turns or key[:10] in used:
            continue
        system = [m for m in messages if m["role"] == "system"][:1]
        tasks.append(
            {
                "taskId": f"m-{key[:10]}",
                "kind": "multi",
                "messages": system,
                "userTurns": users[:max_turns],
                "seed": seed + 1000 + count,
            }
        )
        count += 1
    return tasks


def generations(tasks: list[dict[str, Any]]) -> int:
    return sum(len(t.get("userTurns") or [None]) for t in tasks)


def tasks_text(tasks: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(t, ensure_ascii=False, sort_keys=True) + "\n" for t in tasks)


def read_tasks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
