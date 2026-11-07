"""Vast 임대 GPU 수명 관리 (D-0077, LLD §8.9).

머스크 학습에서 실제로 쓴 절차를 공장으로 옮겼다. 고유 라벨로 한 번만 만들고, 결과가 애매하면
같은 라벨로 찾되 다시 만들지 않는다. 끝나면 삭제하고 목록에서 사라졌는지 확인한다.
SSH 키는 계정 키에 기대지 않고 인스턴스마다 로컬 공개 키를 붙인다(계정 키는 개인 키가 없다).

상태는 학습 계획 폴더의 lease.json에만 남긴다. API 키는 vastai CLI가 자기 설정에서 읽으며
공장은 키 값을 읽거나 기록하지 않는다.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from character_factory_poc.providers.training.errors import RemoteHostError, TrainingLimitError
from character_factory_poc.providers.training.hosts import RemoteHost, VastRemoteHost
from character_factory_poc.providers.training.settings import as_float, as_int, as_str

Runner = Callable[[list[str], float], subprocess.CompletedProcess]
DEFAULT_QUERY = (
    "num_gpus=1 gpu_ram>=45 cpu_ram>=64 disk_space>=110 verified=true rentable=true "
    "rented=false dph_total<0.9"
)


def _run(argv: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class VastSettings:
    vastai_bin: str = "vastai"
    offer_query: str = DEFAULT_QUERY
    gpu_names: tuple[str, ...] = ("L40S", "RTX PRO 5000")
    max_dph: float = 0.9
    template_hash: str = "c412724d111f171ee3c8554066ba564d"
    disk_gb: int = 110
    ssh_public_key: str = "~/.ssh/id_ed25519.pub"
    ssh_private_key: str = "~/.ssh/id_ed25519"
    ready_timeout_s: float = 1800.0
    poll_s: float = 15.0
    credit_reserve_usd: float = 0.5
    label_prefix: str = "cfp"

    @classmethod
    def from_extra(cls, extra: dict[str, Any]) -> VastSettings:
        names = extra.get("gpu_names")
        return cls(
            vastai_bin=os.path.expanduser(as_str(extra, ("vastai_bin",), cls.vastai_bin)),
            offer_query=as_str(extra, ("offer_query",), cls.offer_query),
            gpu_names=tuple(names) if isinstance(names, list) and names else cls.gpu_names,
            max_dph=as_float(extra, ("max_dph",), cls.max_dph, minimum=0.0),
            template_hash=as_str(extra, ("template_hash",), cls.template_hash),
            disk_gb=as_int(extra, ("disk_gb",), cls.disk_gb, minimum=20),
            ssh_public_key=as_str(extra, ("ssh_public_key",), cls.ssh_public_key),
            ssh_private_key=as_str(extra, ("ssh_private_key", "ssh_key"), cls.ssh_private_key),
            ready_timeout_s=as_float(extra, ("ready_timeout_s",), cls.ready_timeout_s, minimum=1.0),
            poll_s=as_float(extra, ("poll_s",), cls.poll_s, minimum=0.0),
            credit_reserve_usd=as_float(extra, ("credit_reserve_usd",), 0.5, minimum=0.0),
            label_prefix=as_str(extra, ("label_prefix",), cls.label_prefix),
        )


class VastCli:
    """vastai CLI를 --raw JSON으로 부른다. 실패 메시지에는 출력 끝부분만 남긴다."""

    def __init__(self, binary: str, runner: Runner | None = None, timeout_s: float = 90.0):
        self.binary = binary
        self.runner = runner or _run
        self.timeout_s = timeout_s

    def call(self, *args: Any) -> Any:
        argv = [self.binary, *(str(a) for a in args), "--raw"]
        try:
            proc = self.runner(argv, self.timeout_s)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RemoteHostError(f"vastai {args[0]} 실행 실패: {type(exc).__name__}") from None
        if proc.returncode != 0:
            tail = ((proc.stderr or "") + (proc.stdout or "")).strip()[-300:]
            raise RemoteHostError(f"vastai {' '.join(str(a) for a in args[:2])} 실패: {tail}")
        out = (proc.stdout or "").strip()
        if not out:
            return {}
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {"message": out[-300:]}

    def credit(self) -> float:
        return float(self.call("show", "user").get("credit") or 0.0)

    def instances(self) -> list[dict[str, Any]]:
        rows = self.call("show", "instances")
        return rows if isinstance(rows, list) else []


@dataclass
class VastLease:
    """한 학습·평가 실행의 GPU 한 대. lease.json이 유일한 기록이다."""

    path: Path
    settings: VastSettings
    cli: VastCli
    host_factory: Callable[[dict[str, Any]], RemoteHost] | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_extra(cls, path: Path, extra: dict[str, Any]) -> VastLease:
        settings = VastSettings.from_extra(extra)
        cli = extra.get("vast_cli") or VastCli(settings.vastai_bin, runner=extra.get("vast_runner"))
        lease = cls(
            path=path,
            settings=settings,
            cli=cli,
            host_factory=extra.get("lease_host_factory"),
            sleep=extra.get("lease_sleep") or time.sleep,
            clock=extra.get("lease_clock") or time.monotonic,
        )
        lease.load()
        return lease

    def load(self) -> dict[str, Any]:
        self.data = json.loads(self.path.read_text("utf-8")) if self.path.exists() else {}
        return self.data

    def _save(self, **update: Any) -> None:
        self.data.update(update, updatedAt=_now())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", "utf-8")
        os.replace(tmp, self.path)

    @property
    def status(self) -> str:
        return str(self.data.get("status") or "NONE")

    @property
    def instance_id(self) -> str | None:
        value = self.data.get("instanceId")
        return str(value) if value is not None else None

    @property
    def label(self) -> str | None:
        value = self.data.get("label")
        return str(value) if value else None

    def is_alive(self) -> bool:
        """지우지 않은 GPU가 있을 수 있는 기록인지 본다(인스턴스 ID나 생성 라벨이 남아 있음)."""
        return self.status not in {"NONE", "DESTROYED"} and bool(self.instance_id or self.label)

    def record(self, **update: Any) -> None:
        """감시(guard)·정리 기록을 lease.json에 덧붙인다."""
        self._save(**update)

    def _owned(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        before = {str(i) for i in self.data.get("preexisting", [])}
        label = self.data.get("label")
        return [r for r in rows if str(r.get("id")) not in before and r.get("label") == label]

    def _choose_offer(self) -> dict[str, Any]:
        s = self.settings
        rows = self.cli.call(
            "search",
            "offers",
            s.offer_query,
            "--storage",
            s.disk_gb,
            "--order",
            "dph_total",
            "--limit",
            100,
        )
        offers = [
            r
            for r in (rows if isinstance(rows, list) else [])
            if r.get("gpu_name") in s.gpu_names and float(r.get("dph_total") or 99) <= s.max_dph
        ]
        if not offers:
            raise RemoteHostError(
                f"조건에 맞는 GPU 제안이 없다({', '.join(s.gpu_names)}, 시간당 ${s.max_dph} 이하)"
            )
        return min(offers, key=lambda r: float(r.get("dph_total") or 99))

    def acquire(self, estimate_usd: float) -> None:
        """GPU를 한 대 만든다. 이미 만든 기록이 있으면 다시 만들지 않는다."""
        if self.status in {"CREATED", "READY"}:
            return
        if self.status == "CREATING":
            self._reconcile()
            return
        if self.status not in {"NONE", "DESTROYED"}:
            raise RemoteHostError(
                f"GPU 임대 기록 상태가 {self.status}다. cfp train cleanup으로 정리한다"
            )
        credit = self.cli.credit()
        need = estimate_usd + self.settings.credit_reserve_usd
        if credit < need:
            raise TrainingLimitError(
                f"Vast 잔액 ${credit:.2f}가 예상 ${estimate_usd:.2f} + 예비 "
                f"${self.settings.credit_reserve_usd:.2f}보다 적다"
            )
        offer = self._choose_offer()
        preexisting = [r.get("id") for r in self.cli.instances()]
        label = f"{self.settings.label_prefix}-{uuid.uuid4().hex[:10]}"
        self.data = {}
        self._save(
            status="CREATING",
            label=label,
            offerId=offer.get("id"),
            gpu=offer.get("gpu_name"),
            dphTotal=offer.get("dph_total"),
            preexisting=preexisting,
            creditBefore=credit,
            estimateUsd=estimate_usd,
            createdAt=_now(),
        )
        created = None
        try:
            result = self.cli.call(
                "create",
                "instance",
                offer["id"],
                "--template_hash",
                self.settings.template_hash,
                "--disk",
                self.settings.disk_gb,
                "--label",
                label,
                "--cancel-unavail",
            )
            if isinstance(result, dict) and result.get("new_contract"):
                created = result["new_contract"]
        except RemoteHostError:
            created = None
        if created is None:
            self._reconcile()
            return
        self._save(status="CREATED", instanceId=created)

    def _reconcile(self) -> None:
        """생성 결과가 애매하면 라벨로 찾는다. 찾지 못해도 다시 만들지 않는다."""
        for _ in range(6):
            owned = self._owned(self.cli.instances())
            if len(owned) == 1:
                self._save(status="CREATED", instanceId=owned[0]["id"], reconciled=True)
                return
            if len(owned) > 1:
                self._save(status="AMBIGUOUS", candidates=[r.get("id") for r in owned])
                raise RemoteHostError("같은 라벨의 GPU가 둘 이상이다. Vast 화면에서 확인한다")
            self.sleep(self.settings.poll_s)
        self._save(status="UNRESOLVED")
        raise RemoteHostError(
            "GPU 생성 결과를 확인하지 못했다. 다시 만들지 않는다. cfp train cleanup으로 확인한다"
        )

    def _endpoint(self, row: dict[str, Any]) -> tuple[str, int] | None:
        ports = row.get("ports") or {}
        for item in ports.get("22/tcp") or []:
            if item.get("HostIp") in {"0.0.0.0", None} and row.get("public_ipaddr"):
                return str(row["public_ipaddr"]), int(item["HostPort"])
        if row.get("ssh_host") and row.get("ssh_port"):
            return str(row["ssh_host"]), int(row["ssh_port"])
        return None

    def host(self) -> RemoteHost:
        if self.status != "READY":
            raise RemoteHostError(f"GPU가 아직 준비되지 않았다({self.status})")
        if self.host_factory is not None:
            return self.host_factory(self.data)
        return VastRemoteHost(
            ssh_host=str(self.data["sshHost"]),
            ssh_port=int(self.data["sshPort"]),
            ssh_key=os.path.expanduser(self.settings.ssh_private_key),
        )

    def wait_ready(self) -> RemoteHost:
        """running이 되고 SSH로 명령이 돌 때까지 기다린다."""
        if self.status == "READY":
            return self.host()
        if self.status != "CREATED" or not self.instance_id:
            raise RemoteHostError(f"GPU 기록 상태가 {self.status}라 준비를 기다릴 수 없다")
        deadline = self.clock() + self.settings.ready_timeout_s
        attached = bool(self.data.get("keyAttached"))
        last = ""
        while self.clock() < deadline:
            try:
                row = self.cli.call("show", "instance", self.instance_id)
            except RemoteHostError:
                row = {}  # 일시적인 조회 실패는 다음 주기에 다시 본다
            row = row if isinstance(row, dict) else {}
            last = str(row.get("actual_status") or "")
            endpoint = self._endpoint(row) if last == "running" else None
            if endpoint is not None:
                if not attached:
                    key_path = Path(os.path.expanduser(self.settings.ssh_public_key))
                    self.cli.call(
                        "attach", "ssh", self.instance_id, key_path.read_text("utf-8").strip()
                    )
                    attached = True
                    self._save(keyAttached=True)
                self._save(sshHost=endpoint[0], sshPort=endpoint[1], status="READY")
                try:
                    host = self.host()
                    host.run(["true"])
                    self._save(readyAt=_now())
                    return host
                except RemoteHostError:
                    self._save(status="CREATED")
            self.sleep(self.settings.poll_s)
        raise RemoteHostError(f"GPU가 제한 시간 안에 준비되지 않았다(마지막 상태 {last or '없음'})")

    def destroy(self) -> None:
        """삭제하고 목록에서 사라진 것을 확인한다. 이미 없으면 기록만 고친다."""
        if not self.instance_id or self.status == "DESTROYED":
            return
        try:
            self.cli.call("destroy", "instance", self.instance_id, "--yes")
        except RemoteHostError:
            pass
        for _ in range(10):
            try:
                rows = self.cli.instances()
            except RemoteHostError:
                rows = None  # 목록을 못 읽으면 사라졌다고 보지 않는다
            if rows is not None and not any(str(r.get("id")) == self.instance_id for r in rows):
                credit = None
                try:
                    credit = self.cli.credit()
                except RemoteHostError:
                    pass
                self._save(status="DESTROYED", destroyedAt=_now(), creditAfter=credit)
                return
            self.sleep(self.settings.poll_s or 1.0)
        self._save(status="DESTROY_UNVERIFIED")
        raise RemoteHostError(
            f"GPU {self.instance_id} 삭제를 확인하지 못했다. Vast 화면에서 확인한다"
        )

    def destroy_by_label(self) -> list[str]:
        """인스턴스 ID 없이 남은 기록(CREATING·UNRESOLVED·AMBIGUOUS)을 라벨로 찾아 지운다.

        라벨이 같고 생성 전 목록에 없던 인스턴스만 지운다. 목록에서 모두 사라진 것을 확인한 뒤에만
        DESTROYED로 남긴다. 찾은 것이 없으면 만들어지지 않은 것으로 보고 DESTROYED로 닫는다.
        """
        if self.status == "DESTROYED":
            return []
        if self.instance_id:
            ident = self.instance_id
            self.destroy()
            return [ident]
        if not self.label:
            raise RemoteHostError("라벨도 인스턴스 ID도 없어 GPU를 찾을 수 없다")
        requested: list[str] = []
        for _ in range(10):
            try:
                rows = self.cli.instances()
            except RemoteHostError:
                rows = None  # 목록을 못 읽으면 사라졌다고 보지 않는다
            if rows is not None:
                remaining = [str(r.get("id")) for r in self._owned(rows)]
                if not remaining:
                    credit = None
                    try:
                        credit = self.cli.credit()
                    except RemoteHostError:
                        pass
                    self._save(
                        status="DESTROYED",
                        destroyedAt=_now(),
                        destroyedIds=requested,
                        labelNotFound=not requested,
                        creditAfter=credit,
                    )
                    return requested
                for ident in remaining:
                    if ident in requested:
                        continue
                    requested.append(ident)
                    try:
                        self.cli.call("destroy", "instance", ident, "--yes")
                    except RemoteHostError:
                        pass
            self.sleep(self.settings.poll_s or 1.0)
        self._save(status="DESTROY_UNVERIFIED", candidates=requested)
        raise RemoteHostError(
            f"라벨 {self.label}의 GPU 삭제를 확인하지 못했다. Vast 화면에서 확인한다"
        )
