"""합성 캐릭터와 가짜 모델 응답. 실제 캐릭터·대화를 쓰지 않는다."""

from __future__ import annotations

import json
from importlib import resources

PLAN = {
    "name": "테스트 하늘",
    "age": 24,
    "job": "동네 책방 직원",
    "coreTraits": ["먼저 제안한다", "자기 기준을 지킨다"],
    "contrastTrait": "실제 잘못은 바로 인정한다",
    "chapters": [
        {"chapterId": "ch1", "scene": "비 오는 책방 창가", "relationStage": "지인"},
        {"chapterId": "ch2", "scene": "야시장 골목", "relationStage": "호감"},
        {"chapterId": "ch3", "scene": "새벽 버스 정류장", "relationStage": "강한 호감"},
    ],
}


def trait_sheet(cid: str, rev: str) -> dict:
    return {
        "schemaVersion": "trait-sheet-v1",
        "characterId": cid,
        "planRev": rev,
        "choice": {
            "attention": "상대의 말에서 감정보다 다음에 할 수 있는 행동을 먼저 본다.",
            "interpretationPriority": "자기 기준을 먼저 지키고 상대 감정은 그 다음에 받는다.",
            "primaryResponse": "먼저 제안한다. 상대가 거절하면 이유를 묻지 않고 다른 안을 낸다.",
            "expressionIntensity": "짧고 단정하게 말한다. 변명을 붙이지 않는다.",
            "switchConditions": [
                "'그냥 들어 줘'라고 하면 제안을 멈추고 듣는다. 거리는 유지한다.",
                "실제 잘못이 확인되면 짧게 인정하고 고친다.",
            ],
        },
        "card": {
            "stance": "친화적 주도형으로 요약한다. 먼저 움직이되 상대를 끌어들인다.",
            "bigFiveNotes": "미정",
            "expressedTraits": {
                "core": [
                    "먼저 제안한다. 상대가 망설이면 선택지를 둘로 줄여 준다.",
                    "자기 기준을 지킨다. 부탁이 기준에 어긋나면 이유 없이 거절한다.",
                ],
                "contrast": "실제 잘못은 바로 인정한다. 사과에 변명을 붙이지 않는다.",
            },
            "judgmentPriorities": [
                {
                    "value": "약속을 지키는 것",
                    "dilemma": "약속과 상대의 급한 부탁이 겹칠 때",
                    "choice": "약속을 먼저 지킨다",
                    "reason": "한 번 미루면 계속 밀린다고 본다",
                    "switch": "상대에게 실제 피해가 생기면 약속을 미룬다",
                },
                {
                    "value": "자기 시간",
                    "dilemma": "친해진 상대가 매일 보자고 할 때",
                    "choice": "주 2회로 정해 말한다",
                    "reason": "페이스가 무너지면 관계도 흔들린다고 본다",
                    "switch": "상대가 힘든 일이 있으면 그 주는 예외로 둔다",
                },
            ],
            "dialogueHabits": {
                "order": "결론을 먼저 말하고 이유는 물으면 짧게 붙인다.",
                "directness": "돌려 말하지 않는다. 싫으면 싫다고 한다.",
                "questions": "질문은 선택을 좁힐 때만 한다. 되묻기보다 제안이 먼저다.",
                "evidence": "근거는 한 문장으로 끝낸다. 길게 설명하지 않는다.",
                "lexicon": "'그럼 이렇게 하자', '됐고'를 자주 쓴다. 감탄사는 거의 없다.",
            },
            "situational": [
                {
                    "condition": "상대가 시험을 망쳤다고 한다",
                    "reaction": "위로보다 다음 시험 일정을 묻고 할 일을 나눈다",
                    "returnOrSwitch": "상대가 듣기만 원하면 제안을 멈춘다",
                },
                {
                    "condition": "칭찬을 받는다",
                    "reaction": "짧게 받고 화제를 돌린다",
                    "returnOrSwitch": "같은 칭찬이 반복되면 웃어넘긴다",
                },
                {
                    "condition": "부탁을 받는다",
                    "reaction": "기준에 맞으면 바로 수락하고 아니면 바로 거절한다",
                    "returnOrSwitch": "거절 뒤 상대가 이유를 물으면 한 문장으로 답한다",
                },
            ],
            "experiences": [
                {
                    "event": "고등학생 때 동아리 행사를 혼자 떠맡았다",
                    "interpretation": "먼저 움직이면 결국 내가 다 하게 된다고 느꼈다",
                    "habitLink": "그래서 제안할 때 역할을 둘로 나눠 상대 몫을 먼저 정한다",
                },
            ],
        },
        "references": [],
        "unresolved": ["card.bigFiveNotes"],
        "typeMappingAssumed": False,
    }


def prompter_output() -> dict:
    sections = json.loads(
        resources.files("character_factory_poc.resources")
        .joinpath("prompt-sections-v1.json")
        .read_text("utf-8")
    )["sections"]
    long = {}
    short = {}
    for s in sections:
        if s in ("SYSTEM_RULES", "OUTPUT"):
            long[s] = ""
            short[s] = ""
        else:
            long[s] = (
                f"{s} 긴 본문. 먼저 제안하고 자기 기준을 지킨다. 실제 잘못은 바로 인정한다. " * 3
            )
            short[s] = f"{s} 짧은 본문. 먼저 제안하고 기준을 지킨다."
    return {"long": long, "short": short}


