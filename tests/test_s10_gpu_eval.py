"""S10 평가 GPU 추론 연결 시험 (D-0077). 가짜 호스트·임대·터널·MockTransport만 쓴다(NFR-08)."""

from __future__ import annotations

import hashlib
import json
import shlex
from pathlib import Path
from typing import Any

import httpx
import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.errors import BudgetExceeded, FactoryError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import write_once_json
from character_factory_poc.providers.training.errors import (
    RemoteHostError,
    TrainingIntegrityError,
)
from character_factory_poc.providers.training.gemma_qlora import N3B_VERSIONS
from character_factory_poc.providers.training.inference import (
    GemmaAdapterChat,
    GpuInferenceSession,
)
from character_factory_poc.stages.s10_eval import prereg as eval_prereg
from character_factory_poc.stages.s10_eval import run as eval_run
from character_factory_poc.stages.s10_eval.run import ChatMessage
from tests.support.flow import approve_plan_v2, make_ctx, through_s2
from tests.test_s10_eval import _context, _fake_models, _prompt_pair
from tests.test_s10_train import FakeRemoteHost

REMOTE_DIR = "/workspace/cfp/infer/c1-ev1"


class ServeHost(FakeRemoteHost):
    """serve_qlora.py 시작 명령을 보면 serve-state.json을 loading → ready(또는 failed)로 바꾼다."""

    def __init__(self, *, fail: bool = False, ready_after: int = 2, wrong_sha: bool = False):
        super().__init__()
        self.fail = fail
        self.ready_after = ready_after
        self.wrong_sha = wrong_sha
        self.serve_dir = ""
        self.polls = 0

    def run(self, argv: list[str]) -> str:
        self.commands.append(argv)
        cmd = argv[-1]
        if "printf" in cmd and "serve.sh" in cmd:
            self.serve_dir = shlex.split(cmd)[1]
            self.polls = 0
            return "started"
        if cmd.startswith("pgrep"):
            return "up"
        return ""

    def _served(self) -> dict[str, str]:
        prefix = f"{self.serve_dir}/adapters/"
        out = {}
        for key, data in self.files.items():
            if key.startswith(prefix) and key.endswith("/adapter_model.safetensors"):
                name = key[len(prefix) :].split("/")[0]
                out[name] = "0" * 64 if self.wrong_sha else hashlib.sha256(data).hexdigest()
        return out

    def read_text(self, path: str) -> str | None:
        if self.serve_dir and path == f"{self.serve_dir}/serve-state.json":
            self.polls += 1
            if self.fail:
                state = {"phase": "failed", "error": "RuntimeError: CUDA out of memory"}
            elif self.polls < self.ready_after:
                state = {"phase": "loading"}
            else:
                state = {
                    "phase": "ready",
                    "adapters": self._served(),
                    "versions": dict(N3B_VERSIONS),
                    "gpu": "NVIDIA L40S",
                }
            self.files[path] = json.dumps(state).encode("utf-8")
        return super().read_text(path)


class FakeTunnel:
    def __init__(self, host: Any, local: int, remote: int):
        self.host, self.local, self.remote = host, local, remote
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeVastCli:
    """vastai CLI 흉내. 만들고 지우는 순서만 기록한다."""

    def __init__(self) -> None:
        self.instances_rows: list[dict[str, Any]] = []
        self.calls: list[tuple[str, ...]] = []
        self.destroyed: list[str] = []

    def call(self, *args: Any) -> Any:
        self.calls.append(tuple(str(a) for a in args))
        head = tuple(str(a) for a in args[:2])
        if head == ("show", "user"):
            return {"credit": 10.0}
        if head == ("search", "offers"):
            return [{"id": 9, "gpu_name": "L40S", "dph_total": 0.5}]
        if head == ("show", "instances"):
            return list(self.instances_rows)
        if head == ("create", "instance"):
            label = args[args.index("--label") + 1]
            self.instances_rows.append({"id": 77, "label": label})
            return {"new_contract": 77}
        if head == ("show", "instance"):
            return {
                "actual_status": "running",
                "public_ipaddr": "203.0.113.5",
                "ports": {"22/tcp": [{"HostIp": "0.0.0.0", "HostPort": "2222"}]},
            }
        if head == ("destroy", "instance"):
            self.destroyed.append(str(args[2]))
            self.instances_rows = [r for r in self.instances_rows if str(r["id"]) != str(args[2])]
            return {}
        return {}

    def credit(self) -> float:
        return float(self.call("show", "user")["credit"])

    def instances(self) -> list[dict[str, Any]]:
        return self.call("show", "instances")


