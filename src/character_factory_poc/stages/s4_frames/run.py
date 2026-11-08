"""S4: 기준 얼굴 + 배경 plate + 선택한 자세로 챕터당 한 장을 합성한다."""

from __future__ import annotations

from pathlib import Path

from character_factory_poc.common.aspect import crop_to_ratio, request_size
from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import CheckFailed, FactoryError
from character_factory_poc.common.face_crop import crop_face
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_bytes,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.scene import CHAPTERS
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import is_twin
from character_factory_poc.providers.base import ImageRequest
from character_factory_poc.stages.image_qa import (
    RUBRICS,
    ensure_judge,
    generate_checked,
    qa_settings,
    summarize,
    worst_case_calls,
)
from character_factory_poc.stages.s2_hero.approve import load_appearance_spec
from character_factory_poc.stages.s3_plan.importer import load_approved_plan_v2
from character_factory_poc.stages.s4_frames.approve import load_frames
from character_factory_poc.stages.s4_frames.page import render_g4_page
from character_factory_poc.stages.s4_frames.prompt import (
    NEGATIVE,
    build_composite_prompt,
    composite_context,
)
from character_factory_poc.stages.s4a_backgrounds.run import (
    assert_no_names,
    carry_qa,
    config_for,
    ranking_guard,
)
from character_factory_poc.stages.s4b_poses.approve import load_scene_and_pose

DEFAULTS = {"aspect_ratio": "9:16", "reference_crop": "face", "face_crop_scale": 1.4}


def s4_config(ctx: Context) -> dict:
    cfg = config_for(ctx, "s4", DEFAULTS)
    if cfg["reference_crop"] not in {"face", "full"}:
        raise CheckFailed("s4", ["reference_crop은 face 또는 full이다"])
    try:
        scale = float(cfg["face_crop_scale"])
    except (TypeError, ValueError) as e:
        raise CheckFailed("s4", ["face_crop_scale은 0보다 큰 숫자다"]) from e
    if not 0 < scale < float("inf"):
        raise CheckFailed("s4", ["face_crop_scale은 0보다 큰 유한한 숫자다"])
    cfg["face_crop_scale"] = scale
    return cfg


def _image_plans(ctx: Context, count: int) -> list[CallPlan]:
    images, judges = worst_case_calls(qa_settings(ctx), count)
    description = f"9:16 챕터 합성 {count}장"
    if judges:
        description += f" (자동 검사 포함 최대 {images}장)"
    plans = [CallPlan("s4", description + " (얼굴 + 배경 plate 참조)", images)]
    if judges:
        plans.append(CallPlan("s4", "챕터 합성 비전 자동 검사 (최대)", judges))
    return plans


def plan_calls(ctx: Context) -> list[CallPlan]:
    s4_config(ctx)
    return _image_plans(ctx, 3)


def _partial_source(ctx, cid, appearance_rev, plan_rev, scene_rev):
    state = ctx.state(cid)
    gate = state.gate("G4")
    if not gate.rev or gate.rev != state.stage("s4").currentRev or not gate.recordRef:
        return None, {}
    rec = read_json(ctx.character_dir(cid) / gate.recordRef)
    if rec["decision"] != "REQUEST_CHANGES":
        return None, {}
    previous = ctx.character_dir(cid) / "s4-frames" / gate.rev
    if not (previous / "inputs.json").exists():
        return None, {}
    inputs = read_json(previous / "inputs.json")
    if (inputs.get("sceneRev"), inputs.get("appearanceRev"), inputs.get("planRev")) != (
        scene_rev,
        appearance_rev,
        plan_rev,
    ):
        return None, {}
    changes = rec.get("requestedChanges", [])
    notes = {
        c["field"]: c["note"]
        for c in changes
        if c.get("field") in CHAPTERS and isinstance(c.get("note"), str) and c["note"].strip()
    }
    if not notes:
        return None, {}
    return previous, notes


