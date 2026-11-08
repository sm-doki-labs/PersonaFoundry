# ruff: noqa: E501  (모델에 보내는 프롬프트 문장은 줄을 나누지 않는다)
"""베이스 시드 이미지 프롬프트(GPT Image 2.6 prompting guide의 구역형 서술을 따른다).

외모군 태그를 영어 구절로 바꿔 넣는다. 이름·인물 지칭·"닮게" 지시는 넣지 않는다.
"""

from __future__ import annotations

from typing import Any

from character_factory_poc.testpath.vocab2 import phrase

EXPRESSIONS = (
    "a soft, natural closed-mouth smile",
    "a calm, relaxed expression with a faint smile",
    "a bright smile showing a little of her teeth",
)

_AGE_DEFAULT = "in her early twenties"

# 촬영·표현 방식. candid는 첫 실행(2026-11-07 r1)의 솔직한 실사, beauty는 아이돌 프로필 사진 톤이다.
LOOKS: dict[str, dict[str, str]] = {
    "candid": {
        "intro": "Create a photorealistic portrait photograph of an original, fictional adult {origin} woman, {age}.",
        "purpose": "This is a casting reference photo for a new character, so her face must be clearly visible, sharp, and evenly lit.",
        "skin": "natural skin texture with fine visible pores",
        "light": "Plain light warm-gray studio backdrop. Soft diffused key light from the front-left with gentle fill, no harsh shadows. Shot like an 85mm portrait lens at eye level with shallow depth of field.",
        "wardrobe": "A simple fitted plain white crew-neck T-shirt with no logos, and small minimal stud earrings.",
        "finish": "- Looks like a real photograph with natural skin texture; no heavy retouching, no plastic or airbrushed skin.",
    },
    "beauty": {
        "intro": "Create a photorealistic beauty portrait of an exceptionally beautiful original, fictional adult {origin} woman, {age}, with the polished visual appeal of a K-pop idol's official profile photo.",
        "purpose": "This is the main casting photo for a romance-app character, so she should look stunning and approachable, with a harmonious, well-proportioned face that stays clearly visible and sharp.",
        "skin": "clear, luminous, even-toned skin with a soft healthy glow and subtle natural texture",
        "light": "Seamless soft ivory studio backdrop. Flattering beauty lighting: a large soft key light slightly above eye level and in front, gentle fill from below, a subtle rim light separating her hair from the backdrop, and bright catchlights in her eyes. Shot like an 85mm portrait lens at eye level with shallow depth of field and creamy background falloff.",
        "wardrobe": "A relaxed-fit plain white crew-neck T-shirt with no logos, and small delicate earrings.",
        "finish": "- Light professional retouching like an official profile photo: even skin and neat flyaway hairs, while keeping real skin texture. No plastic or doll-like skin, no exaggerated or oversized eyes, no uncanny symmetry.",
    },
}


def variant_tags(cluster: dict[str, Any], index: int) -> dict[str, str]:
    """다수결 값은 고정하고, 다수결이 없는 칸만 후보 순서대로 돌려 같은 군 안에서 서로 다르게 한다."""
    tags: dict[str, str] = {k: v for k, v in cluster["common"].items() if k != "vibe"}
    tags.update(cluster["details"])
    for f, options in sorted(cluster["openFields"].items()):
        tags[f] = options[index % len(options)]
    return tags


def apply_styling(
    tags: dict[str, str], cluster: dict[str, Any], index: int, vocab: dict[str, Any]
) -> None:
    """머리·메이크업은 외모군 분위기의 스타일 묶음에서 후보 순서대로 고른다(순위 인물에서 오지 않는다)."""
    table = vocab.get("stylingByVibe", {})
    ranked = sorted(cluster["shares"].get("vibe", {}).items(), key=lambda kv: (-kv[1], kv[0]))
    vibes = list(dict.fromkeys([*cluster["common"].get("vibe", []), *(v for v, _ in ranked[:2])]))
    vibes = [v for v in vibes if v in table]
    if not vibes:
        return
    pool = [p for v in vibes for p in table[v]]
    tags.update(pool[index % len(pool)])


def _join(vocab: dict[str, Any], tags: dict[str, str], fields: tuple[str, ...]) -> str:
    return ", ".join(phrase(vocab, f, tags[f]) for f in fields if f in tags)


def build_seed_prompt(
    cluster: dict[str, Any],
    index: int,
    vocab: dict[str, Any],
    *,
    origin: str = "Korean",
    look: str = "candid",
    signature: dict[str, str] | None = None,
) -> tuple[str, dict[str, str]]:
    style = LOOKS[look]
    expression = (signature or {}).get("expression") or EXPRESSIONS[index % len(EXPRESSIONS)]
    tags = variant_tags(cluster, index)
    apply_styling(tags, cluster, index, vocab)
    age = (
        phrase(vocab, "ageImpression", tags["ageImpression"])
        if "ageImpression" in tags
        else _AGE_DEFAULT
    )
    vibe = " and ".join(phrase(vocab, "vibe", v) for v in cluster["common"].get("vibe", []))
    lines = [
        style["intro"].format(origin=origin, age=age),
        style["purpose"],
        "",
        "Subject:",
    ]
    rows = [
        ("Face", _join(vocab, tags, ("faceShape", "featureIntensity", "cheeks", "jawline"))),
        ("Eyes", _join(vocab, tags, ("eyeShape", "eyelid", "eyeTail", "eyeSize", "aegyoSal"))),
        ("Brows", _join(vocab, tags, ("browShape", "browThickness"))),
        ("Nose", _join(vocab, tags, ("noseBridge", "noseTip"))),
        ("Lips", _join(vocab, tags, ("lipShape", "lipCorners"))),
        (
            "Skin",
            ", ".join(
                x
                for x in (
                    _join(vocab, tags, ("skinTone",)),
                    style["skin"],
                )
                if x
            ),
        ),
        ("Hair", _join(vocab, tags, ("hairLength", "hairColor", "hairStyle", "bangs"))),
        ("Makeup", _join(vocab, tags, ("makeup",))),
        ("Build", _join(vocab, tags, ("build",))),
        ("Signature detail (keep clearly visible)", signature["en"] if signature else ""),
        ("Overall impression", vibe),
    ]
    lines += [f"- {k}: {v}" for k, v in rows if v]
    lines += [
        "",
        "Composition:",
        "Vertical 2:3 frame, waist-up, centered. She faces the camera with shoulders turned slightly, "
        f"eyes looking into the lens, with {expression}. " + style["light"],
        "",
        "Wardrobe:",
        style["wardrobe"],
        "",
        "Constraints:",
        style["finish"],
        "- She is clearly an adult.",
        "- Create a new individual; do not depict or resemble any specific real person.",
        "- No text, no watermark, no logo.",
    ]
    if signature:
        tags["signature"] = signature["key"]
    return "\n".join(lines), tags
