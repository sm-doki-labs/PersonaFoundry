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
from character_factory_poc.providers.video_concurrency import run_video_jobs
from character_factory_poc.providers.xai_video import estimate_cost
from character_factory_poc.stages.s4_frames.approve import load_approved_frames
from character_factory_poc.stages.s5_intro.probe import probe_video
from character_factory_poc.stages.s5_intro.run import NOTES, _write_json
from character_factory_poc.stages.s6_actions.catalog import (
    ALL_CHAPTERS,
    CATALOG,
    NEUTRAL_NEGATIVE,
    PRESETS,
    SIGNATURE_KEY,
    build_prompt,
    clip_of,
    neutral_prompt,
    signature_matches,
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
    # 끝 화면을 첫 화면과 같은 사진으로 고정해 앱에서 영상을 갈아 끼워도 자세가 이어진다(D-0185).
    "pin_last_frame": True,
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
        if cfg.get("motif"):
            # D-0165: 모티브는 등급마다 유저가 정한 시그니처 포즈를 한 편 더한다.
            if not cfg.get("signature"):
                raise CheckFailed("s6", ["영상을 만들려면 시그니처 포즈를 정해 주세요."])
            cfg["actions"].append(SIGNATURE_KEY)
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
    if cfg.get("motif") and cfg.get("video_tier") == "light":
        from .call_loop import VERSION, VideoScene

        cfg["production_profile"] = VERSION
        cfg["video_scene"] = VideoScene.model_validate(cfg.get("video_scene") or {}).model_dump()
        cfg["generate_audio"] = False
        cfg["pin_last_frame"] = True
        sig = cfg.get("signature") or {}
        if sig.get("template", "custom") not in {"custom", "camera_click"}:
            problems.append("시그니처 template은 custom 또는 camera_click이다")
        at = sig.get("middleFrameAtS", 2.0)
        if not isinstance(at, (int, float)) or isinstance(at, bool) or not 0 < at < 4.5:
            problems.append("시그니처 중간 시점은 0초 초과 4.5초 미만이다")
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
    if type(cfg["pin_last_frame"]) is not bool:
        problems.append("pin_last_frame은 boolean이다")
    elif cfg["pin_last_frame"] and cfg["resolution"] == "1080p":
        # xAI는 끝 화면을 정한 요청에 1080p를 받지 않는다(2026-11-12 실제 HTTP 400).
        problems.append(
            "끝 화면 고정(pin_last_frame)은 720p까지만 된다. 1080p가 필요하면 "
            "pin_last_frame = false로 끈다"
        )
    if problems:
        raise CheckFailed("s6", problems)
    cfg["durations"] = durations
    return cfg


def s6_config(ctx: Context, cid: str | None = None) -> dict[str, Any]:
    from character_factory_poc.pipeline.origin import read_signature, read_video_tier

    settings = dict(ctx.config.stage("s6"))
    tier = read_video_tier(ctx.character_dir(cid)) if cid else None
    if tier == "none":
        raise CheckFailed("s6", ["영상 없이 만들기로 정했어요."])
    if tier:
        settings["video_tier"] = tier
        settings["motif"] = is_twin(ctx.character_dir(cid))
        if settings["motif"]:
            settings["signature"] = read_signature(ctx.character_dir(cid))
    if cid and settings.get("motif"):
        from .call_loop import PURPOSES

        folder = ctx.character_dir(cid)
        pack_path = folder / "source-pack.json"
        pack = read_json(pack_path) if pack_path.exists() else {}
        video_path = folder / "video-settings.json"
        saved = read_json(video_path) if video_path.exists() else {}
        settings["video_scene"] = (
            {"purpose": PURPOSES.get(pack.get("chapterTemplate", "FAN_CALL"), PURPOSES["FAN_CALL"])}
            | settings.get("video_scene", {})
            | saved.get("videoScene", {})
        )
    cfg = _resolve_config(settings)
    if cfg.get("production_profile") and cfg.get("signature", {}).get("middleFramePath"):
        if ctx.config.provider("video").adapter not in {
            "xai_video",
            "grok_oauth",
            "grok",
            "fake",
        }:
            raise CheckFailed("s6", ["이 영상 경로는 중간 프레임 전달을 지원하지 않는다"])
        import cv2

        from character_factory_poc.common.source_store import inside

        try:
            source_path = cfg["signature"]["middleFramePath"]
            if Path(source_path).is_absolute():
                raise ValueError("relative path required")
            path = inside(ctx.character_dir(cid), source_path)
            if cv2.imread(str(path)) is None:
                raise ValueError("invalid image")
            cfg["middle_sha256"] = sha256_file(path)
        except (OSError, ValueError) as exc:
            raise CheckFailed(
                "s6", ["중간 자세 사진이 없거나 안전한 이미지 경로가 아니다"]
            ) from exc
    return cfg


def _duration(cfg: dict, key: str) -> int:
    if cfg.get("production_profile") == "call-loop-v1":
        return 6
    return cfg["durations"][clip_of(key, cfg)["pickRole"] or "idle"]


def estimate(ctx: Context, cfg: dict[str, Any], calls: int = 1) -> float:
    pcfg = ctx.config.provider("video")
    if pcfg.adapter not in {"xai_video", "grok_oauth", "grok"}:
        return 0.0
    each = estimate_cost(
        pcfg.model or "grok-imagine-video-1.5",
        cfg["resolution"],
        cfg["duration"],
        pcfg.extra.get("price_per_second"),
        input_images=(2 if cfg.get("pin_last_frame") else 1) + cfg.get("keyframe_count", 0),
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
    if previous.productionProfile != cfg.get(
        "production_profile"
    ) or previous.videoScene != cfg.get("video_scene", {}):
        return None, {}
    settings = {
        "resolution": previous.resolution,
        "aspect_ratio": previous.aspectRatio,
        "generate_audio": previous.generateAudio,
        "pin_last_frame": previous.pinLastFrame,
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
    if cfg.get("motif"):
        signature_changed = not signature_matches(dump(previous), cfg.get("signature"))
        for ch in previous.chapters:
            for action in ch.actions:
                if action.actionKey != SIGNATURE_KEY:
                    continue
                if signature_changed or action.production.get("middleFrame", {}).get(
                    "sha256"
                ) != cfg.get("middle_sha256"):
                    changes.setdefault(action.actionId, action.reviewNote)
    return (gate.rev, changes) if changes else (None, {})


def _carry(ctx: Context, cid: str, cfg: dict) -> tuple[str | None, dict[str, str]]:
    """모티브 등급 올리기·시그니처 바꾸기(D-0166). 승인된 판에서 같은 첫 화면·같은 지시의 몸짓은
    그대로 옮겨 오고, 새로 생기거나 바뀐 몸짓만 다시 만든다. 파일을 쓰지 않는다."""
    if not (cfg.get("motif") and cfg.get("video_tier")):
        return None, {}
    state = ctx.state(cid)
    gate, frame_gate = state.gate("G5b"), state.gate("G4")
    if gate.status != "APPROVED" or not gate.rev or frame_gate.status != "APPROVED":
        return None, {}
    inputs_path = ctx.character_dir(cid) / "s6-actions" / gate.rev / "inputs.json"
    clips_path = inputs_path.with_name("clips.json")
    if not inputs_path.exists() or not clips_path.exists():
        return None, {}
    previous: ActionInputs = read_inputs(inputs_path)
    if previous.productionProfile != cfg.get(
        "production_profile"
    ) or previous.videoScene != cfg.get("video_scene", {}):
        return None, {}
    settings = {
        "resolution": previous.resolution,
        "aspect_ratio": previous.aspectRatio,
        "generate_audio": previous.generateAudio,
        "pin_last_frame": previous.pinLastFrame,
        "candidates": previous.candidates,
    }
    if previous.frameRev != frame_gate.rev or any(cfg[k] != v for k, v in settings.items()):
        return None, {}
    if tuple(ch.chapterId for ch in previous.chapters) != tuple(cfg["chapters"]):
        return None, {}
    changes = {}
    for chapter in previous.chapters:
        old = {a.actionKey: a for a in chapter.actions}
        for key in cfg["actions"]:
            clip = clip_of(key, cfg)
            prompt = build_prompt(key, chapter.chapterId, motif=True, clip=clip)
            was = old.get(key)
            same = was is not None and (
                was.prompt == prompt
                and {k: v for k, v in was.production.items() if k != "middleFrame"}
                == clip.get("production", {})
                and was.production.get("middleFrame", {}).get("sha256")
                == (cfg.get("middle_sha256") if key == SIGNATURE_KEY else None)
                and was.duration == _duration(cfg, key)
                and (was.title, was.description, was.useWhen)
                == (clip["title"], clip["description"], clip["useWhen"])
            )
            if not same:
                changes[f"{chapter.chapterId}-{key}"] = ""
    # 바뀐 것이 없어도 새 판으로 묶는다(등급 표시만 바뀐 경우). 영상은 하나도 새로 만들지 않는다.
    return gate.rev, changes


def _has_bad_frames(ctx: Context, cid: str, rev: str) -> bool:
    inputs = read_inputs(ctx.character_dir(cid) / "s6-actions" / rev / "inputs.json")
    return all(ch.badFrame is not None for ch in inputs.chapters)


def _reuse(ctx: Context, cid: str, cfg: dict) -> tuple[str | None, dict[str, str]]:
    previous, changes = _partial(ctx, cid, cfg)
    return (previous, changes) if previous else _carry(ctx, cid, cfg)


def plan_calls(ctx: Context, cfg: dict[str, Any], cid: str | None = None) -> list[CallPlan]:
    # cfg는 s6_config의 정규화 결과다. 여기서는 쓰기 없이 유효성만 다시 검사한다.
    _resolve_config(cfg)
    previous, changes = _reuse(ctx, cid, cfg) if cid is not None else (None, {})
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
                        raw = rev_dir / "raw" / f"{action.actionId}-v{n}.mp4"
                        receipt = raw.with_suffix(".json")
                        if raw.exists() != receipt.exists():
                            raise CheckFailed("s6", ["생성 원본 저장이 불완전해 재제출하지 않는다"])
                        if raw.exists() and receipt.exists():
                            if sha256_file(raw) != read_json(receipt).get("sha256"):
                                raise CheckFailed("s6", ["생성 원본의 해시가 다르다"])
                            continue
                        durations.append(action.duration)
        chapter_count = len(inputs.chapters)
        action_count = len(inputs.chapters[0].actions)
        candidates = inputs.candidates
        aspect_ratio = inputs.aspectRatio
        resolution = inputs.resolution
        pin_last_frame = inputs.pinLastFrame
    else:
        chapter_count = len(cfg["chapters"])
        action_count = len(cfg["actions"])
        candidates = cfg["candidates"]
        aspect_ratio = cfg["aspect_ratio"]
        for ch in cfg["chapters"]:
            for key in cfg["actions"]:
                if not previous or f"{ch}-{key}" in changes:
                    durations.extend([_duration(cfg, key)] * cfg["candidates"])
        if any(clip_of(key, cfg)["mood"] == "bad" for key in cfg["actions"]) and not (
            previous and _has_bad_frames(ctx, cid, previous)
        ):
            bad_frames = chapter_count
        resolution = cfg["resolution"]
        pin_last_frame = cfg["pin_last_frame"]
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
    cost = sum(
        estimate(
            ctx,
            {
                "duration": d,
                "resolution": resolution,
                "pin_last_frame": pin_last_frame,
                "keyframe_count": int(bool(cfg.get("middle_sha256"))),
            },
        )
        for d in durations
    )
    plans.append(CallPlan("s6", desc, n, est_cost_usd=round(cost, 4)))
    return plans


def _pending_rev(ctx: Context, cid: str) -> str | None:
    stage = ctx.state(cid).stage("s6")
    if stage.status not in {"CHECK_FAILED", "RUNNING"} or not stage.currentRev:
        return None
    path = ctx.character_dir(cid) / "s6-actions" / stage.currentRev / "inputs.json"
    if not path.exists():
        return None
    from character_factory_poc.pipeline.origin import read_signature, read_video_tier

    tier = read_video_tier(ctx.character_dir(cid))
    cfg = s6_config(ctx, cid)
    pending = read_inputs(path)
    if any(
        a.production.get("middleFrame", {}).get("sha256") != cfg.get("middle_sha256")
        for ch in pending.chapters
        for a in ch.actions
        if a.actionKey == SIGNATURE_KEY
    ):
        return None
    if pending.productionProfile != cfg.get("production_profile") or pending.videoScene != cfg.get(
        "video_scene", {}
    ):
        return None
    if tier:
        inputs = read_inputs(path)
        if inputs.preset != f"tier:{tier}" or inputs.frameRev != ctx.state(cid).gate("G4").rev:
            return None
        if is_twin(ctx.character_dir(cid)) and not signature_matches(
            dump(inputs), read_signature(ctx.character_dir(cid))
        ):
            return None
    return stage.currentRev


def run_s6(ctx: Context, cid: str) -> Path:
    cfg = s6_config(ctx, cid)  # 잘못된 설정은 상태·산출물·공급자를 건드리기 전에 거절한다.
    state = ctx.state(cid)
    state.require_deps("s6")
    frames, frame_dir = load_approved_frames(ctx, cid)
    budget = ctx.budget()
    if cfg.get("production_profile") and ctx.config.provider("video").adapter != "fake":
        from .postprocess import require_tools

        require_tools()
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
        previous, changes = _reuse(ctx, cid, cfg) if not inputs_path.exists() else (None, {})
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
        if chapter.badFrame or not needs_bad:
            return (
                dump(chapter.goodFrame),
                dump(chapter.badFrame) if chapter.badFrame else None,
                source,
            )
        # 이전 판(라이트)에는 무표정 첫 화면이 없었다.
        # 영상은 옮겨 오고 그 한 장만 새로 만든다(D-0167).
        good = dump(chapter.goodFrame)
    else:
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
                carried_action = dump(carried[aid])
                middle = carried_action.get("production", {}).get("middleFrame")
                if middle:
                    old_file = rev_dir.parent / previous / middle["path"]
                    if sha256_file(old_file) != middle["sha256"]:
                        raise CheckFailed("s6", ["재사용 중간 사진의 해시가 다르다"])
                    write_once_bytes(rev_dir / middle["path"], old_file.read_bytes())
                actions.append(carried_action)
                continue
            clip = clip_of(key, cfg)
            note = changes.get(aid, "")
            prod = dict(clip.get("production", {}))
            if prod.get("middleFramePath"):
                from character_factory_poc.common.source_store import inside

                source = inside(ctx.character_dir(cid), prod["middleFramePath"])
                rel = f"keyframes/{aid}{source.suffix.lower()}"
                write_once_bytes(rev_dir / rel, source.read_bytes())
                prod["middleFrame"] = {"path": rel, "sha256": sha256_file(rev_dir / rel)}
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
                    "production": prod,
                    "reviewNote": note,
                    "prompt": build_prompt(
                        key, frame.chapterId, note, motif=bool(cfg.get("motif")), clip=clip
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
            "pinLastFrame": cfg["pin_last_frame"],
            "candidates": cfg["candidates"],
            "productionProfile": cfg.get("production_profile"),
            "videoScene": cfg.get("video_scene", {}),
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
    jobs = []
    for chapter in inputs.chapters:
        for frame in (chapter.goodFrame, chapter.badFrame):
            if frame and sha256_file(rev_dir / frame.path) != frame.sha256:
                raise CheckFailed(
                    "s6", [f"{chapter.chapterId}: 고정한 첫 프레임의 sha256이 다르다"]
                )
        for action in chapter.actions:
            jobs.extend((chapter, action, n) for n in range(1, inputs.candidates + 1))

    def generate(item) -> ActionClip:
        chapter, action, n = item
        if previous_dir and action.actionId not in inputs.regenerate:
            clip = validate("action-clip-v2", old[(action.actionId, f"v{n}")])
            asset = clip.asset
            name = f"{action.actionId}-v{n}.json"
            write_once_bytes(rev_dir / asset.filePath, (previous_dir / asset.filePath).read_bytes())
            write_once_bytes(
                rev_dir / "assets" / name, (previous_dir / "assets" / name).read_bytes()
            )
            raw_rel = asset.postprocess.get("rawPath")
            if raw_rel:
                raw_source = previous_dir / raw_rel
                receipt_source = raw_source.with_suffix(".json")
                receipt = read_json(receipt_source)
                if sha256_file(raw_source) != receipt["sha256"]:
                    raise CheckFailed("s6", ["재사용 생성 원본의 해시가 다르다"])
                write_once_bytes(rev_dir / raw_rel, raw_source.read_bytes())
                write_once_json((rev_dir / raw_rel).with_suffix(".json"), receipt)
            return clip.model_copy(update={"reusedFrom": inputs.previousRev})
        with video.job_slot("s6"):
            asset = _generate(ctx, cid, rev, rev_dir, inputs, chapter, action, n, video)
        return ActionClip(
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

    workers = 1 if video.name == "grok_web" else min(6, getattr(video.limits, "limit", 6))
    clips = run_video_jobs(generate, jobs, workers=workers)
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
    first_path = str(rev_dir / first_frame.path)
    settings = {
        "prompt": action.prompt,
        "duration": action.duration,
        "resolution": inputs.resolution,
        "aspectRatio": inputs.aspectRatio,
        "generateAudio": inputs.generateAudio,
        "pinLastFrame": inputs.pinLastFrame,
    }
    keyframes = ()
    if action.production.get("middleFrame"):
        middle = action.production["middleFrame"]
        middle_path = rev_dir / middle["path"]
        if sha256_file(middle_path) != middle["sha256"]:
            raise CheckFailed("s6", ["중간 자세 사진의 해시가 다르다"])
        keyframes = ((action.production["middleFrameAtS"], str(middle_path)),)
    request = VideoRequest(
        stage="s6",
        prompt=action.prompt,
        ref=f"{cid}/{rev}/{name}",
        first_frame=first_path,
        duration=action.duration,
        resolution=inputs.resolution,
        aspect_ratio=inputs.aspectRatio,
        generate_audio=inputs.generateAudio,
        last_frame=first_path if inputs.pinLastFrame else None,
        keyframes=keyframes,
    )
    raw_path = rev_dir / "raw" / f"{name}.mp4"
    receipt_path = raw_path.with_suffix(".json")
    if raw_path.exists() != receipt_path.exists():
        raise CheckFailed("s6", ["생성 원본 저장이 불완전해 재제출하지 않는다"])
    cached = raw_path.exists() and receipt_path.exists()
    if cached:
        receipt = read_json(receipt_path)
        if sha256_file(raw_path) != receipt["sha256"]:
            raise CheckFailed("s6", ["생성 원본의 해시가 다르다"])
        if not job_path.exists():
            raise CheckFailed("s6", ["생성 원본의 작업 기록이 없어 자동 재제출하지 않는다"])
    job = read_json(job_path) if job_path.exists() and (video.resumable or cached) else None
    if not cached and (job is None or job["status"] != "SUBMITTED"):
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
                        ctx,
                        {
                            "duration": action.duration,
                            "resolution": inputs.resolution,
                            "pin_last_frame": inputs.pinLastFrame,
                            "keyframe_count": len(keyframes),
                        },
                    ),
                },
            )
        )
        _write_json(job_path, job)
    if cached:
        receipt = read_json(receipt_path)
        if sha256_file(raw_path) != receipt["sha256"]:
            raise CheckFailed("s6", ["생성 원본의 해시가 다르다"])
        data = raw_path.read_bytes()
    else:
        try:
            result = video.collect(job["jobId"], request)
        except VideoGenerationError as e:
            if not hasattr(e, "job_id"):
                _write_json(job_path, job | {"status": "FAILED", "error": str(e)[:500]})
            raise
        data = result.data
        if data[4:8] != b"ftyp":
            _write_json(job_path, job | {"status": "FAILED", "error": "MP4가 아니다"})
            raise VideoGenerationError(f"{name}: 받은 파일이 MP4가 아니다")
        receipt = {
            "jobId": result.job_id,
            "provider": result.provider,
            "model": result.model,
            "estCostUsd": result.est_cost_usd,
        }
        if action.production:
            write_once_bytes(raw_path, data)
            receipt["sha256"] = sha256_file(raw_path)
            write_once_json(receipt_path, receipt)
    postprocess = {}
    if action.production:
        if receipt["provider"] == "fake_video":
            postprocess = {"status": "fake_unvalidated", "qualityApproved": False}
        else:
            from .postprocess import process

            data, postprocess = process(raw_path, Path(first_path), action.production)
            postprocess["rawPath"] = str(raw_path.relative_to(rev_dir))
    rel = f"videos/{name}.mp4"
    write_once_bytes(rev_dir / rel, data)
    asset = validate(
        "video-asset-v1",
        {
            "videoId": job["videoId"],
            "candidateId": f"v{n}",
            "jobId": receipt["jobId"],
            "provider": receipt["provider"],
            "model": receipt["model"],
            "filePath": rel,
            "fileSha256": sha256_file(rev_dir / rel),
            "bytes": len(data),
            "settings": settings,
            "probe": dump(probe_video(rev_dir / rel)),
            "estCostUsd": receipt["estCostUsd"],
            "postprocess": postprocess,
        },
    )
    write_once_json(asset_path, dump(asset))
    _write_json(job_path, job | {"status": "DONE"})
    return asset
