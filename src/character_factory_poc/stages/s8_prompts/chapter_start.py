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

# 선택한 관계·채널·진행 주체는 생성 모델이 다른 장면으로 바꾸지 않는다.
_SCENE_FRAMES = {
    "FRIEND_CHAT": {
        "sceneFacts": [
            "상대는 오래된 친구다.",
            "인물과 상대는 메신저에서 문자 메시지를 주고받는다.",
        ],
        "sceneBoundaries": [
            "메신저에 보낼 인물의 말만 쓰고 해설·행동 지문·메모를 쓰지 않는다.",
            "확인되지 않은 공동 기억이나 개인사를 만들지 않는다.",
        ],
        "relationship": {
            "addresseeStance": (
                "오래된 친구로 대하되 기획의 말높임을 따른다. "
                "친구라는 이유만으로 반말이나 특정 호칭을 강제하지 않는다."
            ),
            "entryPosture": ["오래된 친구와 메신저 메시지를 주고받고 있다."],
            "presenceReason": "오래된 친구와 메신저로 대화하고 있다.",
            "initiativePolicy": (
                "서로 일상 주제를 꺼내거나 상대의 이야기에 답할 수 있다. "
                "답이 늦거나 상대가 마무리하려 하면 재촉하지 않는다."
            ),
            "sceneWant": "친구와 지금 나누고 싶은 이야기를 편하게 주고받는다.",
        },
    },
    "INTERVIEW": {
        "sceneFacts": [
            "상대는 인터뷰를 진행하는 질문자다.",
            "인물은 인터뷰 대상이며 질문자가 정한 주제와 질문에 답한다.",
        ],
        "sceneBoundaries": [
            "인물의 답변만 쓰고 질문자의 대사·해설·행동 지문을 대신 쓰지 않는다.",
            "확인되지 않은 경력이나 개인사를 만들지 않는다.",
        ],
        "relationship": {
            "addresseeStance": "상대를 인터뷰 질문자로 대하며 기획의 말높임을 따른다.",
            "entryPosture": ["질문자가 진행하는 인터뷰에 응답자로 참여하고 있다."],
            "presenceReason": "질문자가 진행하는 인터뷰에서 질문에 답하기 위해 참여한다.",
            "initiativePolicy": (
                "질문자가 주제와 진행 순서를 정하고 인물은 질문에 답한다. "
                "질문이 불명확할 때만 확인하며 다음 질문을 대신 만들거나 진행을 맡지 않는다."
            ),
            "sceneWant": "질문자가 묻는 내용을 이해하고 확인된 범위에서 답한다.",
        },
    },
}


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


def _scene_frame(out: ChapterStartSet, template: str | None, name: str) -> ChapterStartSet:
    frame = _SCENE_FRAMES.get(template)
    if frame is None:
        return _fan_call_frame(out, template, name)
    for ch in out.chapters:
        ch.sceneFacts = list(frame["sceneFacts"])
        # 기존 경계도 보존하되 계약의 최대 세 칸을 지킨다.
        ch.sceneBoundaries = [" ".join(ch.sceneBoundaries), *frame["sceneBoundaries"]]
        for key, value in frame["relationship"].items():
            setattr(ch.relationship, key, list(value) if isinstance(value, list) else value)
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
    elif template in _SCENE_FRAMES:
        inputs["scene-template"] = {
            "chapterTemplate": template,
            **_SCENE_FRAMES[template],
        }
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
    out = _scene_frame(result.output, template, plan.name)
    write_once_json(rev_dir / "chapter-start.json", dump(out))
    pinned_inputs = {
        "planRev": plan.planRev,
        "traitSheet": sheet_path.relative_to(char_dir).as_posix(),
    }
    from character_factory_poc.stages.s8_prompts.evidence_pipeline import is_evidence

    prompt_rev = ctx.state(cid).stage("s8").currentRev
    prompt_dir = char_dir / "s8-prompts" / str(prompt_rev)
    if is_evidence(prompt_dir):
        from character_factory_poc.common.canonical import sha256_file

        pinned_inputs.update(
            promptRevision=prompt_rev, promptPairSha256=sha256_file(prompt_dir / "prompt-pair.json")
        )
    (rev_dir / "inputs.json").write_text(
        json.dumps(pinned_inputs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_manifest(rev_dir)
    return rev_dir / "chapter-start.json"


def run_s8c(ctx: Context, cid: str) -> Path:
    state = ctx.state(cid)
    state.require_deps("s8c")
    state.transition("s8c", "RUNNING")
    chapter = run_chapter_start(ctx, cid)
    try:
        from character_factory_poc.common.demo_chat import run_samples
    except ImportError:
        run_samples = None
    if run_samples is not None:
        run_samples(ctx, cid)
        write_manifest(chapter.parent)
    state.transition("s8c", "APPROVED", rev=chapter.parent.name)
    return chapter


def load_latest_chapter_start(char_dir: Path) -> dict | None:
    folder = char_dir / "s8-chapters"
    if not folder.exists():
        return None
    revs = sorted(
        (p for p in folder.iterdir() if (p / "chapter-start.json").exists()),
        key=lambda p: int(p.name[2:]),
    )
    return json.loads((revs[-1] / "chapter-start.json").read_text("utf-8")) if revs else None
