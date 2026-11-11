"""S5 실행 (명세 §3, LLD §8.5). cfp video intro와 cfp run의 s5 진입점."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

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
    write_manifest,
    write_once_bytes,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.rework import ReworkBrief
from character_factory_poc.contracts.video import IntroInputs, VideoAsset
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import is_twin
from character_factory_poc.pipeline.rework import load_rework
from character_factory_poc.providers.base import ImageRequest, VideoRequest
from character_factory_poc.providers.xai_video import estimate_cost
from character_factory_poc.stages.s1_reference.preview import subject_phrase
from character_factory_poc.stages.s2_hero.approve import load_appearance_spec
from character_factory_poc.stages.s5_intro import first_frame as ff
from character_factory_poc.stages.s5_intro.page import render_g5_page
from character_factory_poc.stages.s5_intro.probe import probe_video
from character_factory_poc.stages.s5_intro.prompt import build_motion_prompt

# D-0030 제안값, 비율과 첫 프레임은 D-0031(쇼츠 9:16). factory.toml [stages.s5]로 바꾼다.
DEFAULTS: dict[str, Any] = {
    "candidates": 2,
    "duration": 8,
    "resolution": "720p",
    "aspect_ratio": "9:16",
    # vertical: 대표 이미지를 참조로 목표 비율의 첫 프레임을 새로 만든다. hero: 대표 이미지 그대로.
    "first_frame": "vertical",
    "generate_audio": False,
}
NOTES = {
    "xai_video": "xAI 공식 API, 출력 1초당 과금",
    "grok": "Grok 로그인(opencodex) 먼저, 안 되면 xAI API 키. 출력 1초당 과금",
    "grok_oauth": "Grok 로그인(opencodex) 토큰, 출력 1초당 과금(2026-11-12 실제 호출 확인, 비공식 경로)",
    "grok_web": "Grok 웹(구독 사용량), 약관 위험 감수(D-0029)",
    "fake": "가짜 영상, 비용 없음",
}


def s5_config(ctx: Context) -> dict[str, Any]:
    cfg = DEFAULTS | ctx.config.stage("s5")
    if cfg["first_frame"] not in {"vertical", "hero"}:
        raise CheckFailed("s5", [f"first_frame은 vertical 또는 hero다: {cfg['first_frame']!r}"])
    if cfg["first_frame"] == "vertical":
        if not cfg["aspect_ratio"]:
            raise CheckFailed(
                "s5", ["first_frame = vertical이면 aspect_ratio가 필요하다(예: 9:16)"]
            )
        try:
            ff.parse_ratio(cfg["aspect_ratio"])
        except ValueError as e:
            raise CheckFailed("s5", [str(e)]) from e
    return cfg


def estimate(ctx: Context, cfg: dict[str, Any]) -> float:
    pcfg = ctx.config.provider("video")
    if pcfg.adapter not in {"xai_video", "grok_oauth", "grok"}:
        return 0.0
    each = estimate_cost(
        pcfg.model or "grok-imagine-video-1.5-lite",
        str(cfg["resolution"]),
        float(cfg["duration"]),
        pcfg.extra.get("price_per_second"),
    )
    if each is None:
        raise CheckFailed(
            "s5", [f"{pcfg.model} {cfg['resolution']}의 단가가 없다. price_per_second를 설정한다"]
        )
    return round(each * int(cfg["candidates"]), 4)


def rework_prompt_block(brief: ReworkBrief) -> str:
    """수정 요청을 영상 지시에 붙일 문장. 사람 메모 원문은 줄마다 그대로 남긴다(FR-46)."""
    notes = [t.note for t in brief.targets]
    parts = []
    if notes:
        parts.append("Revision notes (keep these in the regenerated clip):")
        parts.extend(f"- {note}" for note in notes)
    if brief.normalizedBy is not None and brief.instructions.strip():
        parts.append("Revision instruction: " + brief.instructions.strip())
    return "\n".join(parts)


def motion_prompt(brief: ReworkBrief | None) -> str:
    base = build_motion_prompt()
    if brief is None:
        return base
    block = rework_prompt_block(brief)
    return f"{base}\n\n{block}" if block else base


def plan_calls(ctx: Context, cfg: dict[str, Any]) -> list[CallPlan]:
    pcfg = ctx.config.provider("video")
    n = int(cfg["candidates"])
    note = NOTES.get(pcfg.adapter, pcfg.adapter)
    ratio = cfg["aspect_ratio"] or "입력 이미지 비율"
    desc = (
        f"소개 영상 후보 {n}편 ({pcfg.model or pcfg.adapter}, {cfg['resolution']}, "
        f"{cfg['duration']}초, {ratio}, {note})"
    )
    plans = []
    if cfg["first_frame"] == "vertical":
        iad = ctx.config.provider("image").adapter
        plans.append(
            CallPlan("s5", f"{cfg['aspect_ratio']} 첫 프레임 1장 (대표 이미지 참조, {iad})", 1)
        )
    plans.append(CallPlan("s5", desc, n, est_cost_usd=estimate(ctx, cfg)))
    return plans


def _write_json(path: Path, obj: Any) -> None:
    """작업 기록은 상태가 바뀌므로 덮어쓴다(원자적 교체). 고정 산출물은 write_once를 쓴다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")
    os.replace(tmp, path)


