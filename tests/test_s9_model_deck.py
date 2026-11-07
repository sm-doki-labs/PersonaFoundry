"""Offline S9 task routing, grounded review, bounded correction and provenance."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from character_factory_poc.common.budget import Budget
from character_factory_poc.common.config import BudgetConfig, ProviderConfig
from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.contracts.dataset import DataHandoff
from character_factory_poc.providers.base import ChatResponse
from character_factory_poc.providers.tracked import TrackedTextModel
from character_factory_poc.stages.s9_data import build, handoff, plan, samples, split

MODELS = {
    "scenarios": "gpt-sol-scenarios",
    "sft_answers": "gemini-flash-writer",
    "screening": "gpt-terra",
    "adjudication": "gpt-sol-review",
    "repair": "gemini-flash-repair",
}
SYSTEM = "You work at a bookshop. Your name is Min. You may be jealous and abrasive."


def written(answer="몰라. 네가 다른 사람 만난다니까 신경 쓰이네."):
    return {
        "skeletonKey": "bookshop-evening",
        "scene": "책방 문을 닫은 저녁이다.",
        "sourceId": "",
        "messages": [
            {"role": "user", "content": "내일 친구 만나."},
            {"role": "assistant", "content": answer},
            {"role": "user", "content": "너는 어디서 일하지?"},
            {"role": "assistant", "content": "책방에서 일해. 그건 왜?"},
        ],
    }


def review(ids, errors=None):
    errors = errors or {}
    return {
        "reviews": [
            {
                "conversationId": cid,
                "verdict": "ERROR" if errors.get(cid) else "PASS",
                "errors": errors.get(cid, []),
            }
            for cid in ids
        ]
    }


def fact_error(quote="병원에서 일해."):
    return {
        "kind": "canon",
        "messageIndex": 3,
        "quote": quote,
        "evidenceSource": "system",
        "evidenceMessageIndex": None,
        "evidenceQuote": "You work at a bookshop.",
        "explanation": "The assistant contradicts the explicit workplace.",
    }


class TaskModel:
    name = "fake"

    def __init__(self, ctx, task, responses):
        self.ctx, self.task, self.responses = ctx, task, list(responses)
        self.model = MODELS[task]

    def complete(self, req):
        self.ctx.requests.append((self.task, req))
        if not self.responses:
            raise AssertionError(f"unexpected {self.task} call")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value(req)
        return ChatResponse(
            text=value if isinstance(value, str) else json.dumps(value, ensure_ascii=False),
            input_tokens=12,
            output_tokens=15,
            elapsed_ms=1,
            model=self.model + "-served",
            provider="fake",
        )


class DeckConfig:
    def __init__(self, root, base=None):
        self.root, self.base = root, base
        self.text_pipeline = {"enabled": True}
        self.profile = "basic_test"

    def __getattr__(self, name):
        if self.base is None:
            raise AttributeError(name)
        return getattr(self.base, name)

    def stage(self, stage):
        return self.base.stage(stage) if self.base else {"batch_size": 2, "concurrency": 1}

    def provider(self, name):
        return self.base.provider(name) if self.base else ProviderConfig(model="generic-" + name)

    def task_provider(self, task):
        return ProviderConfig(model=MODELS[task])

    def text_binding(self, task):
        return {
            "task": task,
            "profile": self.profile,
            "route": "opencodex",
            "model": MODELS[task],
            "reasoning_effort": "high",
            "provider": "fake",
        }


class DeckContext:
    def __init__(self, root, responses):
        self.config = DeckConfig(root)
        self.requests = []
        self.shared_budget = Budget(BudgetConfig(max_calls_per_command=2000))
        self.models = {k: TaskModel(self, k, v) for k, v in responses.items()}

    def budget(self):
        return self.shared_budget

    def character_dir(self, cid):
        return self.config.root / "runs" / "characters" / cid

    def ledger(self, cid):
        return Ledger(self.character_dir(cid) / "ledger")

    def task_model(self, cid, budget, task):
        return TrackedTextModel(self.models[task], self.ledger(cid), budget)

    def text_model(self, *args):
        raise AssertionError("enabled S9 must use task_model")

    def agent_backend(self, *args):
        raise AssertionError("enabled S9 must bypass Codex backend")


def session(tmp_path, responses, ids=None):
    ids = ids or ["c1"]
    ctx = DeckContext(tmp_path, responses)
    s = samples.WriteSession(
        ctx=ctx,
        cid="cf-test",
        stage="s9s",
        rev="ds1",
        cluster="base",
        system=SYSTEM,
        handoff=DataHandoff(
            characterId="cf-test", planSha256="0" * 64, clusterId="base", behaviorTable=[]
        ),
        cfg=plan.s9_config(ctx),
        writer_model="generic-wrong",
    )
    return s, [samples.Slot("SYNTH") for _ in ids], ids


def test_deck_writer_owns_history_and_every_conversation_is_screened(tmp_path):
    s, slots, ids = session(
        tmp_path,
        {
            "sft_answers": [{"conversations": [written(), written("미안, 근데 나도 좀 서운해.")]}],
            "screening": [review(["c1", "c2"])],
        },
        ["c1", "c2"],
    )
    convs = samples.write_batch(s, slots, ids)
    assert [c.provenance.writerModel for c in convs] == ["gemini-flash-writer-served"] * 2
    assert convs[0].messages[1].content == "몰라. 네가 다른 사람 만난다니까 신경 쓰이네."
    assert convs[1].messages[1].content == "미안, 근데 나도 좀 서운해."
    assert [t for t, _ in s.ctx.requests] == ["sft_answers", "screening"]
    payload = s.ctx.requests[1][1].messages[-1].content
    assert all(cid in payload for cid in ids)
    assert "몰라. 네가 다른 사람 만난다니까 신경 쓰이네." in payload
    path = plan.data_dir(s.ctx, s.cid) / s.rev / convs[0].provenance.requestRef
    audit = json.loads(path.read_text())
    assert audit["binding"]["task"] == "sft_answers"
    assert audit["binding"]["profile"] == "basic_test"
    assert audit["responseModel"] == "gemini-flash-writer-served"
    assert len(s.ctx.ledger(s.cid).calls()) == 2


def test_only_confirmed_errors_are_repaired_once_then_rescreened(tmp_path):
    bad = written()
    bad["messages"][3]["content"] = "병원에서 일해."
    errors = {"c1": [fact_error()]}
    s, slots, ids = session(
        tmp_path,
        {
            "sft_answers": [{"conversations": [bad, written("미안, 근데 나도 좀 서운해.")]}],
            "screening": [review(["c1", "c2"], errors), review(["c1", "c2"])],
            "adjudication": [review(["c1", "c2"], errors)],
            "repair": [{"conversations": [written()]}],
        },
        ["c1", "c2"],
    )
    convs = samples.write_batch(s, slots, ids)
    assert convs[0].messages[3].content == "책방에서 일해. 그건 왜?"
    assert convs[0].messages[1].content == bad["messages"][1]["content"]
    assert convs[1].provenance.writerModel == "gemini-flash-writer-served"
    assert convs[0].provenance.writerModel == "gemini-flash-repair-served"
    assert [t for t, _ in s.ctx.requests] == [
        "sft_answers",
        "screening",
        "adjudication",
        "repair",
        "screening",
    ]


def test_sol_can_dismiss_a_grounded_but_incorrect_terra_concern(tmp_path):
    concern = fact_error("책방에서 일해.")
    s, slots, ids = session(
        tmp_path,
        {
            "sft_answers": [{"conversations": [written()]}],
            "screening": [review(["c1"], {"c1": [concern]})],
            "adjudication": [review(["c1"])],
        },
    )
    convs = samples.write_batch(s, slots, ids)
    assert convs[0].messages[3].content == "책방에서 일해. 그건 왜?"
    assert len(s.ctx.requests) == 3


@pytest.mark.parametrize(
    "bad_review",
    [
        review([]),
        review(["c1", "c1"]),
        review(["wrong"]),
        review(["c1"], {"c1": [{**fact_error(), "quote": "invented"}]}),
        review(["c1"], {"c1": [{**fact_error(), "kind": "too_abrasive"}]}),
        review(["c1"], {"c1": [{**fact_error(), "evidenceQuote": "invented canon"}]}),
    ],
)
def test_incomplete_or_ungrounded_screening_cannot_pass(tmp_path, bad_review):
    s, slots, ids = session(
        tmp_path,
        {
            "sft_answers": [{"conversations": [written()]}],
            "screening": [bad_review] * 3,
        },
    )
    with pytest.raises(CheckFailed):
        samples.write_batch(s, slots, ids)
    assert [t for t, _ in s.ctx.requests] == ["sft_answers"] + ["screening"] * 3


def test_unresolved_after_one_round_stops_and_resume_cannot_redraw(tmp_path):
    bad = written()
    bad["messages"][3]["content"] = "병원에서 일해."
    err = review(["c1"], {"c1": [fact_error()]})
    s, slots, ids = session(
        tmp_path,
        {
            "sft_answers": [{"conversations": [bad]}],
            "screening": [err, err],
            "adjudication": [err, err],
            "repair": [{"conversations": [bad]}],
        },
    )
    with pytest.raises(CheckFailed):
        samples.write_batch(s, slots, ids)
    assert len(s.ctx.requests) == 6
    with pytest.raises(CheckFailed):
        samples.write_batch(s, slots, ids)
    assert len(s.ctx.requests) == 6
    assert not (plan.data_dir(s.ctx, s.cid) / s.rev / "conversations/c1.json").exists()


def test_repair_cannot_rewrite_user_or_unflagged_history(tmp_path):
    bad = written()
    bad["messages"][3]["content"] = "병원에서 일해."
    repaired = written()
    repaired["messages"][1]["content"] = "네 선택을 응원해."
    err = review(["c1"], {"c1": [fact_error()]})
    s, slots, ids = session(
        tmp_path,
        {
            "sft_answers": [{"conversations": [bad]}],
            "screening": [err],
            "adjudication": [err],
            "repair": [{"conversations": [repaired]}],
        },
    )
    with pytest.raises(CheckFailed):
        samples.write_batch(s, slots, ids)
    assert len(s.ctx.requests) == 4


def test_network_failure_has_audit_and_no_alternate_model_or_route(tmp_path):
    s, slots, ids = session(tmp_path, {"sft_answers": [RuntimeError("offline failure")]})
    with pytest.raises(RuntimeError, match="offline failure"):
        samples.write_batch(s, slots, ids)
    assert len(s.ctx.requests) == 1
    audits = list((plan.data_dir(s.ctx, s.cid) / s.rev / "requests").glob("data-deck-*.json"))
    assert len(audits) == 1
    assert json.loads(audits[0].read_text())["ok"] is False


def test_format_retry_bound_is_two_and_audits_cover_all_requests(tmp_path):
    s, slots, ids = session(
        tmp_path,
        {
            "sft_answers": ["invalid", "invalid", {"conversations": [written()]}],
            "screening": [review(["c1"])],
        },
    )
    assert samples.write_batch(s, slots, ids)
    audits = list((plan.data_dir(s.ctx, s.cid) / s.rev / "requests").glob("data-deck-*.json"))
    assert len(audits) == 4
    assert s.ctx.shared_budget.used_calls == 4


def test_enabled_sample_plan_bounds_format_screen_adjudicate_and_one_repair(tmp_path):
    ctx = DeckContext(tmp_path, {})
    # 5 clusters × (3 handoff + 18 batch calls); defaults sample_size=12, batch_size=2.
    cfg = plan.s9_config(ctx)
    total = sum(p.calls for p in samples.plan_calls(ctx, "cf-test", cfg))
    assert total == 555
    assert ctx.requests == []


def test_deck_handoff_does_not_author_assistant_dialogue(tmp_path):
    rows = [
        {
            "situation": "A bookshop evening",
            "attention": "Canon workplace",
            "choice": "사용자가 일터를 묻는다",
            "voice": "Use approved system voice",
        }
    ] * 3
    ctx = DeckContext(
        tmp_path,
        {
            "scenarios": [
                {
                    "behaviorTable": rows,
                    "forbidden": ["inventing a workplace"],
                    "notes": "facts only",
                }
            ]
        },
    )
    p = SimpleNamespace(
        clusters=[
            SimpleNamespace(
                clusterId="base",
                label="Base",
                share=1,
                targetConversations=5,
                materials=["SYNTH"],
                sampleSize=1,
            )
        ]
    )
    got = handoff.build_handoff(
        ctx,
        "cf-test",
        plan=p,
        plan_sha="0" * 64,
        cluster_id="base",
        pair=SimpleNamespace(short=SimpleNamespace(text=SYSTEM)),
        sheet=SimpleNamespace(model_dump=lambda **kw: {}),
        workspace=tmp_path / "work/handoff",
        stage="s9s",
        retries=8,
    )
    assert got.voiceExamples == []
    assert [t for t, _ in ctx.requests] == ["scenarios"]


def test_plan_records_actual_task_models_and_route_snapshot_without_calls(tmp_path):
    from tests.support.data_fakes import make_s9_ctx, through_g6

    ctx, _ = make_s9_ctx(tmp_path)
    cid = through_g6(ctx, tmp_path)
    ctx.config = DeckConfig(tmp_path, ctx.config)
    p = plan.run_plan(ctx, cid)
    obj = json.loads((p / "plan.json").read_text())
    assert obj["writerModel"] == "gemini-flash-writer"
    assert obj["judgeModel"] == "gpt-terra"
    snapshot = json.loads((p / "model-deck.json").read_text())
    assert snapshot["bindings"]["sft_answers"]["profile"] == "basic_test"
    ctx.config.profile = "demo"
    with pytest.raises(CheckFailed):
        plan.run_plan(ctx, cid)


def test_batch_success_resume_does_not_redraw_or_change_provenance(tmp_path):
    s, slots, ids = session(
        tmp_path,
        {
            "sft_answers": [{"conversations": [written()]}],
            "screening": [review(["c1"])],
        },
    )
    original = samples.write_batch(s, slots, ids)
    again = samples.write_batch(s, slots, ids)
    assert again == original
    assert len(s.ctx.requests) == 2


@pytest.mark.parametrize("turn", [0, 1])
def test_repair_preserves_all_uncited_user_and_assistant_turns(tmp_path, turn):
    bad = written()
    bad["messages"][3]["content"] = "병원에서 일해."
    repaired = written()
    repaired["messages"][turn]["content"] = "changed unrelated content"
    err = review(["c1"], {"c1": [fact_error()]})
    s, slots, ids = session(
        tmp_path,
        {
            "sft_answers": [{"conversations": [bad]}],
            "screening": [err],
            "adjudication": [err],
            "repair": [{"conversations": [repaired]}],
        },
    )
    with pytest.raises(CheckFailed):
        samples.write_batch(s, slots, ids)
    assert len(s.ctx.requests) == 4


def _enabled_pipeline(tmp_path, monkeypatch, *, same_ending=False):
    from tests.support.data_fakes import make_s9_ctx, through_g6

    ctx, _ = make_s9_ctx(tmp_path)
    cid = through_g6(ctx, tmp_path)
    ctx.config = DeckConfig(tmp_path, ctx.config)
    counter = 0

    def auto_writer(req):
        nonlocal counter
        batch = json.loads(req.messages[1].content)["inputs"]["batch"]
        items = []
        for _ in range(batch["count"]):
            counter += 1
            item = written(f"이번에는 {counter}번째 질문을 듣고 있어.")
            item["skeletonKey"] = f"scene-{counter}"
            item["scene"] = f"책방 문을 닫은 {counter}번째 저녁이다."
            item["messages"][3]["content"] = (
                "그럼 그렇게 하자." if same_ending else f"책방 {counter}번 서가 앞이야."
            )
            items.append(item)
        return {"conversations": items}

    def auto_screen(req):
        convs = json.loads(req.messages[1].content)["inputs"]["conversations"]
        return review([c["conversationId"] for c in convs])

    rows = [
        {
            "situation": "책방의 저녁",
            "attention": "승인된 직업 설정",
            "choice": "사용자가 일터를 묻는다",
            "voice": "승인된 말투 참조",
        }
    ] * 3
    task_ctx = DeckContext(
        tmp_path,
        {
            "scenarios": [
                {"behaviorTable": rows, "forbidden": ["설정에 없는 직업 날조"], "notes": "facts"}
            ]
            * 10,
            "sft_answers": [auto_writer] * 30,
            "screening": [auto_screen] * 30,
        },
    )
    monkeypatch.setattr(ctx, "task_model", task_ctx.task_model)
    monkeypatch.setattr(ctx, "agent_backend", lambda *a: pytest.fail("unexpected Codex backend"))
    return ctx, cid, task_ctx


def test_enabled_pipeline_keeps_both_person_gates_and_screens_bulk(tmp_path, monkeypatch):
    from character_factory_poc.stages.s9_data.approve import approve_g7a

    ctx, cid, task_ctx = _enabled_pipeline(tmp_path, monkeypatch)
    sample_bound = sum(p.calls for p in samples.plan_calls(ctx, cid))
    folder = samples.run_samples(ctx, cid)
    assert ctx.state(cid).gate("G7a").status == "AWAITING_HUMAN"
    assert len(task_ctx.requests) == 15
    assert len(task_ctx.requests) <= sample_bound
    for cluster in plan.CLUSTERS:
        approve_g7a(ctx, cid, {"decision": "SELECT", "cluster": cluster, "reviewer": "human"})
    bulk_bound = sum(p.calls for p in build.plan_calls(ctx, cid))
    before = len(task_ctx.requests)
    assert build.run_build(ctx, cid) == folder
    assert len(task_ctx.requests) - before <= bulk_bound
    assert ctx.state(cid).gate("G7").status == "AWAITING_HUMAN"
    assert ctx.state(cid).stage("s9").status == "AWAITING_HUMAN"
    for path in (folder / "conversations").glob("*.json"):
        conv = json.loads(path.read_text())
        assert conv["provenance"]["writerModel"] == "gemini-flash-writer-served"
    assert not (folder / "frozen.json").exists()


def test_deck_dataset_check_failure_never_triggers_regeneration(tmp_path, monkeypatch):
    from character_factory_poc.stages.s9_data.approve import approve_g7a

    ctx, cid, task_ctx = _enabled_pipeline(tmp_path, monkeypatch, same_ending=True)
    folder = samples.run_samples(ctx, cid)
    for cluster in plan.CLUSTERS:
        approve_g7a(ctx, cid, {"decision": "SELECT", "cluster": cluster, "reviewer": "human"})
    cfg = plan.s9_config(ctx)
    targets = split.needed(plan.load_plan(folder / "plan.json"), cfg)
    expected_batches = sum(
        -(-max(0, n - cfg.sample_size) // cfg.batch_size) for n in targets.values()
    )
    before = len(task_ctx.requests)
    # All per-conversation checks pass; the global repetition detector must stop
    # before any old retry/regeneration loop gets a chance to redraw the data.
    ctx.config.base.stages["s9"]["checks"]["bubble_max_conversations"] = 1
    with pytest.raises(CheckFailed, match="ending_repetition"):
        build.run_build(ctx, cid)
    assert len(task_ctx.requests) - before == 2 * expected_batches
    assert ctx.state(cid).stage("s9").status == "CHECK_FAILED"
    assert not (folder / "dataset.json").exists()


def test_handoff_format_failure_preserves_first_response_and_caps_at_three(tmp_path):
    bad = {
        "behaviorTable": [],
        "voiceExamples": ["invented assistant speech"],
        "forbidden": [],
        "notes": "",
    }
    ctx = DeckContext(tmp_path, {"scenarios": [bad] * 3})
    p = SimpleNamespace(
        clusters=[
            SimpleNamespace(
                clusterId="base",
                label="Base",
                share=1,
                targetConversations=5,
                materials=["SYNTH"],
                sampleSize=1,
            )
        ]
    )
    with pytest.raises(CheckFailed):
        handoff.build_handoff(
            ctx,
            "cf-test",
            plan=p,
            plan_sha="0" * 64,
            cluster_id="base",
            pair=SimpleNamespace(short=SimpleNamespace(text=SYSTEM)),
            sheet=SimpleNamespace(model_dump=lambda **kw: {}),
            workspace=tmp_path / "work/ds1-base-handoff",
            stage="s9s",
            retries=8,
        )
    assert len(ctx.requests) == 3
    audits = list((plan.data_dir(ctx, "cf-test") / "ds1/requests").glob("data-deck-*.json"))
    assert len(audits) == 3
    first = next(
        json.loads(p.read_text()) for p in audits if json.loads(p.read_text())["attempt"] == 1
    )
    assert json.loads(first["response"]) == bad


def test_real_task_model_http_boundary_and_ledger_have_actual_model_and_binding(
    tmp_path, monkeypatch
):
    import httpx

    from character_factory_poc.pipeline.context import Context

    (tmp_path / "factory.toml").write_text('[text_pipeline]\nenabled=true\nprofile="basic_test"\n')
    ctx = Context.load(tmp_path, execute=True)
    calls = []

    def post(_client, url, **kwargs):
        body = kwargs["json"]
        calls.append(body)
        is_writer = body["model"] == ctx.config.task_provider("sft_answers").model
        output = {"conversations": [written()]} if is_writer else review(["c1"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "model": body["model"] + "-served",
                "usage": {"prompt_tokens": 20, "completion_tokens": 30},
                "choices": [
                    {
                        "message": {"content": json.dumps(output, ensure_ascii=False)},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    s, slots, ids = session(tmp_path, {})
    s.ctx = ctx
    convs = samples.write_batch(s, slots, ids)
    assert len(calls) == 2
    assert calls[0]["model"] == "google-antigravity/gemini-3.8-flash"
    assert calls[1]["model"] == "gpt-6.1-terra"
    assert all(c["reasoning_effort"] == "high" for c in calls)
    assert convs[0].provenance.writerModel == "google-antigravity/gemini-3.8-flash-served"
    ledger = ctx.ledger(s.cid).calls()
    assert [row["textBinding"]["task"] for row in ledger] == ["sft_answers", "screening"]
    assert all(row["textBinding"]["route"] == "opencodex" for row in ledger)


def test_scenario_handoff_retains_deterministic_content_checks(tmp_path):
    from character_factory_poc.stages.s9_data import deck

    output = {
        "behaviorTable": [{"situation": "", "attention": "", "choice": "", "voice": ""}] * 3,
        "forbidden": [],
        "notes": "",
    }
    ctx = DeckContext(tmp_path, {"scenarios": [output] * 3})
    p = SimpleNamespace(
        clusters=[
            SimpleNamespace(
                clusterId="base",
                label="Base",
                share=1,
                targetConversations=5,
                materials=["SYNTH"],
                sampleSize=1,
            )
        ]
    )
    with pytest.raises(CheckFailed, match="situation"):
        handoff.build_handoff(
            ctx,
            "cf-test",
            plan=p,
            plan_sha="0" * 64,
            cluster_id="base",
            pair=SimpleNamespace(short=SimpleNamespace(text=SYSTEM)),
            sheet=SimpleNamespace(model_dump=lambda **kw: {}),
            workspace=tmp_path / "work/ds1-base-handoff",
            stage="s9s",
            retries=8,
        )
    assert len(ctx.requests) == 3
    assert deck.enabled(ctx)


def test_final_failure_receipt_retains_explicit_unresolved_reasons(tmp_path):
    bad = written()
    bad["messages"][3]["content"] = "병원에서 일해."
    err = review(["c1"], {"c1": [fact_error()]})
    s, slots, ids = session(
        tmp_path,
        {
            "sft_answers": [{"conversations": [bad]}],
            "screening": [err, err],
            "adjudication": [err, err],
            "repair": [{"conversations": [bad]}],
        },
    )
    with pytest.raises(CheckFailed):
        samples.write_batch(s, slots, ids)
    receipt = next((plan.data_dir(s.ctx, s.cid) / s.rev / "deck-batches").glob("*-outcome.json"))
    outcome = json.loads(receipt.read_text())
    assert outcome["ok"] is False
    assert "semantic errors unresolved after one correction" in outcome["problems"]
    assert "c1: The assistant contradicts the explicit workplace." in outcome["problems"]
