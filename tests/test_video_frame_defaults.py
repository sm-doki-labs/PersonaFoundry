"""Default video route supports explicit frame endpoints; synthetic fixtures only."""

from dataclasses import replace

import pytest

from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.errors import VideoGenerationError
from character_factory_poc.providers.factory import make_video_model
from character_factory_poc.providers.xai_video import XaiVideoModel, estimate_cost
from tests.test_video import _req


@pytest.mark.parametrize("adapter", ["xai_video", "grok_oauth", "grok"])
def test_default_video_model_supports_frame_pins(adapter):
    model = make_video_model(ProviderConfig(adapter=adapter))
    assert model.model == "grok-imagine-video-1.5"


def test_distinct_frame_pins_and_request_preflight(tmp_path):
    req = _req(tmp_path)
    last = tmp_path / "last.png"
    from character_factory_poc.providers.fake_image import solid_png

    last.write_bytes(solid_png(4, 4, (200, 20, 10)))
    req = replace(req, last_frame=str(last))
    body = XaiVideoModel().body(req)
    assert body["image"] != body["last_frame"] and body["resolution"] == "720p"
    with pytest.raises(VideoGenerationError, match="720p"):
        XaiVideoModel().body(replace(req, resolution="1080p"))
    with pytest.raises(VideoGenerationError, match="1.5"):
        XaiVideoModel(model="grok-imagine-video-1.5-lite").body(req)


def test_two_input_images_are_included_in_budget():
    assert estimate_cost("grok-imagine-video-1.5", "720p", 2, input_images=2) == pytest.approx(0.30)
