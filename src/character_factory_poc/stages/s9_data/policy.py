"""S9 창작 인물 정책 검사와 보고 (D-0078, docs/guides/qlora-authored/02-cluster-ratios.md).

세 가지를 학습 분할에 대해 계산한다.

1. 클러스터 비율을 대화·assistant 답변·지도 토큰 세 분모로 보고한다. 지도 토큰은 학습 템플릿
   토큰화가 없어 assistant 글자 수 ÷ `chars_per_token` 근사이고, 보고서에 근사라고 적는다.
2. 정책 `dataset.turnMix`의 턴 구간과 비구간 지표(`maxTurns`, `supervisedTokenShareTurnsGe10`)를
   관측값·목표 범위·판정(PASS/OUT_OF_RANGE/UNKNOWN)으로 낸다. 벗어나도 차단하지 않고 경고다.
   허용 폭이 미정(null)이면 UNKNOWN이고 역시 경고로만 남긴다(02-cluster-ratios.md 8절).
3. 보호 클러스터(`protected`)가 분할 뒤에도 학습 목표의 `protectedMinRatio` 이상 남았는지
   본다. 모자라거나 0이면 차단 실패다(02-cluster-ratios.md 9절 핵심 사례 보호 규칙).

long 클러스터의 턴 범위 위반은 `conversation_items`가 대화 단위 차단 항목으로 내고, 대량 작성의
재작성 고리가 그 대화를 다시 쓴다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from character_factory_poc.contracts.dataset import Conversation, DataPlan, TurnTarget
from character_factory_poc.stages.s9_data import checks
from character_factory_poc.stages.s9_data.plan import S9Config

PASS, OUT, UNKNOWN = "PASS", "OUT_OF_RANGE", "UNKNOWN"
TOKEN_NOTE = (
    "supervisedTokens는 근사다: assistant 메시지 글자 수 ÷ charsPerToken. "
    "학습 템플릿 토큰화와 서버 토큰 해시 일치는 S10에서 따로 확인한다"
)
_EPS = 1e-9


def supervised_approx(conv: Conversation, chars_per_token: float) -> int:
    return checks.approx_tokens(checks.assistant_text(conv), chars_per_token)


def judge(observed: float | None, low: float | None, high: float | None) -> str:
    if observed is None or (low is None and high is None):
        return UNKNOWN
    if low is not None and observed < low - _EPS:
        return OUT
    if high is not None and observed > high + _EPS:
        return OUT
    return PASS


def _range_text(low: float | None, high: float | None) -> str:
    lo = "미정" if low is None else f"{low:g}"
    hi = "미정" if high is None else f"{high:g}"
    return f"{lo}~{hi}"


def _share(part: float, total: float) -> float | None:
    return round(part / total, 4) if total else None


def cluster_shares(
    plan: DataPlan, train: list[Conversation], cfg: S9Config
) -> tuple[dict[str, Any], list[str]]:
    """학습 분할의 클러스터 비율을 세 분모로 낸다. 정책이 있으면 목표·출처·판정을 붙인다."""
    with_policy = plan.policy is not None
    per: dict[str, dict[str, int]] = {}
    for conv in train:
        row = per.setdefault(conv.clusterId, {"conversations": 0, "replies": 0, "tokens": 0})
        row["conversations"] += 1
        row["replies"] += checks.assistant_turns(list(conv.messages))
        row["tokens"] += supervised_approx(conv, cfg.chars_per_token)
    total_c = sum(r["conversations"] for r in per.values())
    total_r = sum(r["replies"] for r in per.values())
    total_t = sum(r["tokens"] for r in per.values())
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    undecided: list[str] = []
    for c in plan.clusters:
        got = per.get(c.clusterId, {"conversations": 0, "replies": 0, "tokens": 0})
        row: dict[str, Any] = {
            "clusterId": c.clusterId,
            "label": c.label,
            "targetShare": c.share,
            "conversations": got["conversations"],
            "conversationShare": _share(got["conversations"], total_c),
            "replies": got["replies"],
            "replyShare": _share(got["replies"], total_r),
            "supervisedTokensApprox": got["tokens"],
            "supervisedTokenShareApprox": _share(got["tokens"], total_t),
        }
        if with_policy and c.policy is not None:
            pol = c.policy
            verdict = judge(row["conversationShare"], pol.minShare, pol.maxShare)
            row.update(
                targetShareSource=pol.shareSource,
                targetShareNote=pol.shareNote,
                protected=pol.protected,
                minShare=pol.minShare,
                minShareSource=pol.minShareSource,
                maxShare=pol.maxShare,
                maxShareSource=pol.maxShareSource,
                verdict=verdict,
                verdictBasis="conversationShare",
            )
            if verdict == OUT:
                warnings.append(
                    f"클러스터 비율 {c.clusterId}: 학습 대화 비중 {row['conversationShare']}가 "
                    f"허용 범위 {_range_text(pol.minShare, pol.maxShare)} 밖이다(차단하지 않음)"
                )
            elif pol.minShare is None and pol.maxShare is None:
                undecided.append(c.clusterId)
        rows.append(row)
    if undecided:
        warnings.append(
            "클러스터 비율 허용 폭 미정으로 판정하지 않음(UNKNOWN): "
            + ", ".join(undecided)
            + " (02-cluster-ratios.md 8절, 차단하지 않음)"
        )
    body = {
        "split": "train",
        "denominators": {
            "conversations": total_c,
            "replies": total_r,
            "supervisedTokensApprox": total_t,
        },
        "supervisedTokens": {
            "approximate": True,
            "charsPerToken": cfg.chars_per_token,
            "note": TOKEN_NOTE,
        },
        "rows": rows,
    }
    return body, warnings


def _turn_row(
    target: TurnTarget, turns: list[int], tokens: list[int]
) -> tuple[dict[str, Any], bool]:
    total = len(turns)
    approximate = False
    count: int | None = None
    observed: float | None
    if target.kind == "band":
        lo, hi = target.low or 0, target.high or 0
        count = sum(1 for t in turns if lo <= t <= hi)
        observed = _share(count, total)
    elif target.kind == "max_turns":
        observed = float(max(turns)) if turns else None
    else:
        approximate = True
        lo = target.low or 0
        all_tokens = sum(tokens)
        observed = _share(sum(k for t, k in zip(turns, tokens, strict=True) if t >= lo), all_tokens)
    row = {
        "key": target.key,
        "kind": target.kind,
        "observed": observed,
        "count": count,
        "min": target.min,
        "minSource": target.minSource,
        "max": target.max,
        "maxSource": target.maxSource,
        "verdict": judge(observed, target.min, target.max),
        "blocking": False,
    }
    if approximate:
        row["approximate"] = True
        row["note"] = TOKEN_NOTE
    return row, target.min is None and target.max is None


def turn_distribution(
    plan: DataPlan, train: list[Conversation], cfg: S9Config
) -> tuple[dict[str, Any] | None, list[str]]:
    if plan.policy is None:
        return None, []
    turns = [checks.assistant_turns(list(c.messages)) for c in train]
    tokens = [supervised_approx(c, cfg.chars_per_token) for c in train]
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    undecided: list[str] = []
    for target in plan.policy.turnTargets:
        row, open_range = _turn_row(target, turns, tokens)
        rows.append(row)
        if row["verdict"] == OUT:
            warnings.append(
                f"턴 분포 {target.key}: 관측 {row['observed']}, 목표 "
                f"{_range_text(target.min, target.max)}(차단하지 않음)"
            )
        elif open_range:
            undecided.append(target.key)
    bands = [t for t in plan.policy.turnTargets if t.kind == "band"]
    outside = sum(1 for t in turns if not any((b.low or 0) <= t <= (b.high or 0) for b in bands))
    if outside:
        warnings.append(f"턴 분포: 어느 구간에도 들지 않는 학습 대화가 {outside}개다")
    if undecided:
        warnings.append("턴 분포 목표 미정(UNKNOWN): " + ", ".join(undecided))
    body = {
        "split": "train",
        "unit": plan.policy.turnUnit,
        "conversations": len(turns),
        "outsideBands": outside,
        "rows": rows,
        "rule": "범위를 벗어나도 차단하지 않고 경고로 둔다",
    }
    return body, warnings


def conversation_items(plan: DataPlan, conversations: list[Conversation]) -> list[dict[str, str]]:
    """long처럼 턴 조건이 있는 클러스터의 대화 단위 차단 항목. 재작성 고리가 다시 쓴다."""
    rules = {
        c.clusterId: c.policy.turnRule
        for c in plan.clusters
        if c.policy is not None and c.policy.turnRule is not None
    }
    items: list[dict[str, str]] = []
    for conv in conversations:
        rule = rules.get(conv.clusterId)
        if rule is None:
            continue
        turns = checks.assistant_turns(list(conv.messages))
        if not rule.minAssistantTurns <= turns <= rule.maxAssistantTurns:
            items.append(
                {
                    "check": "long_turn_range",
                    "conversationId": conv.conversationId,
                    "detail": f"assistant 턴이 {turns}개다. {rule.minAssistantTurns}~"
                    f"{rule.maxAssistantTurns}턴으로 다시 쓴다",
                }
            )
        if conv.checks.blocking.get("long_structure") is False:
            items.append(
                {
                    "check": "long_structure",
                    "conversationId": conv.conversationId,
                    "detail": "화제 전환·후반 계기 위치 표시가 조건에 못 미친다",
                }
            )
    return items


def protected_survival(
    plan: DataPlan,
    conversations: list[Conversation],
    train: list[Conversation],
    anchors: dict[str, list[str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    """보호 클러스터의 분할 전후 수. 학습 목표의 최소 비율보다 적으면 차단 항목을 낸다."""
    if plan.policy is None:
        return [], [], []
    ratio = plan.policy.protectedMinRatio
    present = {c.conversationId for c in conversations}
    rows: list[dict[str, Any]] = []
    blocking: list[dict[str, str]] = []
    warnings: list[str] = []
    for c in plan.clusters:
        if c.policy is None or not c.policy.protected:
            continue
        written = sum(1 for x in conversations if x.clusterId == c.clusterId)
        kept = sum(1 for x in train if x.clusterId == c.clusterId)
        target = c.targetConversations
        minimum = max(1, math.ceil(target * ratio - _EPS)) if target > 0 else 0
        adopted = list((anchors or {}).get(c.clusterId, []))
        removed = [a for a in adopted if a not in present]
        ok = kept >= minimum
        rows.append(
            {
                "clusterId": c.clusterId,
                "targetTrain": target,
                "writtenBeforeSplit": written,
                "trainAfterSplit": kept,
                "minimumTrain": minimum,
                "minRatio": ratio,
                "minRatioSource": plan.policy.protectedMinRatioSource,
                "verdict": PASS if ok else "BLOCKED",
                "anchorsAdopted": adopted,
                "anchorsRemoved": removed,
            }
        )
        if target == 0:
            warnings.append(
                f"보호 클러스터 {c.clusterId}의 학습 목표가 0이다. 클러스터를 빼는 결정은 결정 "
                "장부에 새 ID로 남긴다(02-cluster-ratios.md 9절 6항)"
            )
        elif not ok:
            blocking.append(
                {
                    "check": "protected_cluster_survival",
                    "conversationId": f"cluster:{c.clusterId}",
                    "detail": f"보호 클러스터 {c.clusterId}의 학습 대화가 {kept}개로 목표 "
                    f"{target}의 {ratio:g}배({minimum}개)보다 적다",
                }
            )
        if removed:
            warnings.append(
                f"보호 클러스터 {c.clusterId}: G7a 채택 샘플 {len(removed)}개가 기계 검사 "
                f"재작성으로 빠졌다({', '.join(removed[:5])})"
            )
    return rows, blocking, warnings


@dataclass
class PolicyReport:
    blocking: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cluster_shares: dict[str, Any] = field(default_factory=dict)
    turn_distribution: dict[str, Any] | None = None
    protected: list[dict[str, Any]] = field(default_factory=list)
    policy: dict[str, Any] | None = None

    def body(self) -> dict[str, Any]:
        out: dict[str, Any] = {"clusterShares": self.cluster_shares}
        if self.policy is not None:
            out["policy"] = {
                **self.policy,
                "turnDistribution": self.turn_distribution,
                "protectedClusters": self.protected,
                "blocking": self.blocking,
                "warnings": self.warnings,
            }
        return out


def evaluate(
    plan: DataPlan,
    conversations: list[Conversation],
    train: list[Conversation],
    cfg: S9Config,
    anchors: dict[str, list[str]] | None = None,
) -> PolicyReport:
    shares, share_warnings = cluster_shares(plan, train, cfg)
    report = PolicyReport(cluster_shares=shares)
    if plan.policy is None:
        return report
    turns, turn_warnings = turn_distribution(plan, train, cfg)
    rows, blocking, protect_warnings = protected_survival(plan, conversations, train, anchors)
    report.turn_distribution = turns
    report.protected = rows
    report.blocking = blocking
    report.warnings = share_warnings + turn_warnings + protect_warnings
    report.policy = {
        "name": plan.policy.name,
        "status": plan.policy.status,
        "policySha256": plan.policy.policySha256,
        "proposalValues": plan.policy.proposalValues,
        "notes": plan.policy.notes,
    }
    return report
