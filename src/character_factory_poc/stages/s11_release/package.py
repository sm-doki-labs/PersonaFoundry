"""S11 릴리즈 패키지: 승인된 revision의 파일을 pk<k>에 모아 character-package-v1을 쓴다.

LLD §5.17·§8.10, D-0011·D-0044. 모든 참조 파일의 sha256을 다시 재서 원본 기록과 비교하고,
하나라도 다르면 아무것도 쓰지 않고 멈춘다. S9·S10 산출물이 없으면 sft를 비운 채 패키지를 만든다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import character_factory_poc.contracts  # noqa: F401  (계약 등록)
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import CheckFailed, GateNotApprovedError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_bytes,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.common import ArtifactRef
from character_factory_poc.contracts.dataset import DatasetRev
from character_factory_poc.contracts.frames import ApprovedFrames
from character_factory_poc.contracts.hero import AppearanceSpec
from character_factory_poc.contracts.persona import (
    PromptPair,
    PromptPairV2,
    TraitSheet,
    load_prompt_pair,
)
from character_factory_poc.contracts.planning import CharacterPlanV2
from character_factory_poc.contracts.release import (
    AdapterFile,
    Appearance,
    Chapter,
    CharacterPackage,
    CheckpointSelectionRef,
    GateRef,
    PackageFile,
    Persona,
    Profile,
    Sft,
    SftServing,
    TmiItem,
    Video,
)
from character_factory_poc.contracts.scene import CHAPTERS, ScenePlan
from character_factory_poc.contracts.training import TrainingRun
from character_factory_poc.contracts.video import ApprovedActions, VideoAsset
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import SOURCE, read_origin
from character_factory_poc.stages.s2_hero.approve import load_appearance_spec
from character_factory_poc.stages.s3_plan.importer import load_approved_plan_v2
from character_factory_poc.stages.s4_frames.approve import load_approved_frames
from character_factory_poc.stages.s4b_poses.approve import load_scene_and_pose
from character_factory_poc.stages.s5_intro.approve import load_approved_intro
from character_factory_poc.stages.s6_actions.approve import load_approved_actions
from character_factory_poc.stages.s8_prompts.build import load_latest_trait_sheet

# G9로 넘기기 전에 반드시 승인돼 있어야 하는 관문. S9·S10(G7·G8)은 없어도 된다(D-0044).
REQUIRED_GATES = ("G4", "G5", "G5b", "G6")

#: 채택 어댑터 서빙 기록의 패키지 경로와 어댑터 파일(D-0077).
SERVING_REL = "sft/serving.json"
ADAPTER_FILES = ("adapter_model.safetensors", "adapter_config.json")
DEFAULT_CHAT_TEMPLATE = "gemma-4-thinking"


@dataclass(frozen=True)
class SourceFile:
    """패키지로 복사할 원본 하나. sha256은 원본 기록에서 온다."""

    label: str
    src: Path
    rel: str
    sha256: str


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_gate(ctx: Context, cid: str, gate: str) -> None:
    g = ctx.state(cid).gate(gate)
    if g.status != "APPROVED" or not g.rev:
        raise GateNotApprovedError(f"{cid}: {gate} 승인이 필요하다(현재 {g.status})")


def _check_source(item: SourceFile, problems: list[str]) -> None:
    if not item.src.is_file():
        problems.append(f"{item.label}: 원본 파일이 없다({item.src})")
        return
    actual = sha256_file(item.src)
    if actual != item.sha256:
        problems.append(
            f"{item.label}: sha256 불일치(기록 {item.sha256[:12]}… / 실제 {actual[:12]}…)"
        )


def _copy_checked(rev_dir: Path, items: list[SourceFile]) -> None:
    """검사를 통과한 원본만 바이트 그대로 복사하고 복사본 해시를 다시 확인한다."""
    for item in items:
        data = item.src.read_bytes()
        write_once_bytes(rev_dir / item.rel, data)
        if sha256_file(rev_dir / item.rel) != item.sha256:
            raise CheckFailed("s11", [f"{item.label}: 복사본 해시가 원본 기록과 다르다"])


def load_persona(
    ctx: Context, cid: str
) -> tuple[Persona, list[SourceFile], PromptPair, TraitSheet, list[str]]:
    """G6 승인 prompt-pair와 S7 특질 시트. 텍스트 해시도 다시 잰다."""
    problems: list[str] = []
    gate = ctx.state(cid).gate("G6")
    if gate.status != "APPROVED" or not gate.rev:
        raise GateNotApprovedError(f"{cid}: G6 승인이 필요하다(현재 {gate.status})")
    prompt_dir = ctx.character_dir(cid) / "s8-prompts" / gate.rev
    pair_path = prompt_dir / "persona-version.json"
    if not pair_path.exists():
        pair_path = prompt_dir / "prompt-pair.json"
    pair = load_prompt_pair(pair_path)
    if isinstance(pair, PromptPairV2) or (prompt_dir / "persona-bundle.json").exists():
        from character_factory_poc.stages.s8_prompts.formation import verify_approved_pair

        pair, sheet, sheet_path = verify_approved_pair(ctx, cid, prompt_dir)
    else:
        sheet, sheet_path = load_latest_trait_sheet(ctx, cid)

    for name, prompt in (("long", pair.long), ("short", pair.short)):
        if prompt is None:
            continue
        if text_sha256(prompt.text) != prompt.sha256:
            problems.append(f"persona.{name}Prompt: 텍스트 sha256이 기록과 다르다")
    rules_path = Path(pair.systemRulesRef)
    if pair.systemRulesSha256 and rules_path.is_file():
        if sha256_file(rules_path) != pair.systemRulesSha256:
            problems.append("persona.systemRules: 파일 sha256이 기록과 다르다")
    if sha256_file(sheet_path) != pair.traitSheetSha256:
        problems.append("persona.traitSheet: 특질 시트 sha256이 prompt-pair 기록과 다르다")

    sources = [
        SourceFile("trait-sheet", sheet_path, "persona/trait-sheet.json", sha256_file(sheet_path)),
        SourceFile("prompt-pair", pair_path, "persona/prompt-pair.json", sha256_file(pair_path)),
    ]
    persona = Persona(
        personaVersion=pair.personaVersion or gate.rev,
        traitSheet="persona/trait-sheet.json",
        longPrompt="persona/long-prompt.txt",
        shortPrompt="persona/short-prompt.txt" if pair.short is not None else None,
    )
    if isinstance(pair, PromptPairV2):
        for source_name, path in [
            ("persona-bundle", prompt_dir / "persona-bundle.json"),
            ("blueprint", sheet_path.parent / "blueprint.json"),
            ("formation-dialogues", sheet_path.parent / "formation-dialogues.json"),
            ("quality-profile", sheet_path.parent / "profile.json"),
        ]:
            sources.append(
                SourceFile(source_name, path, f"persona/{source_name}.json", sha256_file(path))
            )
    return persona, sources, pair, sheet, problems


def collect_sft(
    ctx: Context, cid: str, *, adopted_only: bool = False
) -> tuple[Sft, list[SourceFile], list[str]]:
    """S9·S10 산출물을 찾아 패키지 sft/로 모은다. 없으면 null로 둔다(D-0044)."""
    char_dir = ctx.character_dir(cid)
    problems: list[str] = []
    sources: list[SourceFile] = []
    sft = Sft()

    dataset_path = _latest(char_dir / "s9-data", "ds", "dataset.json")
    if dataset_path is not None:
        try:
            dataset: DatasetRev = validate("dataset-rev-v2", read_json(dataset_path))  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001 - 계약 위반은 실패 사유로 남긴다
            problems.append(f"sft.dataset: dataset-rev-v2가 아니다({exc})")
        else:
            sft = sft.model_copy(
                update={"datasetRev": dataset.datasetRev, "datasetDigest": dataset.digest}
            )
            sources.append(
                SourceFile("dataset", dataset_path, "sft/dataset.json", sha256_file(dataset_path))
            )

    adopted = _adopted_binding(ctx, cid)
    runs: list[SourceFile] = []
    for run_path in sorted((char_dir / "s10-train").glob("tr*/**/training-run.json")):
        try:
            run: TrainingRun = validate("training-run-v2", read_json(run_path))  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            problems.append(f"sft.trainingRuns: {run_path.parent.name} 형식 오류({exc})")
            continue
        if adopted_only and (not run.modelBinding or run.modelBinding.ref != adopted):
            continue
        rel = f"sft/training-{run.provider}.json"
        if any(item.rel == rel for item in runs):
            problems.append(f"sft.trainingRuns: 같은 provider 기록이 둘이다({run.provider})")
            continue
        runs.append(SourceFile("training-run", run_path, rel, sha256_file(run_path)))
    sources.extend(runs)
    sft = sft.model_copy(update={"trainingRuns": [item.rel for item in runs]})
    if adopted:
        # 학습 없이 긴 프롬프트로 간 경우(K-0038)에도 G8 채택이 남는다. evalReport는 비어 있다.
        sft = sft.model_copy(update={"adoptedBinding": adopted})

    report_path = _latest_eval_report(ctx, cid)
    if report_path is not None:
        try:
            validate("eval-report-v2", read_json(report_path))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"sft.evalReport: eval-report-v2가 아니다({exc})")
        else:
            sources.append(
                SourceFile(
                    "eval-report", report_path, "sft/eval-report.json", sha256_file(report_path)
                )
            )
            sft = sft.model_copy(
                update={
                    "evalReport": "sft/eval-report.json",
                    "adoptedBinding": adopted,
                }
            )
    return sft, sources, problems


def _latest_eval_report(ctx: Context, cid: str) -> Path | None:
    """G8이 승인한 revision의 평가 보고서. 학습 없이 진행했으면 None이다."""
    gate = ctx.state(cid).gate("G8")
    if gate.status == "APPROVED" and gate.rev:
        path = ctx.character_dir(cid) / "s10-eval" / gate.rev / "report.json"
        return path if path.is_file() else None
    return _latest(ctx.character_dir(cid) / "s10-eval", "ev", "report.json")


def _latest(parent: Path, prefix: str, name: str) -> Path | None:
    """parent 아래 <prefix><k>/<name> 가운데 k가 가장 큰 파일."""
    found: list[tuple[int, Path]] = []
    for rev_dir in parent.glob(f"{prefix}*"):
        number = rev_dir.name[len(prefix) :]
        path = rev_dir / name
        if number.isdigit() and path.is_file():
            found.append((int(number), path))
    return max(found, key=lambda item: item[0])[1] if found else None


def _adopted_binding(ctx: Context, cid: str) -> str | None:
    """G8에서 사람이 고른 model_binding. 기록이 없으면 null로 둔다."""
    gate = ctx.state(cid).gate("G8")
    if gate.status != "APPROVED" or not gate.recordRef:
        return None
    path = ctx.character_dir(cid) / gate.recordRef
    if not path.is_file():
        return None
    selections = read_json(path).get("selections") or []
    return selections[0] if selections else None


def _adoption_arm(ctx: Context, cid: str) -> str | None:
    """G8 adoption.json의 armId. 학습 없이 진행했거나 기록이 없으면 None이다."""
    gate = ctx.state(cid).gate("G8")
    if gate.status != "APPROVED" or not gate.rev:
        return None
    path = ctx.character_dir(cid) / "s10-eval" / gate.rev / "adoption.json"
    if not path.is_file():
        return None
    arm = read_json(path).get("armId")
    return arm if isinstance(arm, str) else None


def _recorded_hashes(artifact_dir: Path) -> dict[str, dict]:
    """원격 회수 기록(complete.json·screen-complete.json)의 파일별 sha256·bytes."""
    recorded: dict[str, dict] = {}
    for name in ("complete.json", "screen-complete.json"):
        path = artifact_dir / "remote" / name
        if not path.is_file():
            continue
        try:
            files = read_json(path).get("files") or []
        except (ValueError, AttributeError):
            continue
        for item in files:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                recorded[item["path"]] = item
    return recorded


def collect_serving(
    ctx: Context, cid: str, adopted: str | None
) -> tuple[SftServing | None, list[str]]:
    """G8이 실제 gemma_qlora 어댑터를 채택했으면 sft-serving-v1을 만든다(D-0077).

    LONG_BASE·가짜 공급자 채택이나 아직 성공하지 않은 학습이면 None이다. 어댑터 가중치는
    복사하지 않고, 원격 회수 기록의 해시와 지금 잰 해시가 같을 때만 참조한다.
    """
    if not adopted or adopted == "LONG_BASE" or adopted.startswith("fake://"):
        return None, []
    arm = _adoption_arm(ctx, cid)
    if arm is not None and arm != "SHORT_GEMMA_SFT":
        return None, []
    char_dir = ctx.character_dir(cid)
    problems: list[str] = []
    match: tuple[Path, TrainingRun] | None = None
    for run_path in sorted((char_dir / "s10-train").glob("tr*/**/training-run.json")):
        try:
            run: TrainingRun = validate("training-run-v2", read_json(run_path))  # type: ignore[assignment]
        except Exception:  # noqa: BLE001 - 형식 오류는 collect_sft가 보고한다
            continue
        if run.provider == "gemma_qlora" and run.modelBinding and run.modelBinding.ref == adopted:
            match = (run_path, run)
            break
    if match is None:
        if arm == "SHORT_GEMMA_SFT":
            problems.append("sft.serving: G8이 채택한 binding의 gemma_qlora 학습 기록이 없다")
        return None, problems
    run_path, run = match
    binding = run.modelBinding
    assert binding is not None
    if run.status != "SUCCEEDED" or binding.provider != "gemma_qlora":
        if arm == "SHORT_GEMMA_SFT" and binding.provider == "gemma_qlora":
            problems.append(f"sft.serving: 채택한 gemma_qlora 학습이 성공하지 않았다({run.status})")
        return None, problems

    artifact_dir = (run_path.parent / "artifacts").resolve()
    adapter_dir = Path(binding.ref)
    if not adapter_dir.is_absolute():
        adapter_dir = artifact_dir / adapter_dir
    adapter_dir = adapter_dir.resolve()
    recorded = _recorded_hashes(artifact_dir)
    files: list[AdapterFile] = []
    for name in ADAPTER_FILES:
        path = adapter_dir / name
        if not path.is_file():
            problems.append(f"sft.serving: 어댑터 파일이 없다({path})")
            continue
        actual, size = sha256_file(path), path.stat().st_size
        rel = path.relative_to(artifact_dir).as_posix() if path.is_relative_to(artifact_dir) else ""
        expected = recorded.get(rel)
        if expected is None:
            problems.append(f"sft.serving: {name}의 회수 기록 해시가 없다(remote/complete.json)")
        elif expected.get("sha256") != actual:
            problems.append(
                f"sft.serving: {name} sha256 불일치"
                f"(기록 {str(expected.get('sha256'))[:12]}… / 실제 {actual[:12]}…)"
            )
        elif isinstance(expected.get("bytes"), int) and expected["bytes"] != size:
            problems.append(f"sft.serving: {name} 바이트 수 불일치")
        files.append(AdapterFile(path=name, sha256=actual, bytes=size))

    selection: CheckpointSelectionRef | None = None
    selection_path = run_path.parent / "checkpoint-selection.json"
    if selection_path.is_file():
        try:
            raw = read_json(selection_path)
        except ValueError as exc:
            problems.append(f"sft.serving: checkpoint-selection.json을 읽을 수 없다({exc})")
        else:
            decision = raw.get("decision") if isinstance(raw, dict) else None
            chosen = raw.get("chosen") if isinstance(raw, dict) else None
            chosen_id = chosen.get("checkpointId") if isinstance(chosen, dict) else None
            binding_id = run.modelBinding.checkpointId if run.modelBinding else None
            if isinstance(decision, str) and (
                decision == "KEEP_INCUMBENT" or decision.startswith("BLOCKED")
            ):
                problems.append(
                    f"sft.serving: 체크포인트 선택 결정이 {decision}라 어댑터를 채택할 수 없다"
                )
            if chosen_id and binding_id and chosen_id != binding_id:
                problems.append(
                    f"sft.serving: 선택 기록의 체크포인트 {chosen_id}와 "
                    f"채택 binding {binding_id}가 다르다"
                )
            selection = CheckpointSelectionRef(
                path=selection_path.relative_to(char_dir).as_posix(),
                sha256=sha256_file(selection_path),
                decision=decision if isinstance(decision, str) else None,
            )
    if problems:
        return None, problems

    applied, requested = run.appliedConfig, run.requestedConfig
    serving = SftServing(
        characterId=cid,
        adoptedBinding=adopted,
        provider="gemma_qlora",
        trainingRun=ArtifactRef(
            ref=f"sft/training-{run.provider}.json", sha256=sha256_file(run_path)
        ),
        baseModel=run.baseModel,
        baseModelRevision=str(
            run.baseModelRevision
            or applied.get("revision")
            or requested.get("baseModelRevision")
            or ""
        ),
        chatTemplate=str(
            applied.get("chatTemplate") or requested.get("chatTemplate") or DEFAULT_CHAT_TEMPLATE
        ),
        checkpointId=binding.checkpointId,
        adapterRef=str(adapter_dir),
        adapterFiles=files,
        runtimeVersions=dict(
            applied.get("runtimeVersions") or requested.get("expectedVersions") or {}
        ),
        checkpointSelection=selection,
    )
    return validate("sft-serving-v1", dump(serving)), []  # type: ignore[return-value]


def collect_gates(char_dir: Path) -> tuple[list[GateRef], list[SourceFile]]:
    """모든 관문 기록을 패키지 gates/로 모은다. 옛 G2 기록도 함께 담는다(D-0042)."""
    refs: list[GateRef] = []
    sources: list[SourceFile] = []
    for path in sorted((char_dir / "gates").glob("*.json")):
        record = validate("gate-record-v1", read_json(path))
        rel = f"gates/{path.name}"
        sources.append(SourceFile(f"gate {record.gate}", path, rel, sha256_file(path)))
        refs.append(
            GateRef(gate=record.gate, rev=record.rev, decision=record.decision, recordRef=rel)
        )
    return refs, sources


def _asset(rev_dir: Path, name: str) -> VideoAsset | None:
    path = rev_dir / "assets" / name
    if not path.is_file():
        return None
    return validate("video-asset-v1", read_json(path))


def _video(
    *,
    video_id: str,
    kind: str,
    chapter_no: int | None,
    clip_key: str,
    title: str,
    description: str,
    use_when: str,
    expression: str,
    asset: VideoAsset,
    rel: str,
) -> Video:
    duration = asset.probe.durationS or float(asset.settings.duration)
    return Video(
        videoId=video_id,
        kind=kind,  # type: ignore[arg-type]
        chapterNo=chapter_no,
        clipKey=clip_key,
        title=title,
        description=description,
        useWhen=use_when,
        expression=expression,
        durationS=duration,
        file=rel,
        provider=asset.provider,
        synthetic=asset.provider.startswith("fake"),
    )


def _consistency(
    cid: str,
    plan: CharacterPlanV2,
    appearance: AppearanceSpec,
    scene: ScenePlan,
    frames: ApprovedFrames,
    actions: ApprovedActions,
    frames_dir: Path,
) -> list[str]:
    """여러 단계의 revision이 서로 맞는지 확인한다. 어긋나면 패키지를 만들지 않는다."""
    problems: list[str] = []
    if scene.planRev != plan.planRev:
        problems.append(f"장면 기획 revision이 다르다({scene.planRev} != {plan.planRev})")
    if frames.planRev != plan.planRev or actions.planRev != plan.planRev:
        problems.append("프레임·동작 영상의 기획 revision이 다르다")
    if frames.appearanceRev != appearance.appearanceRev:
        problems.append("프레임 외모 revision이 다르다")
    if actions.appearanceRev != appearance.appearanceRev:
        problems.append("동작 영상의 외모 revision이 다르다")
    if actions.frameRev != frames.frameRev:
        problems.append("동작 영상의 프레임 revision이 다르다")
    for chapter_id in CHAPTERS:
        frame = next(f for f in frames.frames if f.chapterId == chapter_id)
        if not (frames_dir / frame.path).is_file():
            problems.append(f"{chapter_id}: 승인 프레임 파일이 없다")
    if not cid.startswith("cf-"):
        problems.append(f"캐릭터 ID 형식이 아니다: {cid}")
    return problems


def _profile(plan: CharacterPlanV2) -> Profile:
    card = plan.profileCard
    return Profile(
        name=plan.name,
        gender=plan.gender,
        age=str(plan.age),
        job=plan.job,
        tagline=plan.tagline,
        description=plan.background,
        hobby=card.hobby,
        likes=card.likes,
        dislikes=card.dislikes,
        mbti=card.mbti or "",
        tags=list(card.tags),
        tmiItems=[TmiItem(text=item.text, revealStage=item.revealStage) for item in card.tmi],
    )


def _facts(chapter) -> dict:
    """챕터 사실 파일. 패키지 밖 경로(plate·qa 보고서)를 담지 않는다."""
    payload = dump(chapter)
    for key in ("plate", "qa"):
        payload.pop(key, None)
    return payload


def build_package(ctx: Context, cid: str) -> Path:
    """승인된 revision에서 character-package-v1을 만들고 G9 대기로 둔다."""
    for gate in REQUIRED_GATES:
        _require_gate(ctx, cid, gate)

    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    plan, _ = load_approved_plan_v2(ctx, cid)
    appearance, hero_path = load_appearance_spec(ctx, cid)
    scene, _poses, scene_dir = load_scene_and_pose(ctx, cid)
    frames, frames_dir = load_approved_frames(ctx, cid)
    intro, intro_dir = load_approved_intro(ctx, cid)
    actions, actions_dir = load_approved_actions(ctx, cid)
    persona, persona_sources, pair, _sheet, persona_problems = load_persona(ctx, cid)
    is_twin = read_origin(char_dir) == SOURCE
    sft, sft_sources, sft_problems = collect_sft(ctx, cid, adopted_only=is_twin)
    twin = None
    long_text = pair.long.text
    short_text = pair.short.text if pair.short else None
    public_run = None
    quotes = None
    if is_twin:
        from character_factory_poc.stages.s11_release.twin import release_info

        _require_gate(ctx, cid, "G8")
        twin, quotes = release_info(
            ctx,
            cid,
            plan,
            sft.adoptedBinding,
            [item.src for item in sft_sources if item.label == "training-run"],
        )
        long_text = quotes.public_prompt(long_text)
        short_text = quotes.public_prompt(short_text) if short_text else None
        # prompt-pair와 형성 자료에는 승인 원문이 있다. 앱이 쓰는 특질과 대사 지침만 전달한다.
        persona_sources = [item for item in persona_sources if item.label == "trait-sheet"]
        # 가져온 모델의 원본 기록은 자유 입력 출처·접근 정보를 포함한다.
        # 외부 참조와 확정한 서빙 별칭만 내보낸다.
        if twin.modelMode == "TRAIN" and twin.trainingRecord:
            # 학습 설정은 임대 서버 주소·원격 명령·자유 입력을 포함할 수 있다.
            # 재현용 원본은 해시로만 참조하고 패키지에는 학습 식별자만 담는다.
            run = TrainingRun.model_validate(read_json(char_dir / twin.trainingRecord.ref))
            public_run = run.model_copy(
                update={
                    "requestedConfig": {},
                    "appliedConfig": {},
                    "jobId": None,
                    "transfers": [],
                    "checkpoints": [],
                }
            )
        else:
            sft = sft.model_copy(update={"trainingRuns": []})
        # 평가 자유 서술에는 비교 답이 나올 수 있다. 비교 보고 위치만 메타에 남긴다.
        sft = sft.model_copy(update={"evalReport": None})
        sft_sources = [
            item for item in sft_sources if item.label not in {"training-run", "eval-report"}
        ]
    serving, serving_problems = collect_serving(ctx, cid, sft.adoptedBinding)
    if serving is not None:
        sft = sft.model_copy(update={"serving": SERVING_REL})
    gate_refs, gate_sources = collect_gates(char_dir)

    problems = [
        *persona_problems,
        *sft_problems,
        *serving_problems,
        *_consistency(cid, plan, appearance, scene, frames, actions, frames_dir),
    ]
    sources: list[SourceFile] = [
        SourceFile(
            "appearance.hero",
            hero_path,
            "appearance/hero.png",
            appearance.referenceImage.sha256,
        )
    ]

    by_scene = {chapter.chapterId: chapter for chapter in scene.chapters}
    by_frame = {frame.chapterId: frame for frame in frames.frames}
    arc = {chapter.chapterId: chapter for chapter in plan.chapterArc}
    chapters: list[Chapter] = []
    for chapter_no, chapter_id in enumerate(CHAPTERS, start=1):
        scene_chapter, frame = by_scene[chapter_id], by_frame[chapter_id]
        plate = scene_chapter.plate
        sources.append(
            SourceFile(
                f"chapter {chapter_id} frame",
                frames_dir / frame.path,
                f"chapters/{chapter_id}/frame.png",
                frame.sha256,
            )
        )
        sources.append(
            SourceFile(
                f"chapter {chapter_id} background",
                scene_dir / plate.path,
                f"chapters/{chapter_id}/background.png",
                plate.sha256,
            )
        )
        chapters.append(
            Chapter(
                chapterNo=chapter_no,
                chapterId=chapter_id,
                title=arc[chapter_id].title,
                relationshipStage=arc[chapter_id].entryStage,
                intro=scene_chapter.meetingContext,
                goal=arc[chapter_id].arc,
                facts=f"chapters/{chapter_id}/facts.json",
                frame=f"chapters/{chapter_id}/frame.png",
                background=f"chapters/{chapter_id}/background.png",
            )
        )

    videos: list[Video] = []
    intro_asset = _asset(intro_dir, f"{intro.video.id}.json")
    if intro_asset is None:
        problems.append("videos.intro: 자산 기록이 없다")
    else:
        sources.append(
            SourceFile(
                "videos.intro", intro_dir / intro.video.path, "videos/intro.mp4", intro.video.sha256
            )
        )
        videos.append(
            _video(
                video_id=intro.videoId,
                kind="INTRO",
                chapter_no=None,
                clip_key="",
                title="소개 영상",
                description=intro.notes or "S5 소개 영상",
                use_when="",
                expression="",
                asset=intro_asset,
                rel="videos/intro.mp4",
            )
        )
    for clip in actions.clips:
        asset = _asset(actions_dir, f"{clip.actionId}-{clip.video.id}.json")
        if asset is None:
            problems.append(f"videos.{clip.actionId}: 자산 기록이 없다")
            continue
        rel = f"videos/{clip.chapterId}-{clip.clipKey}.mp4"
        sources.append(
            SourceFile(
                f"videos.{clip.actionId}", actions_dir / clip.video.path, rel, clip.video.sha256
            )
        )
        videos.append(
            _video(
                video_id=clip.videoId,
                kind="ACTION",
                chapter_no=clip.stage,
                clip_key=clip.clipKey,
                title=clip.title,
                description=clip.description,
                use_when=clip.useWhen,
                expression=clip.mood,
                asset=asset,
                rel=rel,
            )
        )

    public_gates = {}
    if quotes:
        # 발표용 관문 기록에 검토자가 붙여 넣은 대화·동의자 이름을 옮기지 않는다.
        for item in gate_sources:
            record = read_json(item.src)
            public_gates[item.rel] = {
                **record,
                "reviewer": "비공개",
                "reasons": "",
                "requestedChanges": [],
            }
            quotes.check(public_gates[item.rel], item.label)
        for item in (*persona_sources, *sft_sources):
            quotes.check(read_json(item.src), item.label)
        quotes.check(dump(_profile(plan)), "profile")
        quotes.check([dump(chapter) for chapter in chapters], "chapters")
        quotes.check([dump(video) for video in videos], "videos")
        quotes.check(dump(appearance), "appearance")
        quotes.check(dump(twin), "twin")
        if public_run:
            quotes.check(dump(public_run), "sft.trainingRuns")
        if serving:
            quotes.check(dump(serving), "sft.serving")
    for item in [*sources, *persona_sources, *sft_sources, *gate_sources]:
        _check_source(item, problems)
    rev = next_rev(char_dir / "s11-release", "pk")
    if problems:
        _fail(ctx, cid, rev, problems)

    rev_dir = char_dir / "s11-release" / rev
    state.transition("s11", "RUNNING", rev=rev)
    try:
        for group in (sources, persona_sources, sft_sources, [] if is_twin else gate_sources):
            _copy_checked(rev_dir, group)
        for rel, record in public_gates.items():
            write_once_json(rev_dir / rel, record)
        spec = dump(appearance)
        spec["referenceImage"] = {**spec["referenceImage"], "path": "appearance/hero.png"}
        write_once_json(rev_dir / "appearance/appearance.json", spec)
        from character_factory_poc.stages.s8_prompts.chapter_start import (
            load_latest_chapter_start,
        )

        chapter_start = load_latest_chapter_start(char_dir)
        for chapter_id in CHAPTERS:
            facts = _facts(by_scene[chapter_id])
            if chapter_start:
                # D-0089: 공장이 만든 챕터 시작 설정을 사실 파일에 함께 담아 내보내기가 쓰게 한다.
                facts["chapterStart"] = next(
                    c for c in chapter_start["chapters"] if c["chapterId"] == chapter_id
                )
            if quotes:
                quotes.check(facts, f"chapters/{chapter_id}/facts.json")
            write_once_json(rev_dir / f"chapters/{chapter_id}/facts.json", facts)
        write_once_text(rev_dir / persona.longPrompt, long_text)
        if persona.shortPrompt is not None and short_text is not None:
            write_once_text(rev_dir / persona.shortPrompt, short_text)
        if public_run is not None:
            path = rev_dir / sft.trainingRuns[0]
            write_once_json(path, dump(public_run))
            if serving:
                serving = serving.model_copy(
                    update={
                        "trainingRun": ArtifactRef(
                            ref=sft.trainingRuns[0], sha256=sha256_file(path)
                        )
                    }
                )
        if serving is not None:
            write_once_json(rev_dir / SERVING_REL, dump(serving))
        package = validate(
            "character-package-v1",
            dump(
                CharacterPackage(
                    characterId=cid,
                    packageRev=rev,
                    twin=twin,
                    builtAt=now_iso(),
                    profile=_profile(plan),
                    appearance=Appearance(
                        appearanceRev=appearance.appearanceRev,
                        heroImage="appearance/hero.png",
                        spec="appearance/appearance.json",
                    ),
                    chapters=chapters,
                    videos=videos,
                    persona=persona,
                    sft=sft,
                    gates=gate_refs,
                    files=_package_files(rev_dir),
                )
            ),
        )
        write_once_json(rev_dir / "package.json", dump(package))
        from character_factory_poc.stages.s11_release.page import render_g9_page

        write_once_text(rev_dir / "gate-G9.html", render_g9_page(cid, rev, package))
        write_manifest(rev_dir)
    except Exception as exc:  # noqa: BLE001 - 실패는 단계 상태로 남긴다
        state.transition("s11", "CHECK_FAILED", rev=rev, error=str(exc)[:500])
        raise
    state.transition("s11", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G9", "AWAITING_HUMAN", rev, None)
    return rev_dir


def _fail(ctx: Context, cid: str, rev: str, problems: list[str]) -> None:
    state = ctx.state(cid)
    state.transition("s11", "RUNNING", rev=rev)
    state.transition("s11", "CHECK_FAILED", rev=rev, error="; ".join(problems[:5]))
    raise CheckFailed("s11", problems)


def load_package(ctx: Context, cid: str) -> tuple[CharacterPackage, Path]:
    """G9가 가리키는 패키지와 그 폴더. 변환기는 G9 승인 뒤에만 부른다."""
    gate = ctx.state(cid).gate("G9")
    if not gate.rev:
        raise GateNotApprovedError(f"{cid}: G9 패키지가 없다(cfp release build)")
    rev_dir = ctx.character_dir(cid) / "s11-release" / gate.rev
    path = rev_dir / "package.json"
    if not path.is_file():
        raise GateNotApprovedError(f"{cid}: {gate.rev}/package.json이 없다")
    return validate("character-package-v1", read_json(path)), rev_dir  # type: ignore[return-value]


def verify_package_files(package: CharacterPackage, rev_dir: Path) -> list[str]:
    """패키지 files 목록과 실제 파일을 대조한다. 적재 전에 부른다(LLD §5.17)."""
    problems: list[str] = []
    listed = {item.path for item in package.files}
    for item in package.files:
        path = rev_dir / item.path
        if not path.is_file():
            problems.append(f"파일 없음: {item.path}")
            continue
        if sha256_file(path) != item.sha256:
            problems.append(f"해시 불일치: {item.path}")
        if path.stat().st_size != item.bytes:
            problems.append(f"바이트 수 불일치: {item.path}")
    for path in sorted(rev_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(rev_dir).as_posix()
        if rel not in _NOT_PACKAGE_ASSETS and rel not in listed:
            problems.append(f"files에 없는 파일: {rel}")
    return problems


def _package_files(rev_dir: Path) -> list[PackageFile]:
    files: list[PackageFile] = []
    for path in sorted(rev_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(rev_dir).as_posix()
        if rel in _NOT_PACKAGE_ASSETS:
            continue
        files.append(PackageFile(path=rel, sha256=sha256_file(path), bytes=path.stat().st_size))
    return files


#: 패키지 자산이 아닌 파일. package.json은 자기 해시를 담을 수 없고, 검토 페이지와
#: manifest.sha256은 패키지 밖에서 만드는 산출물이다(LLD §5.17).
_NOT_PACKAGE_ASSETS = frozenset({"package.json", "manifest.sha256", "gate-G9.html"})


__all__ = [
    "REQUIRED_GATES",
    "SourceFile",
    "build_package",
    "collect_gates",
    "collect_serving",
    "collect_sft",
    "load_package",
    "load_persona",
    "now_iso",
    "text_sha256",
    "verify_package_files",
]
