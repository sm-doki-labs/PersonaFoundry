"""흐름 시드(D-0138, 한소민 장기 대화 시범 gen-r1의 시드 방식).

원문을 읽는 쪽은 시드 작성 모델 하나뿐이다. 시드는 장면을 캐릭터의 생활로 옮긴 시작 상황, 상대 인물,
사건 4~8개, 원문 말의 리듬 설명, 옮기면 안 되는 것을 담고 원문 문장은 담지 않는다(10글자 겹침 검사).
작가에게는 시드만 넘긴다. 시드는 revision의 seeds/에 원본 해시와 함께 남겨 다시 쓰기·대량 작성에서
같은 시드를 쓴다.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import Field

from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.schema import dump, register
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.common import Strict
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.stages.s9_data import checks, deck
from character_factory_poc.stages.s9_data import plan as plan_mod

if TYPE_CHECKING:
    from character_factory_poc.stages.s9_data.samples import Slot, WriteSession

SEED_CONTRACT = "data-seed-output-v1"
_SAFE = re.compile(r"[^A-Za-z0-9_.~-]+")


class FlowSeed(Strict):
    sourceId: str
    scene: str = Field(min_length=5, max_length=200)
    counterpart: str = Field(min_length=5, max_length=300)
    beats: list[str] = Field(min_length=4, max_length=8)
    rhythm: str = Field(min_length=5, max_length=300)
    cautions: list[str] = Field(default_factory=list, max_length=6)


class SeedOutput(Strict):
    seeds: list[FlowSeed] = Field(min_length=1)


register(SEED_CONTRACT)(SeedOutput)

EXAMPLE = {
    "seeds": [
        {
            "sourceId": "원본 sourceId",
            "scene": "누가, 어디서, 어떤 채널로, 무슨 일이 있는 중인지 한 문장",
            "counterpart": "상대: 관계 배정에 맞는 사람. 자기 생활·성격·말 습관 한두 문장",
            "beats": ["사건 1", "사건 2", "사건 3", "사건 4"],
            "rhythm": "원문 말의 길이·주고받는 속도·단답과 연속 말의 섞임",
            "cautions": ["옮기면 안 되는 것"],
        }
    ]
}


def lengths(turns: list[dict[str, str]]) -> dict[str, float]:
    def med(role: str) -> float:
        vals = [len(t["content"]) for t in turns if t.get("role") == role]
        return float(statistics.median(vals)) if vals else 0.0

    return {"userMedianChars": med("user"), "characterMedianChars": med("assistant")}


def seed_problems(out: SeedOutput, wanted: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    ids = [s["sourceId"] for s in wanted]
    got = [s.sourceId for s in out.seeds]
    if got != ids:
        problems.append(f"seeds의 sourceId 순서가 입력과 같아야 한다(입력 {ids}, 받은 값 {got})")
        return problems
    for seed, src in zip(out.seeds, wanted, strict=True):
        original = checks.source_texts(src)
        texts = [seed.scene, seed.counterpart, seed.rhythm, *seed.beats, *seed.cautions]
        if checks.overlaps(texts, original):
            problems.append(f"{seed.sourceId}: 원문과 10글자 이상 이어서 같은 문장이 있다")
        if "?" in seed.scene:
            problems.append(f"{seed.sourceId}: scene에 물음표를 넣지 않는다")
        if any(not 5 <= len(b) <= 120 for b in seed.beats):
            problems.append(f"{seed.sourceId}: beats 한 줄은 5~120자다")
        if any('"' in b or "“" in b for b in seed.beats):
            problems.append(f"{seed.sourceId}: beats에 따옴표 인용을 넣지 않는다")
    return problems


def seed_path(rev_dir: Path, source_id: str) -> Path:
    return rev_dir / "seeds" / f"{_SAFE.sub('-', source_id)}.json"


def _source_sha(source: dict[str, Any]) -> str:
    return sha256_of(source.get("turns") or [])


def _inputs(session: WriteSession, slots: list[Slot]) -> dict[str, Any]:
    tp = session.training
    return {
        "character": tp.core if tp is not None else session.system,
        "seedSources": [
            {
                "index": i,
                "sourceId": s.source["sourceId"],
                "origin": s.source.get("source", "SNS"),
                "channel": s.channel,
                "channelText": tp.channels.get(s.channel, "") if tp else "",
                "relationship": s.relationship,
                "relationshipText": tp.relationships.get(s.relationship, "") if tp else "",
                "lengths": lengths(s.source["turns"]),
                "turns": s.source["turns"],
            }
            for i, s in enumerate(slots)
        ],
    }


def _request(session: WriteSession, slots: list[Slot]) -> tuple[SeedOutput, str, str]:
    inputs = _inputs(session, slots)
    wanted = [s.source for s in slots]
    budget = session.ctx.budget()
    rev_dir = plan_mod.data_dir(session.ctx, session.cid) / session.rev
    if deck.enabled(session.ctx):
        out, ref, actual = deck.request(
            session.ctx,
            session.cid,
            budget=budget,
            stage=session.stage,
            rev_dir=rev_dir,
            task="scenarios",
            role="data_seed",
            contract=SeedOutput,
            inputs=inputs,
            validate_output=lambda o: seed_problems(o, wanted),
        )
        return out, ref, actual
    key = sha256_of([s["sourceId"] for s in wanted])[:10]
    workspace = (
        session.ctx.config.root / "work" / "s9-data" / f"{session.rev}-{session.cluster}-seed-{key}"
    )
    result = run_agent(
        AgentSpec(
            role="data_seed",
            output_contract=SEED_CONTRACT,
            stage=session.stage,
            max_check_retries=session.cfg.max_retries,
        ),
        workspace,
        inputs,
        [lambda o: seed_problems(o, wanted)],
        session.ctx.text_model(session.cid, budget),
        ref=f"{session.cid}/{session.rev}/{session.cluster}/seed-{key}",
        contract_example=EXAMPLE,
        backend=session.ctx.agent_backend(session.cid, budget, session.stage),
    )
    if not result.ok:
        raise CheckFailed(session.stage, [f"흐름 시드: {p}" for p in result.problems])
    return result.output, f"work/s9-data/{workspace.name}", session.writer_model


def attach(session: WriteSession, slots: list[Slot]) -> list[Slot]:
    """실제 대화 재료 자리에 시드를 붙인다. 이미 뽑은 시드는 다시 쓰고, 없는 것만 한 번에 뽑는다."""
    rev_dir = plan_mod.data_dir(session.ctx, session.cid) / session.rev
    found: dict[int, dict[str, Any]] = {}
    missing: list[int] = []
    for i, s in enumerate(slots):
        if s.material != "SNS_REWRITE" or s.source is None:
            continue
        if "seed" in s.source:
            found[i] = s.source["seed"]
            continue
        path = seed_path(rev_dir, s.source["sourceId"])
        if path.exists():
            saved = read_json(path)
            if saved.get("sourceSha256") != _source_sha(s.source):
                raise CheckFailed(session.stage, [f"{path.name}: 원본이 시드를 뽑을 때와 다르다"])
            found[i] = saved["seed"]
        else:
            missing.append(i)
    if missing:
        out, ref, actual = _request(session, [slots[i] for i in missing])
        for i, seed in zip(missing, out.seeds, strict=True):
            body = dump(seed)
            write_once_json(
                seed_path(rev_dir, slots[i].source["sourceId"]),
                {
                    "schemaVersion": "flow-seed-v1",
                    "sourceId": slots[i].source["sourceId"],
                    "sourceSha256": _source_sha(slots[i].source),
                    "seedModel": actual,
                    "requestRef": ref,
                    "seed": body,
                },
            )
            found[i] = body
    return [
        replace(s, source={**s.source, "seed": found[i]}) if i in found else s
        for i, s in enumerate(slots)
    ]
