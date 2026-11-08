# ruff: noqa: E501  (모델에 보내는 프롬프트 문장은 줄을 나누지 않는다)
"""시험 경로 3·4번: 고른 시드 얼굴로 배경·의상 묶음 추천 → 고른 묶음으로 영상용 시드 이미지(9:16).

3번은 시드 이미지를 보는 비전 모델이 앱 영상통화 장소 종류와 챕터에 맞춰 묶음을 낸다.
4번은 GPT Image 2.6 편집으로 같은 얼굴을 추천 의상·배경에 넣는다(공식 가이드의 인물 유지·장소 삽입 형식).
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from character_factory_poc.providers.base import VisionRequest
from character_factory_poc.testpath.image_api import ImageApiError, OpenAIImagesClient

# chat-svc data/의 영상통화 장소 맥락(2026-11-07 원격 최신 기준)
CONTEXT_KINDS = ("cafe", "home", "yajang", "walk-home", "rehearsal-room", "hotel-lounge")
CHAPTERS = {
    "ch1": "첫 만남(낯선 사이 → 아는 사이)",
    "ch2": "첫 데이트(아는 사이 → 썸)",
    "ch3": "썸 데이트(썸 → 연인)",
}
SCENE_SIZE = "1088x1920"


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bundle_request(seed_tags: dict[str, Any], seed_image: Path, count: int) -> VisionRequest:
    tags = ", ".join(f"{k}={v}" for k, v in sorted(seed_tags.items()))
    chapters = "\n".join(f"- {k}: {v}" for k, v in CHAPTERS.items())
    prompt = f"""첨부한 사진은 연애 영상통화 앱에 새로 넣을 가상의 20대 초반 여성 캐릭터의 기준 얼굴이다. 이 얼굴로 영상용 이미지를 만들기 전에, 배경과 의상을 한 묶음으로 {count}개 추천한다.

얼굴 태그: {tags}

앱 맥락:
- 남성 사용자가 이 캐릭터와 영상통화하듯 대화한다. 영상은 9:16 세로, 고정 카메라, 머리부터 허벅지 중간까지 보이는 4분의 3 구도다. 6초짜리 대기(idle) 영상과 짧은 반응 영상의 첫 프레임으로 쓴다.
- 챕터:
{chapters}
- 영상통화 장소 종류(contextKind)는 다음 중 하나: {", ".join(CONTEXT_KINDS)}

규칙:
1. 사진 속 얼굴·머리 스타일·분위기(러블리·청순 계열)에 어울리는 의상과 배경을 고른다. 얼굴과 머리는 바꾸지 않는다.
2. 매력적이고 세련되되 노출은 일상복 수준으로 한다. 속옷·수영복·과한 노출은 넣지 않는다.
3. 배경은 인물 뒤로 부드럽게 흐려져도 장소가 읽히게 한다. 6초 동안 깜빡이는 조명·움직이는 군중처럼 영상에서 튀는 요소는 피한다. 간판 글자·브랜드 로고는 넣지 않는다.
4. 묶음끼리 장소 종류·시간대(낮/밤)·색감이 겹치지 않게 다양하게 한다. 세 챕터가 모두 한 번 이상 나오게 하고, 밤 장면을 두 개 이상 넣는다.
5. en 칸은 이미지 생성 프롬프트에 그대로 넣을 영어 문장으로, 재질·색·조명을 구체적으로 쓴다.

