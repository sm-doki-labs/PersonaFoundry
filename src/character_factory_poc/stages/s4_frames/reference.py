"""Opt-in SOURCE Lite master image from the full, approved S2 photograph.

The plan supplies lineage only. One generation is published for human G4 review;
no scene plates, face crop, automatic visual verdict or retry generation is used.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from character_factory_poc.common.aspect import crop_to_ratio, request_size
from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import CheckFailed, FactoryError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.source_store import inside
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_bytes,
    write_once_json,
    write_once_text,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import (
    read_reference_image,
    read_signature,
    reference_image_enabled,
)
from character_factory_poc.providers.base import ImageRequest
from character_factory_poc.stages.s2_hero.approve import load_appearance_spec
from character_factory_poc.stages.s3_plan.importer import load_approved_plan_v2
from character_factory_poc.stages.s4_frames.page import render_g4_page

SCHEMA = "reference-image-inputs-v1"
NEGATIVE = (
    "multiple people, duplicate person, changed identity, altered facial features, "
    "cropped head, cropped elbows, cropped hands, extra fingers, extra limbs, "
    "raised hands, waving, props in hands, open mouth, added text or watermark"
)


def build_prompt(settings: dict) -> str:
    wardrobe = (
        "Use exactly this requested wardrobe: " + settings["wardrobe"]
        if settings["wardrobe"]
        else "Preserve the exact wardrobe in the source photograph, including colors and details."
    )
    background = (
        "Use exactly this requested background: " + settings["background"]
        if settings["background"]
        else "Preserve the exact background in the source photograph, including colors and details."
    )
    return "\n".join(
        [
            "Create one photographic 9:16 vertical master image of exactly one person, "
            "using the full attached source photograph as the identity reference.",
            "Preserve the same person's identity, facial features, age, skin tone, hair, "
            "body proportions and distinctive details. Do not beautify or redesign the person.",
            wardrobe,
            background,
            "Standard neutral reusable pose: standing upright, facing the camera directly, "
            "both hands clasped behind the back, relaxed shoulders, "
            "and a slight closed-mouth smile. "
            "Hands stay naturally behind the torso; do not invent visible hands in front.",
            # D-0218: 원본보다 넓게 다시 그리면 같은 날 찍은 시그니처 사진과 구도가 달라져
            # 중간 프레임에서 화면이 당겨졌다(2026-11-13 손흥민2).
            "Keep the SAME camera distance, framing and crop as the source photograph: the "
            "person's head and body stay the same size and in the same place in the frame. "
            "Do not zoom out, do not add extra space around the person and do not zoom in. "
            "Only if the source is not 9:16, extend or trim the background at the edges.",
            "Keep all unrequested identity, wardrobe and background details unchanged. "
            "No second person, duplicate body, added text or watermark.",
        ]
    )


POSE_NEGATIVE = (
    "different person, changed identity, changed face, changed hair, changed clothing, "
    "changed background, copied background from the pose photo, second person, duplicate body, "
    "wider shoulders, wider or bulkier torso, changed body width or proportions, zoomed in, "
    "re-framed or cropped differently from the first image, "
    "camera or phone or any object in hands, extra fingers, missing fingers, fused hands, "
    "face hidden by hands, cropped head, cropped hands, added text or watermark"
)
SIGNATURE_FRAME = "signature-frame.json"
SIGNATURE_AT_S = 2.0
#: 중간 프레임 인물 크기가 어긋날 때 다시 만드는 횟수까지 합친 최대 생성 수(D-0210).
SIGNATURE_ATTEMPTS = 3
# Shared by every signature pose: the seed must keep the master's body, or the video visibly
# widens and narrows as it passes through the seed (Son 2026-11-12: torso 1.08-1.14x).
BODY_LOCK = (
    "Keep his or her BODY SHAPE exactly as in the first image: the same shoulder width, torso "
    "width, chest, arm thickness and body proportions. Do not make the body, shoulders or chest "
    "wider or narrower. Do not zoom, crop or re-frame; the head and torso stay the same size "
    "and in the same place in the frame."
)
# Signature templates with an exact hand description. The user's free-text motion is used
# for every other gesture.
POSE_TEMPLATES = {
    "camera_click": (
        "The hands are completely EMPTY. Both hands are up close to the face. Each hand makes "
        'an "L" with thumb and index finger: the right hand at the upper left, index finger '
        "pointing straight across just above the eyebrows, thumb pointing down beside the "
        "cheek; the left hand at the lower right, index finger pointing straight across under "
        "the nose at mouth level, thumb pointing up beside the eye. Together the two L's make a "
        "small tight rectangular frame around the eyes, like a viewfinder held close to the "
        "face. The person looks through the frame straight at the lens and closes the LEFT eye "
        "in a playful wink while the right eye stays open, mouth slightly open in a grin."
    ),
}


def build_pose_prompt(signature: dict) -> str:
    """Redraw only the gesture from the user's pose photo onto the approved master image.

    D-0220: 참고 사진이 있으면 글로 쓴 동작 묘사·템플릿을 넣지 않는다. 묘사와 사진이 함께 있으면
    모델이 둘을 섞어 사진 자세를 덜 따르고, 배경·구도 고정 지시도 흐려졌다(2026-11-13 손흥민).
    """
    return "\n".join(
        [
            "Edit the FIRST attached image.",
            "Make the person in the FIRST image take EXACTLY the same pose as the person in the "
            "SECOND image: the same arms, hands, fingers, head angle and facial expression.",
            "Everything else stays exactly as in the FIRST image: the same person, face, hair, "
            "clothing, body shape, background, logos and lettering, lighting, camera distance, "
            "framing, and the person's size and position in the frame.",
            BODY_LOCK,
            "Take ONLY the pose from the SECOND image; do not copy its background, framing, "
            "zoom, crop, lighting, clothing or text. Do not zoom, crop or move the camera.",
            "Hands are empty with five natural fingers each. Exactly one person.",
        ]
    )


def _pose_reference(folder: Path) -> tuple[Path, dict] | None:
    signature = read_signature(folder) or {}
    rel = signature.get("poseReferencePath")
    if not rel:
        return None
    try:
        path = inside(folder, rel)
    except ValueError as exc:
        raise CheckFailed("s4", ["시그니처 참고 사진 경로가 안전하지 않다"]) from exc
    if not path.is_file():
        raise CheckFailed("s4", ["시그니처 참고 사진을 찾지 못했다"])
    return path, signature


def plan_calls(ctx: Context, cid: str | None = None) -> list[CallPlan]:
    from character_factory_poc.providers.openai_images import image_cost_estimate

    cost = image_cost_estimate(ctx.config.provider("image"))
    calls = [CallPlan("s4", "승인한 전체 사진으로 9:16 기준 이미지 한 장 생성", 1, cost)]
    pose = _pose_reference(ctx.character_dir(cid)) if cid else None
    if pose and pose[1].get("poseUse") != "frame":
        calls.append(
            CallPlan("s4", "기준 이미지에 시그니처 동작을 입힌 중간 프레임 한 장 생성", 1, cost)
        )
    return calls


def _current_inputs(ctx: Context, cid: str) -> tuple[dict, Path, str]:
    folder = ctx.character_dir(cid)
    if not reference_image_enabled(folder):
        raise FactoryError("기준 이미지 생성은 referenceImage를 지정한 모티브 Lite에서만 쓴다")
    state = ctx.state(cid)
    state.require_deps("s4")
    appearance, source = load_appearance_spec(ctx, cid)
    plan, _ = load_approved_plan_v2(ctx, cid)
    if state.gate("G1s").rev != appearance.appearanceRev:
        raise CheckFailed("s4", ["G1s 승인과 기준 사진 revision이 다르다"])
    settings = read_reference_image(folder)
    digest = sha256_file(source)
    if digest != appearance.referenceImage.sha256:
        raise CheckFailed("s4", ["승인한 기준 사진의 해시가 다르다"])
    pose = _pose_reference(folder)
    extra = {}
    if pose:
        pose_path, signature = pose
        use = "frame" if signature.get("poseUse") == "frame" else "reference"
        extra["signaturePose"] = {
            "path": "reference/pose" + pose_path.suffix.lower(),
            "sha256": sha256_file(pose_path),
            "title": signature.get("title", ""),
            "motion": signature.get("motion", ""),
            "middleFrameAtS": SIGNATURE_AT_S,
            "use": use,
            "prompt": build_pose_prompt(signature) if use == "reference" else "",
            "negativePrompt": POSE_NEGATIVE if use == "reference" else "",
        }
    return (
        {
            "schemaVersion": SCHEMA,
            "appearanceRev": appearance.appearanceRev,
            "planRev": plan.planRev,
            "sourceSha256": digest,
            "referenceImage": {
                "id": appearance.referenceImage.id,
                "path": "reference/source.png",
                "sha256": digest,
            },
            "referenceCrop": "full",
            "aspectRatio": "9:16",
            "wardrobe": settings["wardrobe"],
            "background": settings["background"],
            "prompt": build_prompt(settings),
            "negativePrompt": NEGATIVE,
        }
        | extra,
        source,
        plan.name,
    )


def matches_reference_inputs(ctx: Context, cid: str, rev: str | None) -> bool:
    """Only reuse the same frozen settings, approved lineage and unchanged full source."""
    if not rev or not rev.startswith("fr") or not rev[2:].isdigit():
        return False
    try:
        expected, _, _ = _current_inputs(ctx, cid)
        folder = ctx.character_dir(cid) / "s4-frames" / rev
        stored = read_json(folder / "inputs.json")
        pose = expected.get("signaturePose")
        return (
            stored == expected
            and sha256_file(folder / "reference/source.png") == expected["sourceSha256"]
            and (not pose or sha256_file(folder / pose["path"]) == pose["sha256"])
        )
    except (FactoryError, OSError, ValueError, KeyError, TypeError):
        return False


def run_reference(ctx: Context, cid: str) -> Path:
    state = ctx.state(cid)
    state.require_deps("s4")
    budget = ctx.budget()
    budget.check_plan(plan_calls(ctx, cid))
    parent = ctx.character_dir(cid) / "s4-frames"
    rev = next_rev(parent, "fr")
    folder = parent / rev
    state.transition("s4", "RUNNING", rev=rev)
    try:
        inputs, source, name = _current_inputs(ctx, cid)
        # Plain JSON deliberately does not pretend to be the scene-composite input contract.
        write_once_json(folder / "inputs.json", inputs)
        reference = folder / inputs["referenceImage"]["path"]
        write_once_bytes(reference, source.read_bytes())
        if sha256_file(reference) != inputs["sourceSha256"]:
            raise CheckFailed("s4", ["기준 사진을 고정하는 동안 원본이 변경됐다"])
        request = ImageRequest(
            stage="s4",
            ref=f"{cid}/{rev}/ch1-f1",
            prompt=inputs["prompt"],
            negative_prompt=NEGATIVE,
            size=request_size((9, 16)),
            reference_images=(str(reference),),
        )
        result = ctx.image_model(cid, budget).generate(request)
        try:
            data, _, _ = crop_to_ratio(result.data, (9, 16))
        except ValueError as exc:
            raise CheckFailed("s4", [str(exc)]) from exc
        relative = "ch1/f1.png"
        write_once_bytes(folder / relative, data)
        frame = validate(
            "chapter-frame-v1",
            {
                "frameId": "ch1-f1",
                "chapterId": "ch1",
                "appearanceRev": inputs["appearanceRev"],
                "planRev": inputs["planRev"],
                "prompt": request.prompt,
                "negativePrompt": NEGATIVE,
                "model": result.model,
                "provider": result.provider,
                "settings": {
                    "size": request.size,
                    "aspectRatio": "9:16",
                    "inputSchema": SCHEMA,
                },
                "filePath": relative,
                "fileSha256": sha256_file(folder / relative),
                "qa": None,
            },
        )
        write_once_json(folder / "frames.json", [dump(frame)])
        pose_html = ""
        if inputs.get("signaturePose"):
            pose_html = _signature_seed(ctx, cid, rev, folder, inputs, relative, budget)
        # Presentation-only adapter keeps the existing G4 page/answer contract unchanged.
        page_inputs = SimpleNamespace(
            appearanceRev=inputs["appearanceRev"],
            sceneRev="기준 이미지",
            referenceImage=SimpleNamespace(path=inputs["referenceImage"]["path"]),
            identityReference=SimpleNamespace(path=inputs["referenceImage"]["path"]),
            referenceCrop="full",
            cropNote="승인한 전체 사진 참조. 얼굴·복장·배경·손·구도는 사람이 확인한다.",
        )
        page = render_g4_page(
            subject_id=cid, rev=rev, inputs=page_inputs, frames=[frame], name=name
        )
        if pose_html:
            page = page.replace("<fieldset>", pose_html + "<fieldset>", 1)
        write_once_text(folder / "gate-G4.html", page)
        write_manifest(folder)
    except Exception as exc:
        ctx.state(cid).transition("s4", "CHECK_FAILED", rev=rev, error=str(exc))
        raise
    state = ctx.state(cid)
    state.transition("s4", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G4", "AWAITING_HUMAN", rev, None)
    return folder


def _signature_seed(ctx, cid, rev, folder, inputs, base_rel, budget) -> str:
    """Second image: the generated master with only the user's signature gesture applied."""
    from html import escape

    pose = inputs["signaturePose"]
    source, _ = _pose_reference(ctx.character_dir(cid))
    copy = folder / pose["path"]
    write_once_bytes(copy, source.read_bytes())
    if sha256_file(copy) != pose["sha256"]:
        raise CheckFailed("s4", ["시그니처 참고 사진을 고정하는 동안 원본이 변경됐다"])
    from character_factory_poc.stages.s4_frames.framing import align_to_base, distance, face_scale

    if pose.get("use") == "frame":
        return _signature_as_is(folder, pose, copy, base_rel)

    # D-0210: 인물이 기준 사진보다 커지거나 작아지면 영상이 2초에 확대됐다 돌아온다.
    # 얼굴 크기 비율이 범위를 벗어나면 최대 두 번 더 만들고 가장 가까운 것을 쓴다.
    tries: list[dict] = []
    for attempt in range(1, SIGNATURE_ATTEMPTS + 1):
        request = ImageRequest(
            stage="s4",
            ref=f"{cid}/{rev}/ch1-sig" + (f"-try{attempt}" if attempt > 1 else ""),
            prompt=pose["prompt"],
            negative_prompt=pose["negativePrompt"],
            size=request_size((9, 16)),
            reference_images=(str(folder / base_rel), str(copy)),
        )
        result = ctx.signature_image_model(cid, budget).generate(request)
        try:
            data, _, _ = crop_to_ratio(result.data, (9, 16))
        except ValueError as exc:
            raise CheckFailed("s4", [str(exc)]) from exc
        # D-0218: 모델이 지시와 달리 당겨 그려도 얼굴 크기·위치를 기준 사진에 맞춘다.
        data, aligned = align_to_base(folder / base_rel, data)
        candidate = f"ch1/signature-mid-try{attempt}.png"
        write_once_bytes(folder / candidate, data)
        check = face_scale(folder / base_rel, folder / candidate)
        check["aligned"] = aligned
        tries.append({"path": candidate, "data": data, "result": result, "framing": check})
        if check["ok"] is not False:
            break
    best = min(tries, key=lambda t: distance(t["framing"]))
    data, result, framing = best["data"], best["result"], best["framing"]
    relative = "ch1/signature-mid.png"
    write_once_bytes(folder / relative, data)
    write_once_json(
        folder / SIGNATURE_FRAME,
        {
            "frameId": "ch1-sig",
            "baseFramePath": base_rel,
            "baseFrameSha256": sha256_file(folder / base_rel),
            "poseReference": {"path": pose["path"], "sha256": pose["sha256"]},
            "filePath": relative,
            "fileSha256": sha256_file(folder / relative),
            "middleFrameAtS": pose["middleFrameAtS"],
            "prompt": request.prompt,
            "negativePrompt": request.negative_prompt,
            "model": result.model,
            "provider": result.provider,
            "framing": framing,
            "attempts": [{"path": t["path"], "framing": t["framing"]} for t in tries],
        },
    )
    warning = ""
    if framing["ok"] is False:
        warning = (
            f'<p class="warn">중간 프레임의 인물 크기가 기준 사진의 {framing["scale"]:.2f}배예요. '
            "영상이 2초에 확대·축소돼 보일 수 있어요. 다시 만들기를 권해요.</p>"
        )
    return (
        '<fieldset><legend>시그니처 중간 프레임</legend><div class="scene">'
        f'<img class="frame" src="{escape(relative)}" '
        'alt="기준 이미지에 시그니처 동작을 입힌 중간 프레임">'
        f'<img class="ref" src="{escape(pose["path"])}" alt="업로드한 동작 참고 사진">'
        "</div><p>얼굴·복장·배경은 기준 이미지와 같고 동작만 참고 사진을 따라야 해요.</p>"
        + warning
        + "</fieldset>"
    )


