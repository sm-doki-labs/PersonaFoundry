"""기획 v2의 씨앗 일치·행동 대비·이름 유출을 결정론적으로 검사한다."""

from __future__ import annotations

import json
from pathlib import Path

from character_factory_poc.common.call_context import appearance_reading_problems
from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.common.names import MIN_NAME_CHARS, normalize_name
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import read_json
from character_factory_poc.common.textstats import looks_like_bare_adjectives, normalize_text
from character_factory_poc.contracts.planning import CharacterPlanV2, PlanSeed, PlanVariantsOutput


def name_guard(names: list[str]) -> list[dict]:
    """작업 공간에는 순위 인물의 이름 대신 정규화 길이와 해시만 전달한다."""
    return [
        {"length": len(key), "sha256": sha256_text(key)}
        for name in names
        if len(key := normalize_name(name)) >= MIN_NAME_CHARS
    ]


def check_plan_v2(seed: PlanSeed | None, guard: list[dict]):
    """사람의 G3 편집 뒤에는 seed=None으로 명시적인 수정 값을 허용한다."""

    def check(plan: CharacterPlanV2) -> list[str]:
        problems = []
        if seed is not None:
            if seed.job and seed.job not in plan.job:
                problems.append("job: 씨앗의 job을 포함해야 한다")
            if seed.age is not None and seed.age != plan.age:
                problems.append("age: 씨앗의 age와 같아야 한다")
            if seed.gender is not None and seed.gender != plan.gender:
                problems.append("gender: 씨앗의 gender와 같아야 한다")
        for i, trait in enumerate(plan.coreTraits):
            if looks_like_bare_adjectives(trait):
                problems.append(f"coreTraits[{i}]: 형용사 나열 대신 행동을 서술한다")
        if looks_like_bare_adjectives(plan.contrastTrait):
            problems.append("contrastTrait: 형용사 나열 대신 행동을 서술한다")
        # D-0082: 영상통화 카메라 관찰 규칙과 부딪히는 외모·신체 상태 읽기를 막는다.
        reading = {
            "coreTraits": " ".join(plan.coreTraits),
            "contrastTrait": plan.contrastTrait,
            "choices": " ".join(c.situation + " " + c.firstMove for c in plan.choices),
            "misreadings": " ".join(plan.misreadings),
            "voiceSummary": plan.voiceSummary,
            "voiceExamples": " ".join(plan.voiceExamples),
        }
        for field, value in reading.items():
            problems.extend(appearance_reading_problems(field, value))
        text = normalize_name(json.dumps(dump(plan), ensure_ascii=False))
        # find_name_leaks와 같은 정규화·부분 문자열 비교이며 이름 원문은 저장하지 않는다.
        for length in {g["length"] for g in guard}:
            hashes = {g["sha256"] for g in guard if g["length"] == length}
            if any(
                sha256_text(text[i : i + length]) in hashes for i in range(len(text) - length + 1)
            ):
                problems.append("순위 목록의 인물 이름이 기획에 유출됐다(D-0017)")
                break
        return problems

    return check


def check_variants(seed: PlanSeed, count: int, guard: list[dict]):
    def check(output: PlanVariantsOutput) -> list[str]:
        problems = []
        plans = output.variants
        if len(plans) != count:
            problems.append(f"variants: 정확히 {count}개가 필요하다")
        situations = []
        for i, plan in enumerate(plans, 1):
            problems.extend(f"v{i}.{p}" for p in check_plan_v2(seed, guard)(plan))
            keys = [normalize_text(c.situation) for c in plan.choices]
            if len(set(keys)) != len(keys):
                problems.append(f"v{i}.choices: 상황을 중복하지 않는다")
            situations.append(
                {normalize_text(c.situation): normalize_text(c.firstMove) for c in plan.choices}
            )
        if situations:
            same = all(set(s) == set(situations[0]) for s in situations)
            if not same:
                problems.append("choices.situation: 모든 변형에서 같은 상황 집합을 사용한다")
            else:
                for situation in situations[0]:
                    moves = [s[situation] for s in situations]
                    if len(set(moves)) != len(moves):
                        problems.append(
                            f"choices.firstMove: 같은 상황 '{situation}'의 "
                            "첫 행동은 서로 달라야 한다"
                        )
        # axisNote도 승인 페이지로 전달되므로 이름 유출 검사를 함께 적용한다.
        if plans and output.axisNote:
            probe = plans[0].model_copy(update={"notes": output.axisNote})
            problems.extend(p for p in check_plan_v2(None, guard)(probe) if "이름" in p)
        return problems

    return check


def check_own(seed: PlanSeed, guard: list[dict], user_text: str):
    def check(plan: CharacterPlanV2) -> list[str]:
        problems = check_plan_v2(seed, guard)(plan)
        for field, evidence in plan.evidence.items():
            for ev in evidence:
                if ev.kind not in {"USER", "AGENT"}:
                    problems.append(f"evidence.{field}: 직접 쓴 값은 USER, 보완한 값은 AGENT다")
                elif ev.kind == "USER" and (not ev.quote or ev.quote not in user_text):
                    problems.append(f"evidence.{field}: USER quote는 사용자 원문의 인용이어야 한다")
        return problems

    return check


def codex_checks(stage: str, workspace: Path) -> tuple[str, list]:
    """registry가 연결할 s3-variants·s3-own 검사. API와 같은 입력·함수를 쓴다."""
    inputs = Path(workspace) / "inputs"
    seed = validate("plan-seed-v1", read_json(inputs / "seed.json"))
    guard = read_json(inputs / "name-guard.json")
    if stage == "s3-variants":
        count = read_json(inputs / "variant-count.json")
        return "plan-variants-output-v1", [check_variants(seed, count, guard)]
    if stage == "s3-own":
        text = (inputs / "user-text.md").read_text("utf-8")
        return "character-plan-v2", [check_own(seed, guard, text)]
    raise ValueError(f"S3 v2 검사가 없는 단계: {stage}")
