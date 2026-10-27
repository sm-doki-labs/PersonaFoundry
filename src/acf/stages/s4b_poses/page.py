"""G4b 장면 사실 확인과 자세·의상 선택. 모든 동작은 로컬 문서 안에서 끝난다."""

import json

from acf.contracts.scene import POSE_FIELDS
from acf.stages.image_qa import RUBRICS
from acf.stages.s4a_backgrounds.page import custom_control, esc, fields, page_shell, render_qa


def render_g4b_page(cid: str, rev: str, scene, poses) -> str:
    sections = ["<p>장면 사실을 확인하고 챕터마다 자세·의상을 하나씩 고르세요.</p>"]
    by_chapter = {ch.chapterId: ch for ch in poses.chapters}
    for chapter in scene.chapters:
        ch = chapter.chapterId
        facts = fields(
            {
                k: getattr(chapter, k)
                for k in (
                    "place",
                    "timeOfDay",
                    "mood",
                    "sceneFacts",
                    "meetingContext",
                    "relationshipCanon",
                    "sceneBoundaries",
                )
            }
        )
        cards = []
        for pose in by_chapter[ch].candidates:
            cards.append(
                '<article class="card">'
                + f"<h3>{esc(pose.title)}</h3>"
                + fields({f: getattr(pose, f) for f in POSE_FIELDS})
                + f'<label><input type="radio" name="{ch}" value="{esc(pose.poseId)}"> '
                "이 자세·의상 선택</label></article>"
            )
        tweaks = "".join(
            f'<label>{esc(field)} <input id="{ch}-{field}" '
            f'placeholder="선택한 후보의 {esc(field)} 수정 (선택 사항)"></label>'
            for field in POSE_FIELDS
        )
        sections.append(
            f'<fieldset><legend>{ch} 장면과 자세</legend><div class="grid">'
            f'<img class="plate scene" src="{esc(chapter.plate.path)}" '
            f'alt="{esc(chapter.place)} 배경"><div>{facts}</div></div>'
            + render_qa(chapter.qa, RUBRICS["plate-v1"])
            + f'<div class="grid">{"".join(cards)}</div>'
            + custom_control(ch, "자세·의상 직접 정의")
            + "<details><summary>선택한 후보의 세부 항목 수정</summary>"
            + tweaks
            + "</details></fieldset>"
        )
    script = (
        f"const FIELDS={json.dumps(POSE_FIELDS)};"
        "function buildAnswer(){const o=metadata();if(o.decision!=='SELECT')return o;"
        "const {picks,custom}=choices(),tweaks={};for(const ch of Object.keys(picks)){"
        "const changes={};for(const field of FIELDS){const v=$(ch+'-'+field).value.trim();"
        "if(v)changes[field]=v;}if(Object.keys(changes).length)tweaks[ch]=changes;}"
        "return {...o,picks,custom,tweaks};}"
    )
    return page_shell("G4b 장면 확인과 자세 선택", cid, rev, sections, script)
