"""Vast 임대 GPU 수명 테스트. 가짜 vastai runner로 실제 CLI 인자와 lease.json 전이를 확인한다."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from character_factory_poc.providers.training.errors import RemoteHostError, TrainingLimitError
from character_factory_poc.providers.training.hosts import VastRemoteHost
from character_factory_poc.providers.training.vast import VastLease

TEMPLATE = "c412724d111f171ee3c8554066ba564d"
PUBLIC_KEY = "ssh-ed25519 AAAATESTKEY cfp-test"


def offer(offer_id: int, gpu: str, dph: float) -> dict[str, Any]:
    return {"id": offer_id, "gpu_name": gpu, "dph_total": dph}


def running_row(*, ip: str = "203.0.113.7", port: int = 41022) -> dict[str, Any]:
    return {
        "actual_status": "running",
        "public_ipaddr": ip,
        "ports": {"22/tcp": [{"HostIp": "0.0.0.0", "HostPort": str(port)}]},
    }


class FakeVast:
    """vastai CLI를 흉내 낸다. 인스턴스 목록을 상태로 들고 호출 인자를 모두 남긴다."""

    def __init__(
        self,
        *,
        credit: float = 50.0,
        offers: list[dict[str, Any]] | None = None,
        create: str = "ok",
        rows: list[dict[str, Any]] | None = None,
        destroy_after: int = 0,
        destroy_works: bool = True,
    ) -> None:
        self.calls: list[list[str]] = []
        self.credit = credit
        self.offers = offers if offers is not None else [offer(11, "L40S", 0.62)]
        self.instances: list[dict[str, Any]] = [{"id": 900, "label": "someone-else"}]
        self.next_id = 7001
        self.create = create  # ok | ambiguous(만들어졌지만 응답 실패) | fail(만들지 못함)
        self.rows = list(rows) if rows is not None else [running_row()]
        self.destroy_after = destroy_after
        self.destroy_works = destroy_works
        self.destroyed = False
        self.destroyed_ids: set[str] = set()

    def args(self, verb: str, noun: str) -> list[list[str]]:
        return [c for c in self.calls if c[1:3] == [verb, noun]]

    def _ok(self, argv: list[str], payload: Any) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    def __call__(self, argv: list[str], timeout: float) -> subprocess.CompletedProcess:
        self.calls.append(list(argv))
        assert argv[0] == "vastai"
        assert argv[-1] == "--raw"
        verb, noun, *rest = argv[1:-1]
        if (verb, noun) == ("show", "user"):
            return self._ok(argv, {"credit": self.credit})
        if (verb, noun) == ("search", "offers"):
            return self._ok(argv, self.offers)
        if (verb, noun) == ("show", "instances"):
            if self.destroyed_ids and self.destroy_after > 0:
                self.destroy_after -= 1
            elif self.destroyed_ids and self.destroy_works:
                self.instances = [
                    r for r in self.instances if str(r["id"]) not in self.destroyed_ids
                ]
            return self._ok(argv, self.instances)
        if (verb, noun) == ("create", "instance"):
            label = rest[rest.index("--label") + 1]
            if self.create in {"ok", "ambiguous"}:
                self.instances.append({"id": self.next_id, "label": label})
            if self.create == "ok":
                return self._ok(argv, {"success": True, "new_contract": self.next_id})
            return subprocess.CompletedProcess(argv, 1, "", "read timed out")
        if (verb, noun) == ("show", "instance"):
            row = self.rows.pop(0) if len(self.rows) > 1 else self.rows[0]
            return self._ok(argv, row)
        if (verb, noun) == ("attach", "ssh"):
            return self._ok(argv, {"success": True})
        if (verb, noun) == ("destroy", "instance"):
            self.destroyed = True
            self.destroyed_ids.add(str(rest[0]))
            return self._ok(argv, {"success": True})
        raise AssertionError(f"예상하지 못한 vastai 호출: {argv}")


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds or 1.0


class ProbeHost:
    """SSH 확인(run ["true"])만 받는다. 앞의 몇 번은 접속 실패로 답한다."""

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.probes: list[list[str]] = []
        self.seen: list[dict[str, Any]] = []

    def run(self, argv: list[str]) -> str:
        self.probes.append(argv)
        if self.failures:
            self.failures -= 1
            raise RemoteHostError("ssh: connection refused")
        return ""


def lease_extra(
    tmp_path: Path, vast: FakeVast, host: Any = None, clock: FakeClock | None = None
) -> dict[str, Any]:
    pub = tmp_path / "id_test.pub"
    pub.write_text(PUBLIC_KEY + "\n", "utf-8")
    clock = clock or FakeClock()
    host = host or ProbeHost()

    def factory(data: dict[str, Any]) -> Any:
        if hasattr(host, "seen"):
            host.seen.append(dict(data))
        return host

    return {
        "vast_runner": vast,
        "lease_host_factory": factory,
        "lease_sleep": clock.sleep,
        "lease_clock": clock,
        "ssh_public_key": str(pub),
    }


def make_lease(tmp_path: Path, vast: FakeVast, **kw: Any) -> VastLease:
    return VastLease.from_extra(tmp_path / "plan" / "lease.json", lease_extra(tmp_path, vast, **kw))


def saved(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "plan" / "lease.json").read_text("utf-8"))


def test_acquire_rejects_when_credit_below_estimate_plus_reserve(tmp_path: Path) -> None:
    vast = FakeVast(credit=1.0)
    lease = make_lease(tmp_path, vast)

    with pytest.raises(TrainingLimitError):
        lease.acquire(0.8)  # 0.8 + 예비 0.5 = 1.3 > 잔액 1.0

    assert vast.args("create", "instance") == []
    assert vast.args("search", "offers") == []
    assert not (tmp_path / "plan" / "lease.json").exists()


def test_acquire_picks_cheapest_matching_offer_with_expected_cli_args(tmp_path: Path) -> None:
    vast = FakeVast(
        offers=[
            offer(1, "RTX 4090", 0.30),  # 허용 GPU가 아니다
            offer(2, "L40S", 0.95),  # 시간당 상한 0.9 초과
            offer(3, "L40S", 0.71),
            offer(4, "RTX PRO 5000", 0.62),
        ]
    )
    lease = make_lease(tmp_path, vast)

    lease.acquire(0.5)

    search = vast.args("search", "offers")[0]
    assert search[3].startswith("num_gpus=1 ")
    assert search[4:] == ["--storage", "110", "--order", "dph_total", "--limit", "100", "--raw"]
    [create] = vast.args("create", "instance")
    data = saved(tmp_path)
    assert create == [
        "vastai", "create", "instance", "4",
        "--template_hash", TEMPLATE,
        "--disk", "110",
        "--label", data["label"],
        "--cancel-unavail",
        "--raw",
    ]  # fmt: skip
    assert data["label"].startswith("cfp-")
    assert data["status"] == "CREATED"
    assert data["instanceId"] == 7001
    assert data["gpu"] == "RTX PRO 5000"
    assert data["dphTotal"] == 0.62
    assert data["preexisting"] == [900]
    assert data["creditBefore"] == 50.0


def test_acquire_fails_without_matching_offer(tmp_path: Path) -> None:
    vast = FakeVast(offers=[offer(1, "RTX 4090", 0.3), offer(2, "L40S", 1.2)])
    with pytest.raises(RemoteHostError):
        make_lease(tmp_path, vast).acquire(0.5)
    assert vast.args("create", "instance") == []


def test_ambiguous_create_is_resolved_by_label_without_recreating(tmp_path: Path) -> None:
    vast = FakeVast(create="ambiguous")
    lease = make_lease(tmp_path, vast)

    lease.acquire(0.5)

    assert len(vast.args("create", "instance")) == 1
    data = saved(tmp_path)
    assert data["status"] == "CREATED"
    assert data["instanceId"] == 7001
    assert data["reconciled"] is True


def test_failed_create_is_never_retried(tmp_path: Path) -> None:
    vast = FakeVast(create="fail")
    clock = FakeClock()
    lease = make_lease(tmp_path, vast, clock=clock)

    with pytest.raises(RemoteHostError):
        lease.acquire(0.5)
    assert saved(tmp_path)["status"] == "UNRESOLVED"
    assert clock.sleeps  # 라벨로 몇 번 찾아본 뒤 멈춘다

    again = make_lease(tmp_path, vast)
    with pytest.raises(RemoteHostError):
        again.acquire(0.5)
    assert len(vast.args("create", "instance")) == 1


def test_creating_record_reconciles_instead_of_creating(tmp_path: Path) -> None:
    vast = FakeVast()
    vast.instances.append({"id": 7002, "label": "cfp-pending"})
    path = tmp_path / "plan" / "lease.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"status": "CREATING", "label": "cfp-pending", "preexisting": [900]})
    )

    lease = make_lease(tmp_path, vast)
    lease.acquire(0.5)

    assert vast.args("create", "instance") == []
    assert saved(tmp_path)["instanceId"] == 7002


@pytest.mark.parametrize("status", ["CREATED", "READY"])
def test_existing_lease_is_reused_without_any_vast_call(tmp_path: Path, status: str) -> None:
    vast = FakeVast()
    path = tmp_path / "plan" / "lease.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"status": status, "instanceId": 7001, "label": "cfp-x"}))

    make_lease(tmp_path, vast).acquire(0.5)

    assert vast.calls == []


def test_wait_ready_attaches_key_once_and_retries_ssh(tmp_path: Path) -> None:
    vast = FakeVast(
        rows=[
            {"actual_status": "loading"},
            {"actual_status": "running", "ports": {}},  # 22/tcp가 아직 없다
            running_row(),
        ]
    )
    host = ProbeHost(failures=2)
    lease = make_lease(tmp_path, vast, host=host)
    lease.acquire(0.5)

    ready = lease.wait_ready()

    assert ready is host
    attach = vast.args("attach", "ssh")
    assert attach == [["vastai", "attach", "ssh", "7001", PUBLIC_KEY, "--raw"]]
    assert len(host.probes) == 3  # 실패 2번 뒤 성공
    assert all(p == ["true"] for p in host.probes)
    data = saved(tmp_path)
    assert data["status"] == "READY"
    assert data["keyAttached"] is True
    assert (data["sshHost"], data["sshPort"]) == ("203.0.113.7", 41022)
    assert "readyAt" in data
    # 다시 불러도 GPU 조회나 키 붙이기를 반복하지 않는다.
    before = len(vast.calls)
    make_lease(tmp_path, vast, host=host).wait_ready()
    assert len(vast.calls) == before


def test_wait_ready_skips_attach_when_key_already_attached(tmp_path: Path) -> None:
    vast = FakeVast()
    path = tmp_path / "plan" / "lease.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"status": "CREATED", "instanceId": 7001, "keyAttached": True}))

    make_lease(tmp_path, vast).wait_ready()

    assert vast.args("attach", "ssh") == []
    assert saved(tmp_path)["status"] == "READY"


def test_wait_ready_times_out_and_keeps_created(tmp_path: Path) -> None:
    vast = FakeVast(rows=[{"actual_status": "loading"}])
    clock = FakeClock()
    lease = make_lease(tmp_path, vast, clock=clock)
    lease.acquire(0.5)

    with pytest.raises(RemoteHostError, match="loading"):
        lease.wait_ready()

    assert clock.now >= 1800.0
    assert saved(tmp_path)["status"] == "CREATED"
    assert vast.args("attach", "ssh") == []


def test_destroy_waits_until_instance_leaves_list(tmp_path: Path) -> None:
    vast = FakeVast(destroy_after=2)
    lease = make_lease(tmp_path, vast)
    lease.acquire(0.5)

    lease.destroy()

    assert vast.args("destroy", "instance") == [
        ["vastai", "destroy", "instance", "7001", "--yes", "--raw"]
    ]
    assert len(vast.args("show", "instances")) >= 4  # 생성 전 1번 + 삭제 뒤 3번
    data = saved(tmp_path)
    assert data["status"] == "DESTROYED"
    assert data["creditAfter"] == 50.0
    # 이미 지운 기록은 다시 지우지 않는다.
    lease.destroy()
    assert len(vast.args("destroy", "instance")) == 1


def test_destroy_unverified_is_recorded_and_blocks_new_acquire(tmp_path: Path) -> None:
    vast = FakeVast(destroy_works=False)
    lease = make_lease(tmp_path, vast)
    lease.acquire(0.5)

    with pytest.raises(RemoteHostError):
        lease.destroy()

    assert saved(tmp_path)["status"] == "DESTROY_UNVERIFIED"
    with pytest.raises(RemoteHostError):
        make_lease(tmp_path, vast).acquire(0.5)
    assert len(vast.args("create", "instance")) == 1


def test_cli_failure_message_keeps_only_output_tail(tmp_path: Path) -> None:
    def runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(argv, 2, "", "x" * 1000 + " invalid api key")

    lease = VastLease.from_extra(tmp_path / "lease.json", {"vast_runner": runner})
    with pytest.raises(RemoteHostError) as info:
        lease.cli.credit()
    assert "invalid api key" in str(info.value)
    assert len(str(info.value)) < 400


def write_lease(tmp_path: Path, data: dict[str, Any]) -> None:
    path = tmp_path / "plan" / "lease.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), "utf-8")


def test_destroy_by_label_removes_only_new_instances_with_that_label(tmp_path: Path) -> None:
    vast = FakeVast()
    vast.instances += [
        {"id": 7005, "label": "cfp-lost"},
        {"id": 901, "label": "cfp-lost"},  # 생성 전부터 있던 것은 건드리지 않는다
        {"id": 7006, "label": "cfp-other"},
    ]
    write_lease(tmp_path, {"status": "UNRESOLVED", "label": "cfp-lost", "preexisting": [900, 901]})
    lease = make_lease(tmp_path, vast)
    assert lease.is_alive()

    removed = lease.destroy_by_label()

    assert removed == ["7005"]
    assert vast.args("destroy", "instance") == [
        ["vastai", "destroy", "instance", "7005", "--yes", "--raw"]
    ]
    data = saved(tmp_path)
    assert data["status"] == "DESTROYED"
    assert data["destroyedIds"] == ["7005"]
    assert not make_lease(tmp_path, vast).is_alive()


def test_destroy_by_label_closes_record_when_nothing_was_created(tmp_path: Path) -> None:
    vast = FakeVast()
    write_lease(tmp_path, {"status": "CREATING", "label": "cfp-never", "preexisting": [900]})

    assert make_lease(tmp_path, vast).destroy_by_label() == []

    assert vast.args("destroy", "instance") == []
    assert saved(tmp_path)["status"] == "DESTROYED"
    assert saved(tmp_path)["labelNotFound"] is True


def test_destroy_by_label_unverified_keeps_record_alive(tmp_path: Path) -> None:
    vast = FakeVast(destroy_works=False)
    vast.instances.append({"id": 7005, "label": "cfp-stuck"})
    write_lease(tmp_path, {"status": "AMBIGUOUS", "label": "cfp-stuck", "preexisting": [900]})

    with pytest.raises(RemoteHostError):
        make_lease(tmp_path, vast).destroy_by_label()

    assert saved(tmp_path)["status"] == "DESTROY_UNVERIFIED"
    assert make_lease(tmp_path, vast).is_alive()


class ScpRunner:
    """ssh stat과 scp를 흉내 낸다. 앞의 몇 번은 시간 초과나 끊긴 파일로 실패한다."""

    def __init__(self, data: bytes, failures: list[str]) -> None:
        self.data = data
        self.failures = list(failures)
        self.calls: list[tuple[list[str], float]] = []

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess:
        self.calls.append((list(argv), kw["timeout"]))
        if argv[0] == "ssh":
            return subprocess.CompletedProcess(argv, 0, str(len(self.data)).encode(), b"")
        dest = Path(argv[-1])
        mode = self.failures.pop(0) if self.failures else "ok"
        if mode == "timeout":
            dest.write_bytes(self.data[:3])  # 받다가 끊긴 조각
            raise subprocess.TimeoutExpired(argv, kw["timeout"])
        if mode == "short":
            dest.write_bytes(self.data[:3])
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if mode == "error":
            return subprocess.CompletedProcess(argv, 1, b"", b"Connection reset")
        dest.write_bytes(self.data)
        return subprocess.CompletedProcess(argv, 0, b"", b"")


def remote_host(runner: ScpRunner, sleeps: list[float]) -> VastRemoteHost:
    return VastRemoteHost(
        ssh_host="203.0.113.7", ssh_port=41022, runner=runner, sleep=sleeps.append
    )


def test_fetch_timeout_scales_with_file_size() -> None:
    host = VastRemoteHost(ssh_host="h", runner=ScpRunner(b"", []))
    assert host.fetch_timeout(1024) == 120 + 60
    assert host.fetch_timeout(1024**3) == pytest.approx(1024**3 / (2 * 1024**2) + 60)
    assert host.fetch_timeout(None) >= 1800


def test_fetch_retries_with_fresh_transfer_then_succeeds(tmp_path: Path) -> None:
    data = b"adapter-weights-0123456789"
    runner = ScpRunner(data, ["timeout", "short", "error"])
    sleeps: list[float] = []
    dest = tmp_path / "ck" / "adapter_model.safetensors"
    dest.parent.mkdir()

    remote_host(runner, sleeps).fetch("/workspace/cfp/job/ck/adapter_model.safetensors", dest)

    assert dest.read_bytes() == data
    assert not (dest.parent / (dest.name + ".part")).exists()
    scp = [(argv, timeout) for argv, timeout in runner.calls if argv[0] == "scp"]
    assert len(scp) == 4  # 처음 + 재시도 3번
    assert all(timeout == 180 for _argv, timeout in scp)  # 작은 파일은 최소 120초 + 여유 60초
    assert all(argv[-1].endswith(".part") for argv, _timeout in scp)
    assert len(sleeps) == 3


def test_fetch_gives_up_after_retries_without_partial_file(tmp_path: Path) -> None:
    runner = ScpRunner(b"0123456789", ["timeout"] * 4)
    dest = tmp_path / "file.bin"

    with pytest.raises(RemoteHostError, match="4회 시도"):
        remote_host(runner, []).fetch("/r/file.bin", dest)

    assert not dest.exists()
    assert not (tmp_path / "file.bin.part").exists()
