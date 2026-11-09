"""S8c 챕터 시작 설정(D-0089).

승인 기획·성격 시트·브리프 챕터 장면 → chapter-start-v1.

시연 경로의 그래프 단계가 아니라 cfp persona chapters로 따로 부른다.
서비스 내보내기는 이 결과가 있으면 틀 문장 대신 쓴다(stages/export/doki_app/chat_svc.py).
"""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.call_context import appearance_reading_problems
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import next_rev, write_manifest, write_once_json
from character_factory_poc.contracts.chapter_start import ChapterStartSet
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import SOURCE, read_origin
from character_factory_poc.stages.s0_source.run import load_approved_source
from character_factory_poc.stages.s3_plan.importer import load_approved_plan
from character_factory_poc.stages.s7_traits.check import _plan_speech_level

QUOTES = re.compile(r"[\"'“”‘’「」]")


def plan_calls() -> list[CallPlan]:
    return [
        CallPlan(
            "s8c", "챕터 시작 설정(형식 재시도 2회·검사 재시도 1회 포함)", 6, est_cost_usd=None
        )
    ]


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def check_chapter_start(voice_summary: str, ledger: dict | None = None, name: str = ""):
    from character_factory_poc.stages.s7_traits.ledger import concept_tokens, overlap

    exclude = (name[:2],) if name else ()
    traits = {
        t["id"]: concept_tokens(f"{t['trigger']} {t['behavior']}", exclude)
        for t in (ledger or {}).get("traits", [])
    }
    level = _plan_speech_level(voice_summary or "")
    expected = {"formal": "POLITE", "polite": "POLITE", "casual": "CASUAL"}.get(level or "")

    def _check(out: ChapterStartSet) -> list[str]:
        problems = []
        first = out.chapters[0]
        if expected and first.relationship.speechLevel != expected:
            problems.append(
                f"ch1.relationship.speechLevel: 기획 말투 요약의 기본 등급({expected})을 따른다"
            )
        for ch in out.chapters:
            for text in _strings(dump(ch)):
                if QUOTES.search(text):
                    problems.append(f"{ch.chapterId}: 따옴표 대사나 인용을 넣지 않는다")
                    break
            problems += appearance_reading_problems(ch.chapterId, " ".join(_strings(dump(ch))))
            rel = dump(ch.relationship)
            for key in (
                "sceneWant",
                "initiativePolicy",
                "expressionDelta",
                "moodRange",
                "entryPosture",
            ):
                for text in _strings(rel.get(key)):
                    toks = concept_tokens(text, exclude)
                    for tid, tt in traits.items():
                        if overlap(tt, toks) >= 0.6:
                            problems.append(
                                f"{ch.chapterId}.relationship.{key}: 장부 {tid}를 다시 썼다. "
                                "관계 설정은 특질을 다시 서술하지 않는다"
                            )
        return problems

    return _check


def _seed_notes(ctx: Context, cid: str, seed_rev: str) -> str:
    p = ctx.character_dir(cid) / "s3-plan" / "seeds" / f"{seed_rev}.json"
    return json.loads(p.read_text("utf-8")).get("notes", "") if p.exists() else ""


def _example(cid: str, plan_rev: str) -> dict[str, Any]:
    rel = {
        "speechLevel": "POLITE",
        "addresseeStance": "<등급·호칭·거리감·전환 조건>",
        "entryPosture": ["<sceneFacts와 같은 상태값>"],
        "presenceReason": "<지금 이 통화에 있는 이유>",
        "initiativePolicy": "<먼저 꺼낼 수 있는 범위와 거절을 받는 방식>",
        "expressionDelta": ["<이 단계에서 달라지는 표현>"],
        "sceneWant": "<이 장면에서 바라는 것>",
        "moodRange": {k: "<지금 마음 상태 문장>" for k in ("down", "start", "middle", "top")},
        "trustedStory": None,
    }
    return {
        "schemaVersion": "chapter-start-v1",
        "characterId": cid,
        "planRev": plan_rev,
        "chapters": [
            {
                "chapterId": ch,
                "sceneFacts": ["<확인된 사실>", "<확인된 사실>"],
                "sceneBoundaries": ["<이 장면에서 지킬 선>"],
                "relationship": rel,
            }
            for ch in ("ch1", "ch2", "ch3")
        ],
    }


