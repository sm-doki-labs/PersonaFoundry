"""D-0191: reference-preserving, scene-aware silent call loops."""

from __future__ import annotations

from pydantic import Field

from character_factory_poc.contracts.common import Strict

VERSION = "call-loop-v1"
BASICS = ("idle_good", "speak_good", "cheering_good", "laughing_good", "greeting_good")
PURPOSES = {
    "FAN_CALL": "A friendly one-on-one video call with a fan.",
    "FRIEND_CHAT": "A relaxed conversation between friends.",
    "INTERVIEW": "A composed one-on-one interview, responding to the interviewer.",
    "FAMILY_CALL": "A warm conversation with a family member.",
}


class VideoScene(Strict):
    purpose: str = Field(default=PURPOSES["FAN_CALL"], min_length=1, max_length=600)
    referencePose: str = Field(
        default="The exact body posture, hand placement and expression in the reference image.",
        min_length=1,
        max_length=600,
    )
    wardrobe: str = Field(default="The exact clothing in the reference image.", max_length=600)
    background: str = Field(default="The exact background in the reference image.", max_length=600)
    language: str = Field(default="Korean", min_length=1, max_length=50)


RECIPES = {
    "idle_good": (
        "기본 대기",
        "상대의 말을 듣거나 응답을 기다릴 때 반복한다.",
        "IDLE LISTENING. Remain in the exact reference pose and expression. "
        "No speech, no lip movement, no jaw movement and no gestures. "
        "Keep both hands fixed in their reference positions. Only occasional natural blinks "
        "and barely visible breathing, with minimal shoulder motion. Look at the camera "
        "calmly. Do not nod, wave, laugh or begin a reaction. Smoothly match the opening "
        "pose and expression at the end for a seamless repeat.",
    ),
    "speak_good": (
        "기본 말하기",
        "응답을 말하는 동안 반복한다.",
        "TALKING. Keep both hands in the reference position. Only natural lip and jaw movement, "
        "eyes and very small head movements. Speak continuously from the start at ordinary "
        "conversational pace, about three to five syllables per second. Moderate jaw movement. "
        "Finish just before the end and smoothly restore the reference mouth and expression. "
        "Do not add a greeting gesture or reaction. "
        "No fixed dialogue or factual story is supplied.",
    ),
    "cheering_good": (
        "파이팅 말하기",
        "상대에게 격려나 응원을 전할 때 사용한다.",
        "FIGHTING REACTION. Bring the right hand from its reference position to chest height, "
        "make a fist and give one or two small firm fist pumps with an encouraging expression. "
        "Form a brief encouraging utterance with lips only, then return the hand to its "
        "reference position. Do not shout with exaggerated jaw motion.",
    ),
    "laughing_good": (
        "웃으며 말하기",
        "실제로 재미있는 말에 웃으며 반응할 때 사용한다.",
        "LAUGHING REACTION. Brief conversational lip motion leads into one bright natural "
        "silent laugh. Eyes crease and shoulders move lightly; keep the face visible, do not "
        "throw the head back or cover the face. Settle and return to the reference expression.",
    ),
    "greeting_good": (
        "꾸벅 인사",
        "통화 시작이나 명시적인 인사를 한 번 전할 때 사용한다.",
        "BOW GREETING. One light friendly Korean nod-bow: head and upper torso move together "
        "only about 15 to 20 degrees, keeping the face visible, never a deep bow. Keep hands "
        "in the reference position. Straighten and form a brief greeting with lips only. "
        "No waving, repeated bows or movement of the feet.",
    ),
}
CAMERA_CLICK = (
    "CAMERA-CLICK CELEBRATION WITH A WINK. No speech, only a happy grin. Both hands are "
    "completely EMPTY; the camera is mimed with bare fingers only. Right away both hands come "
    'up close to the face. Each hand makes an "L" with thumb and index finger: the right hand '
    "at the upper left, index finger pointing straight across just above the eyebrows, thumb "
    "pointing down beside the cheek; the left hand at the lower right, index finger pointing "
    "straight across under the nose at mouth level, thumb pointing up beside the eye. Together "
    "the two L's make a small tight rectangular frame around the eyes, like a viewfinder held "
    "close to the face. Looking through the frame straight at the lens, the person closes the "
    "LEFT eye in a playful wink while the right eye stays open, mouth slightly open in a grin. "
    "The index finger of the upper hand bends down once like pressing a shutter, one crisp "
    "click; then the eye opens, both hands lower quickly and return to the reference position. "
    "Never create, hold or reveal a camera, phone, lens, box or other prop."
)
# Shared by every clip: motion must not change the body's width or framing (Son signature
# clip widened 1.3x while passing through a wider middle frame, 2026-11-12).
BODY_LOCK = (
    "The body keeps the same shape, shoulder width, torso width and proportions as the "
    "reference image in every frame; the head and torso stay the same size and position."
)