def _adapter(root: Path) -> Path:
    folder = root / "adapter"
    folder.mkdir(parents=True)
    (folder / "adapter_config.json").write_text('{"r": 16, "lora_alpha": 32}', "utf-8")
    (folder / "adapter_model.safetensors").write_bytes(bytes(range(256)) * 3)
    return folder


class Server:
    """MockTransport 처리기. 요청 본문을 모으고 원격 serve-requests.jsonl도 흉내 낸다."""

    def __init__(self, host: ServeHost, *, status: int = 200, text: str | None = None):
        self.host = host
        self.status = status
        self.text = text
        self.requests: list[dict[str, Any]] = []
        self.urls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.urls.append(str(request.url))
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "ValueError: 너무 길다"})
        key = f"{self.host.serve_dir}/serve-requests.jsonl"
        line = json.dumps({"ref": body["ref"], "adapter": body["adapter"]}) + "\n"
        self.host.files[key] = self.host.files.get(key, b"") + line.encode("utf-8")
        served = self.host._served().get(body["adapter"], "")
        text = self.text if self.text is not None else f"젬마 답 {body['seed']}"
        return httpx.Response(
            200,
            json={
                "text": text,
                "finish": "stop",
                "inputTokens": 30,
                "outputTokens": 8,
                "seconds": 0.2,
                "adapter": body["adapter"],
                "adapterSha256": served,
            },
        )


def _extra(host: ServeHost, server: Server, tunnels: list[FakeTunnel], **more: Any) -> dict:
    def factory(h: Any, local: int, remote: int) -> FakeTunnel:
        tunnel = FakeTunnel(h, local, remote)
        tunnels.append(tunnel)
        return tunnel

    return {
        "remote_host": host,
        "chunk_bytes": 100,
        "serve_poll_s": 0.0,
        "serve_sleep": lambda _s: None,
        "tunnel_factory": factory,
        "inference_client": httpx.Client(transport=httpx.MockTransport(server)),
        "local_port": 40001,
        **more,
    }


def test_session_uploads_waits_ready_and_sends_seed(tmp_path: Path) -> None:
    folder = _adapter(tmp_path)
    host = ServeHost(ready_after=3)
    server = Server(host)
    tunnels: list[FakeTunnel] = []
    cfg = ProviderConfig(adapter="gemma_qlora", extra=_extra(host, server, tunnels))
    record = tmp_path / "rec"
    local_sha = sha256_file(folder / "adapter_model.safetensors")
    with GpuInferenceSession(cfg, record, {"gemma_sft": folder}, run_ref="c1-ev1") as session:
        remote = f"{REMOTE_DIR}/adapters/gemma_sft/adapter_model.safetensors"
        assert host.sha256(remote) == local_sha
        assert len([p for p in host.puts if ".part" in p and "safetensors" in p]) == 8
        assert host.sha256(f"{REMOTE_DIR}/adapters/gemma_sft/adapter_config.json") == (
            sha256_file(folder / "adapter_config.json")
        )
        assert f"{REMOTE_DIR}/serve_qlora.py" in host.files
        start = next(c[-1] for c in host.commands if "serve.sh" in c[-1])
        assert "--adapter gemma_sft=adapters/gemma_sft" in start
        assert "--expected-versions" in start and "--port 18123" in start
        assert host.polls == 3  # loading 두 번 뒤 ready
        assert (tunnels[0].local, tunnels[0].remote) == (40001, 18123)
        assert not tunnels[0].closed
        chat = session.chat("gemma_sft", model=str(folder))
        reply = chat.reply(
            [ChatMessage("system", "너는 하린이다"), ChatMessage("user", "안녕")],
            seed=12345,
            ref="c1/ev1/SHORT_GEMMA_SFT/OE/oe01/1",
        )
    assert reply == "젬마 답 12345"
    body = server.requests[0]
    assert server.urls[0] == "http://127.0.0.1:40001/v1/generate"
    assert body["adapter"] == "gemma_sft" and body["seed"] == 12345
    assert (body["max_new_tokens"], body["temperature"], body["top_p"], body["top_k"]) == (
        400,
        0.7,
        0.9,
        50,
    )
    assert body["messages"][0] == {"role": "system", "content": "너는 하린이다"}
    assert tunnels[0].closed
    assert "pkill" in host.commands[-1][-1]
    info = json.loads((record / "inference-session.json").read_text("utf-8"))
    assert info["status"] == "CLOSED" and info["mode"] == "host"
    assert info["servedAdapters"] == {"gemma_sft": local_sha}
    assert info["gpu"] == "NVIDIA L40S" and info["versions"] == N3B_VERSIONS
    assert info["requests"] == 1 and info["cleanup"]["tunnelClosed"] is True
    assert (record / "remote" / "serve-requests.jsonl").exists()
    assert (record / "remote" / "serve-state.json").exists()
    row = json.loads((record / "responses.jsonl").read_text("utf-8").splitlines()[0])
    assert row["seed"] == 12345 and row["adapterSha256"] == local_sha and row["finish"] == "stop"


