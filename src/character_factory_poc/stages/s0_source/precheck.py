"""순서 11: 기준 사진 편집 한 장과 첫 프레임 영상 한 편으로 공급자 응답을 확인한다."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

from character_factory_poc.common.aspect import crop_to_ratio, request_size
from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ImageRequest, VideoRequest
from character_factory_poc.providers.fake_image import solid_png
from character_factory_poc.providers.xai_video import estimate_cost
from character_factory_poc.stages.s4_frames.prompt import NEGATIVE, build_composite_prompt
from character_factory_poc.stages.s5_intro.prompt import build_motion_prompt

DURATION = 6
MODEL_DEFAULT = {
    ("image", "fake"): "fake-image",
    ("image", "codex_image"): "gpt-6.1-sol",
    ("image", "openai_images"): "gpt-image-2.6-sunburst",
    ("video", "fake"): "fake-video",
    ("video", "grok_web"): "grok-imagine-web",
    ("video", "grok"): "grok-imagine-video-1.5",
    ("video", "grok_oauth"): "grok-imagine-video-1.5",
    ("video", "xai_video"): "grok-imagine-video-1.5",
}
STATUS = {
    "SUCCESS": "완성 파일을 받았어요.",
    "REFUSED": "공급자가 요청을 거절했어요.",
    "SAFETY_BLOCKED": "공급자가 안전 정책으로 차단했어요.",
    "ERROR": "처리하지 못했어요. 거절이나 안전 차단으로 확인되지는 않았어요.",
    "SKIPPED": "첫 프레임을 만들지 못해 영상을 요청하지 않았어요.",
}


def _plan(ctx, kinds, resolution):
    steps = []
    for kind in kinds:
        cfg = ctx.config.provider(kind)
        default = MODEL_DEFAULT.get((kind, cfg.adapter))
        if default is None:
            raise FactoryError(f"{kind} 공급자 설정을 확인해 주세요.")
        model = cfg.model or default
        from character_factory_poc.providers.openai_images import image_cost_estimate

        cost = image_cost_estimate(cfg) if kind == "image" else 0.0
        if cfg.adapter in {"grok", "grok_oauth", "xai_video"}:
            cost = estimate_cost(model, resolution, DURATION, cfg.extra.get("price_per_second"))
        if cost is not None and (not math.isfinite(cost) or cost < 0):
            raise FactoryError("영상 단가를 확인해 주세요.")
        steps.append(
            dict(kind=kind, adapter=cfg.adapter, model=model, estimatedUsd=cost, status="PENDING")
        )
    return steps


def _image_request(folder, photo):
    plate = folder / "background.png"
    plate.write_bytes(solid_png(360, 640, (217, 214, 208)))
    scope = SimpleNamespace(
        appearanceOrigin="unspecified",
        characterGender="any",
        ageRange="current age",
        artStyle="photographic",
    )
    scene = SimpleNamespace(
        place="a plain studio",
        timeOfDay="day",
        mood="soft daylight",
        sceneFacts=["plain warm gray wall"],
        meetingContext="a camera test",
        relationshipCanon=["neutral greeting"],
        sceneBoundaries=["only one person"],
    )
    pose = SimpleNamespace(source="USER", customText="Looking at the camera, hands relaxed.")
    return ImageRequest(
        stage="twin-precheck",
        ref="image",
        size=request_size((9, 16)),
        prompt=build_composite_prompt(SimpleNamespace(scope=scope), scene, pose, twin=True),
        negative_prompt=NEGATIVE,
        reference_images=(str(photo), str(plate)),
    )


def _failure(exc):
    # 원문에는 사진 경로·메시지·인증값이 있을 수 있다. 신호만 분류하고 저장하지 않는다.
    message = str(exc).casefold()
    if re.search(
        r"safety|content[_ -]?(policy|filter|moderation)|moderated|moderation[_ -]?blocked|"
        r"""respect_moderation['"]?\s*:\s*false|policy[_ -]?violation|"""
        r"안전.{0,8}(정책|차단)|콘텐츠 정책",
        message,
    ):
        return "SAFETY_BLOCKED"
    if (
        re.search(
            r"refus(al|ed)|request (denied|rejected)|(?:cannot|unable to) (comply|assist|generate)|"
            r"can['’]t (help|assist|generate)|거절|도와드릴 수 없",
            message,
        )
        and "connection refused" not in message
    ):
        return "REFUSED"
    return "ERROR"