JSON만 출력한다:
{{"bundles": [{{"id": "b1", "title": "짧은 한국어 제목", "chapter": "ch1|ch2|ch3", "contextKind": "<장소 종류>", "timeOfDay": "day|night", "background": {{"ko": "", "en": ""}}, "outfit": {{"ko": "", "en": ""}}, "pose": {{"ko": "앉음/서 있음 등", "en": ""}}, "lighting": {{"ko": "", "en": ""}}, "palette": "주요 색 3개", "why": "이 얼굴·분위기에 어울리는 이유 한 문장"}}]}}"""
    return VisionRequest(
        stage="testpath-bundles",
        ref=f"bundles-{seed_image.stem}",
        prompt=prompt,
        images=(("기준 얼굴", str(seed_image)),),
        system="너는 연애 앱 캐릭터의 스타일리스트이자 촬영 감독이다.",
        max_output_tokens=16000,
    )


def parse_bundles(text: str, count: int) -> list[dict[str, Any]]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSON 객체가 없다")
    rows = json.loads(m.group(0)).get("bundles")
    if not isinstance(rows, list) or not rows:
        raise ValueError("bundles 목록이 없다")
    out = []
    for i, b in enumerate(rows[:count], 1):
        for k in ("background", "outfit", "pose", "lighting"):
            if not isinstance(b.get(k), dict) or not b[k].get("en"):
                raise ValueError(f"묶음 {i}: {k}.en이 없다")
        b["id"] = f"b{i}"
        if b.get("contextKind") not in CONTEXT_KINDS:
            b["contextKind"] = "other"
        out.append(b)
    return out


def scene_prompt(bundle: dict[str, Any], signature_en: str | None) -> str:
    keep = "her exact face, facial features, eye shape, nose, lips, skin tone, freckles and beauty marks, hairstyle, hair color, bangs, and proportions"
    sig = f" Keep her signature detail clearly visible: {signature_en}." if signature_en else ""
    return f"""Use image 1 as the identity reference. Create a new photorealistic vertical 9:16 photo of the same woman from image 1 in a new scene. Do not change {keep}; she must be instantly recognizable as the same person.{sig}

Scene:
{bundle["background"]["en"]}

Outfit:
{bundle["outfit"]["en"]}

Pose and framing:
{bundle["pose"]["en"]} Framed from the top of her head to mid-thigh, centered, filling most of the frame like a video-call or vlog shot. She faces the camera, looking into the lens with a gentle, warm smile, hands resting naturally and fully visible. The camera is at chest-to-eye level and static.

Lighting:
{bundle["lighting"]["en"]} Bright, clear catchlights in her eyes; her face is the best-lit part of the image.

Style:
Photorealistic, like a polished lifestyle photo from a K-pop idol's official content: clear luminous skin with subtle natural texture, light professional retouching, background softly out of focus with shallow depth of field but the place still readable.

Constraints:
- Same person as image 1; do not redesign or beautify her into a different face.
- Everyday, tasteful clothing; no lingerie or swimwear.
- No text, no signage letters, no logos, no watermark.
- Realistic hands with five fingers each."""


def render_scenes(
    out_dir: Path,
    seed_image: Path,
    bundles: list[dict[str, Any]],
    signature_en: str | None,
    client: OpenAIImagesClient,
    quality: str = "high",
) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)

    def one(b: dict[str, Any]) -> dict[str, Any]:
        png = out_dir / f"{b['id']}.png"
        meta = out_dir / f"{b['id']}.json"
        if png.exists() and meta.exists():
            return json.loads(meta.read_text("utf-8"))
        prompt = scene_prompt(b, signature_en)
        try:
            res = client.edit(prompt, [seed_image], size=SCENE_SIZE, quality=quality)
        except ImageApiError as e:
            rec = {"id": b["id"], "ok": False, "error": str(e)[:600], "prompt": prompt}
            _write(meta.with_suffix(".error.json"), rec)
            return rec
        png.write_bytes(res.data)
        rec = {
            "id": b["id"],
            "ok": True,
            "file": png.name,
            "elapsedMs": res.elapsed_ms,
            "usage": res.usage,
            "model": client.model,
            "size": SCENE_SIZE,
            "prompt": prompt,
        }
        _write(meta, rec)
        return rec

    with ThreadPoolExecutor(max_workers=max(1, len(bundles))) as pool:
        return list(pool.map(one, bundles))
