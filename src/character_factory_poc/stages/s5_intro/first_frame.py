"""S5 세로 첫 프레임 (D-0031). 쇼츠용 9:16 영상의 첫 장면을 G2 대표 이미지에서 새로 만든다.

이미지→영상은 입력 이미지의 비율을 따른다. 정사각형 대표 이미지를 그대로 넣으면
정사각형 영상이 나오므로, 대표 이미지를 같은 사람의 참조로 붙여 세로 사진을 한 장 만들고
가운데를 기준으로 정확한 비율로 자른다. 비율 도구는 character_factory_poc.common.aspect에 있다.
"""

from __future__ import annotations

from character_factory_poc.common.aspect import (
    MAX_RATIO_DRIFT,
    crop_to_ratio,
    parse_ratio,
    request_size,
)

__all__ = [
    "MAX_RATIO_DRIFT",
    "NEGATIVE",
    "PROMPT",
    "build_prompt",
    "crop_to_ratio",
    "parse_ratio",
    "request_size",
]

PROMPT = (
    "Vertical {ratio} smartphone short-form video opening frame of the same {subject} "
    "as the attached reference image. Keep the same face shape, eyes, nose, lips, skin "
    "tone, hair color and hairstyle, the same outfit and the same backdrop and light. Recompose "
    "as a tall portrait frame: waist-up medium shot, subject centered, eye line in the upper "
    "third, natural headroom, backdrop extended above and below. Relaxed neutral pose facing the "
    "camera, both hands lowered and out of the face area. Natural skin texture, sharp focus on "
    "the eyes, photoreal, shot on a full-frame camera with a 50mm lens. An original person, not "
    "based on any real individual."
)
# 모티브(실존 인물)은 '가상 인물' 문구 대신 기준 사진의 얼굴을 그대로 지키라고만 한다.
TWIN_TAIL = (
    "Keep the person's identity exactly as in the reference image; do not change their face "
    "or make them resemble anyone else."
)
NEGATIVE = "text, watermark, logo, hand on face, chin resting on hand"


def build_prompt(ratio_text: str, subject: str = "Korean woman", *, twin: bool = False) -> str:
    """subject는 외모 명세의 인물 인상·성별(예: "Korean man"). 예전에는 여성으로 고정돼 있었다."""
    prompt = PROMPT.format(ratio=ratio_text, subject=subject if twin else f"fictional {subject}")
    if twin:
        prompt = prompt.replace(
            " An original person, not based on any real individual.", " " + TWIN_TAIL
        )
    return prompt
