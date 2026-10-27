"""S2 기준 사진 프롬프트 (LLD §8.2, D-0043).

외모군 공통 특징·비교 범위만 쓰고 이름은 넣지 않는다(FR-35).
"""

from __future__ import annotations

from typing import Any

from character_factory_poc.contracts.reference import AppearanceCluster, RankingScope
from character_factory_poc.stages.s1_reference.preview import appearance_parts, subject_phrase

NEGATIVE = "text, watermark, logo, blur, plastic skin, hand on face, chin resting on hand"
IDENTITY = (
    "Use the attached reference image(s) as the identity reference: keep the same face shape, "
    "eyes, nose, lips, skin tone, hair color and hairstyle so it clearly reads as the same "
    "fictional person."
)
PHOTO = (
    "Upper body, three-quarter angle, plain studio backdrop, directional window light from the "
    "left with gentle shadows. Natural skin texture with visible pores, no airbrushing, "
    "individual hair strands clearly resolved, sharp focus on the eyes, shot on a full-frame "
    "camera with an 85mm lens at f/2. Keep both hands away from the face; do not rest the chin "
    "on the hand."
)


def build_hero_prompt(
    cluster: AppearanceCluster,
    scope: RankingScope,
    vocab: dict[str, Any],
    has_references: bool = True,
) -> str:
    parts = [
        f"Reference portrait photograph of a fictional {subject_phrase(scope)} "
        f"in their {scope.ageRange}, {scope.artStyle} style."
    ]
    if has_references:
        parts.append(IDENTITY)
    # 사람이 고른 참조 사진이 외형의 기준이다. 외형 태그를 같이 주면 모델이 글을 따라
    # 머리색·머리 모양을 바꿨다(2026-10-21 실제 호출). 참조가 있으면 스타일링·분위기만 준다(D-0023).
    parts += appearance_parts(cluster, vocab, include_looks=not has_references)
    parts.append(PHOTO)
    parts.append("An original person, not based on any real individual.")
    return " ".join(parts)
