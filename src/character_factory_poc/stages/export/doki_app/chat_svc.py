"""패키지 → chat-svc 콘텐츠 트리 조각.

형식은 chat-svc `data/`의 파일 규칙(`content_cli.loader`·`domain/content/*`가 검증하는 모델)과
`scripts/db_ops.content_release publish`의 적재 전 검증을 읽고 이 프로젝트 코드로 다시 적었다.
다른 저장소 코드는 import하지 않는다.

조각에는 우리 캐릭터의 정의 파일과 포인터 매니페스트 하나만 담는다. 런타임 공용 자산
(prompt frame·model config)은 저장소의 것을 revision으로 가리킨다. 대상 저장소의 `data/`
복사본 위에 이 조각을 덮고 포인터를 합쳐 publish한다.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from character_factory_poc.contracts.release import Chapter, CharacterPackage
from character_factory_poc.stages.export.doki_app.naming import (
    chapter_uid,
    character_uid,
    relative_file,
    revision_prefix,
    slug_for,
)

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

EVIDENCE_COMPILERS = {
    "builtin:evidence-pipeline-v1",
    "builtin:evidence-pipeline-v2",
    "builtin:evidence-pipeline-v3",
    "builtin:evidence-pipeline-v4",
    "builtin:evidence-pipeline-v5",
    "builtin:interview-editor-v2",
}
EVIDENCE_HEADERS = (
    "FACTS",
    "LIFE_AND_TASTES",
    "DISPOSITION",
    "WANTS_AND_FEARS",
    "READING_AND_TENSION",
    "CHOICES",
    "VOICE",
    "KNOWS_AND_LIMITS",
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
    # D-0219: 미션 3개 뒤 자유 통화. 관문·평가·정산 없이 연인 단계에서 이어진다(서지안 4번과 같다).
    4: {
        "entry": "DATING",
        "target": "DATING",
        "dialoguePolicy": "free-chat-v1",
        "mode": "FREE_CHAT",
    },
}

#: 자유 통화 챕터의 장면 배경 키(scene.backgrounds). 통화 장면이 하나라 하나만 둔다.
FREE_CHAT_BACKGROUND = "CALL"
FREE_CHAT_TURN_BLOCK = (
    "[FREE_CHAT_TURN]\n"
    "발화자: {character_name}\n"
    "사용자의 방금 입력에 담긴 실제 내용과 요청부터 네 말로 직접 받는다. 그 뒤 자연스러울 때만 "
    "네 생활이나 현재 장면의 다른 소재를 꺼낸다. 이 통화는 정해진 결말이나 목표가 없는 편한 "
    "통화다. 상황이 맞으면 다음에 이야기하고 싶은 것을 먼저 꺼내도 된다. 현재 장면과 관계 "
    "프로파일을 지키고, 사용자의 말·행동·감정·선택이나 둘의 공유 과거를 근거 없이 덧쓰지 "
    "않는다. 청자 대우법은 현재 관계 프로파일의 지시를 따른다."
)
FREE_CHAT_OPENING_BLOCK = (
    "[FREE_CHAT_OPENING_TURN]\n"
    "사용자는 아직 이 통화에서 말하지 않았다. 사용자의 말·행동·생각을 만들어 내지 않는다.\n"
    "두 사람은 이미 여러 번 통화한 사이다. 모르는 사람처럼 인사하지 않고, 이전 대화와 통화가 "
    "있으면 그 흐름을 이어받아 {character_name}이 먼저 건네는 실제 대사 한 턴만 쓴다.\n"
    "청자 대우법은 관계 프로파일의 지시를 따르고, 안전 경계를 지킨다."
)


def is_free_chat(chapter_no: int) -> bool:
    return _SLOTS.get(chapter_no, {}).get("mode") == "FREE_CHAT"


def free_chat_suffix(chapters) -> str:
    """자유 통화 챕터가 붙은 판의 quest revision 꼬리(D-0219). 없으면 예전 이름 그대로다."""
    return "-fc" if any(is_free_chat(c.chapterNo) for c in chapters) else ""


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
    prefix = revision_prefix(package.characterId, package.packageRev, twin=bool(package.twin))
    persona_rev = f"{prefix}-r1"
    # 이름 있는 대화 경로를 담는 번들과 그 상위 참조만 새 revision으로 발행한다.
    version = "v2" if package.twin and package.twin.servingRoute else "v1"
    # D-0219: chat-svc 는 넣은 캐릭터 버전을 지우지 않는다. 4번 자유 통화가 붙은 판은 챕터 목록이
    # 달라 같은 이름으로 다시 보내면 거절되므로 이름을 나눈다.
    quest_rev = f"{prefix}-quest-{version}" + free_chat_suffix(package.chapters)
    sheet = _read_json(relative_file(package_dir, package.persona.traitSheet))
    scene = _scene_facts(package, package_dir)
    prompt = relative_file(package_dir, package.persona.longPrompt).read_text("utf-8")
    evidence = _evidence_sections(package, package_dir, prompt)
    persona = (
        _evidence_persona(package, slug, persona_rev, evidence)
        if evidence is not None
        else _persona(package, slug, persona_rev, sheet)
    )
    if evidence is not None:
        # Relationship profiles and writer contracts must not reintroduce S7 guesses either.
        voice = "\n".join(evidence["voice"])
        sheet = {
            "choice": {"primaryResponse": "\n".join(evidence["choices"])},
            "card": {
                "stance": "\n".join(evidence["disposition"]),
                "dialogueHabits": {"order": voice, "directness": voice},
            },
        }

    files: dict[str, dict[str, Any]] = {f"personas/{persona_rev}.json": persona}
    mapping: list[tuple[str, str, str]] = [
        (
            "persona.longPrompt (evidence-pipeline-v1)"
            if evidence is not None
            else "profile + persona.traitSheet",
            f"chat-svc personas/{persona_rev}.json(character-persona-v6 여덟 섹션)",
            "긴 프롬프트를 여덟 섹션으로 나눠 적는다",
        )
    ]
    dialogue_model = DIALOGUE_MODEL
    if package.twin:
        adopted, route = package.sft.adoptedBinding, package.twin.servingRoute
        if not adopted or (adopted == "LONG_BASE") != (route is None):
            raise ValueError("모티브 G8 채택 대상과 패키지 서빙 경로가 일치하지 않는다")
        if route:
            dialogue_model = f"{prefix}-dialogue-{version}"
            files[f"models/{dialogue_model}.json"] = {
                "configVersion": dialogue_model,
                "servingRoute": route,
                "provider": "openai",
                "endpoint": "openai-chat-completions",
                "baseUrl": None,
                "apiKeyEnv": package.twin.apiKeyEnv or "TWIN_SERVING_API_KEY",
                "model": package.twin.servingModel or route,
                "reasoningEffort": "none",
                "temperature": None,
                "maxOutputTokens": 600,
                "timeoutSeconds": 60,
                "maxRetries": 0,
                "store": False,
            }
        mapping.append(
            (
                "sft.adoptedBinding",
                "chat-svc dialogue.modelConfigRevision",
                f"{dialogue_model} (배포에 등록한 {route} 경로로 연결해요)"
                if route
                else dialogue_model,
            )
        )
    speech_level = _persona_speech_level(prompt, sheet)
    bindings: list[dict[str, str]] = []
    chapter_uids: dict[str, str] = {}
    for chapter in sorted(package.chapters, key=lambda c: c.chapterNo):
        slot = _SLOTS[chapter.chapterNo]
        key = f"ACF-{slug.upper()}-{chapter.chapterId.upper()}"
        uid_text = str(chapter_uid(package.characterId, chapter.chapterId))
        chapter_uids[chapter.chapterId] = uid_text
        asset_rev = f"{prefix}-{chapter.chapterId}-context-v1"
        bundle_rev = f"{prefix}-{chapter.chapterId}-bundle-{version}"
        definition_rev = f"{prefix}-{chapter.chapterId}-{version}"
        profile_rev = f"{prefix}-{chapter.chapterId}-r1"
        facts = scene[chapter.chapterId]
        files[f"chapters/{asset_rev}.json"] = _chapter_asset(asset_rev, key, chapter, facts)
        files[f"split_prompt_bundles/{bundle_rev}.json"] = _bundle(
            prefix, chapter, facts, sheet, bundle_rev, dialogue_model
        )
        if slot.get("mode") == "FREE_CHAT":
            files[f"chapter_definitions/{definition_rev}.json"] = _free_definition(
                definition_rev, key, chapter, slot, asset_rev, bundle_rev
            )
        else:
            files[f"chapter_definitions/{definition_rev}.json"] = _definition(
                definition_rev, key, chapter, slot, asset_rev, bundle_rev
            )
        files[f"relationship_profiles/{profile_rev}.json"] = _profile(
            slug, chapter, key, profile_rev, slot, facts, sheet, package.profile.name, speech_level
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
            (
                "chapters[].chapterNo",
                "chat-svc chapters 순서(1~3 gate 있는 챕터, 4 자유 통화)",
                "",
            ),
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
        "sft.trainingRuns (학습 실행 기록은 패키지에서 참조한다)"
        if package.twin
        else "sft.* (chat-svc 콘텐츠 트리에 학습 결과 칸이 없다)",
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


def _evidence_sections(package: CharacterPackage, root: Path, prompt: str) -> dict | None:
    """Use only package-pinned compiler identity, never infer it from prose headers.

    S11 may omit the private prompt pair. In that case it must manifest-list
    persona/prompt-compiler.json with systemRulesRef, personaVersion and the
    SHA256 of the public longPrompt bytes. No source/review files are followed.
    """
    from character_factory_poc.stages.s11_release.presentation import CHAT_DISCLOSURE

    documents = {}
    for rel in ("persona/prompt-compiler.json", "persona/prompt-pair.json"):
        path = relative_file(root, rel)
        if path.exists() or any(item.path == rel for item in package.files):
            try:
                documents[rel] = _read_json(path)
            except (OSError, ValueError) as exc:
                raise ValueError("evidence compiler metadata is unreadable") from exc
    metadata = documents.get("persona/prompt-compiler.json")
    if metadata is not None and metadata.get("systemRulesRef") not in EVIDENCE_COMPILERS:
        raise ValueError("evidence compiler metadata has an unsupported marker")
    if not any(doc.get("systemRulesRef") in EVIDENCE_COMPILERS for doc in documents.values()):
        return None

    def pinned(rel):
        matches = [item for item in package.files if item.path == rel]
        if len(matches) != 1:
            raise ValueError("evidence compiler input is not pinned in package.files")
        data = relative_file(root, rel).read_bytes()
        if hashlib.sha256(data).hexdigest() != matches[0].sha256 or len(data) != matches[0].bytes:
            raise ValueError("evidence compiler input hash mismatch")
        return data

    public_digest = hashlib.sha256(pinned(package.persona.longPrompt)).hexdigest()
    for rel, doc in documents.items():
        pinned(rel)
        if doc.get("systemRulesRef") not in EVIDENCE_COMPILERS:
            raise ValueError("evidence compiler metadata disagrees")
        if doc.get("personaVersion") != package.persona.personaVersion:
            raise ValueError("evidence compiler persona revision mismatch")
        if rel.endswith("prompt-compiler.json"):
            if set(doc) != {"systemRulesRef", "personaVersion", "longPromptSha256"}:
                raise ValueError("evidence compiler metadata has unexpected fields")
            if doc["longPromptSha256"] != public_digest:
                raise ValueError("evidence public prompt hash mismatch")
        else:
            original = doc.get("long") or {}
            text = original.get("text")
            if (
                doc.get("characterId") != package.characterId
                or not isinstance(text, str)
                or hashlib.sha256(text.encode()).hexdigest() != original.get("sha256")
            ):
                raise ValueError("evidence source pair identity or hash mismatch")
            if prompt.rstrip() not in {text.rstrip(), text.rstrip() + "\n\n" + CHAT_DISCLOSURE}:
                raise ValueError("evidence public prompt differs from source pair")

    body = prompt.rstrip()
    disclosure = body.endswith("\n\n" + CHAT_DISCLOSURE)
    if disclosure:
        body = body[: -len("\n\n" + CHAT_DISCLOSURE)]
    first = re.search(r"^\[FACTS\]$", body, re.M)
    if first is None or not body[: first.start()].strip():
        raise ValueError("evidence prompt needs a preamble and eight sections")
    preamble = body[: first.start()].strip()
    text = body[first.start() :]
    headers = list(re.finditer(r"^\[([^\]\n]+)\][ \t]*$", text, re.M))
    if tuple(match[1] for match in headers) != EVIDENCE_HEADERS:
        raise ValueError("evidence prompt sections are missing, duplicated or out of order")
    sections = {}
    for i, (match, field) in enumerate(zip(headers, PERSONA_SECTIONS, strict=True)):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        value = text[match.end() : end].strip()
        if not value:
            raise ValueError("evidence prompt section is empty")
        sections[field] = [value]
    sections["boundaries"] = [preamble, *sections["boundaries"]]
    if disclosure:
        sections["boundaries"].append(CHAT_DISCLOSURE)
    return sections


def _evidence_persona(package, slug, revision, sections):
    # The target requires a positive numeric age; do not silently invent age 20.
    age = re.fullmatch(r"\s*(\d{1,3})\s*(?:세|살)?\s*", package.profile.age)
    if age is None or not 1 <= int(age[1]) <= 120:
        raise ValueError("evidence persona needs an explicit age for the target schema")
    return {
        "schemaVersion": "character-persona-v6",
        "personaId": slug,
        "revision": revision,
        "displayName": package.profile.name,
        "identity": {
            "age": int(age[1]),
            "occupation": package.profile.job.strip() or "미상",
            "homeBase": "미상",
        },
        "qualityScenarioIds": [f"{slug}-{chapter.chapterId}" for chapter in package.chapters],
        **sections,
    }


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
    start = facts.get("chapterStart")
    if start:
        # D-0089: 공장이 인물별로 만든 챕터 시작 설정을 그대로 쓴다.
        return {
            "chapterAssetId": revision,
            "chapterId": chapter_key,
            "sceneFacts": _clean(start["sceneFacts"]),
            "sceneBoundaries": _clean(start["sceneBoundaries"]),
            "relationshipCanon": _clean(facts.get("relationshipCanon") or []),
            "activityCandidates": [],
        }
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


def _free_definition(
    revision: str,
    chapter_key: str,
    chapter: Chapter,
    slot: dict[str, Any],
    asset_rev: str,
    bundle_rev: str,
) -> dict[str, Any]:
    """D-0219: 관문·평가·정산이 없는 자유 통화 챕터. chat-svc FREE_CHAT 규칙을 따른다."""
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
            "backgrounds": {FREE_CHAT_BACKGROUND: asset_rev},
        },
        "runtime": {
            "mode": "FREE_CHAT",
            "entryStage": slot["entry"],
            "targetStage": slot["target"],
            "initialState": None,
            "dialoguePolicyId": slot["dialoguePolicy"],
            "terminalAction": None,
            "gate": None,
            "completionEvents": [],
            "settlementRuleSetVersion": None,
            "metricCatalogVersion": None,
        },
        "splitPromptBundleRevision": bundle_rev,
    }


def _persona_speech_level(prompt: str, sheet: dict) -> str:
    from character_factory_poc.stages.s7_traits.check import _plan_speech_level

    # S11 패키지는 기획서를 복사하지 않는다. S8이 보존한 말투 요약만 읽고 예시는 제외한다.
    in_voice = False
    descriptions = []
    for line in prompt.splitlines():
        if line in {"[PERSONA / VOICE]", "## PERSONA / VOICE"}:
            in_voice = True
        elif in_voice:
            if line.startswith(("[", "## ", "말투 예시:")):
                break
            descriptions.append(line)
    habits = (sheet.get("card") or {}).get("dialogueHabits") or {}
    for description in [
        *descriptions,
        *habits.values(),
        (sheet.get("choice") or {}).get("expressionIntensity", ""),
    ]:
        # "존댓말 대신 반말", "반말은 쓰지 않는다"에서 배제된 등급을 채택하지 않는다.
        described = re.sub(
            r"(?:존댓말|존대|해요체|합쇼체|하십시오체|합니다체|반말|해체)"
            r"(?:[을를은는]?\s*(?:대신|말고|아니라|쓰지 않|사용하지 않)|이? 아닌)",
            "",
            description,
        )
        level = _plan_speech_level(described)
        if level:
            return "CASUAL" if level == "casual" else "POLITE"
    return "POLITE"


def _chapter_speech(goal: str, default: str) -> tuple[str, str]:
    # 목표에 말 놓기를 제안하거나 친해진다는 표현만으로 전환을 확정하지 않는다.
    switch = r"(?:말을? 놓(?:는다|기로 한다)|반말(?:을 쓴다|로 (?:말한다|바꾼다|전환한다)))"
    for sentence in re.split(r"[.!?\n]", goal):
        clause = sentence.strip()
        if default == "POLITE" and re.fullmatch(
            r".+(?:면|때만|경우에만)\s*,?\s*(?:서로 )?" + switch, clause
        ):
            return "FLEXIBLE", clause + "."
        if re.fullmatch(
            r"(?:(?:두 사람은|둘은|서로|이제|편하게|처음부터|이 장면부터|이번 통화부터) )*"
            + switch,
            clause,
        ):
            return "CASUAL", "반말을 유지한다."
    return default, "반말을 유지한다." if default == "CASUAL" else "존댓말을 유지한다."


def _profile(
    slug: str,
    chapter: Chapter,
    chapter_key: str,
    revision: str,
    slot: dict[str, Any],
    facts: dict[str, Any],
    sheet: dict[str, Any],
    name: str,
    persona_level: str | None = None,
) -> dict[str, Any]:
    choice = sheet.get("choice") or {}
    card = sheet.get("card") or {}
    habits = card.get("dialogueHabits") or {}
    experiences = card.get("experiences") or []
    start = (facts.get("chapterStart") or {}).get("relationship")
    if start:
        # D-0089: 틀 문장 대신 인물별로 저작한 관계 설정(MD-5.5~5.7). 말높임도 고정하지 않는다.
        return {
            "schemaVersion": "chapter-relationship-profile-v3",
            "profileId": f"{slug}-{chapter.chapterId}",
            "revision": revision,
            "personaId": slug,
            "chapterId": chapter_key,
            "appliesToStage": slot["entry"],
            "entryPosture": _clean(start["entryPosture"]),
            "addresseeStance": start["addresseeStance"],
            "speechLevel": start["speechLevel"],
            "initiativePolicy": start["initiativePolicy"],
            "enabledLoopRefs": [],
            "loopModifiers": [],
            "expressionDelta": _clean(start["expressionDelta"]),
            "sceneWant": start["sceneWant"],
            "presenceReason": start["presenceReason"],
            "speakingWay": str(habits.get("directness") or choice.get("expressionIntensity") or ""),
            "moodRange": dict(start["moodRange"]),
            "trustedStory": start.get("trustedStory"),
        }
    meeting = str(facts.get("meetingContext") or chapter.intro or chapter.title)
    scene_facts = _clean(facts.get("sceneFacts") or [])
    speaking = str(habits.get("directness") or choice.get("expressionIntensity") or "짧게 말한다")
    level, register = _chapter_speech(
        chapter.goal, persona_level or _persona_speech_level("", sheet)
    )
    stance = (
        "지금까지 나눈 대화에 맞춰 호칭과 거리를 정한다."
        if slot["entry"] != "STRANGER"
        else "첫 통화에서는 말의 속도와 거리를 조금씩 맞춰 간다."
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
        "addresseeStance": f"{stance} {name}의 말투: {register}",
        "speechLevel": level,
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
    dialogue_model: str = DIALOGUE_MODEL,
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
            "",
            # chat-svc split-frame-r5 계열은 frame의 reasonSemantics를 이 머리말 아래에 넣는다
            # (2026-11-07 원격 최신 기준, 없으면 평가 작업이 거절한다).
            f"[OUTPUT: {ASSESSMENT_SCHEMA}]",
            "schemaVersion, reasons(최대 3개), flagCandidates, blockerCandidates, "
            "topicEventCandidates(최대 3개), meaningful만 반환한다.",
            "",
            "[RELATIONSHIP_EVIDENCE]",
            "- 자리·시간 확인 같은 장면 운영 질문과 의례적 안부는 무변화다.",
            "- 같은 계열의 감탄이나 칭찬이 반복되면 첫 한 건만 reason으로 평가한다.",
            "- 상대를 알아가려는 질문이나 자기 공개로 확장될 때만 새 긍정 reason이다.",
            "- 반복해서 인격을 깎아내리거나 몰아붙이는 발화는 PRESSURE_OR_HOSTILITY다.",
            "",
            "[TOPIC_EVIDENCE]",
            "- 이 챕터는 topic 사건을 만들지 않는다.",
            "- topicEventCandidates는 비운다.",
        ]
    )
    final = (
        "게임 엔진은 이미 결과를 확정했다. 결과를 재판단하지 않고, 확정된 행동과 모순되지 않는 "
        "캐릭터의 발화만 쓴다. 내부 결과명·수치를 대사에서 말하지 않는다."
    )
    slot = _SLOTS[chapter.chapterNo]
    if slot.get("mode") == "FREE_CHAT":
        # D-0219: 자유 통화는 평가·마무리 역할이 없고, 턴·첫마디 지시를 번들에 싣는다.
        return {
            "schemaVersion": "split-prompt-bundle-v3",
            "splitPromptBundleRevision": revision,
            "frameRevision": PROMPT_FRAME_REVISION,
            "dialogue": {
                "promptVersion": f"{slug}-{chapter.chapterId}-dialogue-writer-v1",
                "responseSchemaVersion": "character-dialogue-text-v1",
                "modelConfigRevision": dialogue_model,
                "contract": dialogue,
                "turnBlock": FREE_CHAT_TURN_BLOCK,
                "openingBlock": FREE_CHAT_OPENING_BLOCK,
            },
            "assessment": None,
            "finalDialogue": None,
            "compilerOptions": {
                "writerRegister": "v3",
                "assessorVocabulary": ASSESSOR_VOCABULARY,
            },
        }
    return {
        "schemaVersion": "split-prompt-bundle-v3",
        "splitPromptBundleRevision": revision,
        "frameRevision": PROMPT_FRAME_REVISION,
        "dialogue": {
            "promptVersion": f"{slug}-{chapter.chapterId}-dialogue-writer-v1",
            "responseSchemaVersion": "character-dialogue-text-v1",
            "modelConfigRevision": dialogue_model,
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
            "models": "configVersion",
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
        gated = [
            (revisions.get(c.get("chapterRevision")) or {}).get("runtime", {}).get("gate")
            is not None
            for c in chapters
        ]
        # chat-svc: gate 있는 챕터 정확히 3개로 시작하고, 뒤에는 자유 통화만 붙는다(D-0219).
        if gated[:3] != [True, True, True] or any(gated[3:]):
            problems.append(f"{rel}: gate 있는 챕터 3개 뒤에 자유 통화만 붙어야 한다")
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
        mood = payload.get("moodRange") or {}
        if runtime.get("gate") is not None and set(mood) != {"down", "start", "middle", "top"}:
            problems.append(f"{rel}: affinity gate 챕터는 moodRange 네 단계가 필요하다")
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
        definition = next(
            (
                item
                for item in revisions.values()
                if item.get("splitPromptBundleRevision") == payload.get("splitPromptBundleRevision")
                and "runtime" in item
            ),
            {},
        )
        free = (definition.get("runtime") or {}).get("mode") == "FREE_CHAT"
        for role in ("dialogue",) if free else ("dialogue", "assessment", "finalDialogue"):
            block = payload.get(role)
            if not isinstance(block, dict):
                problems.append(f"{rel}: {role}가 없다")
            elif not roles <= set(block):
                problems.append(f"{rel}: {role} 칸이 모자란다")
            elif not str(block.get("contract") or "").strip():
                problems.append(f"{rel}: {role}.contract가 비었다")
        model = (payload.get("dialogue") or {}).get("modelConfigRevision")
        if model and model != DIALOGUE_MODEL and f"models/{model}.json" not in files:
            problems.append(f"{rel}: 캐릭터별 대화 모델 설정 파일이 없다")
        dialogue_block = payload.get("dialogue") or {}
        if free and not (dialogue_block.get("turnBlock") and dialogue_block.get("openingBlock")):
            problems.append(f"{rel}: 자유 통화 번들에 turnBlock·openingBlock이 없다")
        if free and (payload.get("assessment") is not None or payload.get("finalDialogue")):
            problems.append(f"{rel}: 자유 통화 번들에는 평가·마무리 역할이 없어야 한다")
        if not free and "turnBlock" in dialogue_block:
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
