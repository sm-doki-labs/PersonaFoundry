"""Project approved authoring material into the service's eight persona sections."""

import re
from collections.abc import Mapping
from importlib.resources import files

from character_factory_poc.common.call_context import CALL_OBSERVATION_RULE
from character_factory_poc.common.schema import dump
from character_factory_poc.common.textstats import section_names
from character_factory_poc.contracts.actor_persona import RuntimeContext, RuntimePersona

VERSION = "actor-tendencies-compiler-v3"
SECTIONS = (
    ("facts", "PERSONA / FACTS"),
    ("lifeAndTastes", "PERSONA / LIFE_AND_TASTES"),
    ("disposition", "PERSONA / DISPOSITION"),
    ("wantsAndFears", "PERSONA / WANTS_AND_FEARS"),
    ("readingAndTension", "PERSONA / READING_AND_TENSION"),
    ("choices", "PERSONA / CHOICES"),
    ("voice", "PERSONA / VOICE"),
    ("boundaries", "PERSONA / KNOWS_AND_LIMITS"),
)
FORBIDDEN = (
    "activateWhen",
    "activeWhen",
    "doNotActivateWhen",
    "firstMove:",
    "switchWhen",
    "choiceRuleId",
    "traitId",
    "catalogSha256",
    "제작자가 추가한",
    "CHARACTER_EXAMPLES",
    "CHAPTERS",
    "제공된 내용 뼈대",
)


def _raw(plan):
    return plan if isinstance(plan, Mapping) else dump(plan)


def _check_narrative(value):
    if re.search(
        r"(?im)^\s*(?:\[[^\n]+\]|#{1,6}\s|(?:user|assistant|system|사용자|캐릭터)\s*:)"
        r"|\b(?:sourceRef|sourceSha256|catalogSha256|traitId)\b"
        r"|제작자\s*:|예시\s*대화|대화\s*예시"
        r"|<(?:system|assistant|user|current_context|chapter)[\s>]",
        value,
    ) or re.search(
        r"(?:대답|답변|응답).{0,25}(?:항상|반드시|무조건).{0,80}['\"“”].{0,40}(?:시작|끝|출력)",
        value,
    ):
        raise ValueError("actor narrative contains authoring structure or a fixed reply")


def _unique(lines):
    result = []
    for line in lines:
        if not line or not line.strip():
            continue
        _check_narrative(line)
        normal = " ".join(line.split())
        if normal not in result:
            result.append(normal)
    return result


def _voice_lines(lines):
    """Migrate old authoring notes while preserving actual personality sentences."""
    result = []
    for line in lines:
        _check_narrative(line)
        if not any(word in line for word in ("이 프로필", "승인된", "다음 단계", "출처")):
            result.append(line)
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            if not any(word in sentence for word in ("이 프로필", "승인된", "다음 단계", "출처")):
                result.append(sentence)
    return result


def load_actor_rules(ctx=None):
    custom = (
        (
            ctx.config.stage("s8").get("actor_system_rules_path")
            or ctx.config.stage("s8").get("system_rules_path")
        )
        if ctx
        else None
    )
    if custom:
        path = (ctx.config.root / custom).resolve()
        return path.read_text("utf-8"), str(path)
    return (
        # v3(2026-11-05, D-0089): 마스터 지시서 6절·1.6·1.7을 따른다.
        # 관찰·공동 기억·공통 사실 규칙을
        # 페르소나 칸에서 이쪽으로 옮겼다(MD-1.4).
        # v4(2026-11-08, D-0137): 그림 이모지만 막고 ㅋㅋ·ㅠㅠ·^^는 관계·감정에 맞게 허용한다.
        # v1~v3은 과거 재현용이다.
        files("character_factory_poc.resources").joinpath("actor-system-rules-v4.md").read_text(),
        "builtin:actor-system-rules-v4",
    )


