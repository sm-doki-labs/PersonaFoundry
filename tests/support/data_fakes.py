"""S9 시험 도우미: 가짜 작성 모델, G6까지 진행, 합성 SNS 후보 대화. 네트워크 없음.

가짜 작성 모델은 요청의 `batch` 입력을 읽어 그 수만큼 대화를 돌려준다. 시험마다 결함을
주입한다(첫 SNS 재작성에서 사용자 턴 변조, 긴 답변, 같은 마지막 대사).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.approve import approve_g6
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.support.legacy import import_plan
from tests.support.synthetic import PLAN, prompter_output, trait_sheet

WORDS = ("창가", "골목", "버스", "노을", "서가", "커피", "우산", "기타", "테라스", "계단")


def s9_toml(
    root: Path,
    *,
    target: int = 12,
    sample_size: int = 2,
    batch_size: int = 4,
    max_retries: int = 1,
    validation_base: int = 2,
    augmented_share: float = 0.2,
    eval_per_cluster: int = 1,
    materials_base: str | None = None,
    bubble_cap: int = 50,
    phrase_cap: int = 50,
    max_length_tokens: int = 4096,
) -> str:
    base_materials = f"base = {materials_base}\n" if materials_base else ""
    return f"""
[stages.s9]
target = {target}
sample_size = {sample_size}
batch_size = {batch_size}
concurrency = 1
max_retries = {max_retries}
sns_path = "{root / "sns.jsonl"}"
sns_limit = 20
[stages.s9.materials]
{base_materials}
[stages.s9.validation]
base = {validation_base}
augmented_share = {augmented_share}
eval_per_cluster = {eval_per_cluster}
[stages.s9.checks]
bubble_max_conversations = {bubble_cap}
phrase_max_conversations = {phrase_cap}
max_length_tokens = {max_length_tokens}
"""


def make_s9_ctx(root: Path, toml: str = "", fake: FakeTextModel | None = None):
    (root / "factory.toml").write_text(toml or s9_toml(root), encoding="utf-8")
    ctx = Context.load(root, execute=True)
    model = fake or FakeWriterModel()
    ctx.use_models(model)
    return ctx, model


def through_g6(ctx: Context, root: Path, slug: str = "s9") -> str:
    src = root / "plan.json"
    src.write_text(json.dumps(PLAN, ensure_ascii=False), encoding="utf-8")
    cid = import_plan(ctx, slug, src).characterId
    run_s7(ctx, cid)
    run_s8(ctx, cid, [])
    approve_g6(ctx, cid, {"decision": "APPROVE", "reviewer": "user", "minutes": 1})
    return cid


def write_sns(path: Path, count: int = 4) -> None:
    lines = []
    for i in range(1, count + 1):
        lines.append(
            json.dumps(
                {
                    "conversationId": f"sns{i:03d}",
                    "messages": [
                        {"role": "user", "content": f"오늘 {i}시에 볼 수 있어?"},
                        {"role": "assistant", "content": "응, 갈 수 있어."},
                        {"role": "user", "content": f"{i}시는 조금 늦을 것 같아."},
                        {"role": "assistant", "content": "그럼 조금 늦게 보자."},
                    ],
                },
                ensure_ascii=False,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _block(req, name: str) -> dict[str, Any]:
    match = re.search(rf'<input name="{name}">\n(.*?)\n</input>', req.messages[-1].content, re.S)
    if match is None:
        raise AssertionError(f"입력 블록이 없다: {name}")
    return json.loads(match.group(1))


class FakeWriterModel(FakeTextModel):
    """s7·s8·s9s·s9 에이전트 응답을 한 곳에서 낸다."""

    def __init__(
        self,
        *,
        grouped: bool = False,
        sns_bad_first: bool = False,
        long_reply: bool = False,
        same_ending: bool = False,
        always_reject: str = "",
    ):
        super().__init__()
        self.cid = "cf-unset"
        self.n = 0
        self.grouped = grouped
        self.sns_bad_first = sns_bad_first
        self.sns_bad_served = False
        self.long_reply = long_reply
        self.same_ending = same_ending
        self.always_reject = always_reject
        self.add("AGENT", self.respond)
        self.add("PROBE", "그래, 그렇게 하자.")
        self.add("JUDGE", {"pick": "A", "reasons": "선택이 더 맞는다"})

    def respond(self, req):
        if req.stage == "s7":
            return trait_sheet(self.cid, "pr1")
        if req.stage == "s8":
            return prompter_output()
        user = req.messages[-1].content
        if '<input name="seedSources">' in user:
            return self.seeds(_block(req, "seedSources"))
        if '<input name="batch">' not in user:
            return self.handoff(req)
        return self.writer(req)

    def seeds(self, sources: list[dict[str, Any]]) -> dict[str, Any]:
        # D-0138: 흐름 시드. 원문 문장 없이 장면·상대·사건·리듬만 쓴다.
        self.seed_calls = getattr(self, "seed_calls", 0) + 1
        return {
            "seeds": [
                {
                    "sourceId": s["sourceId"],
                    "scene": f"{WORDS[i % 10]} 근처에서 퇴근길에 문자를 주고받는 저녁.",
                    "counterpart": "상대: 같은 동네에 사는 회사원. 말이 짧고 장난을 잘 친다.",
                    "beats": [
                        "상대가 만날 시간을 묻는다",
                        "캐릭터가 된다고 답한다",
                        "상대가 조금 늦는다고 알린다",
                        "둘이 시간을 늦춰 다시 정한다",
                    ],
                    "rhythm": "둘 다 짧게 주고받고 캐릭터 말은 대개 15자 안팎이다.",
                    "cautions": [],
                }
                for i, s in enumerate(sources)
            ]
        }

    def handoff(self, req) -> dict[str, Any]:
        cluster = _block(req, "cluster")
        name = cluster["clusterId"]
        return {
            "behaviorTable": [
                {
                    "situation": f"{name} 장면 1: 상대가 늦는다고 연락한다",
                    "attention": "상대가 미안해하는지보다 다음 시간을 정했는지 본다",
                    "choice": "괜찮다고 하고 가능한 시간을 둘로 제안한다",
                    "voice": "짧은 두 문장, 장식 없이",
                },
                {
                    "situation": f"{name} 장면 2: 상대가 이유 없이 짧게 답한다",
                    "attention": "오늘 컨디션과 내가 한 말을 함께 본다",
                    "choice": "한 번만 물어보고 답이 없으면 기다린다",
                    "voice": "한 문장, 물음표 하나",
                },
                {
                    "situation": f"{name} 장면 3: 상대가 자기 실수를 인정한다",
                    "attention": "변명보다 고치려는 행동을 본다",
                    "choice": "짧게 받아 주고 다음 행동을 함께 정한다",
                    "voice": "담백하게, 사과를 반복해 요구하지 않는다",
                },
            ],
            "voiceExamples": [f"{name} 예시 하나야.", f"{name} 예시 둘이야."],
            "forbidden": [f"{name}에서 관계를 끊겠다고 말한다"],
            "notes": "시험용 인계안",
        }

    def writer(self, req) -> dict[str, Any]:
        batch = _block(req, "batch")
        rule = batch.get("turnRule")
        if rule:
            # 창작 인물 정책(D-0078)의 long 클러스터: 턴 하한·화제 전환·후반 계기 표시를 지킨다.
            items = []
            for _ in range(batch["count"]):
                self.n += 1
                items.append(self._long_item(self.n, rule))
            return {"conversations": items}
        sources = {int(s["index"]): s for s in batch.get("sources", [])}
        items = []
        for i in range(batch["count"]):
            self.n += 1
            n = self.n
            if i in sources:
                items.append(self._sns_item(sources[i], n))
            else:
                items.append(self._synth_item(batch["clusterId"], n))
        if self.always_reject:
            for item in items:
                item["messages"][1]["content"] = self.always_reject
        return {"conversations": items}

    def _long_item(self, n: int, rule: dict[str, Any]) -> dict[str, Any]:
        turns = int(rule["minAssistantTurns"])
        messages = []
        for t in range(turns):
            word = WORDS[(n + t) % 10]
            messages.append({"role": "user", "content": f"{n}-{t} 이번엔 {word} 얘기 해 볼래?"})
            messages.append(
                {"role": "assistant", "content": f"{word}라면 {n}번 대화 {t}턴째에 좋지."}
            )
        start = math.ceil(len(messages) * float(rule["lateTriggerFromShare"]))
        start += start % 2
        return {
            "skeletonKey": f"long-{n}",
            "scene": f"{WORDS[n % 10]} 근처에서 오래 문자를 주고받는 밤.",
            "sourceId": "",
            "messages": messages,
            "topicShiftAt": [4, 10],
            "lateTriggerAt": [start, start + 2],
        }

    def _sns_item(self, source: dict[str, Any], n: int) -> dict[str, Any]:
        # 시드만 보고 양쪽 대사를 새로 쓴다(D-0138). sns_bad_first면 첫 응답의 캐릭터 말 하나를
        # 길이 상한보다 길게 써서 다시 쓰기를 부른다.
        bad = self.sns_bad_first and not self.sns_bad_served
        self.sns_bad_served = True
        word = WORDS[n % 10]
        count = int(source.get("sourceTurns") or len(source.get("turns") or []) or 4)
        messages = []
        for k in range(count - count % 2):
            if k % 2 == 0:
                fresh = f"{word} 쪽은 {n}번째인데 {k // 2 + 1}번 물어봐도 돼?"
                messages.append({"role": "user", "content": fresh})
            else:
                said = f"{word}에서 기다릴게. {n}-{k}번째 약속이야."
                if bad and k == 1:
                    said += " 그리고 오늘은 할 말이 많아서 길게 이어서 말하는 중이야."
                    said += " 끝까지 들어 줘."
                messages.append({"role": "assistant", "content": said})
        return {
            "skeletonKey": "",
            "scene": f"{word}에서 약속 시간을 맞추는 저녁.",
            "sourceId": source["sourceId"],
            "flowBeats": [
                "상대가 먼저 시간을 묻는다",
                "캐릭터가 된다고 답한다",
                "둘이 시간을 조금 늦춘다",
            ],
            "messages": messages,
        }

    def _synth_item(self, cluster: str, n: int) -> dict[str, Any]:
        key = f"scene-{n // 2}" if self.grouped else f"scene-{n}"
        word = WORDS[n % 10]
        last = (
            "그럼 그렇게 하자."
            if self.same_ending
            else f"{word} 쪽으로 {n}분만 늦게 갈게. 오늘은 그게 맞는 것 같아."
        )
        assistant = f"응, {word} 얘기라면 {n}번째로 들어도 좋아."
        if self.long_reply:
            assistant = assistant + (" 아주 긴 설명을 덧붙인다." * 40)
        return {
            "skeletonKey": key,
            "scene": f"{word} 쪽에서 {cluster} 이야기를 꺼내는 오후.",
            "sourceId": "",
            "messages": [
                {"role": "user", "content": f"{n}번째 이야기인데, {word} 어때?"},
                {"role": "assistant", "content": assistant},
                {"role": "user", "content": "그럼 오늘 몇 시가 좋아?"},
                {"role": "assistant", "content": last},
            ],
        }
