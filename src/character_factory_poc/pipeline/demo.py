"""시연 모드 — 켜면 관문을 모두 자동 승인하고 테스터 미리보기 발행·알림까지 간다.

사용자 2026-11-12: "시연 때는 자동 승인 기능이 있어야 할 거 같음. 이거 켜면 모든 승인 일괄로
다 시켜서 배포까지 하고 알림 주게".

- 캐릭터 단위로 켠다(demo-mode.json). 다른 캐릭터의 실제 검토는 그대로다.
- 승인 기록의 reviewer는 "시연 자동 승인"이다. 사람 검토나 품질 합격이 아니다.
- 사람 전용 관문(G0·G1s·G8 등)도 첫 후보·기본 선택으로 넘긴다. 이 예외는 시연 모드에만 있다.
- 프롬프트만 쓰는 캐릭터(PROMPT_ONLY)만 받는다. 실서비스 chat-svc에 캐릭터별 모델 경로가 없다.
- 유료 단계도 확인 없이 돌리되, 시연을 켠 뒤 쓴 추정 비용이 상한을 넘으면 멈춘다.
- 발행은 테스터 전용(content.segments preview)만 한다. 일반 공개 발행 경로는 없다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.store import read_json

DEMO_FILE = "demo-mode.json"
SCHEMA = "demo-mode-v1"
REVIEWER = "시연 자동 승인"
REASON = "시연 모드 자동 승인. 사람 검토·품질 합격이 아니다."
DEFAULT_BUDGET_USD = 15.0


@dataclass(frozen=True)
class DemoMode:
    enabled: bool
    budgetUsd: float = DEFAULT_BUDGET_USD
    publish: bool = True
    enabledAt: str = ""
    schemaVersion: str = SCHEMA


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def read_demo_mode(char_dir: Path) -> DemoMode | None:
    path = Path(char_dir) / DEMO_FILE
    if not path.is_file():
        return None
    raw = json.loads(path.read_text("utf-8"))
    mode = DemoMode(
        enabled=bool(raw.get("enabled")),
        budgetUsd=float(raw.get("budgetUsd", DEFAULT_BUDGET_USD)),
        publish=bool(raw.get("publish", True)),
        enabledAt=str(raw.get("enabledAt", "")),
    )
    return mode if mode.enabled else None


def write_demo_mode(
    char_dir: Path, *, enabled: bool, budget_usd: float = DEFAULT_BUDGET_USD, publish: bool = True
) -> DemoMode:
    from character_factory_poc.pipeline.origin import read_model_mode

    if enabled:
        if (Path(char_dir) / "model-mode.json").is_file() and read_model_mode(
            char_dir
        ) != "PROMPT_ONLY":
            raise FactoryError("시연 모드는 프롬프트만 쓰는 캐릭터(PROMPT_ONLY)에서만 켤 수 있어요")
        if not 0 < budget_usd <= 200:
            raise FactoryError("시연 예산 상한은 0보다 크고 200달러 이하여야 해요")
    previous = read_demo_mode(char_dir)
    mode = DemoMode(
        enabled=enabled,
        budgetUsd=float(budget_usd),
        publish=publish,
        enabledAt=(previous.enabledAt if previous and enabled else _now()) if enabled else "",
    )
    path = Path(char_dir) / DEMO_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(mode), ensure_ascii=False, indent=2) + "\n", "utf-8")
    events = Path(char_dir) / "demo-mode-events.jsonl"
    with events.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": _now(), **asdict(mode)}, ensure_ascii=False) + "\n")
    return mode


def spent_since(ctx, cid: str, since: str) -> float:
    """시연을 켠 뒤 이 캐릭터가 쓴 추정 비용(달러). 비용 미확인 호출은 0으로 본다."""
    total = 0.0
    for row in ctx.ledger(cid).calls():
        if since and str(row.get("at", "")) < since:
            continue
        cost = row.get("estCostUsd")
        if isinstance(cost, int | float):
            total += float(cost)
    return round(total, 4)


def demo_answer(ctx, cid: str, gate: str) -> dict:
    """관문마다 첫 후보·기본 선택을 고르는 답. 승인 형식은 각 관문 approve와 같다."""
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    rev = state.gate(gate).rev
    answer: dict = {"decision": "APPROVE", "reviewer": REVIEWER, "reasons": REASON}
    if gate == "G3":
        folder = char_dir / "s3-plan" / str(rev)
        if (folder / "variants.json").is_file():
            first = read_json(folder / "variants.json")["candidates"][0]
            answer.update(decision="SELECT", selections=[first["variantId"]])
    elif gate == "G6":
        answer["evidenceReviewed"] = True
    elif gate == "G8":
        from character_factory_poc.stages.s10_eval.prompt_only import PROMPT_ONLY_FILE

        folder = char_dir / "s10-eval" / str(rev)
        doc = read_json(folder / PROMPT_ONLY_FILE) if (folder / PROMPT_ONLY_FILE).is_file() else {}
        options = doc.get("adoptOptions") or []
        if not options:
            raise FactoryError("G8: 학습 없이 진행할 선택지가 없어 시연 자동 승인을 할 수 없어요")
        answer.update(decision="SELECT", adopted=options[0])
    elif gate in {"G7a", "G7"}:
        raise FactoryError(f"{gate}: 학습 데이터 판정은 시연 자동 승인 대상이 아니에요")
    return answer


def approve_demo(ctx, cid: str, gate: str) -> None:
    from character_factory_poc.pipeline.approve import approve_gate

    approve_gate(ctx, cid, gate, demo_answer(ctx, cid, gate))


__all__ = [
    "DEFAULT_BUDGET_USD",
    "DEMO_FILE",
    "REVIEWER",
    "DemoMode",
    "approve_demo",
    "demo_answer",
    "read_demo_mode",
    "spent_since",
    "write_demo_mode",
]