# ---------------------------------------------------------------- S1 (D-0017)
# 이름은 전부 가상이다. 실제 인물·실제 순위를 쓰지 않는다.

RANKING = {
    "schemaVersion": "popularity-ranking-v2",
    "scope": {
        "characterGender": "female",
        "ageRange": "20s",
        "artStyle": "photoreal",
        "appearanceOrigin": "korean",
        "moodHints": ["청순", "시크"],
    },
    "lists": [
        {
            "listId": "actress-2026-10",
            "source": "합성 화제성 순위(테스트)",
            "category": "여자 배우",
            "period": "2026-10",
            "retrievedAt": "2026-10-20",
            "url": "",
            "entries": [
                {"rank": 1, "name": "가상 하윤"},
                {"rank": 2, "name": "가상 서아"},
                {"rank": 3, "name": "가상 지안"},
                {"rank": 4, "name": "가상 도연"},
                {"rank": 5, "name": "가상 유나"},
                {"rank": 6, "name": "가상 미르"},
                {"rank": 7, "name": "가상 채원"},
                {"rank": 8, "name": "가상 무명"},
            ],
        },
        {
            "listId": "girlgroup-2026-10",
            "source": "합성 화제성 순위(테스트)",
            "category": "걸그룹 멤버",
            "period": "2026-10",
            "retrievedAt": "2026-10-20",
            "url": "",
            "entries": [
                {"rank": 1, "name": "가상 리아"},
                {"rank": 2, "name": "가상 세린"},
                {"rank": 3, "name": "가상지안"},
                {"rank": 4, "name": "가상 나래"},
                {"rank": 5, "name": "가상 소율"},
                {"rank": 6, "name": "가상 예나"},
                {"rank": 7, "name": "가상 다온"},
            ],
        },
    ],
    "notes": "테스트용 합성 목록",
}

_GROUP_TAGS = {
    "A": {  # 청순
        "faceShape": "oval",
        "eyeShape": "large-double",
        "hairLength": "long",
        "hairColor": "black",
        "hairStyle": "straight",
        "bangs": "see-through",
        "skinTone": "fair",
        "styling": ["feminine"],
        "mood": ["innocent"],
    },
    "B": {  # 시크
        "faceShape": "small-v",
        "eyeShape": "upturned",
        "hairLength": "bob",
        "hairColor": "black",
        "hairStyle": "straight",
        "bangs": "none",
        "skinTone": "fair",
        "styling": ["minimal", "edgy"],
        "mood": ["chic"],
    },
    "C": {  # 건강미
        "faceShape": "round",
        "eyeShape": "almond",
        "hairLength": "medium",
        "hairColor": "light-brown",
        "hairStyle": "wavy",
        "bangs": "curtain",
        "skinTone": "tan",
        "styling": ["sporty", "casual"],
        "mood": ["healthy", "warm"],
    },
    "X": {  # 혼자 동떨어진 인물
        "faceShape": "square",
        "eyeShape": "monolid",
        "hairLength": "pixie",
        "hairColor": "vivid",
        "hairStyle": "curly",
        "bangs": "full",
        "skinTone": "medium",
        "styling": ["street", "y2k"],
        "mood": ["boyish", "mysterious"],
    },
}
_NAME_GROUP = {
    "가상하윤": "A",
    "가상서아": "A",
    "가상도연": "A",
    "가상채원": "A",
    "가상리아": "B",
    "가상세린": "B",
    "가상나래": "B",
    "가상예나": "B",
    "가상지안": "C",
    "가상유나": "C",
    "가상소율": "C",
    "가상다온": "C",
    "가상미르": "X",
}
_OVERRIDES = {
    "가상서아": {"hairStyle": "wavy"},
    "가상세린": {"skinTone": "light"},
    "가상소율": {"bangs": "unknown"},
    "가상다온": {"mood": ["healthy"]},
}


def scout_features(ranking: dict) -> dict:
    """가짜 Scout 출력. 그룹 A·B·C(각 4명), 동떨어진 1명, 모르는 1명(가상 무명)."""
    from character_factory_poc.common.names import normalize_name
    from character_factory_poc.stages.s1_reference.ranking import build_people, load_ranking

    people = build_people(load_ranking(ranking), 3)
    feats = []
    for p in people.people:
        key = normalize_name(p.name)
        group = _NAME_GROUP.get(key)
        if group is None:
            feats.append(
                {
                    "personId": p.personId,
                    "recognized": False,
                    "tags": {
                        "faceShape": "unknown",
                        "eyeShape": "unknown",
                        "hairLength": "unknown",
                        "hairColor": "unknown",
                        "hairStyle": "unknown",
                        "bangs": "unknown",
                        "skinTone": "unknown",
                        "styling": [],
                        "mood": [],
                    },
                    "confidence": {},
                    "note": "외모를 알지 못한다",
                }
            )
            continue
        tags = dict(_GROUP_TAGS[group]) | _OVERRIDES.get(key, {})
        feats.append(
            {
                "personId": p.personId,
                "recognized": True,
                "tags": tags,
                "confidence": {"hairColor": 0.6, "hairStyle": 0.7},
                "note": "",
            }
        )
    return {
        "schemaVersion": "appearance-features-v1",
        "vocabVersion": "appearance-tag-vocab-v1",
        "features": feats,
        "notes": "머리색은 시기마다 달라 확신도를 낮췄다.",
    }
