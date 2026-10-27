"""S9 데이터 계획 고정 (LLD §5.14·§8.8, D-0044·D-0045).

G6에서 승인한 `prompt-pair-v1`의 짧은 system과 `trait-sheet-v1`로 `data-plan-v1`을
고정한다. 기본값은 학습 가이드 §6·§7·§13의 소민 기준 배합이다: 학습 640대화,
56:8:22:7:7, 클러스터별 샘플 12개, 검증 기반 60 + 보강 클러스터별 10%, 동시 호출 4.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import CheckFailed, FactoryError, GateNotApprovedError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import next_rev, write_manifest, write_once_json
from character_factory_poc.contracts.dataset import ClusterPlan, DataPlan, ValidationPlan
from character_factory_poc.contracts.persona import PromptPair, TraitSheet
from character_factory_poc.pipeline.context import Context

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


def s9_config(ctx: Context) -> S9Config:
    """설정을 읽고 검사한다. 틀리면 호출·파일 쓰기 전에 `CheckFailed`."""
    raw = ctx.config.stage("s9")
    problems: list[str] = []

    target = _int(raw.get("target"), "target", problems, default=640, low=1, high=20000)
    shares = dict(DEFAULT_SHARES)
    for key, value in (raw.get("shares") or {}).items():
        if key not in CLUSTERS:
            problems.append(f"shares.{key}: 알 수 없는 클러스터다({', '.join(CLUSTERS)})")
            continue
        shares[key] = _float(value, f"shares.{key}", problems, default=shares[key], low=0, high=1)
    total = round(sum(shares.values()), 6)
    if abs(total - 1.0) > 0.001:
        problems.append(f"shares 합이 1이 아니다(현재 {total})")

    materials = {c: DEFAULT_MATERIALS[c] for c in CLUSTERS}
    for key, value in (raw.get("materials") or {}).items():
        if key not in CLUSTERS:
            problems.append(f"materials.{key}: 알 수 없는 클러스터다({', '.join(CLUSTERS)})")
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

    validation = raw.get("validation") or {}
    checks = raw.get("checks") or {}
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
        guide_ref=str(raw.get("guide_ref") or GUIDE_REF),
    )
    if problems:
        raise CheckFailed("s9", problems)
    return cfg


def cluster_targets(target: int, shares: dict[str, float]) -> dict[str, int]:
    """클러스터 목표 수. 반올림 차이는 `base`에서 맞춘다(LLD §8.8)."""
    others = 0
    out: dict[str, int] = {}
    for cluster in CLUSTERS:
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


def load_prompt_pair(ctx: Context, cid: str) -> tuple[PromptPair, Path]:
    state = ctx.state(cid)
    gate = state.gate("G6")
    if gate.status != "APPROVED":
        raise GateNotApprovedError(f"{cid}: G6 승인이 필요하다(현재 {gate.status})")
    rev = gate.rev or state.stage("s8").currentRev
    path = ctx.character_dir(cid) / "s8-prompts" / str(rev) / "prompt-pair.json"
    if not path.exists():
        raise FactoryError(f"{cid}: G6가 가리키는 prompt-pair.json이 없다({path})")
    pair = validate("prompt-pair-v1", json.loads(path.read_text("utf-8")))
    if not pair.short.text.strip():
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
    path = ctx.character_dir(cid) / "s7-traits" / str(rev) / "trait-sheet.json"
    if not rev or not path.exists():
        raise FactoryError(f"{cid}: 특질 시트가 없다. 먼저 cfp persona traits를 실행한다")
    return validate("trait-sheet-v1", json.loads(path.read_text("utf-8"))), path  # type: ignore[return-value]


def build_plan(ctx: Context, cid: str) -> DataPlan:
    cfg = s9_config(ctx)
    pair, pair_path = load_prompt_pair(ctx, cid)
    _sheet, _sheet_path = load_trait_sheet(ctx, cid)
    targets = cluster_targets(cfg.target, cfg.shares)
    text_cfg = ctx.config.provider("text")
    judge_cfg = ctx.config.provider("judge")
    return DataPlan(
        characterId=cid,
        personaVersion=persona_version(ctx, cid, pair),
        promptPairSha256=sha256_file(pair_path),
        targetTrainConversations=cfg.target,
        clusters=[
            ClusterPlan(
                clusterId=c,
                label=LABELS[c],
                share=cfg.shares[c],
                targetConversations=targets[c],
                materials=list(cfg.materials[c]),
                sampleSize=cfg.sample_size,
            )
            for c in CLUSTERS
        ],
        validation=ValidationPlan(
            baseConversations=cfg.validation_base,
            augmentedShare=cfg.validation_augmented_share,
        ),
        guideRef=cfg.guide_ref,
        writerModel=text_cfg.model or text_cfg.adapter,
        judgeModel=judge_cfg.model or judge_cfg.adapter,
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
        return data_dir(ctx, cid) / existing
    plan = build_plan(ctx, cid)
    rev = new_rev(ctx, cid)
    state.transition("s9s", "RUNNING", rev=rev)
    rev_dir = data_dir(ctx, cid) / rev
    write_once_json(rev_dir / "plan.json", dump(plan))
    write_manifest(rev_dir)
    return rev_dir
