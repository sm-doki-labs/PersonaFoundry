"""Signature seed: Grok image edit adapter, shared body lock and the camera-click template.

Synthetic data only; no network.
"""

import base64
import io
import json

import pytest

from character_factory_poc.common.errors import ImageGenerationError
from character_factory_poc.providers.base import ImageRequest
from character_factory_poc.providers.xai_images import XAIImageModel
from character_factory_poc.stages.s4_frames import reference
from character_factory_poc.stages.s6_actions import call_loop


def _png(tmp_path, name):
    import cv2
    import numpy as np

    path = tmp_path / name
    cv2.imwrite(str(path), np.full((32, 18, 3), 120, np.uint8))
    return path


def test_edit_request_sends_both_images_and_returns_png(tmp_path, monkeypatch):
    import cv2
    import numpy as np

    monkeypatch.setenv("XAI_API_KEY", "k")
    jpeg = cv2.imencode(".jpg", np.full((32, 18, 3), 90, np.uint8))[1].tobytes()
    sent = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout):
        sent["url"], sent["body"] = req.full_url, json.loads(req.data)
        body = {"data": [{"b64_json": base64.b64encode(jpeg).decode()}]}
        return Resp(json.dumps(body).encode())

    model = XAIImageModel(opener=opener)
    req = ImageRequest(
        stage="s4",
        ref="r",
        prompt="p",
        negative_prompt="n",
        reference_images=(str(_png(tmp_path, "a.png")), str(_png(tmp_path, "b.png"))),
    )
    out = model.generate(req)
    assert sent["url"].endswith("/images/edits")
    assert [i["type"] for i in sent["body"]["images"]] == ["image_url", "image_url"]
    assert sent["body"]["model"] == "grok-imagine-image-2.0"
    assert sent["body"]["prompt"].endswith("Avoid: n")
    assert out.data.startswith(b"\x89PNG") and out.provider == "xai_images"
    with pytest.raises(ImageGenerationError):
        model.generate(ImageRequest(stage="s4", ref="r", prompt="p", reference_images=("x",)))


def test_pose_edit_follows_only_the_reference_photo_and_video_keeps_the_hand_template():
    """D-0220: 참고 사진이 있는 편집 지시에는 글로 쓴 동작·템플릿을 넣지 않는다."""
    click = reference.build_pose_prompt({"template": "camera_click", "motion": "찰칵"})
    other = reference.build_pose_prompt({"template": "custom", "motion": "두 손으로 하트"})
    assert click == other and reference.BODY_LOCK in click
    assert "찰칵" not in click and "두 손으로 하트" not in click and "LEFT eye" not in click
    assert "EXACTLY the same pose as the person in the SECOND image" in click
    assert "wider shoulders" in reference.POSE_NEGATIVE

    cfg = {"signature": {"title": "찰칵", "motion": "m", "template": "camera_click"}}
    clip = call_loop.clip("signature_good", cfg)
    text = call_loop.prompt(clip)
    assert "LEFT eye" in text and call_loop.BODY_LOCK in text
    idle = call_loop.prompt(call_loop.clip("idle_good", cfg))
    assert call_loop.BODY_LOCK in idle  # every clip keeps the body width


def test_master_keeps_source_framing_and_pose_ignores_reference_shot():
    """D-0218: 기준 사진은 원본 구도를 지키고, 시그니처 편집은 참고 사진의 자세만 따른다."""
    master = reference.build_prompt({"wardrobe": "", "background": ""})
    assert "SAME camera distance, framing and crop as the source" in master
    assert "generous space" not in master
    pose = reference.build_pose_prompt({"template": "custom", "motion": "두 손으로 하트"})
    assert "Take ONLY the pose from the SECOND image" in pose
    assert "background, logos and lettering, lighting, camera distance" in pose


def test_signature_clip_follows_the_middle_keyframe_and_motion_is_optional():
    """D-0220: 중간 프레임이 있으면 그 자세가 기준이고, 묘사는 적었을 때만 보탠다."""
    middle = "s4-frames/fr1/ch1/signature-mid.png"
    keyed = {"signature": {"title": "찰칵", "middleFramePath": middle}}
    text = call_loop.clip("signature_good", keyed)["motion"]
    assert "middle keyframe" in text and "Gesture note" not in text
    noted = {"signature": {**keyed["signature"], "motion": "윙크하며 찰칵"}}
    assert "Gesture note: 윙크하며 찰칵." in call_loop.clip("signature_good", noted)["motion"]


def test_start_needs_a_motion_or_a_signature_photo():
    """D-0220: 동작 묘사가 비었으면 시그니처 참고 사진이 있어야 시작할 수 있다."""
    from character_factory_poc.web.sources import summary

    text = {"fileType": "text", "status": "ready", "textId": "a", "problems": []}
    portrait = {"fileType": "photo", "status": "ready", "textId": None, "problems": []}
    pose = portrait | {"photoRole": "signature"}
    draft = {
        "videoTier": "light",
        "signaturePose": {"title": "찰칵", "motion": "", "useWhen": ""},
        "files": [text, portrait],
    }
    problems, ready = summary(draft)
    assert "시그니처 동작을 적거나 시그니처 참고 사진을 올려 주세요." in problems and not ready
    assert summary(draft | {"files": [text, portrait, pose]}) == ([], True)
    written = draft | {"signaturePose": {"title": "찰칵", "motion": "윙크", "useWhen": ""}}
    assert summary(written) == ([], True)


def test_zoomed_signature_frame_is_scaled_back_to_the_master():
    """모델이 인물을 1.2배로 당겨 그려도 얼굴 크기·위치를 기준 사진에 맞춘다.

    빈 가장자리는 기준 사진으로 채운다(D-0218)."""
    import cv2
    import numpy as np

    from character_factory_poc.stages.s4_frames.framing import align_boxes

    h, w = 320, 180
    base = np.zeros((h, w, 3), np.uint8)
    base[:] = (40, 80, 160)
    cv2.rectangle(base, (70, 60), (110, 100), (255, 255, 255), -1)  # 얼굴 40px, 가운데 (90, 80)
    zoom = np.float32([[1.2, 0, 90 - 1.2 * 90], [0, 1.2, 80 - 1.2 * 80]])
    frame = cv2.warpAffine(base, zoom, (w, h))
    out, record = align_boxes(base, frame, (90, 80, 40, 40), (90, 80, 48, 48))
    assert record["applied"] and record["before"] == 1.2
    assert np.abs(out.astype(int) - base.astype(int)).mean() < 3
    same, kept = align_boxes(base, base, (90, 80, 40, 40), (90, 80, 40.4, 40.4))
    assert not kept["applied"] and same is base
    wild, rejected = align_boxes(base, frame, (90, 80, 40, 40), (90, 80, 100, 100))
    assert not rejected["applied"] and wild is frame