def run_precheck(ctx: Context, photo: Path, *, image: bool, video: bool) -> int:
    kinds = [k for k, use in (("image", image), ("video", video)) if use]
    resolution = ctx.config.stage("s5").get("resolution", "720p")
    steps = _plan(ctx, kinds, resolution)
    cid = f"precheck-{uuid4().hex}" if ctx.execute else "precheck-<실행 ID>"
    folder = ctx.character_dir(cid)
    report = folder / "precheck-result.json"
    budget = ctx.budget()
    print("이미지·영상 사전 확인 계획이에요.")
    for step in steps:
        summary = (
            "기준 얼굴을 유지하고 단색 배경에서 카메라를 봐요."
            if step["kind"] == "image"
            else f"{'편집 이미지' if image else '기준 사진'}에서 시작해 "
            f"{DURATION}초 동안 가볍게 웃어요. {resolution}, 9:16, 무음이에요."
        )
        price = step["estimatedUsd"]
        charge = "미확인" if price is None else f"${price:.2f}"
        print(f"  {step['adapter']} / {step['model']} · 1건 · 예상 {charge}: {summary}")
    print(f"기준 사진: {photo}")
    if all(s["estimatedUsd"] is not None for s in steps):
        print(f"합계: {len(steps)}건 · 예상 추가 비용 ${sum(s['estimatedUsd'] for s in steps):.2f}")
    if any(s["adapter"] in {"codex_image", "grok_web"} for s in steps):
        print("구독 경로의 추가 비용은 0달러로 추정해요. 구독 사용량은 소모돼요.")
    print(f"명령 상한: {budget.max_calls}회 / ${budget.config.max_cost_usd_per_command:.2f}")
    print(f"저장 위치: {report} (실행마다 새 폴더를 만들어요.)")
    if not ctx.execute:
        print("계획만 확인했어요. 승인한 뒤 --execute를 붙여 주세요.")
        return 0
    if any(s["estimatedUsd"] is None for s in steps):
        raise FactoryError(
            "예상 비용이 미확인이에요. 이미지 estimated_cost_usd 또는 영상 단가표를 확인해 주세요."
        )
    if not math.isfinite(budget.config.max_cost_usd_per_command):
        raise FactoryError("명령 비용 상한을 유한한 금액으로 정해 주세요.")
    budget.check_plan([CallPlan(s["kind"], "", 1, s["estimatedUsd"]) for s in steps])
    photo = photo.resolve()
    if not photo.is_file():
        raise FactoryError("기준 사진 파일을 찾지 못했어요.")
    with photo.open("rb") as fh:
        if not fh.read(8).startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
            raise FactoryError("기준 사진은 PNG 또는 JPEG로 준비해 주세요.")
    payload = dict(
        schemaVersion="twin-precheck-result-v1", photoSha256=sha256_file(photo), steps=steps
    )
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)

    def save():
        tmp = report.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
        tmp.replace(report)

    first = photo
    ok = True
    save()
    for step in steps:
        kind = step["kind"]
        if not ok:
            step["status"] = "SKIPPED"
        else:
            start = monotonic()
            step["status"] = "STARTED"
            save()
            try:
                if kind == "image":
                    request = _image_request(folder, photo)
                    result = ctx.image_model(cid, budget).generate(request)
                    data, _, _ = crop_to_ratio(result.data, (9, 16))
                    first = folder / "first-frame.png"
                    first.write_bytes(data)
                    artifact = first
                else:
                    model = ctx.video_model(cid, budget)
                    model.check_settings(DURATION, resolution)
                    request = VideoRequest(
                        stage="twin-precheck",
                        ref="video",
                        prompt=build_motion_prompt(),
                        first_frame=str(first),
                        duration=DURATION,
                        resolution=resolution,
                        aspect_ratio="9:16",
                        generate_audio=False,
                    )
                    job = model.submit(request)
                    step["jobId"] = job
                    save()
                    result = model.collect(job, request)
                    if result.data[4:8] != b"ftyp":
                        raise ValueError("MP4 파일을 받지 못했어요.")
                    artifact = folder / "clip.mp4"
                    artifact.write_bytes(result.data)
                step.update(
                    status="SUCCESS",
                    artifact=artifact.name,
                    provider=result.provider,
                    returnedModel=result.model,
                )
            except Exception as exc:
                step.update(status=_failure(exc), errorType=type(exc).__name__)
                ok = False
            step["elapsedSeconds"] = round(monotonic() - start, 3)
        save()
        print(f"{kind}: {STATUS[step['status']]}")
    return int(not ok)