def test_session_rejects_server_with_other_adapter(tmp_path: Path) -> None:
    folder = _adapter(tmp_path)
    host = ServeHost(wrong_sha=True)
    tunnels: list[FakeTunnel] = []
    cfg = ProviderConfig(adapter="gemma_qlora", extra=_extra(host, Server(host), tunnels))
    with pytest.raises(TrainingIntegrityError, match="sha256"):
        with GpuInferenceSession(cfg, tmp_path / "rec", {"gemma_sft": folder}, run_ref="c1-ev1"):
            pass
    assert tunnels == []
    assert "pkill" in host.commands[-1][-1]
    info = json.loads((tmp_path / "rec" / "inference-session.json").read_text("utf-8"))
    assert info["status"] == "FAILED"


def _lease_extra(tmp_path: Path, host: ServeHost, cli: FakeVastCli, tunnels: list) -> dict:
    key = tmp_path / "id_test.pub"
    key.write_text("ssh-ed25519 AAAA test", "utf-8")
    extra = _extra(host, Server(host), tunnels)
    extra.pop("remote_host")
    extra.update(
        vast_cli=cli,
        lease_host_factory=lambda _data: host,
        lease_sleep=lambda _s: None,
        ssh_public_key=str(key),
    )
    return extra


def test_lease_is_destroyed_when_server_fails(tmp_path: Path) -> None:
    folder = _adapter(tmp_path)
    host = ServeHost(fail=True)
    cli = FakeVastCli()
    tunnels: list[FakeTunnel] = []
    cfg = ProviderConfig(adapter="gemma_qlora", extra=_lease_extra(tmp_path, host, cli, tunnels))
    record = tmp_path / "rec"
    with pytest.raises(RemoteHostError, match="CUDA out of memory"):
        with GpuInferenceSession(cfg, record, {"gemma_sft": folder}, run_ref="c1-ev1"):
            pass
    assert cli.destroyed == ["77"]
    assert tunnels == []
    lease = json.loads((record / "lease.json").read_text("utf-8"))
    assert lease["status"] == "DESTROYED"
    info = json.loads((record / "inference-session.json").read_text("utf-8"))
    assert info["mode"] == "lease" and info["status"] == "FAILED"
    assert info["cleanup"]["leaseDestroyed"] is True
    assert (record / "remote" / "serve-state.json").exists()


def test_lease_is_destroyed_when_collection_fails(tmp_path: Path) -> None:
    folder = _adapter(tmp_path)
    host = ServeHost()
    cli = FakeVastCli()
    tunnels: list[FakeTunnel] = []
    cfg = ProviderConfig(adapter="gemma_qlora", extra=_lease_extra(tmp_path, host, cli, tunnels))
    with pytest.raises(RuntimeError, match="중간 실패"):
        with GpuInferenceSession(cfg, tmp_path / "rec", {"gemma_sft": folder}, run_ref="c1-ev1"):
            raise RuntimeError("중간 실패")
    assert cli.destroyed == ["77"] and tunnels[0].closed


