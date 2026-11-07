"""S9 데이터 계획 고정 (LLD §5.14·§8.8, D-0044·D-0045).

G6에서 승인한 `prompt-pair-v1`의 짧은 system과 `trait-sheet-v1`로 `data-plan-v1`을
고정한다. 기본값은 학습 가이드 §6·§7·§13의 소민 기준 배합이다: 학습 640대화,
56:8:22:7:7, 클러스터별 샘플 12개, 검증 기반 60 + 보강 클러스터별 10%, 동시 호출 4.

`[stages.s9] policy = "qlora-authored-v1"`이면 창작 인물 정책(D-0078)의 6클러스터(base 0.51,
situation, history, ownership, conflict, long 0.05)와 라벨·재료·보호 여부·출처를 계획에 쓴다.
정책 수치의 source가 "proposal"이면 운영 시작값이고, 계획의 `policy.proposalValues`에 남긴다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from character_factory_poc.common import qlora_policy as qp
from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file, sha256_of
from character_factory_poc.common.errors import CheckFailed, FactoryError, GateNotApprovedError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import next_rev, write_manifest, write_once_json
from character_factory_poc.contracts.dataset import (
    ClusterPlan,
    ClusterPolicy,
    DataPlan,
    PlanPolicy,
    TurnRule,
    TurnTarget,
    ValidationPlan,
)
from character_factory_poc.contracts.persona import (
    PromptPair,
    PromptPairV2,
    TraitSheet,
    require_short,
)
from character_factory_poc.contracts.persona import (
    load_prompt_pair as read_pair,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s9_data import deck

CLUSTERS: tuple[str, ...] = ("base", "situation", "history", "ownership", "conflict")
DEFAULT_SHARES: dict[str, float] = {
    "base": 0.56,
    "situation": 0.08,
    "history": 0.22,
    "ownership": 0.07,
    "conflict": 0.07,
}
LABELS: dict[str, str] = {
    "base": "말투·관계·일상 기반",
    "situation": "상황 대응: 경청·조건·거절 수용·자기 잘못 수습",
    "history": "이력 정확성: 회상·변경·미제공 사실·조건 유지",
    "ownership": "주체·자기 일정: 생성·유지·합의·취소 구분",
    "conflict": "서운함·갈등: 표현·사과·회복·덜 풀림·선 긋기",
}
DEFAULT_MATERIALS: dict[str, tuple[str, ...]] = {
    "base": ("SNS_REWRITE", "SYNTH"),
    "situation": ("SYNTH",),
    "history": ("SYNTH",),
    "ownership": ("SYNTH",),
    "conflict": ("SYNTH",),
}
GUIDE_REF = (
    "학습 가이드 §6·§7·§13 (한소민 QLoRA, 2026-10-23; 2026-10-27 확인): "
    "/Users/johnhuh619/Documents/Codex/2026-10-14/gem/somin-qlora-project/"
    "docs/데이터셋-프롬프트-구축-가이드.md"
)
POLICY_GUIDE_REF = (
    "창작 인물 QLoRA 운영 규격 (D-0078, 2026-11-02 초안·제안): "
    "docs/guides/qlora-authored/README.md, 02-cluster-ratios.md · "
    "정책 자원 resources/qlora-authored-policy-v1.json"
)
KNOWN_CLUSTERS: frozenset[str] = frozenset((*CLUSTERS, "long"))
FACTORY_MATERIALS: frozenset[str] = frozenset({"SNS_REWRITE", "SYNTH"})
PROTECTED_MIN_RATIO = 0.9
PROTECTED_MIN_RATIO_SOURCE = (
    "proposal (공장 운영 시작값. 정책 dataset.protectedAnchors에 수치가 없어 split.py의 "
    "학습 목표 90% 경고선과 같은 값을 쓴다)"
)
PROPOSAL_NOTE = "source가 proposal인 값은 검증된 최적값이 아니라 운영 시작값이다"


@dataclass(frozen=True)
class S9Config:
    """`[stages.s9]` 설정. 계약에 없는 운영값(동시 호출·배치)도 여기서만 읽는다."""

    target: int
    shares: dict[str, float]
    materials: dict[str, tuple[str, ...]]
    sample_size: int
    concurrency: int
    batch_size: int
    max_retries: int
    validation_base: int
    validation_augmented_share: float
    eval_per_cluster: int
    max_length_tokens: int
    chars_per_token: float
    phrase_ngram: int
    phrase_max_conversations: int
    bubble_max_conversations: int
    forbidden_phrases: tuple[str, ...]
    source_facts: tuple[str, ...]
    sns_path: str
    sns_limit: int
    guide_ref: str
    policy_name: str = ""
    cluster_ids: tuple[str, ...] = CLUSTERS
    labels: dict[str, str] = field(default_factory=lambda: dict(LABELS))
    cluster_policies: dict[str, ClusterPolicy] = field(default_factory=dict)
    plan_policy: PlanPolicy | None = None
    protected_min_ratio: float = PROTECTED_MIN_RATIO

    def turn_rule(self, cluster: str) -> TurnRule | None:
        pol = self.cluster_policies.get(cluster)
        return pol.turnRule if pol is not None else None


def _int(value: Any, name: str, problems: list[str], *, default: int, low: int, high: int) -> int:
    if value is None:
        return default
    if type(value) is not int or not low <= value <= high:
        problems.append(f"{name}은 {low}~{high}의 정수다(받은 값 {value!r})")
        return default
    return value


def _float(
    value: Any, name: str, problems: list[str], *, default: float, low: float, high: float
) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
        problems.append(f"{name}은 {low}~{high}의 수다(받은 값 {value!r})")
        return default
    return float(value)


def _str_list(value: Any, name: str, problems: list[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        problems.append(f"{name}은 비어 있지 않은 문자열 목록이다")
        return ()
    return tuple(v.strip() for v in value)


@dataclass
class _PolicyDefaults:
    """정책에서 읽은 클러스터 기본값. 설정 덮어쓰기 전 상태다."""

    name: str
    raw: dict[str, Any]
    cluster_ids: tuple[str, ...]
    labels: dict[str, str]
    shares: dict[str, float]
    materials: dict[str, tuple[str, ...]]
    material_notes: dict[str, list[str]]
    target: int
    target_source: str


def _policy_materials(entries: list[str]) -> tuple[tuple[str, ...], list[str]]:
    """정책 재료 표기를 공장 재료 코드로 옮긴다. 옮길 수 없는 표기는 메모로 남긴다."""
    picked: list[str] = []
    notes: list[str] = []
    for entry in entries:
        text = str(entry).strip()
        code = text.split()[0] if text else ""
        if code not in FACTORY_MATERIALS:
            notes.append(f"{text!r}: 공장 재료 코드가 아니어서 이번 계획에서 쓰지 않는다")
            continue
        if "stitch" in text:
            notes.append(
                f"{text!r}: SNS 흐름 여러 개를 잇는 재작성은 공장에 없어 쓰지 않는다"
                "(SNS 재작성은 원본 턴 수를 그대로 둔다)"
            )
            continue
        if code not in picked:
            picked.append(code)
    return (tuple(picked) or ("SYNTH",)), notes


def _policy_defaults(name: str, problems: list[str]) -> _PolicyDefaults | None:
    try:
        raw = qp.load_policy(name)
    except ValueError as e:
        problems.append(f"policy: {e}")
        return None
    rows = qp.clusters(raw)
    ids = tuple(str(c.get("id")) for c in rows)
    unknown = [c for c in ids if c not in KNOWN_CLUSTERS]
    if unknown or "base" not in ids or len(set(ids)) != len(ids):
        problems.append(
            f"policy {name}: 클러스터 목록을 계획에 쓸 수 없다({list(ids)}; "
            f"허용 {sorted(KNOWN_CLUSTERS)}, base 필수, 중복 금지)"
        )
        return None
    materials: dict[str, tuple[str, ...]] = {}
    notes: dict[str, list[str]] = {}
    for c in rows:
        materials[c["id"]], notes[c["id"]] = _policy_materials(list(c.get("materials") or []))
    target_node = (raw.get("dataset") or {}).get("targetTrainConversations")
    return _PolicyDefaults(
        name=name,
        raw=raw,
        cluster_ids=ids,
        labels={c["id"]: str(c.get("label") or c["id"]) for c in rows},
        shares=qp.cluster_shares(raw),
        materials=materials,
        material_notes=notes,
        target=int(qp.value(target_node, 640)),
        target_source=qp.source(target_node) or "proposal",
    )


def _long_rule(raw: dict[str, Any], cluster: dict[str, Any]) -> TurnRule:
    """long 클러스터 조건. 정책 turnRule 숫자 필드를 읽고, 없으면 설명문 값을 쓴다."""
    ds = raw.get("dataset") or {}
    low = ds.get("longDialogueMinTurns")
    high = ((ds.get("turnMix") or {}).get("maxTurns") or {}).get("max")
    rule = cluster.get("turnRule") or {}
    desc_src = "policy clusters[long].description (숫자 필드가 없어 문장에서 옮긴 값)"

    def field(key: str, default: float, note: str) -> tuple[float, str]:
        node = rule.get(key)
        if node is None:
            return default, f"{desc_src}: {note}"
        return float(qp.value(node, default)), f"clusters[long].turnRule.{key}: " + (
            qp.source(node) or "미정"
        )

    shifts, shifts_src = field("minTopicShifts", 2, "topic changes at least twice")
    triggers, triggers_src = field("minLateTriggers", 2, "2-3 trigger situations")
    late, late_src = field("lateTriggerFrom", 0.5, "after 50-65% of the dialogue")
    return TurnRule(
        minAssistantTurns=int(qp.value(low, 15)),
        maxAssistantTurns=int(qp.value(high, 30)),
        minTopicShifts=int(shifts),
        minLateTriggers=int(triggers),
        lateTriggerFrom=late,
        sources={
            "minAssistantTurns": "dataset.longDialogueMinTurns: " + (qp.source(low) or "미정"),
            "maxAssistantTurns": "dataset.turnMix.maxTurns.max: " + (qp.source(high) or "미정"),
            "minTopicShifts": shifts_src,
            "minLateTriggers": triggers_src,
            "lateTriggerFrom": late_src,
        },
        description=str(cluster.get("description") or ""),
    )


_BAND = re.compile(r"^(\d+)-(\d+)$")
_SHARE_GE = re.compile(r"^supervisedTokenShareTurnsGe(\d+)$")


def _turn_targets(raw: dict[str, Any]) -> tuple[list[TurnTarget], list[str]]:
    mix = (raw.get("dataset") or {}).get("turnMix") or {}
    out: list[TurnTarget] = []
    notes: list[str] = []
    for key, spec in mix.items():
        if key == "unit" or not isinstance(spec, dict):
            continue
        lo, hi = spec.get("min"), spec.get("max")
        bounds = {
            "min": qp.value(lo),
            "minSource": qp.source(lo),
            "max": qp.value(hi),
            "maxSource": qp.source(hi),
        }
        if m := _BAND.match(key):
            out.append(TurnTarget(key=key, kind="band", low=int(m[1]), high=int(m[2]), **bounds))
        elif key == "maxTurns":
            out.append(TurnTarget(key=key, kind="max_turns", **bounds))
        elif m := _SHARE_GE.match(key):
            out.append(
                TurnTarget(key=key, kind="supervised_token_share_ge", low=int(m[1]), **bounds)
            )
        else:
            notes.append(f"turnMix.{key}: 해석 규칙이 없어 판정하지 않는다")
    return out, notes


def _proposal_paths(raw: dict[str, Any]) -> list[str]:
    """계획에 쓰는 정책 수치 가운데 source가 proposal인 것."""
    out: list[str] = []

    def visit(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if "value" in node and qp.source(node) == "proposal":
                out.append(path)
                return
            for k, v in node.items():
                visit(v, f"{path}.{k}")

    for c in qp.clusters(raw):
        for key in ("targetShare", "minShare", "maxShare"):
            visit(c.get(key), f"clusters.{c['id']}.{key}")
    ds = raw.get("dataset") or {}
    for key in ("targetTrainConversations", "longDialogueMinTurns", "turnMix"):
        visit(ds.get(key), f"dataset.{key}")
    return out


def _cluster_policy(
    pd: _PolicyDefaults,
    cluster: dict[str, Any],
    share_override: bool,
    material_override: bool,
) -> ClusterPolicy:
    cid = cluster["id"]
    target = cluster.get("targetShare")
    src = qp.source(target) or "미정"
    note = str((target or {}).get("note") or "") if isinstance(target, dict) else ""
    if share_override:
        src = f"config:[stages.s9.shares].{cid} (정책값 {qp.value(target)}, source {src})"
    if src == "proposal":
        note = (note + "; " if note else "") + "운영 시작값(proposal)"
    mat_notes = list(pd.material_notes.get(cid, []))
    if material_override:
        mat_notes.append("재료는 config:[stages.s9.materials]가 정책 표기를 덮어썼다")
    lo, hi = cluster.get("minShare"), cluster.get("maxShare")
    return ClusterPolicy(
        shareSource=src,
        shareNote=note,
        protected=bool(cluster.get("protected")),
        minShare=qp.value(lo),
        minShareSource=qp.source(lo) or ("" if lo is not None else "미정"),
        maxShare=qp.value(hi),
        maxShareSource=qp.source(hi) or ("" if hi is not None else "미정"),
        description=str(cluster.get("description") or ""),
        policyMaterials=[str(m) for m in cluster.get("materials") or []],
        materialNotes=mat_notes,
        turnRule=_long_rule(pd.raw, cluster) if cid == "long" else None,
    )


def s9_config(ctx: Context) -> S9Config:
    """설정을 읽고 검사한다. 틀리면 호출·파일 쓰기 전에 `CheckFailed`."""
    raw = ctx.config.stage("s9")
    problems: list[str] = []

    policy_name = raw.get("policy")
    pd: _PolicyDefaults | None = None
    if policy_name is not None and (not isinstance(policy_name, str) or not policy_name.strip()):
        problems.append(f"policy는 정책 이름 문자열이다({', '.join(qp.POLICIES)})")
    elif policy_name:
        pd = _policy_defaults(policy_name.strip(), problems)
        if pd is None:
            raise CheckFailed("s9", problems)

    cluster_ids = pd.cluster_ids if pd else CLUSTERS
    target = _int(
        raw.get("target"), "target", problems, default=pd.target if pd else 640, low=1, high=20000
    )
    shares = dict(pd.shares) if pd else dict(DEFAULT_SHARES)
    share_overrides: set[str] = set()
    for key, value in (raw.get("shares") or {}).items():
        if key not in cluster_ids:
            problems.append(f"shares.{key}: 알 수 없는 클러스터다({', '.join(cluster_ids)})")
            continue
        shares[key] = _float(value, f"shares.{key}", problems, default=shares[key], low=0, high=1)
        share_overrides.add(key)
    total = round(sum(shares.values()), 6)
    if abs(total - 1.0) > 0.001:
        problems.append(f"shares 합이 1이 아니다(현재 {total})")

    materials = dict(pd.materials) if pd else {c: DEFAULT_MATERIALS[c] for c in CLUSTERS}
    material_overrides: set[str] = set()
    for key, value in (raw.get("materials") or {}).items():
        if key not in cluster_ids:
            problems.append(f"materials.{key}: 알 수 없는 클러스터다({', '.join(cluster_ids)})")
            continue
        picked = _str_list(value, f"materials.{key}", problems)
        bad = [m for m in picked if m not in {"SNS_REWRITE", "SYNTH", "NIKL"}]
        if bad:
            problems.append(f"materials.{key}: 알 수 없는 재료 {bad}")
        elif "NIKL" in picked:
            problems.append(
                f"materials.{key}: NIKL은 접근 경로가 정해질 때까지 비활성이다(LLD §8.8)"
            )
        elif picked:
            materials[key] = tuple(picked)
            material_overrides.add(key)

    validation = raw.get("validation") or {}
    checks = raw.get("checks") or {}
    policy_ratio = (
        ((pd.raw.get("dataset") or {}).get("protectedAnchors") or {}).get("minSurvivalRatio")
        if pd is not None
        else None
    )
    protected_ratio = _float(
        raw.get("protected_min_ratio"),
        "protected_min_ratio",
        problems,
        default=float(qp.value(policy_ratio, PROTECTED_MIN_RATIO))
        if policy_ratio is not None
        else PROTECTED_MIN_RATIO,
        low=0,
        high=1,
    )
    extra: dict[str, Any] = {}
    if pd is not None:
        rows = {c["id"]: c for c in qp.clusters(pd.raw)}
        cluster_policies = {
            c: _cluster_policy(pd, rows[c], c in share_overrides, c in material_overrides)
            for c in cluster_ids
        }
        targets, target_notes = _turn_targets(pd.raw)
        if raw.get("protected_min_ratio") is not None:
            ratio_src = "config:[stages.s9].protected_min_ratio"
        elif policy_ratio is not None:
            ratio_src = "dataset.protectedAnchors.minSurvivalRatio: " + (
                qp.source(policy_ratio) or "미정"
            )
        else:
            ratio_src = PROTECTED_MIN_RATIO_SOURCE
        proposals = _proposal_paths(pd.raw)
        if ratio_src == PROTECTED_MIN_RATIO_SOURCE:
            proposals.append("factory.protectedMinRatio")
        elif policy_ratio is not None and qp.source(policy_ratio) == "proposal":
            proposals.append("dataset.protectedAnchors.minSurvivalRatio")
        extra = {
            "policy_name": pd.name,
            "cluster_ids": cluster_ids,
            "labels": pd.labels,
            "cluster_policies": cluster_policies,
            "plan_policy": PlanPolicy(
                name=pd.name,
                schemaVersion=str(pd.raw.get("schemaVersion")),
                status=str(pd.raw.get("status") or ""),
                policySha256=sha256_of(pd.raw),
                targetSource=(
                    "config:[stages.s9].target"
                    if raw.get("target") is not None
                    else "dataset.targetTrainConversations: " + pd.target_source
                ),
                turnUnit=str(
                    ((pd.raw.get("dataset") or {}).get("turnMix") or {}).get("unit") or ""
                ),
                turnTargets=targets,
                protectedMinRatio=protected_ratio,
                protectedMinRatioSource=ratio_src,
                proposalValues=proposals,
                notes=[
                    PROPOSAL_NOTE,
                    "클러스터 비율의 허용 폭(minShare·maxShare)이 미정이면 판정하지 않고 경고로 "
                    "둔다(02-cluster-ratios.md 8절)",
                    "턴 분포 목표를 벗어나도 차단하지 않고 경고로 둔다. 차단은 long 턴 범위와 "
                    "보호 클러스터 생존이다",
                    *target_notes,
                ],
            ),
            "protected_min_ratio": protected_ratio,
        }
    cfg = S9Config(
        target=target,
        shares=shares,
        materials=materials,
        sample_size=_int(
            raw.get("sample_size"), "sample_size", problems, default=12, low=1, high=60
        ),
        concurrency=_int(
            raw.get("concurrency"), "concurrency", problems, default=4, low=1, high=16
        ),
        batch_size=_int(raw.get("batch_size"), "batch_size", problems, default=6, low=1, high=24),
        max_retries=_int(raw.get("max_retries"), "max_retries", problems, default=3, low=0, high=8),
        validation_base=_int(
            validation.get("base"), "validation.base", problems, default=60, low=0, high=2000
        ),
        validation_augmented_share=_float(
            validation.get("augmented_share"),
            "validation.augmented_share",
            problems,
            default=0.10,
            low=0,
            high=1,
        ),
        eval_per_cluster=_int(
            validation.get("eval_per_cluster"),
            "validation.eval_per_cluster",
            problems,
            default=2,
            low=0,
            high=200,
        ),
        max_length_tokens=_int(
            checks.get("max_length_tokens"),
            "checks.max_length_tokens",
            problems,
            default=4096,
            low=256,
            high=32768,
        ),
        chars_per_token=_float(
            checks.get("chars_per_token"),
            "checks.chars_per_token",
            problems,
            default=1.5,
            low=0.5,
            high=4.0,
        ),
        phrase_ngram=_int(
            checks.get("phrase_ngram"), "checks.phrase_ngram", problems, default=6, low=3, high=20
        ),
        phrase_max_conversations=_int(
            checks.get("phrase_max_conversations"),
            "checks.phrase_max_conversations",
            problems,
            default=12,
            low=2,
            high=200,
        ),
        bubble_max_conversations=_int(
            checks.get("bubble_max_conversations"),
            "checks.bubble_max_conversations",
            problems,
            default=6,
            low=1,
            high=200,
        ),
        forbidden_phrases=_str_list(
            checks.get("forbidden_phrases"), "checks.forbidden_phrases", problems
        ),
        source_facts=_str_list(checks.get("source_facts"), "checks.source_facts", problems),
        sns_path=str(raw.get("sns_path") or ""),
        sns_limit=_int(raw.get("sns_limit"), "sns_limit", problems, default=120, low=0, high=5000),
        guide_ref=str(raw.get("guide_ref") or (POLICY_GUIDE_REF if pd else GUIDE_REF)),
        **extra,
    )
    if problems:
        raise CheckFailed("s9", problems)
    return cfg


def cluster_targets(target: int, shares: dict[str, float]) -> dict[str, int]:
    """클러스터 목표 수. 반올림 차이는 `base`에서 맞춘다(LLD §8.8)."""
    others = 0
    out: dict[str, int] = {}
    for cluster in shares:
        if cluster == "base":
            continue
        n = round(target * shares[cluster])
        out[cluster] = n
        others += n
    out["base"] = target - others
    if out["base"] < 0:
        raise CheckFailed(
            "s9",
            [f"base 몫이 음수다(target {target}, 나머지 합 {others}). target이나 shares를 고친다"],
        )
    return out


def plan_cluster_ids(rev_dir: Path) -> tuple[str, ...]:
    """revision의 계획에 적힌 클러스터 순서. 계획이 없으면 기존 5클러스터다."""
    path = rev_dir / "plan.json"
    if not path.exists():
        return CLUSTERS
    return tuple(c.clusterId for c in load_plan(path).clusters)


def load_prompt_pair(ctx: Context, cid: str) -> tuple[PromptPair, Path]:
    state = ctx.state(cid)
    gate = state.gate("G6")
    if gate.status != "APPROVED":
        raise GateNotApprovedError(f"{cid}: G6 승인이 필요하다(현재 {gate.status})")
    rev = gate.rev or state.stage("s8").currentRev
    path = ctx.character_dir(cid) / "s8-prompts" / str(rev) / "prompt-pair.json"
    if not path.exists():
        raise FactoryError(f"{cid}: G6가 가리키는 prompt-pair.json이 없다({path})")
    pair = read_pair(path)
    if isinstance(pair, PromptPairV2) or (path.parent / "persona-bundle.json").exists():
        from character_factory_poc.stages.s8_prompts.formation import verify_bundle

        verify_bundle(ctx, cid, path.parent)
    if not require_short(pair).text.strip():
        raise FactoryError(f"{cid}: 짧은 system이 비어 있다. S8을 다시 돌린다")
    return pair, path  # type: ignore[return-value]


def persona_version(ctx: Context, cid: str, pair: PromptPair) -> str:
    rev = ctx.state(cid).gate("G6").rev or ""
    path = ctx.character_dir(cid) / "s8-prompts" / rev / "persona-version.json"
    if path.exists():
        obj = json.loads(path.read_text("utf-8"))
        return str(obj.get("personaVersion") or rev)
    return str(pair.personaVersion or rev)


def load_trait_sheet(ctx: Context, cid: str) -> tuple[TraitSheet, Path]:
    rev = ctx.state(cid).stage("s7").currentRev
    gate = ctx.state(cid).gate("G6")
    bundle_path = ctx.character_dir(cid) / "s8-prompts" / str(gate.rev) / "persona-bundle.json"
    if gate.status == "APPROVED" and bundle_path.exists():
        from character_factory_poc.stages.s8_prompts.formation import verify_bundle

        _, sheet, path = verify_bundle(ctx, cid, bundle_path.parent)
        return sheet, path
    path = ctx.character_dir(cid) / "s7-traits" / str(rev) / "trait-sheet.json"
    if not rev or not path.exists():
        raise FactoryError(f"{cid}: 특질 시트가 없다. 먼저 cfp persona traits를 실행한다")
    return validate("trait-sheet-v1", json.loads(path.read_text("utf-8"))), path  # type: ignore[return-value]


def build_plan(ctx: Context, cid: str) -> DataPlan:
    cfg = s9_config(ctx)
    pair, pair_path = load_prompt_pair(ctx, cid)
    _sheet, _sheet_path = load_trait_sheet(ctx, cid)
    targets = cluster_targets(cfg.target, cfg.shares)
    text_cfg = (
        ctx.config.task_provider("sft_answers")
        if deck.enabled(ctx)
        else ctx.config.provider("text")
    )
    judge_cfg = (
        ctx.config.task_provider("screening") if deck.enabled(ctx) else ctx.config.provider("judge")
    )
    return DataPlan(
        characterId=cid,
        personaVersion=persona_version(ctx, cid, pair),
        promptPairSha256=sha256_file(pair_path),
        targetTrainConversations=cfg.target,
        clusters=[
            ClusterPlan(
                clusterId=c,
                label=cfg.labels.get(c, c),
                share=cfg.shares[c],
                targetConversations=targets[c],
                materials=list(cfg.materials[c]),
                sampleSize=cfg.sample_size,
                policy=cfg.cluster_policies.get(c),
            )
            for c in cfg.cluster_ids
        ],
        validation=ValidationPlan(
            baseConversations=cfg.validation_base,
            augmentedShare=cfg.validation_augmented_share,
        ),
        guideRef=cfg.guide_ref,
        writerModel=text_cfg.model or text_cfg.adapter,
        judgeModel=judge_cfg.model or judge_cfg.adapter,
        policy=cfg.plan_policy,
    )


def data_dir(ctx: Context, cid: str) -> Path:
    return ctx.character_dir(cid) / "s9-data"


def rev_dirs(ctx: Context, cid: str) -> list[Path]:
    root = data_dir(ctx, cid)
    if not root.exists():
        return []
    out = [
        p for p in root.iterdir() if p.is_dir() and p.name.startswith("ds") and p.name[2:].isdigit()
    ]
    return sorted(out, key=lambda p: int(p.name[2:]))


def latest_rev(ctx: Context, cid: str) -> Path | None:
    dirs = rev_dirs(ctx, cid)
    return dirs[-1] if dirs else None


def open_rev(ctx: Context, cid: str) -> str | None:
    """진행 중인 ds<k>. state가 가리키고 plan.json이 있으면 그 폴더를 쓴다."""
    st = ctx.state(cid).stage("s9s")
    if st.currentRev and (data_dir(ctx, cid) / st.currentRev / "plan.json").exists():
        return st.currentRev
    return None


def new_rev(ctx: Context, cid: str) -> str:
    rev = next_rev(data_dir(ctx, cid), "ds")
    (data_dir(ctx, cid) / rev).mkdir(parents=True, exist_ok=True)
    return rev


def load_plan(path: Path) -> DataPlan:
    return validate("data-plan-v1", json.loads(path.read_text("utf-8")))  # type: ignore[return-value]


def plan_calls() -> list[CallPlan]:
    """계획 고정은 결정적이다. 호출 계획에 0회로 적어 CLI가 같은 형식으로 보여 준다."""
    return [CallPlan("s9s", "data-plan-v1 고정 (결정적, 작성 모델 호출 없음)", 0)]


def run_plan(ctx: Context, cid: str) -> Path:
    """`cfp data plan`: G6 승인 근거로 `data-plan-v1`을 고정한다. 호출은 없다."""
    state = ctx.state(cid)
    state.require_deps("s9s")
    existing = open_rev(ctx, cid)
    if existing and (data_dir(ctx, cid) / existing / "plan.json").exists():
        deck.pin(ctx, data_dir(ctx, cid) / existing)
        return data_dir(ctx, cid) / existing
    plan = build_plan(ctx, cid)
    rev = new_rev(ctx, cid)
    state.transition("s9s", "RUNNING", rev=rev)
    rev_dir = data_dir(ctx, cid) / rev
    write_once_json(rev_dir / "plan.json", dump(plan))
    deck.pin(ctx, rev_dir, create=True)
    write_manifest(rev_dir)
    return rev_dir
