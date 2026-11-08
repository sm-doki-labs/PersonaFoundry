"""앱 통화 클립과 관계 단계 메모로 만드는 결정론적 S6 프롬프트다(D-0040, D-0041)."""

from __future__ import annotations

from dataclasses import dataclass

from character_factory_poc.stages.s6_actions.app_clips import APP_CLIPS

CATALOG = {
    clip["key"]: clip
    | {
        "pickRole": None if clip["playType"] == "idle" else "emotion",
        "actionCategory": None,
    }
    for clip in APP_CLIPS
}
PRESETS = {
    "l2": ["idle_good", "idle_bad", "glad_good", "amused_good", "shy_good", "sorry_good"],
    "full37": list(CATALOG),
}


@dataclass(frozen=True)
class VideoTier:
    chapters: tuple[str, ...]
    actions: tuple[str, ...]


ALL_CHAPTERS = ("ch1", "ch2", "ch3")
_CORE = (
    "idle_good",
    "idle_bad",
    "glad_good",
    "amused_good",
    "shy_good",
    "sorry_good",
    "pouty_good",
    "surprised_good",
    "sad_good",
    "displeased_good",
)
_PRO = _CORE + (
    "affection_good",
    "flutter_good",
    "playful_good",
    "worried_good",
    "hurt_good",
    "sympathy_good",
    "curious_good",
    "joy_good",
    "sheepish_good",
    "angry_bad",
)
VIDEO_TIERS = {
    "light": VideoTier(("ch1",), _CORE),
    "standard": VideoTier(ALL_CHAPTERS, _CORE),
    "pro": VideoTier(ALL_CHAPTERS, _PRO),
    "max": VideoTier(ALL_CHAPTERS, tuple(CATALOG)),
}

STAGE_NOTES = {
    "ch1": "Relationship stage 1, getting to know each other: keep the reaction polite, "
    "slightly reserved and smaller.",
    "ch2": "Relationship stage 2, flirting: let a little shy warmth show.",
    "ch3": "Relationship stage 3, dating: warm, relaxed and close.",
}
NEUTRAL_PROMPT = (
    "Make the same photo as the attached reference — same person, face, hair, pose, hands, "
    "outfit, background, light and framing. Change only the facial expression to a calm neutral "
    "unsmiling expression, relaxed closed lips, eyes open. "
    "The original person is not based on any real individual."
)
NEUTRAL_NEGATIVE = "smile, text, watermark, logo, hand on face"


def neutral_prompt(*, twin: bool = False) -> str:
    """무표정 첫 프레임 지시. 트윈(실존 인물)은 '가상 인물' 문장을 빼고 얼굴 유지만 말한다."""
    if not twin:
        return NEUTRAL_PROMPT
    return NEUTRAL_PROMPT.replace(
        "The original person is not based on any real individual.",
        "Keep the person's identity exactly as in the reference.",
    )


def build_prompt(key: str, chapter_id: str, review_note: str = "") -> str:
    """앱 움직임 원문에 관계 단계·외형 유지 조건과 사람 수정 메모만 덧붙인다."""
    prompt = (
        f"{CATALOG[key]['motion']} {STAGE_NOTES[chapter_id]} "
        "Keep the same person, face, outfit and background as the first frame. "
        "No text, logos or extra people."
    )
    return f"{prompt} Reviewer note: {review_note}" if review_note else prompt