def test_adapter_chat_rejects_error_and_empty_reply(tmp_path: Path) -> None:
    msgs = [ChatMessage("user", "안녕")]
    bad = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(400, json={"error": "길다"}))
    )
    with pytest.raises(FactoryError, match="HTTP 400"):
        GemmaAdapterChat("http://127.0.0.1:1", "gemma_sft", client=bad).reply(msgs, seed=1, ref="r")
    empty = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"text": "  "}))
    )
    chat = GemmaAdapterChat("http://x", "gemma_sft", client=empty, log_path=tmp_path / "r.jsonl")
    with pytest.raises(FactoryError, match="빈 답"):
        chat.reply(msgs, seed=2, ref="r2")
    assert json.loads((tmp_path / "r.jsonl").read_text("utf-8"))["error"] == "빈 답"


# ---- run_eval 연결 ------------------------------------------------------------------------


def _bind_gemma_adapter(ctx, cid: str, folder: Path) -> None:
    run = validate(
        "training-run-v2",
        {
            "characterId": cid,
            "datasetRev": "ds1",
            "datasetDigest": "2" * 64,
            "provider": "gemma_qlora",
            "baseModel": "unsloth/gemma-4-31B-it-unsloth-bnb-4bit",
            "requestedConfig": {"epochs": 2},
            "dryRun": False,
            "estimate": {"usd": 1.0, "basis": "시험 가짜"},
            "budgetUsd": 10.0,
            "status": "SUCCEEDED",
            "modelBinding": {"provider": "gemma_qlora", "ref": str(folder), "checkpointId": "ck"},
        },
    )
    path = ctx.character_dir(cid) / "s10-train" / "tr2" / "gemma_qlora" / "training-run.json"
    write_once_json(path, dump(run))


def _gpu_prepared(tmp_path: Path):
    work = tmp_path / "w"
    work.mkdir()
    ctx, cid = _context(work)
    _fake_models(ctx)
    folder = _adapter(tmp_path)
    _bind_gemma_adapter(ctx, cid, folder)
    build = eval_prereg.build_prereg(ctx, cid)
    arm = next(a for a in build.prereg.arms if a.armId == "SHORT_GEMMA_SFT")
    assert arm.model == str(folder)
    return ctx, cid, build, folder


def test_run_eval_refuses_gpu_arm_without_execute(tmp_path: Path) -> None:
    ctx, cid, build, _ = _gpu_prepared(tmp_path)
    ctx.execute = False
    with pytest.raises(FactoryError, match="--execute") as info:
        eval_run.run_eval(ctx, cid, only_arms=["SHORT_GEMMA_SFT"], only_sets=["OE"])
    assert "$" in str(info.value) and "12턴" in str(info.value)
    assert not (build.rev_dir / "runs" / "SHORT_GEMMA_SFT-OE.json").exists()


def test_run_eval_rejects_gpu_cost_over_budget(tmp_path: Path) -> None:
    ctx, cid, _, _ = _gpu_prepared(tmp_path)
    host = ServeHost()
    ctx.config.providers["gemma_qlora"] = ProviderConfig(
        adapter="gemma_qlora", extra=_extra(host, Server(host), [])
    )
    ctx.config.stages["s10"] = {"gpu_budget_usd": 0.1}
    with pytest.raises(BudgetExceeded, match="gpu_budget_usd"):
        eval_run.run_eval(ctx, cid, only_arms=["SHORT_GEMMA_SFT"], only_sets=["OE"])
    assert host.commands == [] and host.files == {}


