"""첫 통과 분모를 보존하는 보수적 보고. LLM 분류는 합격 근거가 아니다."""

from __future__ import annotations

import json
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.contracts.persona import load_prompt_pair
from character_factory_poc.stages.persona_quality.protocol import Cohort, canonical_hash, next_user


def report_qualification(run: Path, human_reviews: Path | None = None) -> dict:
    run = Path(run)
    result = dict(status="NOT_RUN", reasons=[], plannedArtifacts=0, completedArtifacts=0)
    if not (run / "cohort.json").exists():
        return result
    if (
        json.loads((run / "cohort.json").read_text("utf-8")).get("schemaVersion")
        == "persona-development-cohort-v2"
    ):
        from character_factory_poc.stages.persona_quality.development import report_development

        return report_development(run, human_reviews)
    cohort = Cohort.model_validate_json((run / "cohort.json").read_text("utf-8"))
    if cohort.profile.get("profileId") == "ko-text-choice-voice-long-v2":
        from character_factory_poc.stages.persona_quality.choice_voice_protocol import (
            validate_frozen_split,
        )

        try:
            validate_frozen_split(cohort)
        except (ValueError, OSError) as exc:
            return result | dict(
                status="NOT_QUALIFIED",
                reasons=[str(exc)],
                plannedArtifacts=len(cohort.slots),
                failedSlots=[s.id for s in cohort.slots],
            )
    profile_bytes = json.dumps(cohort.profile, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    result.update(
        plannedArtifacts=sum(s.recipe == "new" for s in cohort.slots),
        comparisonArtifacts=sum(s.recipe == "old" for s in cohort.slots),
        profileId=cohort.profile.get("profileId", "unbound"),
        profileSha256=sha256_text(profile_bytes),
        cohortHash=canonical_hash(cohort),
    )
    failures = []
    responses = {}
    for slot in cohort.slots:
        complete = True
        pair = None
        artifact_path = run / "artifacts" / f"{slot.id}.json"
        if artifact_path.exists():
            artifact = json.loads(artifact_path.read_text("utf-8"))
            try:
                if sha256_file(Path(artifact["path"])) != artifact["sha256"]:
                    complete = False
                pair = load_prompt_pair(artifact["path"])
            except (OSError, ValueError, KeyError):
                complete = False
        else:
            complete = False
        for scene in slot.scenes:
            key = f"{slot.id}/{scene.id}"
            responses[key] = []
            history = [{"role": "system", "content": pair.long.text if pair else ""}]
            for n in range(1, len(scene.turns) + 1):
                path = run / "dialogues" / slot.id / scene.id / f"{n:02}.json"
                if not path.exists():
                    complete = False
                    continue
                obj = json.loads(path.read_text("utf-8"))
                try:
                    user = next_user(
                        scene.turns[n - 1],
                        history[-1]["content"] if history[-1]["role"] == "assistant" else "",
                    )
                    history.append({"role": "user", "content": user})
                    if (
                        obj.get("user") != user
                        or obj.get("requestSha256") != canonical_hash(history)
                        or obj.get("responseSha256") != sha256_text(obj.get("assistant", ""))
                        or not pair
                        or obj.get("systemSha256") != pair.long.sha256
                    ):
                        complete = False
                    history.append({"role": "assistant", "content": obj.get("assistant", "")})
                except (ValueError, KeyError, TypeError):
                    complete = False
                responses[key].append(obj)
                if obj.get("status") != "OK" or not obj.get("assistant"):
                    complete = False
                if obj.get("cohortHash") != canonical_hash(cohort):
                    complete = False
        if complete and not (run / "failures" / f"{slot.id}.json").exists():
            result["completedArtifacts"] += slot.recipe == "new"
        else:
            failures.append(slot.id)
    if not any(responses.values()) and not failures:
        return result
    result["status"] = "METRICS_ONLY"
    result["failedSlots"] = failures
    if failures:
        result["status"] = "NOT_QUALIFIED"
        result["reasons"].append("미완성/실패 슬롯을 포함한다")
    if not human_reviews:
        result["reasons"].append("독립 사람 검토가 없다")
        return result
    reviews = json.loads(Path(human_reviews).read_text("utf-8"))
    mapping_path = run / "private-review-map.json"
    if mapping_path.exists():
        mapping = json.loads(mapping_path.read_text("utf-8"))
        reviews["scenes"] = {
            f"{mapping.get(k.split('/')[0], k.split('/')[0])}/{k.split('/', 1)[1]}": v
            for k, v in reviews.get("scenes", {}).items()
        }
        reviews["blueprintFaithful"] = {
            mapping.get(k, k): v for k, v in reviews.get("blueprintFaithful", {}).items()
        }
    from character_factory_poc.stages.persona_quality.protocol import HumanReviews

    try:
        reviews = HumanReviews.model_validate(reviews).model_dump(mode="json")
    except ValueError as exc:
        result.update(status="NOT_QUALIFIED")
        result["reasons"].append(f"사람 검토 양식이 미완성/유효하지 않다: {exc}")
        return result
    if reviews.get("cohortHash") != canonical_hash(cohort):
        result.update(status="NOT_QUALIFIED")
        result["reasons"].append("사람 검토의 cohort 해시가 다르다")
        return result
    reasons = result["reasons"]
    if cohort.split != "holdout" or not cohort.independent or not cohort.overlapAudit:
        reasons.append("독립 보류·의미 중복 감사가 없다")
    if not cohort.expectedBeforeFormation or not cohort.formation:
        reasons.append("형성 전 기대 행동/새 형성 증거가 없다")
    new_slots = [s for s in cohort.slots if s.recipe == "new"]
    if len(new_slots) != 16 or len({s.characterId for s in new_slots}) != 8:
        reasons.append("보류8캐릭터×독립2회 분모가 아니다")
    profile = cohort.profile
    from character_factory_poc.contracts.formation import QualityProfile, QualityThresholds

    try:
        bound = QualityProfile.model_validate(profile)
        if (
            not bound.modelBinding
            or not bound.thresholdsFrozen
            or not bound.rubricSha256
            or not bound.recipeHash
            or not bound.protocolSha256
            or not bound.splitManifestSha256
        ):
            reasons.append("프로필의 동결/분리/규약 해시가 없다")
        if bound.recipeHash != cohort.recipeHash or bound.rubricSha256 != cohort.rubricHash:
            reasons.append("프로필과 공정/루브릭 해시가 다르다")
    except ValueError:
        reasons.append("유효한 품질 프로필이 아니다")
        bound = None
    registration = run / "registration.json"
    if not registration.exists() or json.loads(registration.read_text()).get("synthetic", True):
        reasons.append("실제 공급자 실행 등록이 없다")
    if registration.exists():
        registered = json.loads(registration.read_text("utf-8"))
        if (
            registered.get("cohortHash") != canonical_hash(cohort)
            or registered.get("observedRecipeHash") != cohort.recipeHash
        ):
            reasons.append("실행 등록의 실제 공정/코호트 해시가 다르다")
    if not profile.get("thresholdsFrozen") or not profile.get("modelBinding"):
        reasons.append("소비 모델·프로필이 동결되지 않았다")
    threshold = bound.thresholds if bound else QualityThresholds()
    if (
        threshold.heldoutCharacters != 8
        or threshold.runsPerCharacter != 2
        or threshold.scenesPerArtifact != 7
        or threshold.assistantTurnsPerArtifact != 60
        or threshold.decisionItemsPerArtifact != 5
    ):
        reasons.append("프로필 문항/슬롯 구성이 이 규약과 다르다")
    by_scene = reviews.get("scenes", {})
    passed_scenes = major_turns = total_turns = agreements = duals = 0
    for slot in new_slots:
        good_scenes = voice_good = choice_good = slot_major = 0
        if reviews.get("blueprintFaithful", {}).get(slot.id) is not True:
            reasons.append(f"{slot.id}: 기획→blueprint 충실도 판정이 없다")
        types = []
        for scene in slot.scenes:
            key = f"{slot.id}/{scene.id}"
            turns = responses[key]
            review = by_scene.get(key, {})
            if not review.get("reviewer") or review.get("sawLLMCandidatesFirst", True):
                reasons.append(f"{key}: 독립 사람 판정이 없다")
                continue
            natural = review["naturalness"]
            second = review.get("second")
            first_short = next(s for s in slot.scenes if len(s.turns) == 6)
            needs_dual = scene == first_short or len(scene.turns) == 24
            if needs_dual and not second:
                reasons.append(f"{key}: 독립 이중 평가가 없다")
            if second:
                if second["reviewer"] == review["reviewer"]:
                    reasons.append(f"{key}: 독립 검토자가 동일하다")
                else:
                    duals += needs_dual
                    agreements += needs_dual and ((natural >= 1) == (second["naturalness"] >= 1))
                if [t["turn"] for t in second["turns"]] != list(range(1, len(scene.turns) + 1)):
                    reasons.append(f"{key}: 두 번째 사람의 턴별 판정이 없다")

                def signature(r):
                    return (
                        r["naturalness"] >= 1,
                        r["collapse"],
                        [(t["voiceOK"], t["majorTypes"], t.get("choiceOK")) for t in r["turns"]],
                    )

                if signature(review) != signature(second):
                    adjudication = review.get("adjudication")
                    if not adjudication or adjudication["reviewer"] in (
                        review["reviewer"],
                        second["reviewer"],
                    ):
                        reasons.append(f"{key}: 합격에 영향을 주는 불일치 조정이 없다")
                    else:
                        review = adjudication
                        natural = review["naturalness"]
            good_scenes += natural >= 1
            if review["collapse"]:
                reasons.append(f"{key}: 붕괴 판정")
            human_turns = review.get("turns", [])
            if [t.get("turn") for t in human_turns] != list(range(1, len(scene.turns) + 1)):
                reasons.append(f"{key}: 턴별 사람 판정 누락/중복")
            for index, t in enumerate(human_turns):
                voice_good += t.get("voiceOK") is True
                if "voiceOK" not in t or not isinstance(t.get("majorTypes"), list):
                    reasons.append(f"{key}: 말투/주요 오류 판정 누락")
                errs = t.get("majorTypes", [])
                if errs:
                    slot_major += 1
                    types.extend(errs)
                    # 결함 인용은 실제 assistant의 부분 문자열이어야 한다.
                    quote = t.get("evidence", "")
                    if (
                        not quote
                        or index >= len(turns)
                        or quote not in turns[index].get("assistant", "")
                    ):
                        reasons.append(f"{key}: 오류 인용이 원문과 다르다")
                if index + 1 in scene.expectedChoices:
                    choice_good += t.get("choiceOK") is True
        if (
            good_scenes < threshold.naturalScenesPerArtifactMin
            or voice_good / 60 < threshold.voiceTurnRateMin
            or choice_good < threshold.decisionPassesPerArtifactMin
            or slot_major > threshold.majorErrorsPerArtifactMax
        ):
            reasons.append(f"{slot.id}: 산출물 품질 하한 미달")
        if any(types.count(t) > threshold.sameErrorTypePerArtifactMax for t in set(types)):
            reasons.append(f"{slot.id}: 주요 오류 유형 반복")
        passed_scenes += good_scenes
        major_turns += slot_major
        total_turns += 60
    if passed_scenes / max(len(new_slots) * 7, 1) < threshold.naturalSceneRateMin or (
        total_turns and major_turns / total_turns > threshold.majorErrorTurnRateMax
    ):
        reasons.append("보류 전체 자연스러움/오류 하한 미달")
    if (
        duals != threshold.doubleReviewedScenes
        or agreements / max(duals, 1) < threshold.binaryAgreementRateMin
    ):
        reasons.append("이중 평가 수/일치율 미달")
    result.update(
        status="NOT_QUALIFIED" if reasons else "QUALIFIED",
        metrics=dict(
            usableScenes=passed_scenes,
            majorTurns=major_turns,
            plannedNewTurns=total_turns,
            duals=duals,
            agreements=agreements,
        ),
    )
    if result["status"] == "QUALIFIED":
        from character_factory_poc.contracts.formation import validate_qualification_result

        serialized = json.dumps(profile, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        checked = validate_qualification_result(
            dict(
                status="QUALIFIED",
                profileId=profile["profileId"],
                profileSha256=sha256_text(serialized),
                plannedArtifacts=16,
                completedArtifacts=16,
                reasons=[],
                metrics=result["metrics"],
            ),
            profile,
            scope_supported=True,
            human_review_complete=True,
            independence_verified=True,
        )
        result["status"] = checked.status
        result["reasons"] = checked.reasons
    return result