def _signature_as_is(folder: Path, pose: dict, copy: Path, base_rel: str) -> str:
    """D-0221: 올린 사진을 편집 없이 중간 프레임으로 쓴다. 9:16 비율과 기준 사진 크기만 맞춘다."""
    from html import escape

    import cv2
    import numpy as np

    from character_factory_poc.stages.s4_frames.framing import face_scale

    try:
        data, _, _ = crop_to_ratio(copy.read_bytes(), (9, 16))
    except ValueError as exc:
        raise CheckFailed("s4", [f"시그니처 사진을 9:16으로 맞추지 못했다: {exc}"]) from exc
    base = cv2.imread(str(folder / base_rel))
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if base is not None and frame is not None and frame.shape[:2] != base.shape[:2]:
        size = (base.shape[1], base.shape[0])
        frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
        data = cv2.imencode(".png", frame)[1].tobytes()
    relative = "ch1/signature-mid.png"
    write_once_bytes(folder / relative, data)
    framing = face_scale(folder / base_rel, folder / relative)
    write_once_json(
        folder / SIGNATURE_FRAME,
        {
            "frameId": "ch1-sig",
            "baseFramePath": base_rel,
            "baseFrameSha256": sha256_file(folder / base_rel),
            "poseReference": {"path": pose["path"], "sha256": pose["sha256"]},
            "filePath": relative,
            "fileSha256": sha256_file(folder / relative),
            "middleFrameAtS": pose["middleFrameAtS"],
            "use": "frame",
            "prompt": "",
            "negativePrompt": "",
            "model": "upload",
            "provider": "upload",
            "framing": framing,
            "attempts": [],
        },
    )
    warning = ""
    if framing["ok"] is False:
        warning = (
            f'<p class="warn">올린 사진의 인물 크기가 기준 사진의 {framing["scale"]:.2f}배예요. '
            "영상이 2초에 확대·축소돼 보일 수 있어요.</p>"
        )
    return (
        '<fieldset><legend>시그니처 중간 프레임</legend><div class="scene">'
        f'<img class="frame" src="{escape(relative)}" alt="올린 사진을 그대로 쓴 중간 프레임">'
        "</div><p>올린 사진을 편집하지 않고 그대로 영상 중간 장면으로 써요.</p>"
        + warning
        + "</fieldset>"
    )


def read_signature_frame(rev_dir: Path) -> dict | None:
    """Verified generated signature seed for an fr revision, or None when not requested."""
    path = rev_dir / SIGNATURE_FRAME
    if not path.exists():
        return None
    record = read_json(path)
    if sha256_file(rev_dir / record["filePath"]) != record["fileSha256"]:
        raise CheckFailed("s4", ["시그니처 중간 프레임이 생성 기록과 다르다"])
    return record