def _fan_call_frame(out: ChapterStartSet, template: str | None, name: str) -> ChapterStartSet:
    if template != "FAN_CALL":
        return out
    from character_factory_poc.stages.s3_plan.speech_profile import _josa

    subject = name + _josa(name, "이", "가")
    frame = (
        f"지금부터 너의 출력은 {subject} 영상통화에서 소리 내어 하는 말 그 자체다. "
        f"계획, 메모, 규칙 요약, 따옴표로 묶은 초안은 쓰지 않고 첫 글자부터 {name}의 말로 시작한다."
    )
    for ch in out.chapters:
        ch.relationship.initiativePolicy = (
            "통화를 시작하는 첫인사 때 한 번 상대의 하루를 물을 수 있고, "
            "그 뒤로는 상대가 꺼낸 이야기에 답하며 대화를 이어 간다. "
            "상대가 답하기 어려워하거나 통화를 마무리하려 하면 그 뜻을 따른다."
        )
        # 경계는 최대 세 칸이다. 이미 세 칸이면 마지막 두 선을 합쳐 모두 보존한다.
        boundaries = ch.sceneBoundaries
        if len(boundaries) == 3:
            boundaries = [boundaries[0], " ".join(boundaries[1:])]
        ch.sceneBoundaries = [*boundaries, frame]
    return out


def run_chapter_start(ctx: Context, cid: str) -> Path:
    from character_factory_poc.stages.s8_prompts.build import load_latest_trait_sheet

    plan, _ = load_approved_plan(ctx, cid)
    sheet, sheet_path = load_latest_trait_sheet(ctx, cid)
    ledger_path = sheet_path.parent / "trait-ledger.json"
    ledger = json.loads(ledger_path.read_text("utf-8")) if ledger_path.exists() else None
    raw_plan = {k: v for k, v in dump(plan).items() if k != "voiceExamples"}
    budget = ctx.budget()
    budget.check_plan(plan_calls())
    char_dir = ctx.character_dir(cid)
    rev = next_rev(char_dir / "s8-chapters", "cs")
    rev_dir = char_dir / "s8-chapters" / rev
    inputs = {
        "character-plan": raw_plan,
        # D-0091: 장부가 있으면 장부만 준다. 관계 설정은 그 특질을 다시 쓰지 않는다.
        "trait-ledger" if ledger else "trait-sheet": ledger
        or {k: dump(sheet)[k] for k in ("choice", "card")},
        "brief-notes.md": _seed_notes(ctx, cid, plan.seedRev) or "(브리프 없음)",
    }
    template = None
    if read_origin(char_dir) == SOURCE:
        pack, _, _ = load_approved_source(ctx, cid)
        template = pack.chapterTemplate
    if template == "FAN_CALL":
        inputs["fan-call.md"] = (
            resources.files("character_factory_poc.prompts")
            .joinpath("chapter_start_fan.md")
            .read_text("utf-8")
        )
    result = run_agent(
        AgentSpec("chapter_start", "chapter-start-v1", "s8c", max_check_retries=1),
        rev_dir / "workspace",
        inputs,
        [check_chapter_start(plan.voiceSummary, ledger, plan.name)],
        ctx.role_model(cid, budget, "chapter_start"),
        ref=f"{cid}/{rev}",
        contract_example=_example(cid, plan.planRev),
        backend=ctx.agent_backend(cid, budget, "s8c"),
    )
    if not result.ok:
        raise SystemExit("챕터 시작 설정 검사 실패:\n- " + "\n- ".join(result.problems))
    out = _fan_call_frame(result.output, template, plan.name)
    write_once_json(rev_dir / "chapter-start.json", dump(out))
    (rev_dir / "inputs.json").write_text(
        json.dumps(
            {"planRev": plan.planRev, "traitSheet": sheet_path.relative_to(char_dir).as_posix()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_manifest(rev_dir)
    return rev_dir / "chapter-start.json"


def load_latest_chapter_start(char_dir: Path) -> dict | None:
    folder = char_dir / "s8-chapters"
    if not folder.exists():
        return None
    revs = sorted(
        (p for p in folder.iterdir() if (p / "chapter-start.json").exists()),
        key=lambda p: int(p.name[2:]),
    )
    return json.loads((revs[-1] / "chapter-start.json").read_text("utf-8")) if revs else None
