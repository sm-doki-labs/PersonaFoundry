"""G4 챕터별 승인·수정 요청 페이지. 수정 요청한 챕터만 다시 생성한다."""

from character_factory_poc.stages.image_qa import RUBRICS
from character_factory_poc.stages.s4a_backgrounds.page import esc, page_shell, render_qa


def render_g4_page(*, subject_id, rev, inputs, frames, name):
    sections = [
        f"<p>{esc(name)} · 외모 {esc(inputs.appearanceRev)} · 장면 {esc(inputs.sceneRev)}</p>",
        "<p>얼굴·장소·자세를 확인하고 챕터마다 승인하거나 수정 내용을 적어 주세요.</p>",
        f'<img class="ref" src="{esc(inputs.referenceImage.path)}" alt="G2 기준 얼굴">',
        f'<img class="ref" src="{esc(inputs.identityReference.path)}" alt="생성에 사용한 얼굴 참조">',
        f"<p>{esc(inputs.referenceCrop)} · {esc(inputs.cropNote)}</p>",
    ]
    for frame in frames:
        ch = frame.chapterId
        sections.append(
            f'<fieldset><legend>{ch}</legend><div class="scene">'
            f'<img class="frame" src="{esc(frame.filePath)}" alt="{esc(frame.frameId)} 합성 장면">'
            "</div>"
            + render_qa(frame.qa, RUBRICS["composite-v1"])
            + "<details><summary>생성 지시 확인</summary>"
            f"<pre>{esc(frame.prompt)}</pre></details>"
            f'<label><input type="radio" name="{ch}" value="APPROVE"> 이 챕터 승인</label>'
            f'<label><input type="radio" name="{ch}" value="REQUEST_CHANGES"> 이 챕터 수정</label>'
            f'<label for="note-{ch}">바꿀 내용 (수정 요청 시 필수)</label>'
            f'<textarea id="note-{ch}"></textarea></fieldset>'
        )
    script = (
        "function buildAnswer(){const o=metadata();if(o.decision==='REJECT')return o;"
        "const requestedChanges=[];for(const ch of CH){"
        "const r=document.querySelector('input[name='+ch+']:checked');"
        "if(!r)throw Error(ch+'의 승인 또는 수정을 선택하세요.');"
        "if(r.value==='REQUEST_CHANGES'){const note=$('note-'+ch).value.trim();"
        "if(!note)throw Error(ch+'에서 바꿀 내용을 적어 주세요.');"
        "requestedChanges.push({field:ch,note});}}"
        "return {...o,decision:requestedChanges.length?'REQUEST_CHANGES':'APPROVE',"
        "...(requestedChanges.length?{requestedChanges}:{})};}"
    )
    return page_shell(
        "G4 챕터 완성 이미지 승인",
        subject_id,
        rev,
        sections,
        script,
        decisions=("APPROVE", "REJECT"),
    )
