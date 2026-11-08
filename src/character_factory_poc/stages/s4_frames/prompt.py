"""S4 합성 프롬프트. 얼굴·배경·자세의 참조 범위를 분리한다(D-0027, D-0034)."""

from character_factory_poc.stages.s1_reference.preview import subject_phrase

NEGATIVE = (
    "text, watermark, logo, blur, plastic skin, extra people in focus, "
    "hand on face, chin resting on hand"
)
# 기준 사진의 자세가 새 장면에 섞이지 않게 명시한다(D-0027).
POSE = (
    "Use the reference only for identity, not for pose, outfit or background; "
    "follow the scene and composition below."
)
HANDS = (
    "Hands: follow the composition; if it does not say what the hands do, keep them relaxed "
    "and away from the face — do not rest the chin or cheek on a hand and do not touch the face."
)


# 모티브는 실존 인물이 기준 사진에 있다. '가상 인물'이라고 적으면 기준 사진과 어긋난 얼굴을 만든다.
TWIN_IDENTITY = (
    "Keep the person's identity exactly as in reference image 1; do not change their face "
    "or make them resemble anyone else."
)
ORIGINAL_IDENTITY = "An original person, not based on any real individual."


def build_composite_prompt(
    appearance, scene, pose, job: str = "", revision_note: str = "", *, twin: bool = False
) -> str:
    scope = appearance.scope
    subject = (
        f"the {subject_phrase(scope)} shown in reference image 1"
        if twin
        else f"a fictional {subject_phrase(scope)}"
    )
    parts = [
        f"Cinematic still photograph of {subject} "
        f"in their {scope.ageRange}, {scope.artStyle} style.",
        "Reference image 1 is the identity reference: use its face for identity only.",
        POSE,
        "Reference image 2 is the empty background plate: keep the same place, light and layout.",
        f"Scene: {scene.place}. Time: {scene.timeOfDay}. Light and color: {scene.mood}.",
        "Scene facts: " + "; ".join(scene.sceneFacts) + ".",
        f"Meeting context: {scene.meetingContext}.",
        "Relationship canon: " + "; ".join(scene.relationshipCanon) + ".",
        "Scene boundaries: " + "; ".join(scene.sceneBoundaries) + ".",
        f"Occupation context: {job}.",
    ]
    if pose.source == "USER":
        parts.append(f"User-defined pose, outfit and expression: {pose.customText}.")
    else:
        parts.extend(
            [
                f"Body: {pose.body}. Hands: {pose.hands}. Props: {pose.props}.",
                f"Gaze: {pose.gaze}. Expression: {pose.expression}. Outfit: {pose.outfit}.",
                f"Composition: {pose.shot}. Next natural movement: {pose.motionHint}.",
            ]
        )
    parts.extend(
        [
            HANDS,
            "Vertical 9:16 framing, suitable as the first frame of an animated video.",
            "Natural skin texture, sharp focus on the face, realistic photographic light.",
            TWIN_IDENTITY if twin else ORIGINAL_IDENTITY,
        ]
    )
    if revision_note:
        parts.append(f"Revision note: {revision_note}")
    return " ".join(parts)


def composite_context(scene, pose) -> str:
    """판정에는 장면 요약과 선택한 자세·의상·표정을 주고 생성 지시는 제외한다."""
    parts = [
        f"Scene: {scene.place}. Time: {scene.timeOfDay}. Mood: {scene.mood}.",
        "Scene facts: " + "; ".join(scene.sceneFacts) + ".",
    ]
    if pose.source == "USER":
        parts.append(f"User-defined pose, outfit and expression: {pose.customText}.")
    else:
        parts.extend(
            [
                f"Body: {pose.body}. Hands: {pose.hands}. Props: {pose.props}.",
                f"Gaze: {pose.gaze}. Expression: {pose.expression}. Outfit: {pose.outfit}.",
                f"Composition: {pose.shot}. Next natural movement: {pose.motionHint}.",
            ]
        )
    return " ".join(parts)
