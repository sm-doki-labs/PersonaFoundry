"""패키지 → chat-svc 콘텐츠 트리 조각.

형식은 chat-svc `data/`의 파일 규칙(`content_cli.loader`·`domain/content/*`가 검증하는 모델)과
`scripts/db_ops.content_release publish`의 적재 전 검증을 읽고 이 프로젝트 코드로 다시 적었다.
다른 저장소 코드는 import하지 않는다.

조각에는 우리 캐릭터의 정의 파일과 포인터 매니페스트 하나만 담는다. 런타임 공용 자산
(prompt frame·model config)은 저장소의 것을 revision으로 가리킨다. 대상 저장소의 `data/`
복사본 위에 이 조각을 덮고 포인터를 합쳐 publish한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acf.contracts.release import Chapter, CharacterPackage
from acf.stages.export.doki_app.naming import chapter_uid, character_uid, relative_file, slug_for

#: chat-svc 현행 head(0028_authoring_project_locale)의 공용 자산 revision.
PROMPT_FRAME_REVISION = "split-frame-r5-v41"
DIALOGUE_MODEL = "dialogue-gemini-3-6-flash-native-minimal-v1"
ASSESSOR_MODEL = "assessor-gemini-3-6-flash-minimal-v1"
FINAL_MODEL = "final-dialogue-gemini-3-6-flash-minimal-v1"
ASSESSOR_VOCABULARY = "v5"
RULE_SET_VERSION = "relationship-rules-v3"
ASSESSMENT_SCHEMA = "turn-assessment-v3"

POINTER_MANIFEST = "content-pointers-v2.json"

PERSONA_SECTIONS = (
    "facts",
    "lifeAndTastes",
    "disposition",
    "wantsAndFears",
    "readingAndTension",
    "choices",
    "voice",
    "boundaries",
)

#: 챕터 자리별 런타임 계약(chat-svc 규칙표 이름). 챕터 구조는 코드가 소유하고,
#: 이 파일은 그 값을 고른다(D-0033의 ch1~ch3 자리).
_SLOTS: dict[int, dict[str, Any]] = {
    1: {
        "entry": "STRANGER",
        "target": "ACQUAINTANCE",
        "dialoguePolicy": "first-meeting-v1",
        "terminal": "USER_PROPOSE_ACTIVITY",
        "router": "ACTIVITY_INVITATION",
        "routerVersion": "first-meeting-final-proposal-router-v1",
        "passAct": "ACCEPT_WITH_CONDITION",
        "affinityTarget": 50,
    },
    2: {
        "entry": "ACQUAINTANCE",
        "target": "FLIRTING",
        "dialoguePolicy": "first-date-v1",
        "terminal": "USER_CONFIRM_MUTUAL_INTEREST",
        "router": "MUTUAL_INTEREST_CONFIRMATION",
        "routerVersion": "first-date-confirm-router-v2",
        "passAct": "ACCEPT",
        "affinityTarget": 50,
    },
    3: {
        "entry": "FLIRTING",
        "target": "DATING",
        "dialoguePolicy": "some-date-v1",
        "terminal": "USER_CONFESS",
        "router": "CONFESSION",
        "routerVersion": "some-date-confess-router-v1",
        "passAct": "ACCEPT",
        "affinityTarget": 55,
    },
}


@dataclass(frozen=True)
class ChatTree:
    files: dict[str, dict[str, Any]]
    mapping: list[tuple[str, str, str]]
    unmapped: list[str]
    persona_revision: str
    quest_revision: str
    chapter_uids: dict[str, str]


def build_tree(package: CharacterPackage, package_dir: Path) -> ChatTree:
    slug = slug_for(package.characterId)
    uid = str(character_uid(package.characterId))
    persona_rev = f"{slug}-r1"
    quest_rev = f"{slug}-quest-v1"
    sheet = _read_json(relative_file(package_dir, package.persona.traitSheet))
    scene = _scene_facts(package, package_dir)
    persona = _persona(package, slug, persona_rev, sheet)

    files: dict[str, dict[str, Any]] = {f"personas/{persona_rev}.json": persona}
    mapping: list[tuple[str, str, str]] = [
        (
            "profile + persona.traitSheet",
            f"chat-svc personas/{persona_rev}.json(character-persona-v6 여덟 섹션)",
            "긴 프롬프트를 여덟 섹션으로 나눠 적는다",
        )
    ]
    bindings: list[dict[str, str]] = []
    chapter_uids: dict[str, str] = {}
    for chapter in sorted(package.chapters, key=lambda c: c.chapterNo):
        slot = _SLOTS[chapter.chapterNo]
        key = f"ACF-{slug.upper()}-{chapter.chapterId.upper()}"
        uid_text = str(chapter_uid(package.characterId, chapter.chapterId))
        chapter_uids[chapter.chapterId] = uid_text
        asset_rev = f"{slug}-{chapter.chapterId}-context-v1"
        bundle_rev = f"{slug}-{chapter.chapterId}-bundle-v1"
        definition_rev = f"{slug}-{chapter.chapterId}-v1"
        profile_rev = f"{slug}-{chapter.chapterId}-r1"
        facts = scene[chapter.chapterId]
        files[f"chapters/{asset_rev}.json"] = _chapter_asset(asset_rev, key, chapter, facts)
        files[f"split_prompt_bundles/{bundle_rev}.json"] = _bundle(
            slug, chapter, facts, sheet, bundle_rev
        )
        files[f"chapter_definitions/{definition_rev}.json"] = _definition(
            definition_rev, key, chapter, slot, asset_rev, bundle_rev
        )
        files[f"relationship_profiles/{profile_rev}.json"] = _profile(
            slug, chapter, key, profile_rev, slot, facts, sheet, package.profile.name
        )
        bindings.append(
            {
                "chapterUid": uid_text,
                "chapterRevision": definition_rev,
                "profileRevision": profile_rev,
                "chapterSlug": f"{slug}-{chapter.chapterId}",
            }
        )

    files[f"quests/{quest_rev}.json"] = {
        "schemaVersion": "character-quest-v4",
        "questRevision": quest_rev,
        "characterUid": uid,
        "characterSlug": slug,
        "display": {
            "name": package.profile.name,
            "tagline": package.profile.tagline,
            "order": 90,
        },
        "personaRevision": persona_rev,
        "chapters": bindings,
    }
    files[f"pointers/{POINTER_MANIFEST}"] = {
        "schemaVersion": "content-pointer-manifest-v2",
        "pointers": [
            {
                "kind": "quest",
                "key": uid,
                "state": "ACTIVE",
                "revision": quest_rev,
                "locale": "ko",
            }
        ],
    }
    mapping.extend(
        [
            ("characterId", "chat-svc quest.characterUid", "결정적 uuid5. api-svc 시드와 같은 값"),
            ("profile.name", "chat-svc quest.display.name", ""),
            ("profile.tagline", "chat-svc quest.display.tagline", ""),
            ("persona.personaVersion", "chat-svc quest.personaRevision", ""),
            ("chapters[].chapterNo", "chat-svc chapters 순서(1~3, gate 있는 챕터)", ""),
            ("chapters[].title", "chat-svc chapter_definitions.display.title", ""),
            ("chapters[].goal", "chat-svc chapter_definitions.display.goalSummary", ""),
            (
                "chapters[].facts",
                "chat-svc chapters(sceneFacts·sceneBoundaries·relationshipCanon)",
                "",
            ),
            (
                "chapters[].intro",
                "chat-svc chapters(sceneFacts) + relationshipProfiles.presenceReason",
                "",
            ),
        ]
    )
    unmapped = [
        "persona.shortPrompt (chat-svc 콘텐츠 트리에 짧은 system 칸이 없다: SFT 입력 몫)",
        "sft.* (chat-svc 콘텐츠 트리에 학습 결과 칸이 없다)",
        "videos.* (chat-svc 콘텐츠는 대사·장면만 갖는다: api-svc 몫)",
        "chapters[].background (chat-svc CHAPTER 모드 배경 칸은 FREE_CHAT 전용)",
        "gates[] (대상 시스템에 관문 기록 표가 없다)",
    ]
    return ChatTree(
        files=files,
        mapping=mapping,
        unmapped=unmapped,
        persona_revision=persona_rev,
        quest_revision=quest_rev,
        chapter_uids=chapter_uids,
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 객체가 아니다: {path.name}")
    return payload


def _clean(items: list[Any]) -> list[str]:
    seen: list[str] = []
    for item in items:
        text = " ".join(str(item or "").split())
        if text and text not in seen:
            seen.append(text)
    return seen


def _scene_facts(package: CharacterPackage, package_dir: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for chapter in package.chapters:
        out[chapter.chapterId] = _read_json(relative_file(package_dir, chapter.facts))
    return out


def _persona(
    package: CharacterPackage, slug: str, revision: str, sheet: dict[str, Any]
) -> dict[str, Any]:
    profile = package.profile
    choice = sheet.get("choice") or {}
    card = sheet.get("card") or {}
    expressed = card.get("expressedTraits") or {}
    habits = card.get("dialogueHabits") or {}
    situations = card.get("situational") or []
    experiences = card.get("experiences") or []
    priorities = card.get("judgmentPriorities") or []

    facts = _clean(
        [
            f"{profile.name}은 {profile.age}살이고, {profile.job} 일을 한다."
            if profile.job
            else f"{profile.name}은 {profile.age}살이다.",
            profile.description,
            *[f"{e.get('event', '')} {e.get('interpretation', '')}" for e in experiences],
        ]
    ) or [f"{profile.name}은 {profile.tagline or profile.job or '평범한 하루를 사는 사람'}이다."]

    life = _clean(
        [
            f"쉬는 날에는 {profile.hobby}를 즐긴다." if profile.hobby else "",
            f"좋아하는 것: {profile.likes}." if profile.likes else "",
            *[f"'{tag}'라는 말로 자기 취향을 설명한다." for tag in profile.tags],
        ]
    ) or ["평범한 하루의 작은 취향을 오래 기억한다."]

    disposition = _clean(
        [
            str(choice.get("primaryResponse") or ""),
            str(choice.get("expressionIntensity") or ""),
            str(card.get("stance") or ""),
            *[str(item) for item in (expressed.get("core") or [])],
            str(expressed.get("contrast") or ""),
        ]
    ) or ["먼저 상대가 한 말을 정확히 듣고, 자기 방식으로 답한다."]

    wants = _clean(
        [
            *[str(p.get("reason") or "") for p in priorities],
            *[str(item) for item in (choice.get("switchConditions") or [])],
        ]
    ) or ["상대가 자기 말을 기억해 주기를 바란다."]

    tension = _clean(
        [
            *[f"{p.get('dilemma', '')}일 때 {p.get('choice', '')}를 고른다." for p in priorities],
            *[f"{s.get('condition', '')}이면 {s.get('reaction', '')}." for s in situations],
        ]
    ) or ["상대의 반응이 자기와 다를 때 자기만 앞서 간 것은 아닌지 먼저 살핀다."]

    choices = _clean(
        [
            str(choice.get("attention") or ""),
            str(choice.get("interpretationPriority") or ""),
            str(choice.get("primaryResponse") or ""),
            *[f"{p.get('value', '')}: {p.get('choice', '')}" for p in priorities],
        ]
    ) or ["말보다 실제로 지킨 행동을 먼저 본다."]

    voice = _clean(
        [
            str(habits.get("order") or ""),
            str(habits.get("directness") or ""),
            str(habits.get("questions") or ""),
            str(habits.get("evidence") or ""),
            str(habits.get("lexicon") or ""),
        ]
    ) or ["짧은 문장으로 담백하게 말한다."]

    boundaries = _clean(
        [
            f"{profile.name}은 상대가 직접 말하지 않은 사생활과 과거를 안다고 꾸미지 않는다.",
            f"싫어하는 것({profile.dislikes})을 이유로 상대를 몰아붙이지 않는다."
            if profile.dislikes
            else "",
            "고함·협박·반복 요구로 마음을 얻지 않는다.",
            *[str(item) for item in (choice.get("switchConditions") or [])],
        ]
    )

    sections = {
        "facts": facts,
        "lifeAndTastes": life,
        "disposition": disposition,
        "wantsAndFears": wants,
        "readingAndTension": tension,
        "choices": choices,
        "voice": voice,
        "boundaries": boundaries,
    }
    payload: dict[str, Any] = {
        "schemaVersion": "character-persona-v6",
        "personaId": slug,
        "revision": revision,
        "displayName": profile.name,
        "identity": {
            "age": _age(profile.age),
            "occupation": profile.job or "학생",
            "homeBase": _first_sentence(profile.description) or "서울",
        },
        "qualityScenarioIds": [f"{slug}-{chapter.chapterId}" for chapter in package.chapters],
        **sections,
    }
    return payload


def _age(value: str) -> int:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    age = int(digits) if digits else 20
    return age if 1 <= age <= 120 else 20


def _first_sentence(text: str) -> str:
    for part in str(text or "").replace("\n", " ").split(". "):
        if part.strip():
            return part.strip().rstrip(".")
    return ""


def _chapter_asset(
    revision: str, chapter_key: str, chapter: Chapter, facts: dict[str, Any]
) -> dict[str, Any]:
    scene_facts = _clean([facts.get("meetingContext"), *(facts.get("sceneFacts") or [])])[:5]
    canon = _clean(facts.get("relationshipCanon") or []) or _clean(
        [facts.get("meetingContext") or chapter.intro]
    )
    return {
        "chapterAssetId": revision,
        "chapterId": chapter_key,
        "sceneFacts": scene_facts or [chapter.intro or chapter.title],
        "sceneBoundaries": _clean(facts.get("sceneBoundaries") or [])
        or ["장면 밖 장소 이동과 행동 지문을 만들지 않는다."],
        "relationshipCanon": canon,
        "activityCandidates": [],
    }


def _definition(
    revision: str,
    chapter_key: str,
    chapter: Chapter,
    slot: dict[str, Any],
    asset_rev: str,
    bundle_rev: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": "chapter-definition-v2",
        "chapterRevision": revision,
        "chapterId": chapter_key,
        "display": {
            "title": chapter.title,
            "goalSummary": chapter.goal or chapter.title,
            "inputHint": "메시지를 입력하세요",
            "kernelReady": True,
        },
        "scene": {
            "sceneKey": f"{chapter_key}-SCENE",
            "chapterAssetRevision": asset_rev,
            "activityRevision": None,
            "meetingContexts": {},
        },
        "runtime": {
            "entryStage": slot["entry"],
            "targetStage": slot["target"],
            "initialState": {},
            "dialoguePolicyId": slot["dialoguePolicy"],
            "terminalAction": {
                "type": slot["terminal"],
                "routerStrategy": slot["router"],
                "routerVersion": slot["routerVersion"],
                "activityRevision": None,
            },
            "gate": {
                "terminalBlockers": [
                    "BOUNDARY_VIOLATION",
                    "HOSTILITY_UNRESOLVED",
                    "REPEATED_PRESSURE",
                ],
                "failBlockerCode": "FAIL_TERMINAL_BLOCKER",
                "phaseGate": None,
                "prerequisiteKind": None,
                "prerequisiteActivityRevision": None,
                "failPrerequisiteCode": "FAIL_PREREQUISITE_NOT_DISCLOSED",
                "minPositiveMeaningful": 4,
                "minDistinctReasons": 2,
                "requiredReasonCode": None,
                "readinessFailureCode": "FAIL_RELATIONSHIP_READINESS_UNMET",
                "noProposalFailureCode": "FAIL_NO_USER_PROPOSAL",
                "passCodes": [
                    "PASS_RELATIONSHIP_READINESS_MET",
                    "PASS_EVIDENCE_DIVERSITY_MET",
                ],
                "passAct": slot["passAct"],
                "affinity": {
                    "target": slot["affinityTarget"],
                    "categoryWeights": {
                        "INTEREST": 10000,
                        "CARE": 10000,
                        "CHARM": 10000,
                        "SINCERITY": 10000,
                        "CERTAINTY": 10000,
                    },
                    "rulesVersion": "affinity-rules-v2",
                },
            },
            "completionEvents": [f"CHAPTER_SETTLED:{chapter_key}"],
            "settlementRuleSetVersion": "affinity-settlement-rules-v1",
            "metricCatalogVersion": "affinity-metrics-v6",
        },
        "splitPromptBundleRevision": bundle_rev,
    }


def _profile(
    slug: str,
    chapter: Chapter,
    chapter_key: str,
    revision: str,
    slot: dict[str, Any],
    facts: dict[str, Any],
    sheet: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    choice = sheet.get("choice") or {}
    card = sheet.get("card") or {}
    habits = card.get("dialogueHabits") or {}
    experiences = card.get("experiences") or []
    meeting = str(facts.get("meetingContext") or chapter.intro or chapter.title)
    scene_facts = _clean(facts.get("sceneFacts") or [])
    speaking = str(habits.get("directness") or choice.get("expressionIntensity") or "짧게 말한다")
    stance = (
        "이미 아는 사이로 편하게 반말을 유지한다."
        if slot["entry"] != "STRANGER"
        else "처음 만난 사이로, 말의 속도와 거리를 조금씩 맞춰 간다."
    )
    trusted = None
    if experiences:
        event = str(experiences[0].get("event") or "")
        trusted = f"{event} 이야기는 이 사람을 믿게 되면 꺼낼 수 있다." if event else None
    return {
        "schemaVersion": "chapter-relationship-profile-v3",
        "profileId": f"{slug}-{chapter.chapterId}",
        "revision": revision,
        "personaId": slug,
        "chapterId": chapter_key,
        "appliesToStage": slot["entry"],
        "entryPosture": _clean([f"현재 장면: {meeting}", *(scene_facts[:1])]),
        "addresseeStance": f"{name}과 사용자는 {stance}",
        "speechLevel": "CASUAL",
        "initiativePolicy": (
            f"{str(choice.get('primaryResponse') or '먼저 할 말을 하나 고른다')}. "
            "상대가 거절하면 같은 요청을 반복하지 않고, 관계를 끝내겠다는 말로 압박하지 않는다."
        ),
        "enabledLoopRefs": [],
        "loopModifiers": [],
        "expressionDelta": _clean(
            [str(card.get("stance") or ""), str(choice.get("expressionIntensity") or "")]
        )
        or ["상대의 온도가 낮으면 같은 크기의 반응을 한 번만 청한다."],
        "sceneWant": f"{chapter.goal or chapter.title} 쪽으로 대화를 이어 가고 싶다.",
        "presenceReason": meeting,
        "speakingWay": speaking,
        "moodRange": {
            "down": f"지금은 {chapter.title}에서 조금 위축되어 있다. 말수가 적다.",
            "start": f"지금은 {chapter.title}의 대화를 천천히 시작하는 중이다.",
            "middle": f"지금은 {chapter.title}에서 서로를 조금씩 알아 가는 중이다.",
            "top": f"지금은 {chapter.title}의 끝에 가까워졌다. 마음을 조심스럽게 드러낸다.",
        },
        "trustedStory": trusted,
    }


def _bundle(
    slug: str,
    chapter: Chapter,
    facts: dict[str, Any],
    sheet: dict[str, Any],
    revision: str,
) -> dict[str, Any]:
    habits = (sheet.get("card") or {}).get("dialogueHabits") or {}
    scene_facts = " / ".join(_clean(facts.get("sceneFacts") or []))
    boundaries = " / ".join(_clean(facts.get("sceneBoundaries") or []))
    voice = str(habits.get("order") or "짧은 문장으로 담백하게 말한다")
    dialogue = "\n".join(
        [
            f"[DIALOGUE_SERVICE_CONTRACT: {chapter.chapterId}]",
            f"- 현재 장면: {scene_facts or chapter.intro}.",
            f"- 말투: {voice}",
            "- 사용자의 말·행동·표정을 대신 만들지 않고 캐릭터의 대사만 쓴다.",
            "- 사용자가 직접 말하지 않은 사실을 안다고 꾸미지 않는다.",
            "- 관계 수치·호감 판정·게임 목표·평가 결과를 대사에서 설명하지 않는다.",
            "- 한 턴은 1~3문장으로 끝내고, 문장 수를 채우려고 말을 보태지 않는다.",
            f"- 장면 경계: {boundaries or '장면 밖 장소 이동을 만들지 않는다.'}",
        ]
    )
    assessment = "\n".join(
        [
            "[TURN_ASSESSOR]",
            "- 이미 확정된 현재 한 턴의 의미만 분류한다. 다음 전개를 쓰지 않는다.",
            "- reasons는 최대 3개, topicEventCandidates는 최대 3개까지만 적는다.",
            "- 누적 점수·챕터 결과·관계 확정 여부를 만들지 않는다.",
        ]
    )
    final = (
        "게임 엔진은 이미 결과를 확정했다. 결과를 재판단하지 않고, 확정된 행동과 모순되지 않는 "
        "캐릭터의 발화만 쓴다. 내부 결과명·수치를 대사에서 말하지 않는다."
    )
    slot = _SLOTS[chapter.chapterNo]
    return {
        "schemaVersion": "split-prompt-bundle-v3",
        "splitPromptBundleRevision": revision,
        "frameRevision": PROMPT_FRAME_REVISION,
        "dialogue": {
            "promptVersion": f"{slug}-{chapter.chapterId}-dialogue-writer-v1",
            "responseSchemaVersion": "character-dialogue-text-v1",
            "modelConfigRevision": DIALOGUE_MODEL,
            "contract": dialogue,
        },
        "assessment": {
            "promptVersion": f"{slug}-{chapter.chapterId}-turn-assessor-v1",
            "responseSchemaVersion": ASSESSMENT_SCHEMA,
            "modelConfigRevision": ASSESSOR_MODEL,
            "contract": assessment,
            "relationshipRuleSetVersion": RULE_SET_VERSION,
        },
        "finalDialogue": {
            "promptVersion": f"{slug}-{chapter.chapterId}-final-dialogue-writer-v1",
            "responseSchemaVersion": "final-chapter-dialogue-v1",
            "modelConfigRevision": FINAL_MODEL,
            "contract": final,
            "responseFocus": f"{chapter.title} 장면의 마무리",
            "responseContexts": {
                slot["passAct"]: "확정된 결과를 캐릭터의 말투로 담담하게 받아들인다.",
                "DEFER": "아직 더 알아 가야 한다는 뜻을 분명히 하되 비난하지 않는다.",
                "DECLINE": "마음이 같지 않다는 뜻을 정중하지만 분명하게 전한다.",
            },
        },
        "compilerOptions": {"writerRegister": "v3", "assessorVocabulary": ASSESSOR_VOCABULARY},
    }


def validate_content_tree(files: dict[str, dict[str, Any]]) -> list[str]:
    """chat-svc 파일 규칙을 이 프로젝트 코드로 다시 검사한다(적재 전 확인)."""
    problems: list[str] = []
    revisions: dict[str, dict[str, Any]] = {}
    for rel, payload in files.items():
        stem = Path(rel).stem
        kind = rel.split("/", 1)[0]
        revision_field = {
            "personas": "revision",
            "relationship_profiles": "revision",
            "quests": "questRevision",
            "chapter_definitions": "chapterRevision",
            "chapters": "chapterAssetId",
            "split_prompt_bundles": "splitPromptBundleRevision",
        }.get(kind)
        if revision_field is None:
            continue
        revision = payload.get(revision_field)
        if not isinstance(revision, str) or revision != stem:
            problems.append(f"{rel}: 파일명과 {revision_field}가 다르다")
        revisions[revision] = payload
    problems.extend(_persona_problems(files, revisions))
    problems.extend(_quest_problems(files, revisions))
    problems.extend(_profile_problems(files, revisions))
    problems.extend(_bundle_problems(files, revisions))
    problems.extend(_pointer_problems(files, revisions))
    return problems


def _persona_problems(files, revisions) -> list[str]:
    problems: list[str] = []
    for rel, payload in files.items():
        if not rel.startswith("personas/"):
            continue
        if payload.get("schemaVersion") != "character-persona-v6":
            problems.append(f"{rel}: character-persona-v6가 아니다")
            continue
        for section in PERSONA_SECTIONS:
            items = payload.get(section)
            if not isinstance(items, list) or not items or any(not str(i).strip() for i in items):
                problems.append(f"{rel}: {section}가 비었다")
        identity = payload.get("identity") or {}
        if not isinstance(identity.get("age"), int) or identity["age"] <= 0:
            problems.append(f"{rel}: identity.age가 정수가 아니다")
        for key in ("occupation", "homeBase"):
            if not str(identity.get(key) or "").strip():
                problems.append(f"{rel}: identity.{key}가 비었다")
        scenarios = payload.get("qualityScenarioIds") or []
        if not scenarios or len(scenarios) != len(set(scenarios)):
            problems.append(f"{rel}: qualityScenarioIds가 비었거나 중복이다")
    return problems


def _quest_problems(files, revisions) -> list[str]:
    problems: list[str] = []
    for rel, payload in files.items():
        if not rel.startswith("quests/"):
            continue
        if payload.get("schemaVersion") != "character-quest-v4":
            problems.append(f"{rel}: character-quest-v4가 아니다")
            continue
        for key in ("characterUid", "characterSlug", "personaRevision"):
            if not str(payload.get(key) or "").strip():
                problems.append(f"{rel}: {key}가 비었다")
        display = payload.get("display") or {}
        if set(display) != {"name", "tagline", "order"}:
            problems.append(f"{rel}: display 칸이 다르다")
        if display.get("order") is None:
            problems.append(f"{rel}: display.order가 null이다(컴파일이 거절한다)")
        persona_rev = payload.get("personaRevision")
        if persona_rev not in revisions:
            problems.append(f"{rel}: personaRevision 대상을 찾지 못했다")
        chapters = payload.get("chapters") or []
        if len(chapters) != 3:
            problems.append(f"{rel}: gate 있는 챕터 3개가 아니다")
        uids = [chapter.get("chapterUid") for chapter in chapters]
        if len(uids) != len(set(uids)):
            problems.append(f"{rel}: chapterUid가 중복이다")
        for chapter in chapters:
            for key in ("chapterRevision", "profileRevision"):
                if chapter.get(key) not in revisions:
                    problems.append(f"{rel}: {key} 대상을 찾지 못했다({chapter.get(key)})")
            definition = revisions.get(chapter.get("chapterRevision")) or {}
            scene = definition.get("scene") or {}
            asset = revisions.get(scene.get("chapterAssetRevision")) or {}
            profile = revisions.get(chapter.get("profileRevision")) or {}
            if asset.get("chapterId") != definition.get("chapterId"):
                problems.append(f"{rel}: 챕터 자산의 chapterId가 다르다")
            if profile.get("chapterId") != definition.get("chapterId"):
                problems.append(f"{rel}: 관계 프로필의 chapterId가 다르다")
    return problems


def _profile_problems(files, revisions) -> list[str]:
    fields = {
        "schemaVersion",
        "profileId",
        "revision",
        "personaId",
        "chapterId",
        "appliesToStage",
        "entryPosture",
        "addresseeStance",
        "speechLevel",
        "initiativePolicy",
        "enabledLoopRefs",
        "loopModifiers",
        "expressionDelta",
        "sceneWant",
        "presenceReason",
        "speakingWay",
        "moodRange",
        "trustedStory",
    }
    problems: list[str] = []
    for rel, payload in files.items():
        if not rel.startswith("relationship_profiles/"):
            continue
        if payload.get("schemaVersion") != "chapter-relationship-profile-v3":
            problems.append(f"{rel}: chapter-relationship-profile-v3가 아니다")
            continue
        if set(payload) != fields:
            problems.append(f"{rel}: 칸이 v3와 다르다")
        mood = payload.get("moodRange") or {}
        if set(mood) != {"down", "start", "middle", "top"}:
            problems.append(f"{rel}: affinity gate 챕터는 moodRange 네 단계가 필요하다")
        if payload.get("enabledLoopRefs"):
            problems.append(f"{rel}: v6 persona에는 loop가 없어 enabledLoopRefs가 비어야 한다")
        definition = next(
            (
                item
                for item in revisions.values()
                if item.get("chapterId") == payload.get("chapterId") and "runtime" in item
            ),
            None,
        )
        if definition is None:
            problems.append(f"{rel}: chapterId에 맞는 챕터 정의가 없다")
            continue
        runtime = definition.get("runtime") or {}
        if payload.get("appliesToStage") != runtime.get("entryStage"):
            problems.append(f"{rel}: appliesToStage가 챕터 entryStage와 다르다")
    return problems


def _bundle_problems(files, revisions) -> list[str]:
    roles = {"promptVersion", "responseSchemaVersion", "modelConfigRevision", "contract"}
    problems: list[str] = []
    for rel, payload in files.items():
        if not rel.startswith("split_prompt_bundles/"):
            continue
        if payload.get("schemaVersion") != "split-prompt-bundle-v3":
            problems.append(f"{rel}: split-prompt-bundle-v3가 아니다")
            continue
        if not payload.get("frameRevision"):
            problems.append(f"{rel}: frameRevision이 없다")
        for role in ("dialogue", "assessment", "finalDialogue"):
            block = payload.get(role)
            if not isinstance(block, dict):
                problems.append(f"{rel}: {role}가 없다")
            elif not roles <= set(block):
                problems.append(f"{rel}: {role} 칸이 모자란다")
            elif not str(block.get("contract") or "").strip():
                problems.append(f"{rel}: {role}.contract가 비었다")
        if "turnBlock" in (payload.get("dialogue") or {}):
            problems.append(f"{rel}: CHAPTER 번들에 turnBlock이 있다")
        assessment = payload.get("assessment") or {}
        if assessment and assessment.get("relationshipRuleSetVersion") != RULE_SET_VERSION:
            problems.append(f"{rel}: assessorVocabulary와 rule set이 짝이 아니다")
        if assessment and assessment.get("responseSchemaVersion") != ASSESSMENT_SCHEMA:
            problems.append(f"{rel}: assessment 응답 스키마가 v5 어휘와 짝이 아니다")
        compiler = payload.get("compilerOptions") or {}
        if set(compiler) != {"writerRegister", "assessorVocabulary"}:
            problems.append(f"{rel}: compilerOptions 칸이 다르다")
    return problems


def _pointer_problems(files, revisions) -> list[str]:
    problems: list[str] = []
    manifest = files.get(f"pointers/{POINTER_MANIFEST}")
    if manifest is None:
        return ["포인터 매니페스트가 없다"]
    if set(manifest) != {"schemaVersion", "pointers"}:
        problems.append("포인터 매니페스트 칸이 다르다")
    for entry in manifest.get("pointers") or []:
        if set(entry) != {"kind", "key", "state", "revision", "locale"}:
            problems.append("포인터 항목 칸이 다르다")
            continue
        if entry["state"] != "ACTIVE" or entry["revision"] not in revisions:
            problems.append("포인터 대상 revision이 이 조각에 없다")
        if entry["kind"] == "quest":
            quest = revisions.get(entry["revision"]) or {}
            if entry["key"] != quest.get("characterUid"):
                problems.append("quest 포인터 key와 characterUid가 다르다")
    return problems


def write_tree(root: Path, tree: ChatTree) -> dict[str, str]:
    """조각을 파일로 쓴다. 반환값은 상대 경로 → sha256."""
    import hashlib

    digests: dict[str, str] = {}
    for rel, payload in sorted(tree.files.items()):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
        data = text.encode("utf-8")
        path.write_bytes(data)
        digests[rel] = hashlib.sha256(data).hexdigest()
    return digests


__all__ = [
    "POINTER_MANIFEST",
    "PROMPT_FRAME_REVISION",
    "ChatTree",
    "build_tree",
    "validate_content_tree",
    "write_tree",
]
