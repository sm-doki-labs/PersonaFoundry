"""사람이 쓴 기획 씨앗을 단조 증가하는 sd revision으로 고정한다."""

from __future__ import annotations

import fcntl
import re

from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import next_rev, read_json, write_once_json
from character_factory_poc.contracts.planning import PlanSeed
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s3_plan.common import appearance_input

_UNSET = object()


class SeedConflict(ValueError):
    """A second writer changed the immutable seed while the editor was open."""


def _seed_paths(ctx: Context, cid: str):
    folder = ctx.character_dir(cid) / "s3-plan" / "seeds"
    return sorted(
        (p for p in folder.glob("sd*.json") if re.fullmatch(r"sd\d+", p.stem)),
        key=lambda p: int(p.stem[2:]),
    )


def write_seed(
    ctx: Context, cid: str, fields: dict, *, trait_ids=None, expected_seed_rev=_UNSET
) -> PlanSeed:
    """비운 성별은 승인 외모 범위에서 채우고 기존 씨앗은 보존한다."""
    folder = ctx.character_dir(cid) / "s3-plan" / "seeds"
    raw = dict(fields)
    from character_factory_poc.stages.s3_plan.trait_recommendations import (
        resolve_traits,
        verify_selected_traits,
    )

    if trait_ids is not None:
        raw["selectedTraits"] = [dump(t) for t in resolve_traits(trait_ids)]
    if not raw.get("gender"):
        appearance = appearance_input(ctx, cid)
        gender = (appearance or {}).get("scope", {}).get("characterGender")
        if gender in {"female", "male"}:
            raw["gender"] = gender
    if not isinstance(raw.get("personality"), str) or not raw["personality"].strip():
        raise ValueError("성격을 한 단어 이상 입력해 주세요.")
    folder.mkdir(parents=True, exist_ok=True)
    state = ctx.state(cid)
    # State transitions use this same lock; re-read while holding it so a stage cannot
    # become RUNNING between the protection check and the immutable seed write.
    with state._locked(), (folder / ".seed.lock").open("a") as lock:
        state._reload()
        if state.stage("s3").status in {"RUNNING", "AWAITING_HUMAN", "APPROVED"} or any(
            stage.status == "RUNNING" for stage in state.state.stages.values()
        ):
            raise SeedConflict("기획을 실행하거나 검토 중입니다. 수정 요청 뒤 설정을 바꿔 주세요.")
        fcntl.flock(lock, fcntl.LOCK_EX)
        paths = _seed_paths(ctx, cid)
        actual = paths[-1].stem if paths else None
        if expected_seed_rev is not _UNSET and actual != expected_seed_rev:
            raise SeedConflict("다른 화면에서 설정이 바뀌었습니다. 최신 설정을 다시 불러와 주세요.")
        number = max(int(next_rev(folder, "sd")[2:]), int(paths[-1].stem[2:]) + 1 if paths else 1)
        raw.update(characterId=cid, seedRev=f"sd{number}")
        seed: PlanSeed = validate("plan-seed-v1", raw)  # type: ignore[assignment]
        verify_selected_traits(seed.selectedTraits)
        write_once_json(folder / f"{seed.seedRev}.json", dump(seed))
    return seed


_LABEL = r"[^\n:：]*[:：][ \t]*(.+)"


def seed_fields_from_brief(text: str) -> dict:
    """D-0080: 페르소나 우선 브리프를 씨앗으로 옮긴다.

    브리프 원문 전체를 notes에 그대로 보존하고, 성격·나이·성별·직업만 표시된 줄에서 뽑는다.
    뽑지 못한 칸은 비워 두며 변형 저작이 notes를 근거로 채운다.
    """
    body = text.strip()
    if not body:
        raise ValueError("브리프가 비어 있다")

    def labelled(*labels: str) -> str:
        for label in labels:
            m = re.search(re.escape(label) + _LABEL, body)
            if m and m.group(1).strip():
                return m.group(1).strip()
        return ""

    personality = labelled("핵심 성격", "성격", "분위기 키워드")
    if not personality:
        lines = [ln.strip().lstrip("-*").strip() for ln in body.splitlines()]
        personality = next((ln for ln in lines if ln and not ln.startswith("#")), body)
    fields: dict = {"personality": personality[:300], "notes": body}
    who = labelled("캐릭터 성별", "성별")
    if any(w in who for w in ("남성", "남자")):
        fields["gender"] = "male"
    elif any(w in who for w in ("여성", "여자")):
        fields["gender"] = "female"
    age = re.search(r"(\d{2})\s*세", who or body)
    if age and int(age.group(1)) >= 18:
        fields["age"] = int(age.group(1))
    job = labelled("직업", "하는 일")
    if job:
        fields["job"] = job[:120]
    return fields


def load_latest_seed(ctx: Context, cid: str) -> PlanSeed | None:
    """번호가 가장 큰 씨앗을 읽는다. 아직 쓰지 않았으면 None이다."""
    paths = _seed_paths(ctx, cid)
    if not paths:
        return None
    return validate("plan-seed-v1", read_json(paths[-1]))  # type: ignore[return-value]
