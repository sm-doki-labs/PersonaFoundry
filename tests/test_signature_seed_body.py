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


def test_body_lock_is_shared_and_camera_click_uses_the_hand_template():
    click = reference.build_pose_prompt({"template": "camera_click", "motion": "찰칵"})
    other = reference.build_pose_prompt({"template": "custom", "motion": "두 손으로 하트"})
    assert reference.BODY_LOCK in click and reference.BODY_LOCK in other
    assert "LEFT eye" in click and "찰칵" not in click
    assert "두 손으로 하트" in other and "LEFT eye" not in other
    assert "wider shoulders" in reference.POSE_NEGATIVE

    cfg = {"signature": {"title": "찰칵", "motion": "m", "template": "camera_click"}}
    clip = call_loop.clip("signature_good", cfg)
    text = call_loop.prompt(clip)
    assert "LEFT eye" in text and call_loop.BODY_LOCK in text
    idle = call_loop.prompt(call_loop.clip("idle_good", cfg))
    assert call_loop.BODY_LOCK in idle  # every clip keeps the body width
