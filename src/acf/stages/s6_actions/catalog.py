"""앱 통화 클립과 관계 단계 메모로 만드는 결정론적 S6 프롬프트다(D-0040, D-0041)."""

from __future__ import annotations

from acf.stages.s6_actions.app_clips import APP_CLIPS

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
    "standard": [clip["key"] for clip in APP_CLIPS],
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


def build_prompt(key: str, chapter_id: str, review_note: str = "") -> str:
    """앱 움직임 원문에 관계 단계·외형 유지 조건과 사람 수정 메모만 덧붙인다."""
    prompt = (
        f"{CATALOG[key]['motion']} {STAGE_NOTES[chapter_id]} "
        "Keep the same person, face, outfit and background as the first frame. "
        "No text, logos or extra people."
    )
    return f"{prompt} Reviewer note: {review_note}" if review_note else prompt
