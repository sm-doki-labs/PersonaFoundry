"""비용 보고서 cost-report-v1 (명세 §24.5, FR-69, LLD §22.2).

원장 행만 읽는다. 재계산 모드도 결과만 돌려주고 원래 원장의 비용 칸을 고치지 않는다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

SCHEMA = "cost-report-v1"
# 이미지·영상 행은 각자의 단가 계산이 있으므로 기록된 비용을 그대로 쓴다(PRD §20.5).
NO_RECOMPUTE_KINDS = frozenset({"IMAGE", "VIDEO"})
# codex exec 행(PRD §20.5 범위 밖). 텍스트 덱 호출도 kind AGENT를 쓰므로 공급자로 가린다.
CODEX_KINDS = frozenset({"AGENT", "AGENT_TAINTED"})
CODEX_PROVIDERS = frozenset({"codex_exec", "fake_codex"})
TOKEN_KEYS = (
    "inputTokens",
    "cachedInputTokens",
    "cacheWriteTokens",
    "outputTokens",
    "reasoningTokens",
)
BILLING_LABELS = {
    "api_billed": "공식 API 청구 추정",
    "relay_equivalent": "API 환산(중계 호출)",
    "unverified": "과금 구분 미확인",
    "none": "비용 없음(가짜 공급자)",
    "unknown": "과금 구분 미상(이전 기록)",
}
LEGACY_ROUTE_CLASSES = {"opencodex": "relay_equivalent", "test": "unverified", "api": "api_billed"}


def billing_class(row: dict[str, Any]) -> str:
    billing = row.get("billing")
    if isinstance(billing, dict) and billing.get("class"):
        return str(billing["class"])
    # 과금 구분이 없는 이전 기록: 가짜 공급자와 덱 경로가 남은 행만 추정하고 나머지는 미상이다.
    if row.get("provider") == "fake":
        return "none"
    route = (row.get("textBinding") or {}).get("route")
    if route in LEGACY_ROUTE_CLASSES:
        return LEGACY_ROUTE_CLASSES[route]
    return "unknown"


def outside_token_pricing(row: dict[str, Any]) -> bool:
    """단가표로 값을 매기지 않는 행: 이미지·영상과 codex exec 실행."""
    kind = row.get("kind")
    return kind in NO_RECOMPUTE_KINDS or (
        kind in CODEX_KINDS and row.get("provider") in CODEX_PROVIDERS
    )


def counts_as_unpriced(row: dict[str, Any]) -> bool:
    """비용 값이 없을 때 이 행을 단가 미확인으로 셀지(FR-67). 비용 유무는 호출한 쪽이 본다."""
    return bool(row.get("ok")) and billing_class(row) != "none" and not outside_token_pricing(row)


def price_model(row: dict[str, Any]) -> str:
    """재계산에 쓸 요청 모델. 단가 기록 → 덱 해석 모델 → 응답 모델 순으로 고른다."""
    return str(
        (row.get("price") or {}).get("model")
        or (row.get("textBinding") or {}).get("model")
        or row.get("model")
        or ""
    )


def _usage(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "inputTokens": row.get("inputTokens"),
        "cachedInputTokens": row.get("cachedInputTokens"),
        "cacheWriteTokens": row.get("cacheWriteTokens"),
        "outputTokens": row.get("outputTokens"),
        "reasoningTokens": row.get("reasoningTokens"),
        "finishReason": row.get("finishReason"),
        "usageSource": row.get("usageSource"),
    }


def _bucket() -> dict[str, Any]:
    return {
        "calls": 0,
        **{k: 0 for k in TOKEN_KEYS},
        "estCostUsd": 0.0,
        "unpricedCalls": 0,
        "truncatedCalls": 0,
        "failedCalls": 0,
    }


def _add(bucket: dict[str, Any], row: dict[str, Any], cost: float | None) -> None:
    bucket["calls"] += 1
    for key in TOKEN_KEYS:
        bucket[key] += row.get(key) or 0
    if cost is not None:
        bucket["estCostUsd"] += cost
    elif counts_as_unpriced(row):
        # 비용 미확인은 0으로 더하지 않고 따로 센다(FR-67).
        bucket["unpricedCalls"] += 1
    if not row.get("ok"):
        bucket["failedCalls"] += 1
    if row.get("finishReason") == "length":
        bucket["truncatedCalls"] += 1


def _round(bucket: dict[str, Any]) -> dict[str, Any]:
    bucket["estCostUsd"] = round(bucket["estCostUsd"], 8)
    return bucket


def _recomputed(row, at, overrides, pricing, refs: list[dict]) -> float | None:
    if outside_token_pricing(row):
        return row.get("estCostUsd")
    if not row.get("ok") or billing_class(row) == "none":
        return None
    entry = pricing.lookup(price_model(row), at, overrides)
    if entry is None:
        return None
    ref = pricing.price_ref(entry)
    if ref is not None and ref not in refs:
        refs.append(ref)
    return pricing.estimate(_usage(row), entry).get("usd")


def build(
    rows: list[dict[str, Any]],
    *,
    recompute: bool = False,
    overrides: dict | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """원장 행으로 cost-report-v1을 만든다.

    recompute=True면 행의 estCostUsd 대신 at(기본 지금 UTC)의 단가로 다시 계산한다.
    단가표 기간이 확인일부터 시작하므로 과거 호출 시각으로 찾지 않고 at 기준으로 환산한다.
    """
    refs: list[dict] = []
    if recompute:
        from character_factory_poc.common import pricing

        at = at or datetime.now(UTC)
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
    totals = _bucket()
    by_stage: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    by_billing: dict[str, dict[str, Any]] = {}
    for row in rows:
        if recompute:
            cost = _recomputed(row, at, dict(overrides or {}), pricing, refs)
        else:
            cost = row.get("estCostUsd")
        cls = billing_class(row)
        for bucket in (
            totals,
            by_stage.setdefault(str(row.get("stage", "")), _bucket()),
            by_model.setdefault(str(row.get("model", "")), _bucket()),
            by_billing.setdefault(cls, _bucket()),
        ):
            _add(bucket, row, cost)
    _round(totals)
    for group in (by_stage, by_model, by_billing):
        for bucket in group.values():
            _round(bucket)
    for cls in ("api_billed", "relay_equivalent"):
        totals[cls] = by_billing[cls]["estCostUsd"] if cls in by_billing else 0.0
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "basis": "현재 단가 환산" if recompute else "원장 기록",
        "totals": totals,
        "byStage": by_stage,
        "byModel": by_model,
        "byBilling": by_billing,
        "billingLabels": {cls: BILLING_LABELS.get(cls, cls) for cls in sorted(by_billing)},
    }
    if recompute:
        report["recomputedAt"] = at.isoformat(timespec="seconds")
        report["priceTables"] = sorted({str(r.get("table")) for r in refs if r.get("table")})
        report["priceRefs"] = refs
    return report