def _pending_rev(ctx: Context, cid: str) -> str | None:
    """직전 실행이 원격 대기·실패로 멈췄거나 프로세스가 끊겨 RUNNING으로 남았으면 그 rev에서 이어 간다.

    첫 프레임과 설정(inputs.json)을 다시 만들지 않고, 받은 영상과 제출한 작업을 다시 쓴다."""
    st = ctx.state(cid).stage("s5")
    if st.status not in {"CHECK_FAILED", "RUNNING"} or not st.currentRev:
        return None
    inputs = ctx.character_dir(cid) / "s5-intro" / st.currentRev / "inputs.json"
    return st.currentRev if inputs.exists() else None


def run_s5(ctx: Context, cid: str) -> Path:
    state = ctx.state(cid)
    state.require_deps("s5")  # s2 승인(외모 명세) 필요(D-0042)
    spec, hero = load_appearance_spec(ctx, cid)
    cfg = s5_config(ctx)
    brief = load_rework(ctx, cid, "G5")
    budget = ctx.budget()
    budget.check_plan(plan_calls(ctx, cfg))
    char_dir = ctx.character_dir(cid)
    rev = _pending_rev(ctx, cid) or next_rev(char_dir / "s5-intro", "vi")
    rev_dir = char_dir / "s5-intro" / rev
    state.transition("s5", "RUNNING", rev=rev)
    try:
        _run(ctx, cid, rev, rev_dir, spec, hero, cfg, budget, brief)
    except (CheckFailed, VideoGenerationError, ImageGenerationError) as e:
        ctx.state(cid).transition("s5", "CHECK_FAILED", rev=rev, error=str(e))
        raise
    state = ctx.state(cid)
    state.transition("s5", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G5", "AWAITING_HUMAN", rev, None)
    return rev_dir


def _first_frame(ctx, cid, rev, rev_dir, spec, hero, cfg, budget) -> tuple[dict, dict]:
    """첫 프레임을 rev 폴더에 고정하고 (firstFrame, firstFrameSource)를 돌려준다(D-0031)."""
    hero_ref = {
        "id": spec.referenceImage.id,
        "path": "hero.png",
        "sha256": sha256_file(Path(hero)),
    }
    write_once_bytes(rev_dir / "hero.png", Path(hero).read_bytes())
    if cfg["first_frame"] == "hero":
        write_once_bytes(rev_dir / "first-frame.png", Path(hero).read_bytes())
        source: dict[str, Any] = {"mode": "hero", "hero": hero_ref}
    else:
        ratio_text = str(cfg["aspect_ratio"])
        ratio = ff.parse_ratio(ratio_text)
        prompt = ff.build_prompt(
            ratio_text, subject_phrase(spec.scope), twin=is_twin(ctx.character_dir(cid))
        )
        res = ctx.image_model(cid, budget).generate(
            ImageRequest(
                stage="s5",
                prompt=prompt,
                ref=f"{cid}/{rev}/first-frame",
                negative_prompt=ff.NEGATIVE,
                size=ff.request_size(ratio),
                reference_images=(str(rev_dir / "hero.png"),),
            )
        )
        write_once_bytes(rev_dir / "first-frame-raw.png", res.data)
        try:
            png, raw_size, cropped = ff.crop_to_ratio(res.data, ratio)
        except ValueError as e:
            raise CheckFailed("s5", [str(e)]) from e
        write_once_bytes(rev_dir / "first-frame.png", png)
        source = {
            "mode": "generated",
            "hero": hero_ref,
            "prompt": prompt,
            "negativePrompt": ff.NEGATIVE,
            "provider": res.provider,
            "model": res.model,
            "rawSize": list(raw_size),
            "croppedSize": list(cropped),
        }
    first = {
        "id": "first-frame" if source["mode"] == "generated" else spec.referenceImage.id,
        "path": "first-frame.png",
        "sha256": sha256_file(rev_dir / "first-frame.png"),
    }
    return first, source


def _run(ctx, cid, rev, rev_dir, spec, hero, cfg, budget, brief: ReworkBrief | None = None) -> None:
    video = ctx.video_model(cid, budget)
    video.check_settings(int(cfg["duration"]), str(cfg["resolution"]))  # 첫 프레임을 만들기 전에
    inputs_path = rev_dir / "inputs.json"
    if inputs_path.exists():  # 재개: 첫 프레임과 설정은 처음 고정한 것을 쓴다(다시 만들지 않는다)
        inputs: IntroInputs = validate(  # type: ignore[assignment]
            "intro-inputs-v2", json.loads(inputs_path.read_text("utf-8"))
        )
    else:
        first, source = _first_frame(ctx, cid, rev, rev_dir, spec, hero, cfg, budget)
        plan_rev = (
            ctx.state(cid).gate("G3").rev
            if ctx.state(cid).gate("G3").status == "APPROVED"
            else None
        )
        inputs = validate(  # type: ignore[assignment]
            "intro-inputs-v2",
            {
                "appearanceRev": spec.appearanceRev,
                "planRev": plan_rev,
                "firstFrame": first,
                "firstFrameSource": source,
                "provider": video.name,
                "model": video.model,
                "settings": {
                    "prompt": motion_prompt(brief),
                    "duration": int(cfg["duration"]),
                    "resolution": str(cfg["resolution"]),
                    "aspectRatio": cfg["aspect_ratio"],
                    "generateAudio": bool(cfg["generate_audio"]),
                },
                "candidates": int(cfg["candidates"]),
            },
        )
        write_once_json(inputs_path, dump(inputs))
    settings = dump(inputs.settings)
    first = dump(inputs.firstFrame)
    total = inputs.candidates
    req_base = dict(
        stage="s5",
        prompt=settings["prompt"],
        first_frame=str(rev_dir / "first-frame.png"),
        duration=settings["duration"],
        resolution=settings["resolution"],
        aspect_ratio=settings["aspectRatio"],
        generate_audio=settings["generateAudio"],
    )
    assets: list[VideoAsset] = []
    for n in range(1, total + 1):
        cand = f"v{n}"
        vid = f"vd-{cid}-intro-{rev}-{n}"
        asset_path = rev_dir / "assets" / f"{cand}.json"
        if asset_path.exists():  # 재개: 이미 받은 영상은 다시 만들지 않는다
            assets.append(validate("video-asset-v1", json.loads(asset_path.read_text("utf-8"))))  # type: ignore[arg-type]
            continue
        req = VideoRequest(ref=f"{cid}/{rev}/{cand}", **req_base)
        job_path = rev_dir / "jobs" / f"{cand}.json"
        job: dict[str, Any] | None = None
        if job_path.exists() and video.resumable:
            prev = json.loads(job_path.read_text("utf-8"))
            if prev.get("status") == "SUBMITTED":
                job = prev
        if job is None:
            job_id = video.submit(req)
            job = dump(
                validate(
                    "video-job-v1",
                    {
                        "videoId": vid,
                        "candidateId": cand,
                        "stage": "s5",
                        "provider": video.name,
                        "model": video.model,
                        "jobId": job_id,
                        "status": "SUBMITTED",
                        "settings": settings,
                        "firstFrameSha256": first["sha256"],
                        "estCostUsd": estimate(ctx, cfg | {"candidates": 1}),
                    },
                )
            )
            _write_json(job_path, job)
        try:
            res = video.collect(job["jobId"], req)
        except VideoGenerationError as e:
            if not hasattr(
                e, "job_id"
            ):  # 시간 초과가 아니면 실패로 남긴다. 시간 초과는 SUBMITTED로 두고 이어 받는다
                _write_json(job_path, job | {"status": "FAILED", "error": str(e)[:500]})
            raise
        if res.data[4:8] != b"ftyp":
            _write_json(job_path, job | {"status": "FAILED", "error": "MP4가 아니다"})
            raise VideoGenerationError(f"{cand}: 받은 파일이 MP4가 아니다")
        rel = f"videos/{cand}.mp4"
        write_once_bytes(rev_dir / rel, res.data)
        asset: VideoAsset = validate(  # type: ignore[assignment]
            "video-asset-v1",
            {
                "videoId": vid,
                "candidateId": cand,
                "jobId": res.job_id,
                "provider": res.provider,
                "model": res.model,
                "filePath": rel,
                "fileSha256": sha256_file(rev_dir / rel),
                "bytes": len(res.data),
                "settings": settings,
                "probe": dump(probe_video(rev_dir / rel)),
                "estCostUsd": res.est_cost_usd,
            },
        )
        write_once_json(asset_path, dump(asset))
        _write_json(job_path, job | {"status": "DONE"})
        assets.append(asset)
    write_once_json(rev_dir / "videos.json", [dump(a) for a in assets])
    write_once_text(
        rev_dir / "gate-G5.html",
        render_g5_page(subject_id=cid, rev=rev, inputs=inputs, assets=assets),
    )
    write_manifest(rev_dir)
