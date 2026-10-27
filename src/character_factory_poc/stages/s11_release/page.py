"""G9 패키지 요약 페이지 (LLD §8.10). 네트워크 요청이 없는 정적 HTML 한 장이다."""

from __future__ import annotations

from character_factory_poc.contracts.release import CharacterPackage
from character_factory_poc.stages.s4a_backgrounds.page import esc, page_shell


def _profile_block(package: CharacterPackage) -> str:
    p = package.profile
    rows = {
        "이름": p.name,
        "성별": p.gender,
        "나이": p.age,
        "직업": p.job,
        "한 줄": p.tagline,
        "소개": p.description,
        "취미": p.hobby,
        "좋아함": p.likes,
        "싫어함": p.dislikes,
        "MBTI": p.mbti,
        "태그": ", ".join(p.tags),
        "TMI": " / ".join(f"{item.text}(단계 {item.revealStage})" for item in p.tmiItems),
    }
    return (
        "<dl>"
        + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in rows.items() if v)
        + "</dl>"
    )


def render_g9_page(cid: str, rev: str, package: CharacterPackage) -> str:
    synthetic = sum(1 for video in package.videos if video.synthetic)
    sections = [
        f"<p>패키지 <code>{esc(package.packageRev)}</code> · "
        f"외모 {esc(package.appearance.appearanceRev)} · "
        f"persona {esc(package.persona.personaVersion)}</p>",
        "<h2>프로필</h2>" + _profile_block(package),
        f'<img class="ref" src="{esc(package.appearance.heroImage)}" alt="기준 얼굴">',
        "<h2>챕터</h2><table><thead><tr><th>#</th><th>제목</th><th>관계 단계</th>"
        "<th>목표</th><th>이미지</th></tr></thead><tbody>"
        + "".join(
            f"<tr><td>{ch.chapterNo}</td><td>{esc(ch.title)}</td>"
            f"<td>{esc(ch.relationshipStage)}</td><td>{esc(ch.goal)}</td>"
            f'<td><img class="frame" src="{esc(ch.frame)}" alt="{esc(ch.chapterId)} 장면"></td>'
            "</tr>"
            for ch in package.chapters
        )
        + "</tbody></table>",
        f"<h2>영상 {len(package.videos)}편</h2>"
        f"<p>가짜 공급자로 만든 영상 {synthetic}편. 실제 공급자 영상은 0편이면 표시가 없다.</p>"
        + "".join(
            f"<p><b>{esc(v.kind)}</b> {esc(v.title or v.videoId)} · "
            f"{'가짜' if v.synthetic else '실제'} · {esc(v.provider)} · {v.durationS:.1f}초"
            f"{' · ' + esc(v.clipKey) if v.clipKey else ''}</p>"
            f'<video controls preload="none" src="{esc(v.file)}"></video>'
            for v in package.videos[:6]
        ),
        "<h2>대화 경로</h2>"
        f"<p>긴 프롬프트: <code>{esc(package.persona.longPrompt)}</code> · "
        f"짧은 프롬프트: <code>{esc(package.persona.shortPrompt)}</code></p>"
        f"<p>SFT: 데이터셋 {esc(package.sft.datasetRev or '없음')} · "
        f"학습 {len(package.sft.trainingRuns)}건 · "
        f"평가 보고서 {esc(package.sft.evalReport or '없음')}</p>",
        "<h2>관문 기록</h2><ul>"
        + "".join(
            f"<li>{esc(g.gate)} · {esc(g.rev)} · {esc(g.decision)} · "
            f'<a href="{esc(g.recordRef)}">기록</a></li>'
            for g in package.gates
        )
        + "</ul>",
        "<h2>파일</h2><ul>"
        + "".join(f"<li>{esc(f.path)} · {f.bytes} bytes</li>" for f in package.files)
        + "</ul>",
    ]
    script = "function buildAnswer(){const o=metadata();return {...o,reasons:$('reasons').value};}"
    return page_shell(
        "G9 릴리즈 패키지 검토",
        cid,
        rev,
        sections,
        script,
        decisions=("APPROVE", "REJECT"),
    )
