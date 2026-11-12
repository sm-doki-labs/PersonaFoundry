"""s9h의 같은 장면을 G6 긴 프롬프트와 서빙 가능한 SFT 조건에서 재생한다."""

from __future__ import annotations

import json
import math
import random
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file, sha256_of
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.errors import BudgetExceeded, FactoryError
from character_factory_poc.common.store import (
    read_json,
    verify_manifest,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.common import ArtifactRef
from character_factory_poc.contracts.training import Arm
from character_factory_poc.contracts.twin_comparison import Condition, Trial, TwinComparison
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import BIND_EXISTING, SOURCE, TRAIN
from character_factory_poc.pipeline.origin import read_model_mode, read_origin
from character_factory_poc.providers.factory import make_text_model
from character_factory_poc.providers.tracked import TrackedTextModel
from character_factory_poc.stages.s0_source.run import read_jsonl
from character_factory_poc.stages.s10_eval import blind
from character_factory_poc.stages.s10_eval.judge import ask_judge
from character_factory_poc.stages.s10_eval.prereg import (
    SFT_PROVIDERS,
    model_family,
    read_prereg,
)
from character_factory_poc.stages.s10_eval.run import (
    GPU_ADAPTER,
    ChatMessage,
    ChatModel,
    GpuEvalPlan,
    TextModelChat,
    _model_for,
    _read_prompt,
    adapter_dir,
    plan_gpu_eval,
    turn_seed,
)


class BoundArm(Arm):
    """외부 모델에는 학습 환경(Gemma/Vertex) 이름을 추측해서 붙이지 않는다."""

    armId: Literal["BOUND_SFT"] = "BOUND_SFT"


@dataclass
class Route:
    arm: Arm
    base: str
    cfg: ProviderConfig | None = None
    injected: ChatModel | None = None
    gpu: GpuEvalPlan | None = None

    @property
    def served(self):
        return self.arm.armId == "LONG_BASE" or any((self.cfg, self.injected, self.gpu))


def _inputs(ctx, cid):
    char = ctx.character_dir(cid)
    state = ctx.state(cid)
    if read_origin(char) != SOURCE:
        raise FactoryError("비교 평가는 모티브에서만 실행한다")
    ho, g0, g6 = state.stage("s9h"), state.gate("G0"), state.gate("G6")
    if any(s.status != "APPROVED" for s in (ho, g0, g6)) or not ho.currentRev or not g6.rev:
        raise FactoryError("비교 평가에는 승인된 G0·s9h·G6이 필요하다")
    folder = char / "s9h-holdout" / ho.currentRev
    if verify_manifest(folder):
        raise FactoryError("s9h 장면의 해시가 다르다")
    summary = read_json(folder / "summary.json")
    path = folder / "scenes.jsonl"
    scenes = read_jsonl(path)
    if (
        summary["sourceRev"] != g0.rev
        or not scenes
        or len(scenes) != summary["sceneCount"]
        or len({s["sceneId"] for s in scenes}) != len(scenes)
    ):
        raise FactoryError("현재 출처와 비교 장면이 일치하지 않는다")
    return char, path, scenes, char / "s8-prompts" / g6.rev


def _routes(ctx, cid, prompts, folder, models, count):
    char = ctx.character_dir(cid)
    mode = read_model_mode(char)
    text = ctx.config.provider("text")

    def prompt_ref(name):
        p = prompts / name
        return ArtifactRef(ref=p.relative_to(char).as_posix(), sha256=sha256_file(p))

    base = Route(
        Arm(armId="LONG_BASE", model=text.model or text.adapter, promptRef=prompt_ref("long.md")),
        text.model or text.adapter,
        text,
    )
    routes = [base]
    if mode == TRAIN:
        prereg, _ = read_prereg(folder)
        training_rev = ctx.state(cid).stage("s10t").currentRev
        for arm in prereg.arms:
            if (char / arm.promptRef.ref).parent != prompts:
                raise FactoryError("사전 등록 프롬프트와 승인된 G6 판이 다르다")
            if arm.armId == "LONG_BASE":
                if arm != base.arm:
                    raise FactoryError("사전 등록한 LONG_BASE와 현재 모델 또는 프롬프트가 다르다")
                continue
            if arm.model.startswith("UNBOUND:"):
                routes.append(Route(arm, ""))
                continue
            from character_factory_poc.stages.s10_train.io import read_run

            run = read_run(
                char
                / "s10-train"
                / (training_rev or "-")
                / SFT_PROVIDERS[arm.armId]
                / "training-run.json"
            )
            if (
                run.characterId != cid
                or run.datasetRev != ctx.state(cid).gate("G7").rev
                or run.status != "SUCCEEDED"
                or run.dryRun
                or not run.modelBinding
                or run.modelBinding.ref != arm.model
            ):
                raise FactoryError("현재 학습 연결·데이터와 사전 등록이 다르다")
            alias = run.appliedConfig.get("servingRoute") or run.requestedConfig.get("servingRoute")
            alias = (
                alias or "twin-" + sha256_of([cid, arm.model, run.modelBinding.checkpointId])[:20]
            )
            routes.append(Route(arm, run.baseModel, ctx.config.providers.get(alias)))
    elif mode == BIND_EXISTING:
        from character_factory_poc.stages.s10_eval.twin import _inputs as decision_inputs

        doc = decision_inputs(ctx, cid)
        binding = doc["binding"]
        arm = BoundArm(model=doc["adoptOptions"][0], promptRef=prompt_ref("short.md"))
        routes.append(
            Route(arm, binding["baseModel"], ctx.config.providers.get(binding["servingRoute"]))
        )
    for r in routes:
        if models and not r.arm.model.startswith("UNBOUND:"):
            r.injected = models.get(r.arm.model) or models.get(r.arm.armId)
        if not r.served and adapter_dir(r.arm) is not None:
            r.gpu = plan_gpu_eval(ctx, count)
    return routes


def _plan(ctx, routes, n):
    # 서빙별 단가가 다르므로 가장 비싼 생성/심사 한 요청의 보수적인 상한을 쓴다.
    cap = ctx.config.stage("s10").get("comparison_call_usd_upper")
    if cap is not None and (type(cap) not in (float, int) or not math.isfinite(cap) or cap <= 0):
        raise FactoryError("comparison_call_usd_upper는 양의 유한한 USD 상한이어야 한다")

    def upper(cfg):
        return 0 if cfg and cfg.adapter == "fake" else (cap * n if cap is not None else None)

    plans = []
    for r in routes:
        if r.served:
            plans.append(
                r.gpu.call_plan()
                if r.gpu
                else CallPlan(
                    "s10",
                    r.arm.armId + " 비교 생성",
                    n,
                    (0 if r.injected.name.startswith("fake") else upper(None))
                    if r.injected
                    else upper(r.cfg),
                )
            )
            plans.append(
                CallPlan(
                    "s10", r.arm.armId + " 블라인드 심사", n, upper(ctx.config.provider("judge"))
                )
            )
    return plans


def plan_calls(
    ctx: Context, cid: str, *, models: Mapping[str, ChatModel] | None = None
) -> list[CallPlan]:
    char, _, scenes, prompts = _inputs(ctx, cid)
    if ctx.config.stage("s10").get("comparison", "run") == "skip":
        return []
    folder = char / "s10-eval" / (ctx.state(cid).stage("s10").currentRev or "-")
    return _plan(ctx, _routes(ctx, cid, prompts, folder, models, len(scenes)), len(scenes))


@contextmanager
def _serve(ctx, cid, folder, r, budget):
    arm = r.arm
    if r.injected:
        yield _model_for(ctx, cid, arm, {arm.armId: r.injected}, budget)
    elif arm.armId == "LONG_BASE":
        yield _model_for(ctx, cid, arm, None, budget)
    elif r.gpu:
        from character_factory_poc.providers.training.gemma_qlora import GemmaSettings
        from character_factory_poc.providers.training.inference import GpuInferenceSession

        p = r.gpu
        with GpuInferenceSession(
            p.cfg,
            folder / "twin-inference",
            {GPU_ADAPTER: adapter_dir(arm)},
            GemmaSettings.from_extra(p.cfg.extra, p.cfg.model),
            run_ref=f"{cid}-{folder.name}-twin",
            estimate_usd=p.usd,
            max_wall_seconds=p.wall_seconds,
        ) as session:
            yield session.chat(GPU_ADAPTER, model=arm.model, max_new_tokens=p.max_new_tokens)
    else:
        cfg = r.cfg
        inner = make_text_model(cfg)
        from character_factory_poc.common.api_routes import billing_for

        tracked = TrackedTextModel(
            inner,
            ctx.ledger(cid),
            budget,
            billing=billing_for(cfg),
            price_overrides=ctx.price_overrides(),
        )
        yield TextModelChat(ctx._limited(tracked, "text"))


def _normal(s):
    return " ".join(s.split())


def _windows(text, width):
    text = _normal(text)
    return {text[i : i + width] for i in range(len(text) - width + 1)}


def _overlap_index(ctx, cid, prompts, width):
    groups = {"TRAIN": set(), "PROMPT": set(), "VOICE": set()}
    for p in (prompts / "long.md", prompts / "short.md"):
        if p.is_file():
            groups["PROMPT"].update(_windows(p.read_text("utf-8"), width))
    source = prompts / "source-plan.json"
    if source.is_file():
        for e in read_json(source).get("sourceVoice", {}).get("examples", []):
            groups["VOICE"].update(_windows(e["quote"], width))
    char = ctx.character_dir(cid)
    if read_model_mode(char) == TRAIN:
        gate = ctx.state(cid).gate("G7")
        if gate.status != "APPROVED" or not gate.rev:
            raise FactoryError("학습 대화 대조에는 승인된 G7이 필요하다")
        for row in read_jsonl(char / "s9-data" / gate.rev / "train.jsonl"):
            for m in row["messages"]:
                if m["role"] != "system":
                    groups["TRAIN"].update(_windows(m["content"], width))
    return groups


def _sides(n):
    rng = random.SystemRandom()
    sides = list("AB" * (n // 2)) + ([rng.choice("AB")] if n % 2 else [])
    rng.shuffle(sides)
    return sides


def _family(model):
    # 같은 모델의 vendor/model, relay/model, bare 별칭을 같은 계열로 본다.
    short = model.lower().split("/")[-1]
    for prefix, family in [
        ("gpt", "openai"),
        ("claude", "anthropic"),
        ("gemini", "google"),
        ("gemma", "google"),
    ]:
        if short.startswith(prefix):
            return family
    return model_family(model.lower())


@contextmanager
def _private_call(ref):
    # 공급자 오류 본문에는 요청/응답 일부가 들어갈 수 있다. 상태·GPU 로그에 전달하지 않는다.
    try:
        yield
    except BudgetExceeded:
        raise
    except Exception as exc:
        raise FactoryError(f"{ref}: 비교 모델 호출 실패 ({type(exc).__name__})") from None


def _run_condition(ctx, cid, folder, r, c, scenes, index, width, judge, budget):
    judge_sides, blind_sides = _sides(len(scenes)), _sides(len(scenes))
    items = []
    prompt = _read_prompt(ctx.character_dir(cid), r.arm)
    with _serve(ctx, cid, folder, r, budget) as model:
        if _family(judge.model) == _family(model.model):
            raise FactoryError("생성 모델과 판정 모델의 계열이 같다(D-0010)")
        c.servingModel = model.model
        for i, (scene, side, blind_side) in enumerate(
            zip(scenes, judge_sides, blind_sides, strict=True)
        ):
            history = [{"role": m["speaker"], "text": m["text"]} for m in scene["context"]]
            messages = [ChatMessage("system", prompt)]
            for m in history:
                messages.append(
                    ChatMessage(
                        "assistant" if m["role"] == "SUBJECT" else "user",
                        ("[다른 참여자] " if m["role"] == "OTHER" else "") + m["text"],
                    )
                )
            user = scene["user"]["text"]
            messages.append(ChatMessage("user", user))
            ref = f"{cid}/{folder.name}/twin/{c.armId}/{i + 1}"
            with _private_call(ref):
                reply = model.reply(messages, seed=turn_seed(101, i + 1), ref=ref).strip()
            if not reply:
                raise FactoryError(f"{ref}: 빈 생성 답")
            actual = scene["actualReply"]["text"]
            a, b = (actual, reply) if side == "A" else (reply, actual)
            with _private_call(ref + "/judge"):
                pick = ask_judge(
                    judge,
                    prompt_name="twin_actual.md",
                    user_text=json.dumps(
                        dict(context=history, user=user, A=a, B=b), ensure_ascii=False
                    ),
                    ref=ref + "/judge",
                    max_output_tokens=64,
                ).get("pick")
            if pick not in ("A", "B"):
                raise FactoryError(f"{ref}: 심사 답에 A/B 선택이 없다")
            grams = _windows(reply, width)
            c.trials.append(
                Trial(
                    sceneId=scene["sceneId"],
                    pairId=uuid4().hex,
                    modelActual=side,
                    modelPick=pick,
                    blindActual=blind_side,
                    exact=_normal(reply) == _normal(actual),
                    overlap=[k for k, v in index.items() if not v.isdisjoint(grams)],
                )
            )
            items.append((scene, reply))
    c.ballot = uuid4().hex
    c.modelScore = blind.score(sum(t.modelPick == t.modelActual for t in c.trials), len(c.trials))
    return blind.render_pages(c, items)


def build_comparison(ctx, cid, folder, *, models=None):
    """호출 전 전체 조건의 계획을 검사한다. 완성한 판은 재호출하지 않는다."""
    char, path, scenes, prompts = _inputs(ctx, cid)
    if (folder / blind.BASE).is_file():
        blind.verify_evidence(folder)
        saved = read_json(folder / blind.BASE)
        if saved["scenesSha256"] != sha256_file(path):
            raise FactoryError("비교 세트가 바뀌었다. 새 G8 판이 필요하다")
        return
    routes = _routes(ctx, cid, prompts, folder, models, len(scenes))
    choice = ctx.config.stage("s10").get("comparison", "run")
    if choice not in ("run", "skip"):
        raise FactoryError('[stages.s10] comparison은 "run" 또는 "skip"이다')
    # skip: 비교 생성·심사를 하지 않고 G8에 평가 생략으로 남긴다(D-0187).
    skip = choice == "skip"
    plans = [] if skip else _plan(ctx, routes, len(scenes))
    width = ctx.config.stage("s10").get("comparison_overlap_chars", 20)
    if type(width) is not int or width < 1:
        raise FactoryError("comparison_overlap_chars는 양의 정수여야 한다")
    budget = ctx.budget()
    budget.check_plan(plans)
    unknown = any(p.est_cost_usd is None for p in plans)
    if ctx.execute and unknown:
        raise FactoryError("유료 비교 전에 [stages.s10] comparison_call_usd_upper를 설정한다")
    for r in routes:
        if not skip and r.gpu and r.gpu.usd > r.gpu.budget_usd:
            raise BudgetExceeded("비교 생성 GPU 비용 상한을 넘는다")
    judge_cfg = ctx.config.provider("judge")
    judge = ctx.judge_model(cid, budget) if ctx.execute and not skip else None
    # 공급자 설정이 전혀 없는 로컬 공장은 채택 화면은 열되 심사 성과를 만들지 않는다.
    unconfigured = bool(
        judge
        and not judge_cfg.model
        and judge.name == "fake"
        and ctx.text_model(cid, budget).model == judge.model
        and not models
    )
    if judge and not unconfigured:
        for r in routes:
            if r.served and _family(judge_cfg.model or judge.model) in {
                _family(m)
                for m in (
                    r.base,
                    r.cfg.model if r.cfg else "",
                    r.injected.model if r.injected else "",
                )
                if m
            }:
                raise FactoryError("생성 모델과 판정 모델의 계열이 같다(D-0010)")
    active = ctx.execute and not unconfigured and not skip
    index = _overlap_index(ctx, cid, prompts, width) if active else {}
    conditions, pages = [], []
    for r in routes:
        status = (
            "NO_SERVING"
            if not r.served
            else "SKIPPED"
            if skip
            else "NO_JUDGE"
            if unconfigured
            else "COMPLETE"
            if active
            else "PLANNED"
        )
        c = Condition(
            armId=r.arm.armId,
            model=r.arm.model,
            servingModel=None,
            promptSha256=r.arm.promptRef.sha256,
            status=status,
            modelScore=blind.score(0, 0),
            humanScore=blind.score(0, 0),
        )
        if status == "COMPLETE":
            blind_page, demo_page = _run_condition(
                ctx, cid, folder, r, c, scenes, index, width, judge, budget
            )
            pages += [
                (f"twin-blind-{c.ballot}.html", blind_page),
                (f"twin-demo-{c.ballot}.html", demo_page),
            ]
        conditions.append(c)
    report = TwinComparison(
        characterId=cid,
        revision=folder.name,
        mode=read_model_mode(char),
        holdoutRev=path.parent.name,
        scenesSha256=sha256_file(path),
        sceneCount=len(scenes),
        overlapChars=width,
        judgeModel=judge.model if judge else judge_cfg.model or judge_cfg.adapter,
        plannedCalls=sum(p.calls for p in plans),
        costUpperUsd=None if unknown else sum(p.est_cost_usd for p in plans),
        conditions=conditions,
    )
    for name, page in pages:
        write_once_text(folder / name, page)
    name = blind.BASE if ctx.execute else blind.PLAN
    write_once_json(folder / name, report.model_dump())


def append_twin_comparison(
    ctx: Context, cid: str, *, models: Mapping[str, ChatModel] | None = None
) -> Path:
    """TRAIN의 judge_and_report 직후 호출. 현재 열린 G8 판의 경로를 반환한다."""
    char = ctx.character_dir(cid)
    gate = ctx.state(cid).gate("G8")
    if (
        read_origin(char) != SOURCE
        or read_model_mode(char) != TRAIN
        or gate.status != "AWAITING_HUMAN"
        or not gate.rev
    ):
        raise FactoryError("모티브 TRAIN 보고가 연 G8이 필요하다")
    folder = char / "s10-eval" / gate.rev
    if not (folder / "report.json").is_file():
        raise FactoryError("기존 s10 보고서를 먼저 만든다")
    build_comparison(ctx, cid, folder, models=models)
    blind.refresh_page(folder)
    return folder
