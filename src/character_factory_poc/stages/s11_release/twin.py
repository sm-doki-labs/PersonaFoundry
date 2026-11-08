"""모티브 릴리즈에 공개할 G0·G8 요약. 비교 세트와 비교 보고 본문은 읽지 않는다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_of
from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.common import ArtifactRef
from character_factory_poc.contracts.model_binding import ModelBindingImport
from character_factory_poc.contracts.planning import CharacterPlanV2
from character_factory_poc.contracts.release import TwinRelease
from character_factory_poc.contracts.training import TrainingRun
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import read_model_mode
from character_factory_poc.stages.s0_source.run import STAGE_DIR, load_approved_source
from character_factory_poc.stages.s10_eval.blind import BASE, REVIEWED
from character_factory_poc.stages.s11_release.presentation import CHAT_DISCLOSURE


def _route(root: Path, cid: str, mode: str, adopted: str | None, runs: list[Path]) -> str | None:
    if adopted == "LONG_BASE":
        return None
    if not adopted or mode == "PROMPT_ONLY":
        raise CheckFailed("s11", ["모티브 G8의 채택 기록이 없거나 모델 준비 방식과 다르다"])
    matches = []
    for path in runs:
        run = TrainingRun.model_validate(read_json(path))
        if run.characterId == cid and run.modelBinding and run.modelBinding.ref == adopted:
            matches.append(run)
    if len(matches) != 1 or matches[0].status != "SUCCEEDED" or matches[0].dryRun:
        raise CheckFailed("s11", ["G8 채택 대상과 일치하는 성공한 모델 기록 하나가 필요하다"])
    run = matches[0]
    if mode == "BIND_EXISTING":
        slot = re.fullmatch(r"model-prep/(mb[1-9]\d*)/binding\.json", adopted)
        if not slot or run.provider != "IMPORTED-" + slot[1]:
            raise CheckFailed("s11", ["G8 채택 대상이 가져온 모델의 연결 기록과 다르다"])
        binding = read_json(root / adopted)
        if binding != run.appliedConfig.get("binding"):
            raise CheckFailed("s11", ["가져온 모델의 binding과 학습 기록이 다르다"])
        route = ModelBindingImport.model_validate(binding).servingRoute
    else:
        # 기존 학습 계약은 경로·체크포인트만 갖는다. 서빙 시 이 이름으로 모델을 등록한다.
        route = run.appliedConfig.get("servingRoute", run.requestedConfig.get("servingRoute"))
        if route is None:
            route = "twin-" + sha256_of([cid, adopted, run.modelBinding.checkpointId])[:20]
    if not isinstance(route, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", route):
        raise CheckFailed("s11", ["servingRoute에는 서빙 주소나 키 대신 모델 별칭을 넣는다"])
    return route


@dataclass(frozen=True)
class SourceQuotes:
    pattern: re.Pattern[str]

    def public_prompt(self, text: str) -> str:
        body = "\n".join(
            line
            for line in text.splitlines()
            if not line.startswith(("말투 예시:", "아래는 본인의 실제 발화다"))
            and not self.pattern.search(line)
        )
        # D-0126 (1): 대화 모델이 읽는 판에 AI 표시를 붙인다. 발표 점검이 이 문단을 확인한다.
        return body.rstrip("\n") + "\n\n" + CHAT_DISCLOSURE + "\n"

    def check(self, payload: object, label: str) -> None:
        if isinstance(payload, dict):
            for value in payload.values():
                self.check(value, label)
        elif isinstance(payload, list):
            for value in payload:
                self.check(value, label)
        elif isinstance(payload, str) and self.pattern.search(payload):
            # 오류·장부에도 원문을 남기지 않는다.
            raise CheckFailed("s11", [f"{label}: 승인 원문 인용을 요약으로 바꿔야 한다"])


def release_info(
    ctx: Context, cid: str, plan: CharacterPlanV2, adopted: str | None, runs: list[Path]
) -> tuple[TwinRelease, SourceQuotes]:
    root = ctx.character_dir(cid)
    pack, index, corpus = load_approved_source(ctx, cid)
    variants = read_json(root / "s3-plan" / plan.planRev / "variants.json")
    digest = sha256_file(root / STAGE_DIR / index.sourceRev / "source-pack.json")
    if (
        index.characterId != cid
        or index.sourceRev != "sp" + plan.seedRev.removeprefix("sd")
        or variants["seedSha256"] != digest
    ):
        raise CheckFailed("s11", ["G3 기획이 가리키는 G0 출처 묶음과 다르다"])
    mode = read_model_mode(root)
    gate = ctx.state(cid).gate("G8")
    folder = root / "s10-eval" / gate.rev
    decision_file = folder / "prompt-only.json"
    if mode in {"PROMPT_ONLY", "BIND_EXISTING"} and not decision_file.is_file():
        raise CheckFailed("s11", ["G8 모델 결정 파일이 없다"])
    if decision_file.is_file():
        ref = decision_file.relative_to(root).as_posix()
        shown = read_json(root / gate.recordRef)["shownArtifacts"]
        if {"ref": ref, "sha256": sha256_file(decision_file)} not in shown:
            raise CheckFailed("s11", ["G8에서 확인한 모델 결정 파일이 달라졌다"])
        decision = read_json(decision_file)
        if mode == "BIND_EXISTING" and adopted != "LONG_BASE":
            if not runs or decision.get("binding") != read_json(runs[0]).get(
                "appliedConfig", {}
            ).get("binding"):
                raise CheckFailed("s11", ["G8 승인 뒤 연결 모델의 설정이 바뀌었다"])
        if decision.get("mode", mode) != mode or adopted not in decision["adoptOptions"]:
            raise CheckFailed("s11", ["모델 준비 방식 또는 채택 대상이 G8 결정과 다르다"])
    route = _route(root, cid, mode, adopted, runs)
    config = ctx.config.providers.get(route) if route else None
    record = None
    if route:
        (selected,) = runs
        record = ArtifactRef(
            ref=selected.relative_to(root).as_posix(), sha256=sha256_file(selected)
        )

    report = next((folder / n for n in (REVIEWED, BASE) if (folder / n).is_file()), None)
    info = TwinRelease(
        sourcePackSha256=digest,
        subjectKind=pack.subject.kind,
        usageScope=pack.usageBasis.scope,
        consentRecorded=bool(pack.usageBasis.consentBy and pack.usageBasis.consentDate),
        modelMode=mode,
        chapterTemplate=pack.chapterTemplate,
        startButtonLabel="안부 전화하기"
        if pack.chapterTemplate == "FAMILY_CALL"
        else "통화 시작하기",
        voiceId=pack.voiceId,
        servingRoute=route,
        servingModel=(config.model if config and config.model else route),
        apiKeyEnv=(config.api_key_env if config and config.api_key_env else "TWIN_SERVING_API_KEY")
        if route
        else None,
        trainingRecord=record,
        comparisonReport=report.relative_to(root).as_posix() if report else None,
    )

    # S8은 승인 원문을 양쪽 프롬프트에 의도적으로 넣는다. 내보낼 판에서만
    # 인용 행(선택 기준·말투 예시 포함)을 빼고, 승인본과 비교 세트는 건드리지 않는다.
    quotes = {r["text"].strip() for r in corpus}
    quotes.update(
        e.quote for refs in plan.evidence.values() for e in refs if e.kind == "SOURCE" and e.quote
    )
    quotes.discard("")
    # 짧은 감탄사나 한 글자가 다른 단어의 일부로 쓰인 경우까지 지우지 않는다.
    alternatives = [
        re.escape(q) if len(q) >= 4 else r"(?<!\w)" + re.escape(q) + r"(?!\w)"
        for q in sorted(quotes, key=len, reverse=True)
        if q
    ]
    pattern = re.compile("|".join(alternatives) or r"(?!)")

    return info, SourceQuotes(pattern)
