"""S10 조건별 응답 수집 `eval-run-v1` (LLD §5.15·§8.9).

응답 모델은 주입하는 `ChatModel` 포트다. 연속 대화는 모델 답을 다음 턴 이력에 그대로 넣고
턴마다 다른 시드를 쓴다. model_binding → 추론 모델 연결은 호출자(통합 갈래)가 만든다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_of, sha256_text
from character_factory_poc.common.errors import FactoryError
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
                calls += sum(len(item.get("turns") or [1]) for item in doc["items"])
    if calls:
        budget.check_plan([CallPlan("s10", f"남은 평가 응답 {calls}회", calls)])
    prompts: dict[str, str] = {}
    for arm, spec, doc in pending:
        if arm.armId not in prompts:
            prompts[arm.armId] = _read_prompt(char_dir, arm)
        model = _model_for(ctx, cid, arm, models, budget)
        run = collect_arm_set(
            character_id=cid,
            rev=rev,
            prereg=prereg,
            prereg_sha=digest,
            arm=arm,
            set_spec=spec,
            set_doc=doc,
            prompt_text=prompts[arm.armId],
            model=model,
        )
        write_once_json(run_path(rev_dir, arm.armId, spec.setId), dump(run))
    write_manifest(rev_dir)
    return rev_dir


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
