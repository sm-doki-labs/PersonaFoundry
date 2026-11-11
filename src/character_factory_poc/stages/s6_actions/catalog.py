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
# 모티브는 배경 하나·같은 옷으로 몸짓만 늘린다(D-0163). 등급은 장면 수가 아니라 몸짓 수로 갈린다.
_MOTIF_PRO = _PRO + (
    "amused_good_strong",
    "expectant_good",
    "admiring_good",
    "grateful_good",
    "rapport_good",
    "surprised_good_strong",
    "wistful_good",
    "dumbfounded_good",
)
# 라이트는 가장 빨리 확인하는 판이다. 몸짓 5개 + 시그니처 포즈 1개 = 6편(D-0167).
# 무표정 대기가 없어 무표정 첫 화면도 만들지 않는다. 앱은 단계당 10편 미만이면 단계를 열지 않으니
# 앱 내보내기에서는 경고가 난다(D-0119). 대화해 보기의 옅은 반응 대체(반가움·피식)는 남는다.
_MOTIF_LIGHT = ("idle_good", "glad_good", "amused_good", "shy_good", "pouty_good")
MOTIF_VIDEO_TIERS = {
    "light": VideoTier(("ch1",), _MOTIF_LIGHT),
    "standard": VideoTier(("ch1",), _PRO),
    "pro": VideoTier(("ch1",), _MOTIF_PRO),
    "max": VideoTier(("ch1",), tuple(CATALOG)),
}


def video_tiers(motif: bool) -> dict[str, VideoTier]:
    return MOTIF_VIDEO_TIERS if motif else VIDEO_TIERS


STAGE_NOTES = {
    "ch1": "Relationship stage 1, getting to know each other: keep the reaction polite, "
    "slightly reserved and smaller.",
    "ch2": "Relationship stage 2, flirting: let a little shy warmth show.",
    "ch3": "Relationship stage 3, dating: warm, relaxed and close.",
}
# 모티브 영상은 연애 단계 문장 대신 일대일 통화 분위기만 붙인다.
MOTIF_STAGE_NOTE = (
    "A friendly one-on-one video call: natural, warm and composed, with small realistic movements."
)


def stage_note(chapter_id: str, *, motif: bool = False) -> str:
    return MOTIF_STAGE_NOTE if motif else STAGE_NOTES[chapter_id]


# 시그니처 포즈(D-0165). 유저가 정한 동작 하나를 모티브의 모든 등급에 한 편씩 더한다.
# 대화 중에는 감정 반응과 같은 후보로 들어가, '이럴 때'를 보고 자동으로 고른다.
SIGNATURE_KEY = "signature_good"


def signature_clip(signature: dict) -> dict:
    title = signature["title"].strip()
    motion = signature["motion"].strip()
    use_when = (signature.get("useWhen") or "").strip()
    return {
        "key": SIGNATURE_KEY,
        "playType": "reaction",
        "mood": "good",
        "title": title,
        "description": motion,
        "useWhen": (
            f"{title} — 이 사람을 대표하는 시그니처 포즈. {use_when}"
            if use_when
            else f"{title} — 이 사람을 대표하는 시그니처 포즈. 반가운 인사, 축하, "
            "자기를 대표하는 순간을 이야기할 때."
        ),
        "motion": (
            f'The person performs their own signature pose, "{title}". '
            f"The pose, described by the user in Korean: {motion} "
            "Make the gesture clear, confident and instantly recognizable, hold it for a beat, "
            "then lower the hands and ease back into the exact gentle smile of the reference "
            "image, holding it calmly to the end. The person is seen from a distance with most of "
            "the body in frame, so make the pose readable through the arms, shoulders and posture "
            "as well as the face. The feet stay planted: no stepping, no walking, no turning "
            "the whole body. The final frame matches the first frame in pose. Perform the "
            "movement at real-life speed — never slow motion."
        ),
        "pickRole": "emotion",
        "actionCategory": None,
    }


def clip_of(key: str, cfg: dict) -> dict:
    """카탈로그 몸짓, 또는 이 캐릭터의 시그니처 포즈."""
    if key == SIGNATURE_KEY:
        return signature_clip(cfg["signature"])
    return CATALOG[key]


def signature_matches(inputs: dict, signature: dict | None) -> bool:
    """만든 영상 입력의 시그니처가 지금 설정과 같은가. 시그니처를 바꾸면 영상을 다시 만든다."""
    actions = [a for ch in inputs.get("chapters", []) for a in ch.get("actions", [])]
    made = next((a for a in actions if a.get("actionKey") == SIGNATURE_KEY), None)
    if not signature:
        return made is None
    want = signature_clip(signature)
    return bool(made) and all(made.get(k) == want[k] for k in ("title", "description", "useWhen"))


NEUTRAL_PROMPT = (
    "Make the same photo as the attached reference — same person, face, hair, pose, hands, "
    "outfit, background, light and framing. Change only the facial expression to a calm neutral "
    "unsmiling expression, relaxed closed lips, eyes open. "
    "The original person is not based on any real individual."
)
NEUTRAL_NEGATIVE = "smile, text, watermark, logo, hand on face"


def neutral_prompt(*, twin: bool = False) -> str:
    """무표정 첫 프레임 지시. 모티브(실존 인물)은 '가상 인물' 문장을 빼고 얼굴 유지만 말한다."""
    if not twin:
        return NEUTRAL_PROMPT
    return NEUTRAL_PROMPT.replace(
        "The original person is not based on any real individual.",
        "Keep the person's identity exactly as in the reference.",
    )


def build_prompt(
    key: str,
    chapter_id: str,
    review_note: str = "",
    *,
    motif: bool = False,
    clip: dict | None = None,
) -> str:
    """앱 움직임 원문에 관계 단계·외형 유지 조건과 사람 수정 메모만 덧붙인다."""
    prompt = (
        f"{(clip or CATALOG[key])['motion']} {stage_note(chapter_id, motif=motif)} "
        "Keep the same person, face, outfit and background as the first frame. "
        "No text, logos or extra people."
    )
    return f"{prompt} Reviewer note: {review_note}" if review_note else prompt
