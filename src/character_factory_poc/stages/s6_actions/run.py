"""S6 동작 영상 실행과 부분 재생성·작업 재개를 맡는다(D-0038, D-0040, D-0041)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from character_factory_poc.common.aspect import crop_to_ratio, parse_ratio, request_size
from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import (
    CheckFailed,
    ImageGenerationError,
    VideoGenerationError,
)
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_bytes,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.video import ActionClip, ActionInputs
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import is_twin
from character_factory_poc.providers.base import ImageRequest, VideoRequest
from character_factory_poc.providers.xai_video import estimate_cost
from character_factory_poc.stages.s4_frames.approve import load_approved_frames
from character_factory_poc.stages.s5_intro.probe import probe_video
from character_factory_poc.stages.s5_intro.run import NOTES, _write_json
from character_factory_poc.stages.s6_actions.catalog import (
    ALL_CHAPTERS,
    CATALOG,
    NEUTRAL_NEGATIVE,
    PRESETS,
    build_prompt,
    neutral_prompt,
    stage_note,
    video_tiers,
)
from character_factory_poc.stages.s6_actions.light import LIGHT_INPUTS, read_inputs
from character_factory_poc.stages.s6_actions.page import render_g5b_page

DEFAULTS: dict[str, Any] = {
    "preset": "l2",
    "actions": [],
    "candidates": 1,
    "resolution": "720p",
    "aspect_ratio": "9:16",
    "generate_audio": False,
    "durations": {"idle": 15, "emotion": 10, "special": 6},
}


def _resolve_config(settings: dict[str, Any]) -> dict[str, Any]:
    cfg = DEFAULTS | settings
    problems = []
    preset, actions = cfg["preset"], cfg["actions"]
    if "video_tier" in cfg:
        tier = cfg["video_tier"]
        tiers = video_tiers(bool(cfg.get("motif")))
        if not isinstance(tier, str) or tier not in tiers:
            raise CheckFailed("s6", ["video_tier는 light·standard·pro·max 중 하나다"])
        cfg["chapters"] = tiers[tier].chapters
        cfg["actions"] = list(tiers[tier].actions)
        cfg["preset"] = f"tier:{tier}"
    else:
        if preset == "standard":
            preset = "full37"
        if not isinstance(preset, str) or preset not in (*PRESETS, "custom"):
            problems.append("preset은 l2·full37(옛 이름 standard)·custom 중 하나다")
        if (
            not isinstance(actions, list)
            or any(not isinstance(key, str) or key not in CATALOG for key in actions)
            or (
                isinstance(actions, list)
                and len(actions) != len(set(key for key in actions if isinstance(key, str)))
            )
        ):
            problems.append("actions는 중복 없는 카탈로그 키 목록이어야 한다")
        if preset == "custom" and not actions:
            problems.append("custom에는 actions가 필요하다")
        if not problems:
            cfg["chapters"] = ALL_CHAPTERS
            cfg["actions"] = list(actions or PRESETS[preset])
            cfg["preset"] = "custom" if actions else preset
    durations = cfg["durations"]
    if not isinstance(durations, dict):
        problems.append("durations는 idle·emotion·special 길이를 담은 객체다")
    else:
        durations = DEFAULTS["durations"] | durations
        for role, value in durations.items():
            if role not in DEFAULTS["durations"] or type(value) is not int or not 1 <= value <= 15:
                problems.append(f"durations.{role}는 1~15의 정수다")
    if type(cfg["candidates"]) is not int or not 1 <= cfg["candidates"] <= 4:
        problems.append("candidates는 1~4의 정수다")
    if cfg["resolution"] not in ("480p", "720p", "1080p"):
        problems.append("resolution은 480p·720p·1080p 중 하나다")
    try:
        if not isinstance(cfg["aspect_ratio"], str):
            raise ValueError("aspect_ratio는 '9:16' 형식의 문자열이다")
        parse_ratio(cfg["aspect_ratio"])
    except ValueError as e:
        problems.append(str(e))
    if type(cfg["generate_audio"]) is not bool:
        problems.append("generate_audio는 boolean이다")
    if problems:
        raise CheckFailed("s6", problems)
    cfg["durations"] = durations
    return cfg


def s6_config(ctx: Context, cid: str | None = None) -> dict[str, Any]:
    from character_factory_poc.pipeline.origin import read_video_tier

    settings = dict(ctx.config.stage("s6"))
    tier = read_video_tier(ctx.character_dir(cid)) if cid else None
    if tier == "none":
        raise CheckFailed("s6", ["영상 없이 만들기로 정했어요."])
    if tier:
        settings["video_tier"] = tier
        settings["motif"] = is_twin(ctx.character_dir(cid))
    return _resolve_config(settings)


def _duration(cfg: dict, key: str) -> int:
    return cfg["durations"][CATALOG[key]["pickRole"] or "idle"]


def estimate(ctx: Context, cfg: dict[str, Any], calls: int = 1) -> float:
    pcfg = ctx.config.provider("video")
    if pcfg.adapter not in {"xai_video", "grok_oauth"}:
        return 0.0
    each = estimate_cost(
        pcfg.model or "grok-imagine-video-1.5-lite",
        cfg["resolution"],
        cfg["duration"],
        pcfg.extra.get("price_per_second"),
    )
    if each is None:
        raise CheckFailed(
            "s6", [f"{pcfg.model} {cfg['resolution']}의 단가가 없다. price_per_second를 설정한다"]
        )
    return round(each * calls, 4)


def _partial(ctx: Context, cid: str, cfg: dict) -> tuple[str | None, dict[str, str]]:
    """G4와 설정이 그대로인 수정 요청만 동작 단위 재생성으로 좁힌다. 파일을 쓰지 않는다."""
    gate = ctx.state(cid).gate("G5b")
    frame_gate = ctx.state(cid).gate("G4")
    if gate.status != "REJECTED" or not gate.rev or frame_gate.status != "APPROVED":
        return None, {}
    char_dir = ctx.character_dir(cid)
    record_path = char_dir / "gates" / f"G5b-{gate.rev}.json"
    inputs_path = char_dir / "s6-actions" / gate.rev / "inputs.json"
    if not record_path.exists() or not inputs_path.exists():
        return None, {}
    record = read_json(record_path)
    if record.get("decision") != "REQUEST_CHANGES":
        return None, {}
    previous: ActionInputs = read_inputs(inputs_path)
    settings = {
        "resolution": previous.resolution,
        "aspect_ratio": previous.aspectRatio,
        "generate_audio": previous.generateAudio,
        "candidates": previous.candidates,
    }
    if previous.frameRev != frame_gate.rev or any(cfg[k] != v for k, v in settings.items()):
        return None, {}
    if tuple(ch.chapterId for ch in previous.chapters) != cfg["chapters"]:
        return None, {}
    for chapter in previous.chapters:
        if [a.actionKey for a in chapter.actions] != cfg["actions"] or any(
            a.duration != _duration(cfg, a.actionKey) for a in chapter.actions
        ):
            return None, {}
    changes = {c["field"]: c["note"] for c in record["requestedChanges"]}
    return (gate.rev, changes) if changes else (None, {})


def plan_calls(ctx: Context, cfg: dict[str, Any], cid: str | None = None) -> list[CallPlan]:
    # cfg는 s6_config의 정규화 결과다. 여기서는 쓰기 없이 유효성만 다시 검사한다.
    _resolve_config(cfg)
    previous, changes = _partial(ctx, cid, cfg) if cid is not None else (None, {})
    pending = _pending_rev(ctx, cid) if cid is not None else None
    durations = []
    bad_frames = 0
    if pending:
        rev_dir = ctx.character_dir(cid) / "s6-actions" / pending
        inputs: ActionInputs = read_inputs(rev_dir / "inputs.json")
        for chapter in inputs.chapters:
            for action in chapter.actions:
                if inputs.previousRev and action.actionId not in inputs.regenerate:
                    continue
                for n in range(1, inputs.candidates + 1):
                    if not (rev_dir / "assets" / f"{action.actionId}-v{n}.json").exists():
                        durations.append(action.duration)
        chapter_count = len(inputs.chapters)
        action_count = len(inputs.chapters[0].actions)
        candidates = inputs.candidates
        aspect_ratio = inputs.aspectRatio
        resolution = inputs.resolution
    else:
        chapter_count = len(cfg["chapters"])
        action_count = len(cfg["actions"])
        candidates = cfg["candidates"]
        aspect_ratio = cfg["aspect_ratio"]
        for ch in cfg["chapters"]:
            for key in cfg["actions"]:
                if not previous or f"{ch}-{key}" in changes:
                    durations.extend([_duration(cfg, key)] * cfg["candidates"])
        if not previous and any(CATALOG[key]["mood"] == "bad" for key in cfg["actions"]):
            bad_frames = chapter_count
        resolution = cfg["resolution"]
    pcfg = ctx.config.provider("video")
    note = NOTES.get(pcfg.adapter, pcfg.adapter)
    if previous:
        note += f", {previous} 수정 요청 {len(changes)}개 동작만 재생성"
    n = len(durations)
    desc = (
        f"동작 영상 {n}편 ({chapter_count}챕터 × 동작 {action_count}개 × 후보 {candidates}, "
        f"{pcfg.model or pcfg.adapter}, {resolution}, 동작별 길이, "
        f"{aspect_ratio}, {note})"
    )
    plans = []
    if bad_frames:
        adapter = ctx.config.provider("image").adapter
        plans.append(
            CallPlan(
                "s6",
                f"무표정 첫 프레임 {bad_frames}장 (G4 이미지 표정만 바꿈, {adapter})",
                bad_frames,
            )
        )
    cost = sum(estimate(ctx, {"duration": d, "resolution": resolution}) for d in durations)
    plans.append(CallPlan("s6", desc, n, est_cost_usd=round(cost, 4)))
    return plans


def _pending_rev(ctx: Context, cid: str) -> str | None:
    stage = ctx.state(cid).stage("s6")
    if stage.status not in {"CHECK_FAILED", "RUNNING"} or not stage.currentRev:
        return None
    path = ctx.character_dir(cid) / "s6-actions" / stage.currentRev / "inputs.json"
    if not path.exists():
        return None
    from character_factory_poc.pipeline.origin import read_video_tier

    tier = read_video_tier(ctx.character_dir(cid))
    if tier:
        inputs = read_inputs(path)
        if inputs.preset != f"tier:{tier}" or inputs.frameRev != ctx.state(cid).gate("G4").rev:
            return None
    return stage.currentRev


def run_s6(ctx: Context, cid: str) -> Path:
    cfg = s6_config(ctx, cid)  # 잘못된 설정은 상태·산출물·공급자를 건드리기 전에 거절한다.
    state = ctx.state(cid)
    state.require_deps("s6")
    frames, frame_dir = load_approved_frames(ctx, cid)
    budget = ctx.budget()
    budget.check_plan(plan_calls(ctx, cfg, cid))
    rev = _pending_rev(ctx, cid) or next_rev(ctx.character_dir(cid) / "s6-actions", "va")
    rev_dir = ctx.character_dir(cid) / "s6-actions" / rev
    try:
        video = ctx.video_model(cid, budget)
        inputs_path = rev_dir / "inputs.json"
        if inputs_path.exists():
            inputs: ActionInputs = read_inputs(inputs_path)
            durations = {a.duration for ch in inputs.chapters for a in ch.actions}
            resolution = inputs.resolution
        else:
            durations = {_duration(cfg, key) for key in cfg["actions"]}
            resolution = cfg["resolution"]
        for duration in sorted(durations):
            video.check_settings(duration, resolution)
        for frame in frames.frames:
            if sha256_file(frame_dir / frame.path) != frame.sha256:
                raise CheckFailed("s6", [f"{frame.frameId}: G4 승인 이미지의 sha256이 다르다"])
        previous, changes = _partial(ctx, cid, cfg) if not inputs_path.exists() else (None, {})
        state.transition("s6", "RUNNING", rev=rev)
        if not inputs_path.exists():
            inputs = _make_inputs(
                ctx, cid, rev, rev_dir, frames, frame_dir, cfg, video, budget, previous, changes
            )
            write_once_json(inputs_path, dump(inputs))
        _run(ctx, cid, rev, rev_dir, inputs, video)
    except (CheckFailed, VideoGenerationError, ImageGenerationError) as e:
        state = ctx.state(cid)
        if state.stage("s6").status != "RUNNING":
            state.transition("s6", "RUNNING", rev=rev)
        state.transition("s6", "CHECK_FAILED", rev=rev, error=str(e))
        raise
    state = ctx.state(cid)
    state.transition("s6", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G5b", "AWAITING_HUMAN", rev, None)
    return rev_dir


def _first_frames(ctx, cid, rev, rev_dir, frame, frame_dir, needs_bad, cfg, budget, old):
    """G4 복사본과 표정 편집본을 고정한다. 부분 재생성은 원본·편집 출처까지 복사한다."""
    good = {
        "id": frame.frameId,
        "path": f"first-frames/{frame.chapterId}-good.png",
        "sha256": frame.sha256,
    }
    if old:
        previous, chapter = old
        previous_dir = rev_dir.parent / previous
        for ref in (chapter.goodFrame, chapter.badFrame):
            if ref:
                path = previous_dir / ref.path
                if sha256_file(path) != ref.sha256:
                    raise CheckFailed(
                        "s6", [f"{frame.chapterId}: 재사용 첫 프레임의 sha256이 다르다"]
                    )
                write_once_bytes(rev_dir / ref.path, path.read_bytes())
        source = None
        if chapter.badFrame:
            raw_path = f"first-frames/{frame.chapterId}-bad-raw.png"
            write_once_bytes(rev_dir / raw_path, (previous_dir / raw_path).read_bytes())
            source = dump(chapter.badFrameSource.model_copy(update={"reusedFrom": previous}))
        return dump(chapter.goodFrame), dump(chapter.badFrame) if chapter.badFrame else None, source
    write_once_bytes(rev_dir / good["path"], (frame_dir / frame.path).read_bytes())
    if not needs_bad:
        return good, None, None
    ratio = parse_ratio(cfg["aspect_ratio"])
    neutral = neutral_prompt(twin=is_twin(ctx.character_dir(cid)))
    result = ctx.image_model(cid, budget).generate(
        ImageRequest(
            stage="s6",
            prompt=neutral,
            ref=f"{cid}/{rev}/{frame.chapterId}-bad-frame",
            negative_prompt=NEUTRAL_NEGATIVE,
            size=request_size(ratio),
            reference_images=(str(rev_dir / good["path"]),),
        )
    )
    write_once_bytes(rev_dir / f"first-frames/{frame.chapterId}-bad-raw.png", result.data)
    try:
        png, raw_size, cropped_size = crop_to_ratio(result.data, ratio)
    except ValueError as e:
        raise CheckFailed("s6", [str(e)]) from e
    bad_path = f"first-frames/{frame.chapterId}-bad.png"
    write_once_bytes(rev_dir / bad_path, png)
    bad = {
        "id": f"{frame.chapterId}-bad",
        "path": bad_path,
        "sha256": sha256_file(rev_dir / bad_path),
    }
    source = {
        "source": good,
        "prompt": neutral,
        "negativePrompt": NEUTRAL_NEGATIVE,
        "provider": result.provider,
        "model": result.model,
        "rawSize": list(raw_size),
        "croppedSize": list(cropped_size),
    }
    return good, bad, source


def _make_inputs(ctx, cid, rev, rev_dir, frames, frame_dir, cfg, video, budget, previous, changes):
    old_chapters = {}
    if previous:
        old: ActionInputs = read_inputs(rev_dir.parent / previous / "inputs.json")
        old_chapters = {ch.chapterId: ch for ch in old.chapters}
    chapters = []
    for frame in sorted(frames.frames, key=lambda f: f.chapterId):
        if frame.chapterId not in cfg["chapters"]:
            continue
        old_ch = old_chapters.get(frame.chapterId)
        carried = {a.actionId: a for a in old_ch.actions} if old_ch else {}
        actions = []
        for key in cfg["actions"]:
            aid = f"{frame.chapterId}-{key}"
            if previous and aid not in changes:
                actions.append(dump(carried[aid]))
                continue
            clip = CATALOG[key]
            note = changes.get(aid, "")
            actions.append(
                {
                    "actionId": aid,
                    "actionKey": key,
                    "playType": clip["playType"],
                    "pickRole": clip["pickRole"],
                    "actionCategory": clip["actionCategory"],
                    "mood": clip["mood"],
                    "title": clip["title"],
                    "description": clip["description"],
                    "useWhen": clip["useWhen"],
                    "duration": _duration(cfg, key),
                    "reviewNote": note,
                    "prompt": build_prompt(
                        key, frame.chapterId, note, motif=bool(cfg.get("motif"))
                    ),
                }
            )
        good, bad, source = _first_frames(
            ctx,
            cid,
            rev,
            rev_dir,
            frame,
            frame_dir,
            any(a["mood"] == "bad" for a in actions),
            cfg,
            budget,
            (previous, old_ch) if previous else None,
        )
        chapters.append(
            {
                "chapterId": frame.chapterId,
                "frameId": frame.frameId,
                "stageNote": stage_note(frame.chapterId, motif=bool(cfg.get("motif"))),
                "goodFrame": good,
                "badFrame": bad,
                "badFrameSource": source,
                "actions": actions,
            }
        )
    return validate(
        LIGHT_INPUTS
        if cfg.get("video_tier") and tuple(cfg["chapters"]) == ("ch1",)
        else "action-inputs-v2",
        {
            "frameRev": frames.frameRev,
            "appearanceRev": frames.appearanceRev,
            "planRev": frames.planRev,
            "provider": video.name,
            "model": video.model,
            "preset": cfg["preset"],
            "resolution": cfg["resolution"],
            "aspectRatio": cfg["aspect_ratio"],
            "generateAudio": cfg["generate_audio"],
            "candidates": cfg["candidates"],
            "previousRev": previous,
            "regenerate": [
                a["actionId"]
                for ch in chapters
                for a in ch["actions"]
                if not previous or a["actionId"] in changes
            ],
            "chapters": chapters,
        },
    )


def _run(ctx, cid, rev, rev_dir, inputs, video) -> None:
    previous_dir = rev_dir.parent / inputs.previousRev if inputs.previousRev else None
    old = {}
    if previous_dir:
        old = {
            (c["actionId"], c["asset"]["candidateId"]): c
            for c in read_json(previous_dir / "clips.json")
        }
    clips = []
    for chapter in inputs.chapters:
        for frame in (chapter.goodFrame, chapter.badFrame):
            if frame and sha256_file(rev_dir / frame.path) != frame.sha256:
                raise CheckFailed(
                    "s6", [f"{chapter.chapterId}: 고정한 첫 프레임의 sha256이 다르다"]
                )
        for action in chapter.actions:
            for n in range(1, inputs.candidates + 1):
                if previous_dir and action.actionId not in inputs.regenerate:
                    clip = validate("action-clip-v2", old[(action.actionId, f"v{n}")])
                    asset = clip.asset
                    name = f"{action.actionId}-v{n}.json"
                    write_once_bytes(
                        rev_dir / asset.filePath, (previous_dir / asset.filePath).read_bytes()
                    )
                    write_once_bytes(
                        rev_dir / "assets" / name, (previous_dir / "assets" / name).read_bytes()
                    )
                    clip = clip.model_copy(update={"reusedFrom": inputs.previousRev})
                else:
                    asset = _generate(ctx, cid, rev, rev_dir, inputs, chapter, action, n, video)
                    clip = ActionClip(
                        actionId=action.actionId,
                        chapterId=chapter.chapterId,
                        actionKey=action.actionKey,
                        playType=action.playType,
                        mood=action.mood,
                        pickRole=action.pickRole,
                        actionCategory=action.actionCategory,
                        title=action.title,
                        frameId=chapter.frameId,
                        asset=asset,
                    )
                clips.append(clip)
    write_once_json(rev_dir / "clips.json", [dump(c) for c in clips])
    write_once_text(
        rev_dir / "gate-G5b.html",
        render_g5b_page(subject_id=cid, rev=rev, inputs=inputs, clips=clips),
    )
    write_manifest(rev_dir)


def _generate(ctx, cid, rev, rev_dir, inputs, chapter, action, n, video):
    name = f"{action.actionId}-v{n}"
    asset_path = rev_dir / "assets" / f"{name}.json"
    job_path = rev_dir / "jobs" / f"{name}.json"
    if asset_path.exists():
        asset = validate("video-asset-v1", read_json(asset_path))
        if job_path.exists():
            job = read_json(job_path)
            if job["status"] != "DONE":
                _write_json(job_path, job | {"status": "DONE"})
        return asset
    first_frame = chapter.badFrame if action.mood == "bad" else chapter.goodFrame
    settings = {
        "prompt": action.prompt,
        "duration": action.duration,
        "resolution": inputs.resolution,
        "aspectRatio": inputs.aspectRatio,
        "generateAudio": inputs.generateAudio,
    }
    request = VideoRequest(
        stage="s6",
        prompt=action.prompt,
        ref=f"{cid}/{rev}/{name}",
        first_frame=str(rev_dir / first_frame.path),
        duration=action.duration,
        resolution=inputs.resolution,
        aspect_ratio=inputs.aspectRatio,
        generate_audio=inputs.generateAudio,
    )
    job = read_json(job_path) if job_path.exists() and video.resumable else None
    if job is None or job["status"] != "SUBMITTED":
        job_id = video.submit(request)
        job = dump(
            validate(
                "video-job-v1",
                {
                    "videoId": f"vd-{cid}-{action.actionId}-{rev}-{n}",
                    "candidateId": f"v{n}",
                    "stage": "s6",
                    "provider": video.name,
                    "model": video.model,
                    "jobId": job_id,
                    "status": "SUBMITTED",
                    "settings": settings,
                    "firstFrameSha256": first_frame.sha256,
                    "estCostUsd": estimate(
                        ctx, {"duration": action.duration, "resolution": inputs.resolution}
                    ),
                },
            )
        )
        _write_json(job_path, job)
    try:
        result = video.collect(job["jobId"], request)
    except VideoGenerationError as e:
        if not hasattr(e, "job_id"):
            _write_json(job_path, job | {"status": "FAILED", "error": str(e)[:500]})
        raise
    if result.data[4:8] != b"ftyp":
        _write_json(job_path, job | {"status": "FAILED", "error": "MP4가 아니다"})
        raise VideoGenerationError(f"{name}: 받은 파일이 MP4가 아니다")
    rel = f"videos/{name}.mp4"
    write_once_bytes(rev_dir / rel, result.data)
    asset = validate(
        "video-asset-v1",
        {
            "videoId": job["videoId"],
            "candidateId": f"v{n}",
            "jobId": result.job_id,
            "provider": result.provider,
            "model": result.model,
            "filePath": rel,
            "fileSha256": sha256_file(rev_dir / rel),
            "bytes": len(result.data),
            "settings": settings,
            "probe": dump(probe_video(rev_dir / rel)),
            "estCostUsd": result.est_cost_usd,
        },
    )
    write_once_json(asset_path, dump(asset))
    _write_json(job_path, job | {"status": "DONE"})
    return asset