def project_actor_persona(plan, sheet, bp) -> RuntimePersona:
    """Exact deduplication is not a semantic or psychological quality judgment."""
    p = _raw(plan)
    gender = {"female": "여성", "male": "남성", "other": ""}.get(p.get("gender"), "")
    identity_fact = f"{p['name']}{_topic(p['name'])} {p['age']}세 {gender} {p['job']}이다."
    return RuntimePersona(
        facts=_unique([identity_fact, p.get("background", "")]),
        lifeAndTastes=_unique(p.get("lifeAndTastes", [])),
        disposition=_unique(
            list(p["coreTraits"])
            + [p.get("contrastTrait", "")]
            + [t["behavior"] for t in p.get("selectedTraits", [])]
        ),
        wantsAndFears=_unique(p.get("wantsAndFears", [])),
        readingAndTension=_unique([sheet.choice.attention, sheet.choice.interpretationPriority]),
        # Priorities describe tendencies; activation/switch tables stay internal.
        choices=_unique(rule.priority for rule in bp.decisionRules),
        voice=_unique(
            _voice_lines(
                [
                    p.get("voiceSummary", ""),
                    sheet.choice.expressionIntensity,
                    bp.voiceProfile.speechLevel,
                    bp.voiceProfile.relationshipDistance,
                    bp.voiceProfile.emotionalVariation,
                    bp.voiceProfile.rhythm,
                    bp.voiceProfile.directness,
                    *bp.voiceProfile.lexicon,
                    *bp.voiceProfile.avoidRepetition,
                ]
            )
        ),
        boundaries=_unique(
            p.get("boundaries", [])
            + [
                "상대에 대해서는 직접 들은 것과 실제로 함께 겪은 일만 안다. "
                "자기 경험과 상대의 경험을 구분하고 상상한 일을 공동 기억으로 만들지 않는다.",
                "제안과 확정된 약속은 다르다. 변경과 취소는 실제 대화의 최신 내용대로 받아들인다.",
                "확인하지 않은 실제 현재 정보는 안다고 꾸미지 않는다. "
                "조회 도구가 없으면 검색하거나 확인해 오겠다고 약속하지 않는다.",
                CALL_OBSERVATION_RULE,
            ]
        ),
    )


def _render(plan, profile, rules_text, runtime_context):
    _check_narrative(rules_text)
    p = _raw(plan)
    sections = {
        "ACTOR_IDENTITY": f"캐릭터 이름: {p['name']}",
        "INPUT_AND_BOUNDARIES": rules_text.strip(),
    }
    for field, label in SECTIONS:
        body = "\n".join(getattr(profile, field))
        if field == "choices":
            body = "자주 고르는 경향이다. 지금 마음과 장면이 우선한다.\n" + body
        sections[label] = body
    if runtime_context is not None:
        for value in (runtime_context.relationship, runtime_context.scene):
            if value:
                _check_narrative(value)
        lines = []
        if runtime_context.relationship:
            lines.append("현재 관계: " + runtime_context.relationship)
        if runtime_context.scene:
            lines.append("현재 장면: " + runtime_context.scene)
        if runtime_context.speechLevel:
            lines.append(
                "현재 말높임: "
                + {"CASUAL": "자연스러운 반말", "POLITE": "자연스러운 존댓말"}[
                    runtime_context.speechLevel
                ]
            )
        if lines:
            sections["CURRENT_CONTEXT"] = "\n".join(lines)
    sections["OUTPUT"] = (
        "이 인물이 상대에게 할 말만 출력한다. 해설·라벨·행동 지문·상대의 대사는 쓰지 않는다."
    )
    text = "\n\n".join(f"[{key}]\n{value}" for key, value in sections.items())
    if section_names(text) != list(sections):
        raise ValueError("actor section structure differs from the runtime contract")
    return text, sections


def compose_actor_runtime(plan, sheet, bp, *, rules_text=None, runtime_context=None, long_max=8000):
    if runtime_context is not None and not isinstance(runtime_context, RuntimeContext):
        raise TypeError("runtime_context must be one RuntimeContext")
    if rules_text is None:
        rules_text, _ = load_actor_rules()
    profile = project_actor_persona(plan, sheet, bp)
    text, sections = _render(plan, profile, rules_text, runtime_context)
    if len(text) > long_max:
        raise ValueError(f"actor long {len(text)} chars exceeds {long_max}; no truncation")
    verify_actor_runtime(
        text, plan, sheet, bp, rules_text=rules_text, runtime_context=runtime_context
    )
    return text, sections


def verify_actor_runtime(text, plan, sheet, bp, *, rules_text=None, runtime_context=None):
    if rules_text is None:
        rules_text, _ = load_actor_rules()
    expected, _ = _render(plan, project_actor_persona(plan, sheet, bp), rules_text, runtime_context)
    if expected != text:
        raise ValueError("actor personality/body differs from approved source projection")
    if any(term in text for term in FORBIDDEN):
        raise ValueError("actor prompt contains authoring metadata, examples or chapter list")


def _topic(name: str) -> str:
    """이름 뒤 주제 조사: 받침이 있으면 '은', 없으면 '는'. 한글이 아니면 '은(는)'."""
    last = name.strip()[-1:] if name.strip() else ""
    if not ("가" <= last <= "힣"):
        return "은(는)"
    return "은" if (ord(last) - 0xAC00) % 28 else "는"


def _bare(text: str) -> str:
    """문장 끝 마침표·공백을 떼어 이어 붙일 때 '..'이 생기지 않게 한다."""
    return text.strip().rstrip(".。 ").strip()


