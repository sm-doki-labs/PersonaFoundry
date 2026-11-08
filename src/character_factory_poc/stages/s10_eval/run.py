"""S10 조건별 응답 수집 `eval-run-v1` (LLD §5.15·§8.9).

응답 모델은 주입하는 `ChatModel` 포트다. 연속 대화는 모델 답을 다음 턴 이력에 그대로 넣고
턴마다 다른 시드를 쓴다. 주입이 없고 SHORT_GEMMA_SFT의 model_binding이 실제 어댑터 폴더면
(D-0077) --execute에서만 GPU 비용을 확인하고 임대 GPU 추론 세션을 열어 그 조건만 수집한다.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_of, sha256_text
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.errors import BudgetExceeded, FactoryError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import write_manifest, write_once_json
from character_factory_poc.contracts.training import (
    Arm,
    ArmId,
    EvalItem,
    EvalPrereg,
    EvalRun,
    EvalSet,
    SetId,
    Turn,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ChatRequest, Message, TextModel
from character_factory_poc.stages.s10_eval.prereg import load_prereg
from character_factory_poc.stages.s10_eval.sets import SET_IDS, check_set_doc, load_set

DEFAULT_MAX_OUTPUT_TOKENS = 400
DEFAULT_TEMPERATURE = 0.75
GPU_ARM: ArmId = "SHORT_GEMMA_SFT"
GPU_ADAPTER = "gemma_sft"
DEFAULT_GPU_SECONDS_PER_TURN = 10.0
DEFAULT_GPU_PREP_SECONDS = 900.0
DEFAULT_GPU_BUDGET_USD = 5.0


@dataclass(frozen=True)
class ChatMessage:
    role: str  # system | user | assistant
    content: str


class ChatModel(Protocol):
    """평가용 대화 포트. 실제 학습 모델 어댑터는 이 포트를 구현해 주입한다."""

    name: str
    model: str

    def reply(self, messages: Sequence[ChatMessage], *, seed: int, ref: str) -> str: ...


class TextModelChat:
    """기존 TextModel을 평가 대화 포트로 감싼다. 시드는 metadata로 넘긴다."""

    def __init__(
        self,
        model: TextModel,
        *,
        stage: str = "s10",
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ):
        self.inner = model
        self.stage = stage
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def model(self) -> str:
        return self.inner.model

    def reply(self, messages: Sequence[ChatMessage], *, seed: int, ref: str) -> str:
        request = ChatRequest(
            kind="EVAL",
            stage=self.stage,
            messages=tuple(Message(m.role, m.content) for m in messages),
            ref=ref,
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
            metadata={"seed": seed},
        )
        return self.inner.complete(request).text.strip()


def turn_seed(base: int, turn_no: int) -> int:
    """턴마다 다른 시드. 같은 대화 안에서 절대 겹치지 않는다."""
    return base * 10_000 + turn_no


def _arm(prereg: EvalPrereg, arm_id: ArmId) -> Arm:
    for arm in prereg.arms:
        if arm.armId == arm_id:
            return arm
    raise FactoryError(f"사전 등록에 {arm_id} 조건이 없다")


def _eval_set(prereg: EvalPrereg, set_id: SetId) -> EvalSet:
    for item in prereg.sets:
        if item.setId == set_id:
            return item
    raise FactoryError(f"사전 등록에 {set_id} 세트가 없다")


def _read_prompt(char_dir: Path, arm: Arm) -> str:
    rel = Path(arm.promptRef.ref)
    if rel.is_absolute() or ".." in rel.parts:
        raise FactoryError(f"프롬프트 경로가 캐릭터 폴더 밖을 가리킨다: {rel}")
    path = char_dir / rel
    if not path.exists():
        raise FactoryError(f"조건 프롬프트가 없다: {rel}")
    text = path.read_text("utf-8")
    if sha256_text(text) != arm.promptRef.sha256:
        raise FactoryError(f"조건 프롬프트가 사전 등록 뒤 바뀌었다: {rel}")
    return text


def _model_for(
    ctx: Context,
    cid: str,
    arm: Arm,
    models: Mapping[str, ChatModel] | None,
    budget,
) -> ChatModel:
    if models and arm.armId in models:
        return models[arm.armId]
    if models and arm.model in models:
        return models[arm.model]
    if models is None and (
        arm.armId == "LONG_BASE" or ctx.config.provider("text").adapter == "fake"
    ):
        # 가짜 텍스트 공급자면 세 조건 모두 같은 가짜 모델로 오프라인 흐름을 끝까지 돈다.
        return TextModelChat(ctx.text_model(cid, budget))
    raise FactoryError(
        f"{arm.armId}의 평가 응답 모델이 없다. model_binding({arm.model}) → 추론 모델 연결은 "
        "통합 담당이 ChatModel 포트로 주입한다(이 단계는 인터페이스만 둔다)"
    )


def _history(item: dict) -> list[ChatMessage]:
    return [ChatMessage(h["role"], h["content"]) for h in item.get("history", [])]


def collect_arm_set(
    *,
    character_id: str,
    rev: str,
    prereg: EvalPrereg,
    prereg_sha: str,
    arm: Arm,
    set_spec: EvalSet,
    set_doc: dict,
    prompt_text: str,
    model: ChatModel,
) -> EvalRun:
    """한 조건·한 세트를 실행한다. 파일을 쓰지 않는다(시험에서 직접 부른다)."""
    check_set_doc(set_doc)
    items: list[EvalItem] = []
    continuous = set_doc["setId"] in {"APOLOGY", "LONG200"}
    for idx, raw in enumerate(set_doc["items"]):
        base = set_spec.seeds[idx % len(set_spec.seeds)] + idx * 1_000
        if continuous:
            messages: list[ChatMessage] = [ChatMessage("system", prompt_text)]
            turns: list[Turn] = []
            for n, script_turn in enumerate(raw["turns"], start=1):
                messages.append(ChatMessage("user", script_turn["user"]))
                seed = turn_seed(base, n)
                reply = model.reply(
                    messages,
                    seed=seed,
                    ref=f"{character_id}/{rev}/{arm.armId}/{set_doc['setId']}/{raw['itemId']}/{n}",
                ).strip()
                if not reply:
                    raise FactoryError(f"{raw['itemId']} {n}턴: 빈 응답")
                messages.append(ChatMessage("assistant", reply))
                turns.append(Turn(user=script_turn["user"], reply=reply, seed=seed))
            items.append(
                EvalItem(itemId=raw["itemId"], personaId=raw.get("personaId", ""), turns=turns)
            )
            continue
        messages = [ChatMessage("system", prompt_text), *_history(raw)]
        messages.append(ChatMessage("user", raw["question"]))
        seed = turn_seed(base, 1)
        reply = model.reply(
            messages,
            seed=seed,
            ref=f"{character_id}/{rev}/{arm.armId}/{set_doc['setId']}/{raw['itemId']}/1",
        ).strip()
        if not reply:
            raise FactoryError(f"{raw['itemId']}: 빈 응답")
        items.append(
            EvalItem(
                itemId=raw["itemId"],
                personaId=raw.get("personaId", ""),
                turns=[Turn(user=raw["question"], reply=reply, seed=seed)],
            )
        )
    return validate(
        "eval-run-v1",
        dump(
            EvalRun(
                characterId=character_id,
                preregSha256=prereg_sha,
                armId=arm.armId,
                setId=set_spec.setId,
                model=arm.model,
                items=items,
            )
        ),
    )  # type: ignore[return-value]


def run_path(rev_dir: Path, arm_id: str, set_id: str) -> Path:
    return rev_dir / "runs" / f"{arm_id}-{set_id}.json"


def count_turns(prereg: EvalPrereg, char_dir: Path, sets: Iterable[SetId]) -> int:
    total = 0
    for sid in sets:
        spec = _eval_set(prereg, sid)
        doc = load_set(char_dir, spec.ref.ref, spec.ref.sha256)
        for item in doc["items"]:
            total += len(item.get("turns") or [1])
    return total


def plan_calls(
    prereg: EvalPrereg,
    char_dir: Path,
    *,
    only_sets: Iterable[SetId] | None = None,
    only_arms: Iterable[ArmId] | None = None,
) -> list[CallPlan]:
    sets = list(only_sets or SET_IDS)
    arms = list(only_arms or [a.armId for a in prereg.arms])
    per_arm = count_turns(prereg, char_dir, sets)
    return [CallPlan("s10", f"평가 응답 {len(arms)}조건 × {len(sets)}세트", per_arm * len(arms))]


def _existing_run(path: Path, prereg_sha: str, arm: Arm, set_id: SetId) -> EvalRun | None:
    if not path.exists():
        return None
    run = validate("eval-run-v1", json.loads(path.read_text("utf-8")))
    if run.preregSha256 != prereg_sha:
        raise FactoryError(
            f"기존 응답 {path.name}의 사전 등록 해시가 다르다. 새 ev revision에서 다시 수집한다"
        )
    if run.armId != arm.armId or run.setId != set_id:
        raise FactoryError(f"기존 응답 {path.name}의 조건·세트가 다르다")
    return run  # type: ignore[return-value]


def adapter_dir(arm: Arm) -> Path | None:
    """SHORT_GEMMA_SFT의 model_binding이 어댑터 두 파일이 있는 실제 폴더면 그 경로."""
    from character_factory_poc.providers.training.inference import is_adapter_dir

    if arm.armId != GPU_ARM:
        return None
    path = Path(arm.model)
    if not path.is_absolute() or not is_adapter_dir(path):
        return None
    return path


def needs_gpu_eval(ctx: Context, cid: str) -> bool:
    """최신 학습 결과가 실제 Gemma 어댑터 폴더면 평가가 GPU를 빌린다(웹 실행 확인, D-0130)."""
    from character_factory_poc.providers.training.inference import is_adapter_dir
    from character_factory_poc.stages.s10_train.io import latest_rev, read_run

    rev_dir = latest_rev(ctx, cid)
    if rev_dir is None:
        return False
    for path in sorted(rev_dir.glob("*/training-run.json")):
        try:
            run = read_run(path)
        except (FactoryError, ValueError, OSError):
            continue
        binding = run.modelBinding
        if binding is None or binding.provider != "gemma_qlora":
            continue
        ref = Path(binding.ref)
        if ref.is_absolute() and is_adapter_dir(ref):
            return True
    return False


def gemma_config(ctx: Context) -> ProviderConfig:
    """학습과 같은 gemma_qlora 설정(D-0077). [stages.s10t] providers의 별칭도 따른다."""
    from character_factory_poc.stages.s10_train.io import _config_for, resolve_providers

    try:
        for item in resolve_providers(ctx, None):
            if item.adapter == "gemma_qlora":
                return item.cfg
    except FactoryError:
        pass
    return _config_for(ctx, "gemma_qlora")


@dataclass(frozen=True)
class GpuEvalPlan:
    turns: int
    seconds: float
    usd: float
    budget_usd: float
    hourly_rate_usd: float
    max_new_tokens: int
    cfg: ProviderConfig

    @property
    def hours(self) -> float:
        return self.seconds / 3600.0

    @property
    def wall_seconds(self) -> float:
        """서버 수명 상한. GPU 예산을 다 쓰는 시간과 학습 설정의 GPU 시간 상한 가운데 짧은 쪽."""
        from character_factory_poc.providers.training.gemma_qlora import GemmaSettings

        cap = GemmaSettings.from_extra(self.cfg.extra, self.cfg.model).max_gpu_hours * 3600.0
        if self.hourly_rate_usd > 0:
            cap = min(cap, self.budget_usd / self.hourly_rate_usd * 3600.0)
        return max(cap, 60.0)

    def call_plan(self) -> CallPlan:
        return CallPlan(
            "s10",
            f"{GPU_ARM} 임대 GPU 응답 {self.turns}턴(약 {self.hours:.2f}시간, "
            f"시간당 ${self.hourly_rate_usd:.2f})",
            self.turns,
            est_cost_usd=self.usd,
        )

    def describe(self) -> str:
        return (
            f"예상 {self.turns}턴, GPU 약 {self.hours:.2f}시간, 약 ${self.usd:.2f}"
            f"(GPU 예산 ${self.budget_usd:.2f})"
        )


def plan_gpu_eval(ctx: Context, turns: int) -> GpuEvalPlan:
    """턴수 × [stages.s10] gpu_seconds_per_turn + 준비 시간으로 GPU 비용을 잡는다."""
    from character_factory_poc.providers.training.gemma_qlora import GemmaSettings

    stage = ctx.config.stage("s10")
    cfg = gemma_config(ctx)
    settings = GemmaSettings.from_extra(cfg.extra, cfg.model)
    per_turn = float(stage.get("gpu_seconds_per_turn", DEFAULT_GPU_SECONDS_PER_TURN))
    prep = float(stage.get("gpu_prep_seconds", DEFAULT_GPU_PREP_SECONDS))
    budget_usd = float(stage.get("gpu_budget_usd", DEFAULT_GPU_BUDGET_USD))
    max_new = int(stage.get("gpu_max_new_tokens", DEFAULT_MAX_OUTPUT_TOKENS))
    if per_turn < 0 or prep < 0 or budget_usd < 0 or max_new < 1:
        raise FactoryError(
            "[stages.s10] gpu_* 설정은 0 이상(gpu_max_new_tokens는 1 이상)이어야 한다"
        )
    seconds = turns * per_turn + prep
    usd = math.ceil(seconds / 3600.0 * settings.hourly_rate_usd * 10_000) / 10_000
    return GpuEvalPlan(
        turns=turns,
        seconds=seconds,
        usd=usd,
        budget_usd=budget_usd,
        hourly_rate_usd=settings.hourly_rate_usd,
        max_new_tokens=max_new,
        cfg=cfg,
    )


def _turns(doc: dict) -> int:
    return sum(len(item.get("turns") or [1]) for item in doc["items"])


def _collect_and_write(
    *,
    cid: str,
    rev: str,
    rev_dir: Path,
    prereg: EvalPrereg,
    digest: str,
    work: list[tuple[Arm, EvalSet, dict]],
    prompts: dict[str, str],
    char_dir: Path,
    model_for,
) -> None:
    for arm, spec, doc in work:
        if arm.armId not in prompts:
            prompts[arm.armId] = _read_prompt(char_dir, arm)
        run = collect_arm_set(
            character_id=cid,
            rev=rev,
            prereg=prereg,
            prereg_sha=digest,
            arm=arm,
            set_spec=spec,
            set_doc=doc,
            prompt_text=prompts[arm.armId],
            model=model_for(arm),
        )
        write_once_json(run_path(rev_dir, arm.armId, spec.setId), dump(run))


def run_eval(
    ctx: Context,
    cid: str,
    models: Mapping[str, ChatModel] | None = None,
    *,
    only_sets: Iterable[SetId] | None = None,
    only_arms: Iterable[ArmId] | None = None,
) -> Path:
    """사전 등록을 확인하고 조건×세트 응답을 모아 `eval-run-v1`을 쓴다."""
    prereg, digest, rev_dir = load_prereg(ctx, cid)
    state = ctx.state(cid)
    state.require_deps("s10")
    char_dir = ctx.character_dir(cid)
    sets = list(only_sets or SET_IDS)
    arms = list(only_arms or [a.armId for a in prereg.arms])
    budget = ctx.budget()
    rev = rev_dir.name
    pending: list[tuple[Arm, EvalSet, dict]] = []
    calls = 0
    for arm_id in arms:
        arm = _arm(prereg, arm_id)
        for sid in sets:
            spec = _eval_set(prereg, sid)
            doc = load_set(char_dir, spec.ref.ref, spec.ref.sha256)
            if _existing_run(run_path(rev_dir, arm_id, sid), digest, arm, sid) is None:
                pending.append((arm, spec, doc))
                calls += _turns(doc)
    gpu_pending = [p for p in pending if adapter_dir(p[0]) is not None] if models is None else []
    other = [p for p in pending if p not in gpu_pending]
    gpu_plan: GpuEvalPlan | None = None
    plans: list[CallPlan] = []
    if gpu_pending:
        gpu_plan = plan_gpu_eval(ctx, sum(_turns(doc) for _, _, doc in gpu_pending))
        if not ctx.execute:
            raise FactoryError(
                f"{GPU_ARM} 평가 응답은 임대 GPU에서 학습 어댑터로 만든다. "
                f"{gpu_plan.describe()}. --execute가 있어야 실행한다"
            )
        if gpu_plan.usd > gpu_plan.budget_usd + 1e-9:
            raise BudgetExceeded(
                f"{GPU_ARM} GPU 평가 예상 ${gpu_plan.usd:.2f}가 [stages.s10] gpu_budget_usd "
                f"${gpu_plan.budget_usd:.2f}를 넘는다({gpu_plan.describe()})"
            )
        plans.append(gpu_plan.call_plan())
    other_calls = calls - (gpu_plan.turns if gpu_plan else 0)
    if other_calls:
        plans.insert(0, CallPlan("s10", f"남은 평가 응답 {other_calls}회", other_calls))
    if plans:
        budget.check_plan(plans)
    prompts: dict[str, str] = {}
    common = dict(
        cid=cid, rev=rev, rev_dir=rev_dir, prereg=prereg, digest=digest, prompts=prompts,
        char_dir=char_dir,
    )  # fmt: skip
    _collect_and_write(
        work=other, model_for=lambda arm: _model_for(ctx, cid, arm, models, budget), **common
    )
    if gpu_pending and gpu_plan is not None:
        _collect_gpu(ctx, cid, gpu_plan, gpu_pending, common)
    write_manifest(rev_dir)
    return rev_dir


def _collect_gpu(
    ctx: Context,
    cid: str,
    plan: GpuEvalPlan,
    work: list[tuple[Arm, EvalSet, dict]],
    common: dict,
) -> None:
    """GPU 세션을 한 번 열어 SHORT_GEMMA_SFT의 남은 세트를 모두 받고 닫는다."""
    from character_factory_poc.providers.training.gemma_qlora import GemmaSettings
    from character_factory_poc.providers.training.inference import GpuInferenceSession

    arm = work[0][0]
    folder = adapter_dir(arm)
    assert folder is not None
    session = GpuInferenceSession(
        plan.cfg,
        common["rev_dir"] / "inference",
        {GPU_ADAPTER: folder},
        GemmaSettings.from_extra(plan.cfg.extra, plan.cfg.model),
        run_ref=f"{cid}-{common['rev']}",
        estimate_usd=plan.usd,
        max_wall_seconds=plan.wall_seconds,
    )
    with session:
        chat = session.chat(GPU_ADAPTER, model=arm.model, max_new_tokens=plan.max_new_tokens)
        _collect_and_write(work=work, model_for=lambda _arm: chat, **common)


def load_runs(prereg: EvalPrereg, rev_dir: Path) -> dict[tuple[ArmId, SetId], EvalRun]:
    """사전 등록의 모든 조건·세트 응답을 읽는다. 빠졌거나 해시가 다르면 거절한다."""
    out: dict[tuple[ArmId, SetId], EvalRun] = {}
    for arm in prereg.arms:
        for spec in prereg.sets:
            path = run_path(rev_dir, arm.armId, spec.setId)
            if not path.exists():
                raise FactoryError(f"평가 응답이 없다: {path.name}. cfp eval run을 먼저 실행한다")
            run = validate("eval-run-v1", json.loads(path.read_text("utf-8")))
            if run.preregSha256 != sha256_of(dump(prereg)):
                raise FactoryError(f"응답 {path.name}의 사전 등록 해시가 다르다")
            out[(arm.armId, spec.setId)] = run  # type: ignore[assignment]
    return out


def load_set_docs(prereg: EvalPrereg, char_dir: Path) -> dict[SetId, dict]:
    return {spec.setId: load_set(char_dir, spec.ref.ref, spec.ref.sha256) for spec in prereg.sets}
