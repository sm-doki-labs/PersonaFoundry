"""합성 출처 묶음과 프로세스 안의 가짜 공급자만 쓴다."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from character_factory_poc.cli import main
from character_factory_poc.common.errors import ProviderRequestError, ProviderTransportError
from character_factory_poc.pipeline.batch import run_batch
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers import tracked
from character_factory_poc.providers.base import ChatRequest
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.openai_compat import OpenAICompatTextModel
from tests.test_source_s0 import _good_digest, _write_pack


def _spec(tmp):
    rows = []
    for slug, mode, kind in [
        ("football-role", "train", "PUBLIC_FIGURE"),
        ("parent-role", "prompt", "PRIVATE_PERSON"),
    ]:
        path = _write_pack(tmp / slug, kind=kind)
        pack = json.loads(path.read_text())
        pack["subject"]["displayName"] = "합성 손흥민 역" if mode == "train" else "합성 부모님 역"
        path.write_text(json.dumps(pack))
        rows.append(
            dict(
                slug=slug,
                origin="twin",
                model_mode=mode,
                source_pack=str(path.relative_to(tmp)),
                until="G0",
                max_parallel=2,
            )
        )
    return {"schemaVersion": "batch-spec-v1", "max_parallel": 2, "characters": rows}


def _lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_two_twins_overlap_and_resume_without_replaying_ledgers(tmp_path):
    ctx = Context.load(tmp_path, True)
    overlap = threading.Barrier(2)

    def digest(req):
        overlap.wait(timeout=4)
        return _good_digest(req)

    ctx.use_models(FakeTextModel(responses={"AGENT": digest}))
    report = run_batch(ctx, _spec(tmp_path))
    path = ctx.config.runs_dir / "batches" / report.batchId / "batch-report.json"
    rows = json.loads(path.read_text())["characters"]
    assert [r["modelMode"] for r in rows] == ["TRAIN", "PROMPT_ONLY"]
    for row in rows:
        cid = row["characterId"]
        folder = ctx.character_dir(cid)
        assert row["waitingGates"] == ["G0"] and row["status"] == "waiting", row
        assert row["stages"] == [
            {
                "stage": "s0",
                "attempt": 1,
                "start": _lines(folder / "ledger/stage-events.jsonl")[0]["at"],
                "end": _lines(folder / "ledger/stage-events.jsonl")[-1]["at"],
                "result": "AWAITING_HUMAN",
            }
        ]
        assert len(_lines(folder / "ledger/calls.jsonl")) == 1
        assert (
            json.loads((folder / "s0-source/sp1/source-index.json").read_text())["characterId"]
            == cid
        )
    resumed = run_batch(
        ctx, {"characters": [{"character_id": r["characterId"], "until": "G0"} for r in rows]}
    )
    assert all(
        r.waitingGates == ["G0"] and r.stages == [] and r.providerWaitSeconds == 0
        for r in resumed.characters
    )


def test_cli_plan_and_invalid_batch_do_not_create_anything(tmp_path, capsys):
    spec = _spec(tmp_path)
    file = tmp_path / "spec.json"
    file.write_text(json.dumps(spec))
    assert main(["--root", str(tmp_path), "batch", "run", "--spec", str(file)]) == 0
    assert "dry run" in capsys.readouterr().out
    spec["characters"].append(spec["characters"][0])
    file.write_text(json.dumps(spec))
    assert main(["--root", str(tmp_path), "batch", "run", "--spec", str(file), "--execute"]) == 1
    assert not (tmp_path / "runs").exists()


def test_failure_is_local_and_reported(tmp_path):
    ctx = Context.load(tmp_path, True)
    spec = _spec(tmp_path)
    other = ctx.config.root / spec["characters"][1]["source_pack"]
    (other.parent / "mom.txt").unlink()
    ctx.use_models(FakeTextModel(responses={"AGENT": _good_digest}))
    report = run_batch(ctx, spec)
    good, bad = report.characters
    assert good.status == "waiting"
    assert bad.status == "failed" and bad.failedStages == ["s0"]


def test_limit_is_shared_across_contexts_and_queue_wait_is_local(tmp_path):
    (tmp_path / "factory.toml").write_text("[orchestrator.provider_limits]\ntext=1\n")
    active = peak = 0
    lock = threading.Lock()
    ready = threading.Barrier(5)

    def fake(req):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(active, peak)
        time.sleep(0.025)  # 가짜 호출 처리 시간
        with lock:
            active -= 1
        return req.ref

    def one(i):
        ctx = Context.load(tmp_path, True)
        ctx.use_models(FakeTextModel(responses={"AGENT": fake}))
        model = ctx.text_model(str(i), ctx.budget())
        ready.wait(timeout=4)
        return model.complete(ChatRequest("AGENT", "s3", (), str(i))).text

    with ThreadPoolExecutor(max_workers=4) as pool:
        fs = [pool.submit(one, i) for i in range(4)]
        ready.wait(timeout=4)
        assert [f.result() for f in fs] == list("0123")
    assert peak == 1
    waits = list((tmp_path / "runs/characters").glob("*/ledger/provider-waits.jsonl"))
    assert waits and all(_lines(w)[0]["reason"] == "capacity" for w in waits)


def test_429_retries_recorded_and_no_second_transport_loop(tmp_path, monkeypatch):
    ctx = Context.load(tmp_path, True)
    delays = []
    monkeypatch.setattr(tracked.time, "sleep", delays.append)

    def busy(req):
        raise ProviderTransportError("rate_limit", "synthetic", 429)

    inner = FakeTextModel(responses={"*": busy})
    ctx.use_models(inner)
    model = ctx.text_model("one", ctx.budget())
    model.transport_retries = 3
    with pytest.raises(ProviderTransportError):
        model.complete(ChatRequest("AGENT", "s3", (), "r"))
    assert delays == [1, 2, 4, 8, 16]
    assert len(inner.requests) == len({r.ref for r in inner.requests}) == 6
    rows = _lines(ctx.ledger("one").folder / tracked.WAIT_FILE)
    assert [r["delay"] for r in rows] == delays
    assert all(r["reason"] == "rate_limit" and r["seconds"] >= 0 for r in rows)

    def rejected(req):
        raise ProviderRequestError(400, "invalid")

    inner.add("*", rejected)
    with pytest.raises(ProviderRequestError):
        model.complete(ChatRequest("AGENT", "s3", (), "other"))
    assert len(inner.requests) == 7


def test_native_http_retry_has_one_owner(tmp_path, monkeypatch):
    ctx = Context.load(tmp_path, True)
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(429)

    monkeypatch.setattr(httpx.Client, "post", post)
    delays = []
    monkeypatch.setattr(tracked.time, "sleep", delays.append)
    inner = OpenAICompatTextModel("http://local.invalid", "stub", max_retries=2)
    ctx.use_models(inner)
    model = ctx.text_model("one", ctx.budget())
    model.transport_retries = 3
    with pytest.raises(ProviderTransportError):
        model.complete(ChatRequest("AGENT", "s3", (), "r"))
    assert len(calls) == 3 and delays == [1, 2]
    assert [r["delay"] for r in _lines(ctx.ledger("one").folder / tracked.WAIT_FILE)] == delays


def test_recovered_429_wait_is_counted_once_per_character(tmp_path, monkeypatch):
    ctx = Context.load(tmp_path, True)

    def busy(req):
        raise ProviderRequestError(429, "synthetic")

    # 두 캐릭터에 독립된 응답 큐를 준다. 둘 다 한 번씩 거절당한 뒤 정상 digest를 받는다.
    ctx.use_models(FakeTextModel(responses={"AGENT": [busy, _good_digest]}))
    real_sleep = time.sleep
    monkeypatch.setattr(tracked.time, "sleep", lambda _: real_sleep(0.002))
    report = run_batch(ctx, _spec(tmp_path))
    for row in report.characters:
        assert row.status == "waiting", row
        ledger = ctx.ledger(row.characterId).folder
        waits = _lines(ledger / tracked.WAIT_FILE)
        assert [w["delay"] for w in waits] == [1]
        assert 0 < row.providerWaitSeconds == waits[0]["seconds"]
        assert [r["ok"] for r in _lines(ledger / "calls.jsonl")] == [False, True]


def test_tuning_factory_shares_slots_and_writes_character_waits(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from character_factory_poc.common.config import ProviderConfig
    from character_factory_poc.providers.training import (
        FakeTrainingProvider,
        make_training_provider,
    )

    (tmp_path / "factory.toml").write_text("[orchestrator.provider_limits]\ntuning=2\n")
    ready = threading.Barrier(4)
    first_pair = threading.Barrier(2)
    lock = threading.Lock()
    active = peak = entered = 0

    def fake_status(self, run, request):
        nonlocal active, peak, entered
        with lock:
            active += 1
            entered += 1
            pair = entered <= 2
            peak = max(active, peak)
        if pair:
            first_pair.wait(timeout=3)
            time.sleep(0.025)
        with lock:
            active -= 1
        return run

    monkeypatch.setattr(FakeTrainingProvider, "status", fake_status)

    def one(i):
        folder = tmp_path / "runs/characters" / str(i) / "s10-train/tr1/fake"
        provider = make_training_provider("fake", ProviderConfig())
        ready.wait(timeout=4)
        return provider.status(i, SimpleNamespace(plan_dir=folder))

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(one, range(4))) == list(range(4))
    assert peak == 2
    waits = list((tmp_path / "runs/characters").glob("*/ledger/provider-waits.jsonl"))
    assert waits and all(_lines(w)[0]["kind"] == "tuning" for w in waits)
