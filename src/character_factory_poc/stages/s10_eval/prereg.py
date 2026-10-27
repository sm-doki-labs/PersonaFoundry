"""S10 사전 등록 `eval-prereg-v2` (LLD §5.15·§8.9, D-0006·D-0045).

세트·조건·판정 방식·기준을 학습·평가 전에 고정하고 sha256을 낸다. 학습 결과의 model_binding은
읽기만 하고, 추론 모델 연결은 호출자가 주입한다(인터페이스만 둔다).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from character_factory_poc.common.canonical import sha256_of, sha256_text
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import (
    next_rev,
    write_manifest,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.common import ArtifactRef
from character_factory_poc.contracts.planning import CharacterPlanV2
from character_factory_poc.contracts.training import Arm, Criterion, EvalPrereg, EvalSet, JudgeSpec
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import now_iso
from character_factory_poc.stages.s3_plan.importer import load_approved_plan
from character_factory_poc.stages.s10_eval.sets import SET_IDS, RenderedSet, render_sets, write_sets

ARM_IDS = ("LONG_BASE", "SHORT_GEMMA_SFT", "SHORT_GEMINI_SFT")
SFT_ARMS = ("SHORT_GEMMA_SFT", "SHORT_GEMINI_SFT")
SFT_PROVIDERS = {"SHORT_GEMMA_SFT": "gemma_qlora", "SHORT_GEMINI_SFT": "vertex_gemini"}
HUMAN_PAIRS = 20
HUMAN_SAMPLE_SEED = 20261027
DEFAULT_SEEDS: dict[str, list[int]] = {
    "OE": [101],
    "SE": [211],
    "APOLOGY": [307],
    "LONG200": [401, 409, 419, 431],
}


class PreregMismatchError(FactoryError):
    """사전 등록 파일과 해시가 다르다. 분석을 거절한다(D-0006)."""


@dataclass(frozen=True)
class PreregBuild:
    revision: str
    rev_dir: Path
    prereg: EvalPrereg
    sha256: str


def default_criteria() -> list[Criterion]:
    """G8 기본 기준(D-0045 (3)). 수치는 설정이 아니라 사전 등록에 고정한다."""
    return [
        Criterion(
            id="repeat_rate_101_200",
            metric="repeat_rate_101_200",
            comparator="<=",
            threshold=0.05,
            appliesTo="SFT_ANY",
        ),
        Criterion(
            id="memory_recall_200",
            metric="memory_recall_200",
            comparator=">=",
            threshold=0.9,
            appliesTo="SFT_ANY",
        ),
        Criterion(
            id="apology_recovery",
            metric="apology_recovery",
            comparator=">=",
            threshold=0.667,
            appliesTo="SFT_ANY",
        ),
    ]


def model_family(model: str) -> str:
    """ProviderConfig.family와 같은 규칙. 'vendor/model'이면 vendor, 아니면 첫 토큰."""
    if "/" in model:
        return model.split("/", 1)[0]
    return model.split("-", 1)[0] if model else ""


def _prompt_pair(ctx: Context, cid: str) -> tuple[dict[str, Any], str, Path, Path]:
    state = ctx.state(cid)
    st = state.stage("s8")
    if not st.currentRev or st.status not in {"AWAITING_HUMAN", "APPROVED"}:
        raise FactoryError(f"{cid}: G6 프롬프트 쌍이 없다(S8 상태 {st.status})")
    rev_dir = ctx.character_dir(cid) / "s8-prompts" / st.currentRev
    pair = json.loads((rev_dir / "prompt-pair.json").read_text("utf-8"))
    validate("prompt-pair-v1", pair)
    long_path, short_path = rev_dir / "long.md", rev_dir / "short.md"
    if not long_path.exists() or not short_path.exists():
        raise FactoryError(f"{cid}: S8 프롬프트 파일(long.md·short.md)이 없다")
    return pair, st.currentRev, long_path, short_path


def discover_bindings(ctx: Context, cid: str) -> dict[str, dict[str, str]]:
    """S10 학습(D1)이 남긴 training-run-v2에서 성공한 modelBinding을 읽는다.

    파일 레이아웃은 LLD §5.15를 따른다: s10-train/tr<k>/<provider>/training-run.json.
    쓰기는 하지 않는다(학습 공급자는 D1 소관).
    """
    root = ctx.character_dir(cid) / "s10-train"
    found: dict[str, dict[str, str]] = {}
    if not root.exists():
        return found
    for path in sorted(root.glob("tr*/*/training-run.json")):
        try:
            run = json.loads(path.read_text("utf-8"))
            validate("training-run-v2", run)
        except Exception:
            continue
        provider = run.get("provider")
        arm = next((a for a, p in SFT_PROVIDERS.items() if p == provider), None)
        if arm is None or run.get("status") != "SUCCEEDED" or not run.get("modelBinding"):
            continue
        binding = run["modelBinding"]
        found[arm] = {
            "ref": binding["ref"],
            "baseModel": run.get("baseModel", ""),
            "checkpointId": binding.get("checkpointId", ""),
        }
    return found


def _judge_spec(ctx: Context, bindings: dict[str, dict[str, str]]) -> JudgeSpec:
    judge = ctx.config.provider("judge")
    text = ctx.config.provider("text")
    family = judge.family()
    if not family:
        raise FactoryError("판정 모델 계열을 알 수 없다. [providers.judge] model을 설정한다")
    generation = [(text.model or text.adapter, text.family())]
    for arm, info in bindings.items():
        base = info.get("baseModel", "")
        generation.append((base or SFT_PROVIDERS[arm], model_family(base)))
    same = [m for m, fam in generation if fam and fam == family]
    if same:
        raise FactoryError(
            "판정 모델과 생성 모델의 계열이 같다(D-0010). 평가를 시작할 수 없다: "
            f"judge={judge.model} family={family}, generation={same}"
        )
    return JudgeSpec(model=judge.model or judge.adapter, family=family, orderSwap=True)


def _arms(
    ctx: Context,
    cid: str,
    long_path: Path,
    short_path: Path,
    bindings: dict[str, dict[str, str]],
) -> list[Arm]:
    char_dir = ctx.character_dir(cid)
    text_model = ctx.config.provider("text").model or ctx.config.provider("text").adapter
    arms = [
        Arm(
            armId="LONG_BASE",
            promptRef=ArtifactRef(
                ref=long_path.relative_to(char_dir).as_posix(),
                sha256=sha256_text(long_path.read_text("utf-8")),
            ),
            model=text_model,
        )
    ]
    for arm in SFT_ARMS:
        info = bindings.get(arm)
        ref = info["ref"] if info else f"UNBOUND:{SFT_PROVIDERS[arm]}"
        arms.append(
            Arm(
                armId=arm,  # type: ignore[arg-type]
                promptRef=ArtifactRef(
                    ref=short_path.relative_to(char_dir).as_posix(),
                    sha256=sha256_text(short_path.read_text("utf-8")),
                ),
                model=ref,
            )
        )
    return arms


def build_prereg(
    ctx: Context,
    cid: str,
    *,
    seeds: dict[str, list[int]] | None = None,
    criteria: list[Criterion] | None = None,
    human_pairs: int = HUMAN_PAIRS,
    relationship: str | None = None,
) -> PreregBuild:
    """세트를 렌더링·고정하고 eval-prereg-v2를 쓴다. 새 ev<k> revision을 만든다."""
    state = ctx.state(cid)
    state.require_deps("s10")
    plan, _ = load_approved_plan(ctx, cid)
    if not isinstance(plan, CharacterPlanV2):
        raise FactoryError("S10 평가는 character-plan-v2 기획서가 필요하다")
    pair, pair_rev, long_path, short_path = _prompt_pair(ctx, cid)
    bindings = discover_bindings(ctx, cid)
    judge = _judge_spec(ctx, bindings)
    rendered: dict[str, RenderedSet] = render_sets(plan, cid, relationship=relationship)

    char_dir = ctx.character_dir(cid)
    rev = next_rev(char_dir / "s10-eval", "ev")
    rev_dir = char_dir / "s10-eval" / rev
    state.transition("s10", "RUNNING", rev=rev)
    refs = write_sets(char_dir, rev, rendered)

    seed_map = dict(DEFAULT_SEEDS)
    seed_map.update(seeds or {})
    sets = [
        EvalSet(
            setId=sid,
            ref=ArtifactRef(ref=refs[sid]["ref"], sha256=refs[sid]["sha256"]),
            seeds=seed_map[sid],
            perTurnSeed=True,
            personas=4 if sid == "LONG200" else 1,
        )
        for sid in SET_IDS
    ]
    persona_version = pair.get("personaVersion") or f"s8-{pair_rev}"
    prereg = validate(
        "eval-prereg-v2",
        dump(
            EvalPrereg(
                characterId=cid,
                personaVersion=persona_version,
                arms=_arms(ctx, cid, long_path, short_path, bindings),
                sets=sets,
                judge=judge,
                humanPairs=human_pairs,
                criteria=criteria or default_criteria(),
                frozenAt=now_iso(),
            )
        ),
    )
    digest = sha256_of(dump(prereg))
    write_once_json(rev_dir / "prereg.json", dump(prereg))
    write_once_text(rev_dir / "prereg.sha256", digest + "\n")
    write_manifest(rev_dir)
    return PreregBuild(revision=rev, rev_dir=rev_dir, prereg=prereg, sha256=digest)  # type: ignore[arg-type]


def current_rev(ctx: Context, cid: str) -> str:
    st = ctx.state(cid).stage("s10")
    if st.currentRev:
        return st.currentRev
    root = ctx.character_dir(cid) / "s10-eval"
    if root.exists():
        revs = sorted(
            [p.name for p in root.iterdir() if p.is_dir() and p.name.startswith("ev")],
            key=lambda n: int(n[2:]) if n[2:].isdigit() else -1,
        )
        if revs:
            return revs[-1]
    raise FactoryError(f"{cid}: S10 사전 등록이 없다. cfp eval prereg를 먼저 실행한다")


def read_prereg(rev_dir: Path) -> tuple[EvalPrereg, str]:
    """prereg.json과 prereg.sha256을 대조한다. 다르면 분석을 거절한다(D-0006)."""
    path = rev_dir / "prereg.json"
    hash_path = rev_dir / "prereg.sha256"
    if not path.exists() or not hash_path.exists():
        raise FactoryError(f"사전 등록 파일이 없다: {rev_dir}")
    obj = json.loads(path.read_text("utf-8"))
    prereg = validate("eval-prereg-v2", obj)
    expected = hash_path.read_text("utf-8").strip()
    actual = sha256_of(dump(prereg))
    if actual != expected:
        raise PreregMismatchError(
            "사전 등록 해시가 다르다. 평가 세트·조건·기준을 바꿨다면 "
            "새 ev revision으로 다시 등록한다"
            f"\n  기록 {expected}\n  실제 {actual}"
        )
    return prereg, actual  # type: ignore[return-value]


def load_prereg(ctx: Context, cid: str) -> tuple[EvalPrereg, str, Path]:
    rev = current_rev(ctx, cid)
    rev_dir = ctx.character_dir(cid) / "s10-eval" / rev
    prereg, digest = read_prereg(rev_dir)
    return prereg, digest, rev_dir
