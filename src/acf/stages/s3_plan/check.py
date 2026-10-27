"""S3 기획서 초안 검사 (FR-13, D-0005)."""

from __future__ import annotations

from acf.common.textstats import looks_like_bare_adjectives
from acf.contracts.plan import PERSONALITY_FIELDS, CharacterPlan


def check_plan_draft(brief_text: str, appearance_rev: str | None = None):
    """appearance_rev가 있으면(G2 승인 뒤, D-0024) 그 값을 그대로 쓰고 챕터마다 조명·구도를 채웠는지 본다."""

    def _check(plan: CharacterPlan) -> list[str]:
        p: list[str] = []
        if appearance_rev and plan.appearanceRev != appearance_rev:
            p.append(f"appearanceRev: 입력의 '{appearance_rev}'를 그대로 쓴다")
        if appearance_rev:
            for c in plan.chapters:
                if not c.lighting.strip():
                    p.append(
                        f"chapters.{c.chapterId}.lighting: 장면의 빛을 한 줄로 쓴다(S4 프레임용)"
                    )
                if not c.composition.strip():
                    p.append(
                        f"chapters.{c.chapterId}.composition: 인물의 자세·구도를 한 줄로 쓴다(S4 프레임용)"
                    )
        for f in ("name", "age", "job", *PERSONALITY_FIELDS, "chapters"):
            evs = plan.evidence.get(f, [])
            if not evs:
                p.append(f"evidence.{f}: 근거가 없다(BRIEF·PRESET·USER 중 하나)")
            for ev in evs:
                if ev.kind == "BRIEF" and ev.quote and ev.quote not in brief_text:
                    p.append(f"evidence.{f}: 인용 '{ev.quote[:30]}…'이 브리프 원문에 없다")
        for i, t in enumerate(plan.coreTraits):
            if looks_like_bare_adjectives(t):
                p.append(f"coreTraits[{i}]: 행동으로 서술한다('먼저 제안한다'처럼)")
        if looks_like_bare_adjectives(plan.contrastTrait):
            p.append("contrastTrait: 행동으로 서술한다")
        for c in plan.chapters:
            if len(c.scene) < 6:
                p.append(f"chapters.{c.chapterId}.scene: 장소·시간이 드러나게 한 줄로 쓴다")
        if not plan.notes.strip():
            p.append("notes: 어떤 프리셋을 왜 골랐는지, 무엇이 창작 설정인지 적는다")
        return p

    return _check