def production(key: str, cfg: dict) -> dict:
    if cfg.get("production_profile") != VERSION:
        return {}
    if key in {"idle_good", "speak_good"}:
        return {"version": VERSION, "returnByS": 6.0, "trimWindowS": None}
    signature = key == "signature_good"
    result = {
        "version": VERSION,
        "returnByS": 4.5 if signature else 3.0,
        "trimWindowS": [4.0, 5.0] if signature else [2.5, 3.5],
    }
    if signature and cfg.get("signature", {}).get("middleFramePath"):
        result["middleFramePath"] = cfg["signature"]["middleFramePath"]
        result["middleFrameAtS"] = cfg["signature"].get("middleFrameAtS", 2.0)
    return result


def clip(key: str, cfg: dict) -> dict:
    scene = VideoScene.model_validate(cfg.get("video_scene") or {})
    if key == "signature_good":
        sig = cfg["signature"]
        title, use_when = sig["title"], sig.get("useWhen") or "이 인물을 대표하는 동작을 요청할 때."
        motion = (
            CAMERA_CLICK
            if sig.get("template") == "camera_click"
            else (
                "SIGNATURE. Perform exactly this user-specified gesture once: "
                + sig["motion"]
                + ". Make it clear, then smoothly restore the reference pose."
            )
        )
    else:
        title, use_when, motion = RECIPES[key]
    prod = production(key, cfg)
    return {
        "key": key,
        "title": title,
        "description": motion,
        "useWhen": use_when,
        "motion": motion,
        "playType": "idle"
        if key == "idle_good"
        else "speaking"
        if key == "speak_good"
        else "reaction",
        "mood": "good",
        "pickRole": None if key in {"idle_good", "speak_good"} else "emotion",
        "actionCategory": None,
        "production": prod,
        "scene": scene.model_dump(),
    }


def prompt(clip: dict, note: str = "") -> str:
    scene, prod = VideoScene.model_validate(clip["scene"]), clip["production"]
    sections = [
        (
            "Cast",
            "Exactly one person, the person already in the reference image, throughout. "
            "Nobody appears, fades in, enters, or is added.",
        ),
        (
            "Identity Preservation",
            "Preserve the exact face, facial structure, eyes, eyebrows, "
            "nose, lips, hairstyle, hair color, skin tone, age and body shape. "
            + BODY_LOCK
            + " "
            + scene.wardrobe,
        ),
        (
            "Purpose",
            scene.purpose + " Silent reusable video-call clips; voice is added separately. "
            "Scene descriptions guide behavior, never invent visual facts "
            "or change the photograph.",
        ),
        (
            "Start and End Frames",
            "Use the same reference photograph as the exact first and last "
            "frame. Restore its posture, hands, expression and mouth smoothly, without a jump. "
            + scene.referencePose,
        ),
        (
            "Camera",
            "Locked camera, same framing, angle, distance and lighting. "
            "No cuts, zoom, pan, orbit or reframing.",
        ),
        (
            "Background",
            scene.background + " Preserve existing logos and lettering, positions, "
            "colors and shapes. Do not blur, warp, remove or invent text. No new objects. "
            "Do not add a prop to the hands.",
        ),
        (
            "Motion",
            "Real-time speed, never slow motion or stretched to fill time. "
            "Keep the face sharp and recognizable. Feet stay planted, no walking or turning away. "
            "Preserve the reference sitting or standing posture. Moving the arms never widens "
            "or narrows the shoulders or torso.",
        ),
        (
            "Audio",
            "Completely silent: no voice, laughter sound, shutter, crowd, music or effects. "
            + (
                "No lip movement at any time; no audio track."
                if clip["key"] == "idle_good"
                else "Lip movement only in " + scene.language + "; no audio track."
            ),
        ),
        ("Requested Clip", clip["motion"]),
    ]
    if clip["key"] == "idle_good":
        sections.append(
            (
                "Timing",
                "Generate 6 seconds of quiet listening. Keep the entire clip. "
                "Mouth stays in the reference shape for the whole clip. "
                "Start and end in the same reference pose for seamless looping.",
            )
        )
    elif prod.get("trimWindowS"):
        end = prod["returnByS"]
        sections.append(
            (
                "Timing",
                f"Generate 6 seconds. Complete the gesture and return to the "
                f"exact reference pose by {end:.1f} seconds. From {end:.1f} seconds to the end, "
                "hold that pose still with only natural blinking. Start no new movement.",
            )
        )
    else:
        sections.append(
            (
                "Timing",
                "Generate 6 seconds of continuous natural talking. "
                "Finish just before 6.0 seconds; keep the entire clip.",
            )
        )
    if prod.get("middleFramePath"):
        sections.append(
            (
                "Middle Frame",
                "A supplied keyframe pins the signature gesture at "
                f"{prod['middleFrameAtS']:.1f} seconds. Pass through that pose, then return.",
            )
        )
    if note:
        sections.append(("Reviewer Adjustment", note + " Keep all preservation and timing rules."))
    sections.append(
        ("Final Constraint", "Only the reference person is present for the entire clip.")
    )
    return "\n\n".join(f"## {title}\n{body}" for title, body in sections)