def _identity_reference(rev_dir, appearance, ref_src, cfg):
    rel = f"reference/{appearance.referenceImage.id}.png"
    ref_bytes = ref_src.read_bytes()
    write_once_bytes(rev_dir / rel, ref_bytes)
    original = {
        "id": appearance.referenceImage.id,
        "path": rel,
        "sha256": sha256_file(rev_dir / rel),
    }
    identity, mode, note = dict(original), "full", ""
    if cfg["reference_crop"] == "face":
        cropped = crop_face(ref_bytes, scale=cfg["face_crop_scale"])
        if cropped is None:
            note = "얼굴을 찾지 못해 전체 기준 이미지를 참조로 썼다"
        else:
            data, box = cropped
            rel = f"reference/{appearance.referenceImage.id}-face.png"
            write_once_bytes(rev_dir / rel, data)
            identity = {
                "id": f"{appearance.referenceImage.id}-face",
                "path": rel,
                "sha256": sha256_file(rev_dir / rel),
            }
            mode = "face"
            note = f"얼굴 상자(left, top, side) = {box[0]}, {box[1]}, {box[2]}"
    return original, identity, mode, note


def run_s4(ctx: Context, cid: str) -> Path:
    state = ctx.state(cid)
    state.require_deps("s4")
    appearance, ref_src = load_appearance_spec(ctx, cid)
    plan, _ = load_approved_plan_v2(ctx, cid)
    scene, poses, scene_dir = load_scene_and_pose(ctx, cid)
    if scene.planRev != plan.planRev or poses.sceneRev != scene.sceneRev:
        raise CheckFailed("s4", ["기획·장면·자세 revision이 서로 다르다. S4a부터 다시 고른다"])
    cfg = s4_config(ctx)
    previous, notes = _partial_source(
        ctx, cid, appearance.appearanceRev, plan.planRev, scene.sceneRev
    )
    regenerate = [ch for ch in CHAPTERS if ch in notes] if previous else list(CHAPTERS)
    budget = ctx.budget()
    budget.check_plan(_image_plans(ctx, len(regenerate)))
    settings = qa_settings(ctx)
    warning = ensure_judge(ctx, settings)
    rev = next_rev(ctx.character_dir(cid) / "s4-frames", "fr")
    rev_dir = ctx.character_dir(cid) / "s4-frames" / rev
    state.transition("s4", "RUNNING", rev=rev)
    try:
        guard = ranking_guard(ctx, cid, appearance.sourceReferenceRev)
        original, identity, mode, crop_note = _identity_reference(rev_dir, appearance, ref_src, cfg)
        inputs = validate(
            "frames-inputs-v2",
            {
                "appearanceRev": appearance.appearanceRev,
                "planRev": plan.planRev,
                "sceneRev": scene.sceneRev,
                "aspectRatio": "9:16",
                "referenceImage": original,
                "identityReference": identity,
                "referenceCrop": mode,
                "cropNote": crop_note,
                "regenerate": regenerate,
                "carriedFrom": previous.name if previous else None,
                "revisionNotes": notes,
            },
        )
        write_once_json(rev_dir / "inputs.json", dump(inputs))
        write_once_json(rev_dir / "scene-plan.json", dump(scene))
        write_once_json(rev_dir / "pose-plan.json", dump(poses))
        by_pose = {p.chapterId: p for p in poses.chapters}
        jobs = []
        for chapter in scene.chapters:
            src = scene_dir / chapter.plate.path
            if sha256_file(src) != chapter.plate.sha256:
                raise CheckFailed("s4", ["배경 plate의 해시가 다르다"])
            rel = f"plates/{chapter.chapterId}.png"
            write_once_bytes(rev_dir / rel, src.read_bytes())
            if chapter.chapterId in regenerate:
                prompt = build_composite_prompt(
                    appearance,
                    chapter,
                    by_pose[chapter.chapterId],
                    plan.job,
                    notes.get(chapter.chapterId, ""),
                    twin=is_twin(ctx.character_dir(cid)),
                )
                assert_no_names(prompt + NEGATIVE, guard)
                jobs.append(
                    (
                        chapter.chapterId,
                        rel,
                        prompt,
                        composite_context(chapter, by_pose[chapter.chapterId]),
                    )
                )
        frames = []
        old = {f.chapterId: f for f in load_frames(previous)} if previous else {}
        for chapter in CHAPTERS:
            if chapter in regenerate:
                continue
            frame = old[chapter]
            src = previous / frame.filePath
            if sha256_file(src) != frame.fileSha256:
                raise CheckFailed("s4", ["이월할 프레임의 해시가 다르다"])
            write_once_bytes(rev_dir / frame.filePath, src.read_bytes())
            carry_qa(previous, rev_dir, frame.qa)
            frames.append(
                frame.model_copy(
                    update={
                        "settings": frame.settings | {"carriedFrom": previous.name},
                    }
                )
            )
        model = ctx.image_model(cid, budget)
        vision = ctx.vision_model(cid, budget) if settings.enabled else None
        for chapter, plate_rel, prompt, context in jobs:
            request = ImageRequest(
                stage="s4",
                prompt=prompt,
                ref=f"{cid}/{rev}/{chapter}-f1",
                negative_prompt=NEGATIVE,
                size=request_size((9, 16)),
                reference_images=(str(rev_dir / identity["path"]), str(rev_dir / plate_rel)),
            )
            qa = None
            if settings.enabled:
                rubric = RUBRICS["composite-v1"]
                outcome = generate_checked(
                    image_model=model,
                    vision=vision,
                    request=request,
                    ratio=(9, 16),
                    rubric=rubric,
                    context=context,
                    judge_refs=[
                        (f"identity reference ({mode})", str(rev_dir / identity["path"])),
                        ("background plate", str(rev_dir / plate_rel)),
                    ],
                    out_dir=rev_dir,
                    image_id=f"{chapter}-f1",
                    settings=settings,
                    warning=warning,
                )
                report = outcome.report
                report_rel = f"qa/{chapter}-f1.json"
                write_once_json(rev_dir / report_rel, dump(report))
                qa = summarize(report, rubric, report_rel)
                data, provider, model_name = (
                    outcome.data,
                    report.generatorProvider,
                    report.generatorModel,
                )
            else:
                result = model.generate(request)
                try:
                    data, _, _ = crop_to_ratio(result.data, (9, 16))
                except ValueError as e:
                    raise CheckFailed("s4", [str(e)]) from e
                provider, model_name = result.provider, result.model
            rel = f"{chapter}/f1.png"
            write_once_bytes(rev_dir / rel, data)
            frames.append(
                validate(
                    "chapter-frame-v1",
                    {
                        "frameId": f"{chapter}-f1",
                        "chapterId": chapter,
                        "appearanceRev": appearance.appearanceRev,
                        "planRev": plan.planRev,
                        "prompt": prompt,
                        "negativePrompt": NEGATIVE,
                        "model": model_name,
                        "provider": provider,
                        "qa": dump(qa) if qa else None,
                        "settings": {
                            "size": request_size((9, 16)),
                            "aspectRatio": "9:16",
                            "sceneRev": scene.sceneRev,
                        },
                        "fileSha256": sha256_file(rev_dir / rel),
                        "filePath": rel,
                    },
                )
            )
        frames.sort(key=lambda frame: frame.chapterId)
        frames_json = [dump(frame) for frame in frames]
        assert_no_names(frames_json, guard)
        write_once_json(rev_dir / "frames.json", frames_json)
        write_once_text(
            rev_dir / "gate-G4.html",
            render_g4_page(
                subject_id=cid,
                rev=rev,
                inputs=inputs,
                frames=frames,
                name=plan.name,
            ),
        )
        write_manifest(rev_dir)
    except FactoryError as e:
        ctx.state(cid).transition("s4", "CHECK_FAILED", rev=rev, error=str(e))
        raise
    state = ctx.state(cid)
    state.transition("s4", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G4", "AWAITING_HUMAN", rev, None)
    return rev_dir
