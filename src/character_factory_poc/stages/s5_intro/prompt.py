"""S5 움직임 프롬프트 (LLD §8.5). 첫 프레임이 인물·옷·배경을 정하므로 움직임과 카메라만 쓴다."""

from __future__ import annotations

MOTION = (
    "Gentle, natural motion starting from the first frame: a slight head turn and a soft smile "
    "toward the camera, subtle hair movement, natural blinking and breathing. Static camera or a "
    "very slow push-in. Keep the same person, face, outfit and background as the first frame. "
    "Hands stay relaxed and away from the face. No text, no logos, no extra people."
)


def build_motion_prompt() -> str:
    return MOTION