def _choice_lines(sheet) -> list[str]:
    """선택 경향을 '상황 → 행동' 한 줄로 만든다(K-0073).

    판단 우선순위는 상황(dilemma)이 빠지면 언제 하는 행동인지 알 수 없어 아무 때나 하는 행동처럼
    읽힌다. 상황·선택·전환을 한 줄에 함께 둔다.
    """
    lines = ["특별한 단서가 없을 때 → " + _bare(sheet.choice.primaryResponse) + "."]
    lines += list(sheet.choice.switchConditions)
    for r in sheet.card.judgmentPriorities:
        line = f"{_bare(r.dilemma)} → {_bare(r.choice)}."
        if r.switch.strip():
            line += f" 다만 {_bare(r.switch)}."
        lines.append(line)
    return lines


def compose_approved_sheet(plan, sheet, *, rules_text, voice=None):
    """Compile the legacy approved sheet using the current actor section contract."""
    p = _raw(plan)
    # D-0080: 기획서에 없는 칸을 빈 섹션으로 조립하지 않는다(구형 character-plan-v1 등).
    missing = [
        field
        for field in ("lifeAndTastes", "wantsAndFears", "voiceSummary", "boundaries")
        if not p.get(field)
    ]
    if missing:
        raise ValueError(
            "승인 기획서에 프롬프트 섹션 원천이 비어 있다: "
            + ", ".join(missing)
            + ". 최신 기획 경로(씨앗 → 변형)로 새 기획을 만든다"
        )
    gender = {"female": "여성", "male": "남성", "other": ""}.get(p.get("gender"), "")
    profile = RuntimePersona(
        facts=_unique(
            [
                f"{p['name']}{_topic(p['name'])} {p['age']}세 {gender} {p['job']}이다.",
                p.get("background", ""),
            ]
        ),
        lifeAndTastes=_unique(p.get("lifeAndTastes", [])),
        disposition=_unique(
            list(p["coreTraits"])
            + [p.get("contrastTrait", "")]
            + [t["behavior"] for t in p.get("selectedTraits", [])]
            + [sheet.card.stance]
        ),
        wantsAndFears=_unique(p.get("wantsAndFears", [])),
        readingAndTension=_unique(
            [sheet.choice.attention, sheet.choice.interpretationPriority] + p.get("misreadings", [])
        ),
        choices=_unique(_choice_lines(sheet)),
        # D-0090: 말투는 기획 말투 확정 결과 한 칸이 소유한다(MD-1.4).
        # 성격 시트 말버릇 칸은 검토·내보내기용이다.
        voice=voice or _unique([p.get("voiceSummary", "")]),
        # D-0089: 공동 기억·약속·관찰 규칙은 공유 프레임이 소유한다(MD-1.4). 인물의 한계만 남긴다.
        boundaries=_unique(p.get("boundaries", [])),
    )
    text, sections = _render(plan, profile, rules_text, None)
    if any(term in text for term in FORBIDDEN):
        raise ValueError("actor prompt contains authoring metadata or examples")
    return text, sections


#: D-0091 분량 원칙: 선택 칸 머리에 둔다. 대부분의 턴은 평소 모습으로 답한다.
BASE_RATE_LINE = (
    "대부분의 턴은 위의 평소 모습과 아래 기본 대응으로 답한다. 아래 경향은 그 계기가 지금 대화에 "
    "실제로 있을 때만 나오고, 계기가 없는 턴에 끌어오거나 여러 상황에 되풀이하지 않는다."
)


def _ledger_line(t) -> str:
    line = (
        f"{_bare(t.trigger)} → {_bare(t.behavior)}. {_bare(t.nearMiss)}에는 이 경향을 쓰지 않는다."
    )
    if t.rarity == "rare":
        line += " 대화 전체에서 드물게 나온다."
    return line


def compose_from_ledger(plan, ledger, *, rules_text, voice=None):
    """D-0091: 특질 장부에서 조립한다. 한 특질은 한 칸에 한 번만 들어간다(MD-1.4)."""
    p = _raw(plan)
    gender = {"female": "여성", "male": "남성", "other": ""}.get(p.get("gender"), "")
    profile = RuntimePersona(
        facts=_unique(
            [
                f"{p['name']}{_topic(p['name'])} {p['age']}세 {gender} {p['job']}이다.",
                p.get("background", ""),
            ]
        ),
        lifeAndTastes=_unique(p.get("lifeAndTastes", [])[:5]),
        disposition=_unique(ledger.disposition),
        wantsAndFears=_unique([ledger.coreTension]),
        readingAndTension=_unique([ledger.reading]),
        choices=_unique(
            [BASE_RATE_LINE, "특별한 단서가 없을 때 → " + _bare(ledger.defaultResponse) + "."]
            + [_ledger_line(t) for t in ledger.traits]
        ),
        voice=voice or _unique([p.get("voiceSummary", "")]),
        boundaries=_unique(p.get("boundaries", [])),
    )
    text, sections = _render(plan, profile, rules_text, None)
    if any(term in text for term in FORBIDDEN):
        raise ValueError("actor prompt contains authoring metadata or examples")
    return text, sections