def test_run_eval_collects_gemma_arm_through_gpu_session(tmp_path: Path) -> None:
    ctx, cid, build, folder = _gpu_prepared(tmp_path)
    host = ServeHost()
    server = Server(host)
    tunnels: list[FakeTunnel] = []
    ctx.config.providers["gemma_qlora"] = ProviderConfig(
        adapter="gemma_qlora", extra=_extra(host, server, tunnels)
    )
    rev_dir = eval_run.run_eval(ctx, cid, only_arms=["SHORT_GEMMA_SFT"], only_sets=["OE", "SE"])
    oe = validate(
        "eval-run-v1",
        json.loads((rev_dir / "runs" / "SHORT_GEMMA_SFT-OE.json").read_text("utf-8")),
    )
    assert oe.model == str(folder) and len(oe.items) == 12
    sent = {(b["ref"], b["seed"]) for b in server.requests}
    for item in oe.items:
        turn = item.turns[0]
        assert turn.reply == f"젬마 답 {turn.seed}"
        assert (f"{cid}/{rev_dir.name}/SHORT_GEMMA_SFT/OE/{item.itemId}/1", turn.seed) in sent
    assert len(server.requests) == 24
    assert {b["adapter"] for b in server.requests} == {"gemma_sft"}
    assert (rev_dir / "runs" / "SHORT_GEMMA_SFT-SE.json").exists()
    assert not (rev_dir / "runs" / "LONG_BASE-OE.json").exists()
    assert len(tunnels) == 1 and tunnels[0].closed  # 두 세트를 한 세션으로 받았다
    info = json.loads((rev_dir / "inference" / "inference-session.json").read_text("utf-8"))
    assert info["status"] == "CLOSED" and info["requests"] == 24
    assert info["runRef"] == f"{cid}-{rev_dir.name}"


# ---- 사전 등록: 설정하지 않은 SFT 조건 제외 ---------------------------------------------------


def _prereg_with(root: Path, providers: str, bound: tuple[str, ...]):
    extra = (
        '[providers.text]\nadapter = "fake"\nmodel = "base-model"\n'
        '[providers.judge]\nadapter = "fake"\nmodel = "anthropic/claude-opus-5-5"\n'
        f"[budget]\nmax_calls_per_command = 20000\n[stages.s10t]\nproviders = {providers}\n"
    )
    ctx, _ = make_ctx(root, extra)
    cid = through_s2(ctx)
    approve_plan_v2(ctx, cid)
    _prompt_pair(ctx, cid)
    state = ctx.state(cid)
    state.set_gate("G7", "APPROVED", "ds1", "gates/G7-ds1.json")
    state.transition("s10t", "RUNNING", rev="tr1")
    state.transition("s10t", "AWAITING_HUMAN", rev="tr1")
    bases = {"gemma_qlora": "google/gemma-4-31B-it", "vertex_gemini": "google/gemini-3.1"}
    for provider in bound:
        run = validate(
            "training-run-v2",
            {
                "characterId": cid,
                "datasetRev": "ds1",
                "datasetDigest": "2" * 64,
                "provider": provider,
                "baseModel": bases[provider],
                "requestedConfig": {"epochs": 1},
                "dryRun": False,
                "estimate": {"usd": 0.0, "basis": "시험 가짜"},
                "budgetUsd": 10.0,
                "status": "SUCCEEDED",
                "modelBinding": {
                    "provider": provider,
                    "ref": f"{provider}-r1",
                    "checkpointId": "c",
                },
            },
        )
        path = ctx.character_dir(cid) / "s10-train" / "tr1" / provider / "training-run.json"
        write_once_json(path, dump(run))
    _fake_models(ctx)
    return ctx, cid


@pytest.mark.parametrize(
    ("providers", "bound", "expected"),
    [
        ('["gemma_qlora"]', ("gemma_qlora",), ["LONG_BASE", "SHORT_GEMMA_SFT"]),
        ('["vertex_gemini"]', (), ["LONG_BASE", "SHORT_GEMINI_SFT"]),
        ('["fake"]', (), ["LONG_BASE", "SHORT_GEMMA_SFT", "SHORT_GEMINI_SFT"]),
    ],
)
def test_prereg_drops_unconfigured_sft_arms(
    tmp_path: Path, providers: str, bound: tuple[str, ...], expected: list[str]
) -> None:
    ctx, cid = _prereg_with(tmp_path, providers, bound)
    build = eval_prereg.build_prereg(ctx, cid)
    assert [a.armId for a in build.prereg.arms] == expected
    models = {a.armId: a.model for a in build.prereg.arms}
    if "SHORT_GEMINI_SFT" in models and not bound:
        assert models["SHORT_GEMINI_SFT"] == "UNBOUND:vertex_gemini"


def test_prereg_rejects_when_no_sft_arm_remains(tmp_path: Path) -> None:
    ctx, cid = _prereg_with(tmp_path, "[]", ())
    with pytest.raises(FactoryError, match="평가할 SFT 조건이 없다"):
        eval_prereg.build_prereg(ctx, cid)
