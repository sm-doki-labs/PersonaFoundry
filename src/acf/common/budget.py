"""예산 (명세 §12, FR-33). 실행 전 예상 호출 수를 계산하고 상한을 넘으면 거절한다."""

from __future__ import annotations

from dataclasses import dataclass

from acf.common.config import BudgetConfig
from acf.common.errors import BudgetExceeded


@dataclass
class CallPlan:
    stage: str
    description: str
    calls: int
    est_cost_usd: float = 0.0


@dataclass
class Budget:
    config: BudgetConfig
    max_calls_override: int | None = None
    used_calls: int = 0

    @property
    def max_calls(self) -> int:
        if self.max_calls_override is None:
            return self.config.max_calls_per_command
        return min(self.max_calls_override, self.config.max_calls_per_command)

    def check_plan(self, plans: list[CallPlan]) -> None:
        total = sum(p.calls for p in plans)
        cost = sum(p.est_cost_usd for p in plans)
        if total > self.max_calls:
            raise BudgetExceeded(f"예상 호출 {total}회가 상한 {self.max_calls}회를 넘는다")
        if cost > self.config.max_cost_usd_per_command:
            raise BudgetExceeded(
                f"예상 비용 {cost:.2f} USD가 상한 {self.config.max_cost_usd_per_command:.2f}를 넘는다"
            )

    def consume(self, n: int = 1) -> None:
        if self.used_calls + n > self.max_calls:
            raise BudgetExceeded(f"실행 중 호출 상한 {self.max_calls}회에 닿았다")
        self.used_calls += n


def format_plan(plans: list[CallPlan]) -> str:
    lines = ["호출 계획 (dry run; --execute 없이는 실행하지 않는다)"]
    for p in plans:
        lines.append(f"  {p.stage:<6} {p.calls:>4}회  {p.description}")
    total = sum(p.calls for p in plans)
    cost = sum(p.est_cost_usd for p in plans)
    lines.append(f"  합계 {total}회, 예상 비용 {cost:.2f} USD")
    return "\n".join(lines)
