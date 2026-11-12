"""예산 (명세 §12, FR-33). 실행 전 예상 호출 수를 계산하고 상한을 넘으면 거절한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from character_factory_poc.common.config import BudgetConfig
from character_factory_poc.common.errors import BudgetExceeded


@dataclass
class CallPlan:
    stage: str
    description: str
    calls: int
    est_cost_usd: float | None = 0.0


@dataclass
class Budget:
    config: BudgetConfig
    max_calls_override: int | None = None
    used_calls: int = 0
    _lock: object = field(default_factory=Lock, repr=False, compare=False)

    @property
    def max_calls(self) -> int:
        if self.max_calls_override is None:
            return self.config.max_calls_per_command
        return min(self.max_calls_override, self.config.max_calls_per_command)

    def check_plan(self, plans: list[CallPlan]) -> None:
        total = sum(p.calls for p in plans)
        cost = sum(p.est_cost_usd or 0.0 for p in plans)
        if total > self.max_calls:
            raise BudgetExceeded(f"예상 호출 {total}회가 상한 {self.max_calls}회를 넘는다")
        if cost > self.config.max_cost_usd_per_command:
            raise BudgetExceeded(
                f"예상 비용 {cost:.2f} USD가 상한 {self.config.max_cost_usd_per_command:.2f}를 넘는다"
            )

    def consume(self, n: int = 1) -> None:
        with self._lock:
            if self.used_calls + n > self.max_calls:
                raise BudgetExceeded(f"실행 중 호출 상한 {self.max_calls}회에 닿았다")
            self.used_calls += n


def format_plan(plans: list[CallPlan]) -> str:
    lines = ["호출 계획 (dry run; --execute 없이는 실행하지 않는다)"]
    for p in plans:
        lines.append(f"  {p.stage:<6} {p.calls:>4}회  {p.description}")
    total = sum(p.calls for p in plans)
    cost = sum(p.est_cost_usd or 0.0 for p in plans)
    if any(p.est_cost_usd is None for p in plans):
        lines.append(f"  합계 {total}회, 예상 비용 미확인(단가 없음)")
    else:
        lines.append(f"  합계 {total}회, 예상 비용 {cost:.2f} USD")
    return "\n".join(lines)


class RunBudget:
    """Locked durable reservations shared by generation, judging and replies.

    Prices are explicit conservative upper bounds per million tokens. Unknown
    usage retains the reservation; a resume never turns an unknown outcome into
    permission to call the provider again.
    """

    def __init__(
        self,
        path,
        *,
        max_calls,
        max_tokens,
        max_cost_usd,
        input_rate_per_million,
        output_rate_per_million,
        synthetic=False,
    ):
        import math
        from pathlib import Path

        if any(
            x is None or not math.isfinite(x) or x < 0 or (not synthetic and x == 0)
            for x in (input_rate_per_million, output_rate_per_million)
        ):
            raise ValueError("verified or conservative price rates are required")
        if (
            max_calls <= 0
            or max_tokens <= 0
            or not math.isfinite(max_cost_usd)
            or max_cost_usd <= 0
        ):
            raise ValueError("positive finite run budget caps are required")
        self.path = Path(path)
        self.limits = dict(
            maxCalls=max_calls,
            maxTokens=max_tokens,
            maxCostUsd=max_cost_usd,
            inputRate=input_rate_per_million,
            outputRate=output_rate_per_million,
            synthetic=synthetic,
        )
        self.synthetic = synthetic
        self._transaction(lambda state: None)

    def _transaction(self, action):
        import fcntl
        import json
        import os
        import uuid

        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Lock a stable inode; replace the state atomically without a truncate window.
        with self.path.with_suffix(self.path.suffix + ".lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.exists():
                try:
                    state = json.loads(self.path.read_text("utf-8"))
                except (ValueError, OSError) as exc:
                    raise ValueError("corrupt or empty run budget; usage cannot be reset") from exc
            else:
                state = dict(limits=self.limits, reservations={})
            if state["limits"] != self.limits:
                raise ValueError("run budget limits changed; resume cannot reset its envelope")
            result = action(state)
            temporary = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                with temporary.open("w", encoding="utf-8") as stream:
                    stream.write(json.dumps(state, sort_keys=True) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                directory = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temporary.unlink(missing_ok=True)
            return result

    def _totals(self, state):
        rows = state["reservations"].values()
        return (
            len(state["reservations"]),
            sum(r["chargedTokens"] for r in rows),
            sum(r["chargedCost"] for r in state["reservations"].values()),
        )

    @property
    def max_calls(self):
        return self.limits["maxCalls"]

    @property
    def used_calls(self):
        return self._transaction(lambda state: self._totals(state)[0])

    @property
    def used_tokens(self):
        return self._transaction(lambda state: self._totals(state)[1])

    def check_plan(self, plans):
        if sum(p.calls for p in plans) + self.used_calls > self.max_calls:
            raise BudgetExceeded("planned calls exceed remaining shared run envelope")

    def consume(self, n=1):
        raise BudgetExceeded("shared budget requires a token/cost reservation before each call")

    def reserve(self, request_id, *, input_tokens, output_tokens):
        if (
            type(input_tokens) is not int
            or type(output_tokens) is not int
            or min(input_tokens, output_tokens) < 0
        ):
            raise ValueError("token reservation must use nonnegative integer bounds")
        cost = (
            input_tokens * self.limits["inputRate"] + output_tokens * self.limits["outputRate"]
        ) / 1_000_000

        def reserve_one(state):
            if request_id in state["reservations"]:
                raise BudgetExceeded("duplicate request reservation; redraw forbidden")
            calls, tokens, used_cost = self._totals(state)
            if (
                calls + 1 > self.max_calls
                or tokens + input_tokens + output_tokens > self.limits["maxTokens"]
                or used_cost + cost > self.limits["maxCostUsd"]
            ):
                raise BudgetExceeded("shared calls/tokens/cost cap reached")
            state["reservations"][request_id] = dict(
                inputUpper=input_tokens,
                outputUpper=output_tokens,
                chargedTokens=input_tokens + output_tokens,
                chargedCost=cost,
                status="RESERVED",
            )

        self._transaction(reserve_one)

    def settle(self, request_id, *, input_tokens, output_tokens):
        def settle_one(state):
            row = state["reservations"][request_id]
            if row["status"] != "RESERVED":
                raise BudgetExceeded("request was already settled")
            valid = (
                type(input_tokens) is int
                and type(output_tokens) is int
                and min(input_tokens, output_tokens) >= 0
            )
            if not valid:
                row["status"] = "UNKNOWN"
                return False
            row.update(
                status="SETTLED",
                chargedTokens=input_tokens + output_tokens,
                chargedCost=(
                    input_tokens * self.limits["inputRate"]
                    + output_tokens * self.limits["outputRate"]
                )
                / 1_000_000,
            )
            return input_tokens > row["inputUpper"] or output_tokens > row["outputUpper"]

        if self._transaction(settle_one):
            raise BudgetExceeded("provider usage exceeded reserved token bounds")
