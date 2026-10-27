"""임대 GPU 원격 호스트 (LLD §8.9, D-0044 (9)).

`RemoteHost`는 조각 전송·원격 sha256·명령 실행·회수·삭제만 노출한다. 학습 공급자는 이 인터페이스로
이어 올리기와 해시 확인을 하고, 테스트는 가짜 호스트로 네트워크 없이 같은 순서를 확인한다.

VastRemoteHost는 ssh/scp(subprocess)와 Vast REST(httpx)를 쓴다. Vast의 인스턴스 생성·삭제 요청
본문과 응답 필드는 실제 호출로 확인하지 않았으므로(2026-10-27) 첫 실행 전에 대시보드/API 문서와
대조해야 한다. 비밀값은 환경변수 이름으로만 받고 오류 메시지에 넣지 않는다.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import PurePosixPath
from typing import Any, Protocol

import httpx

from character_factory_poc.providers.training.errors import RemoteHostError, TrainingError
from character_factory_poc.providers.training.settings import as_int, as_str


class RemoteHost(Protocol):
    def sha256(self, path: str) -> str | None: ...

    def put_chunk(self, path: str, data: bytes) -> None: ...

    def concat(self, parts: list[str], dest: str) -> None: ...

    def write_text(self, path: str, text: str) -> None: ...

    def read_text(self, path: str) -> str | None: ...

    def run(self, argv: list[str]) -> str: ...

    def fetch(self, remote: str, local: Any) -> None: ...

    def delete(self, path: str) -> None: ...


class VastRemoteHost:
    """ssh/scp로 파일을 옮기고 명령을 실행한다. 인스턴스 생성·삭제는 REST를 쓴다."""

    def __init__(
        self,
        *,
        ssh_host: str,
        ssh_port: int = 22,
        ssh_user: str = "root",
        ssh_key: str = "",
        api_base: str = "https://console.vast.ai/api/v0",
        api_key_env: str = "VAST_API_KEY",
        timeout_s: float = 120.0,
        client: httpx.Client | None = None,
    ):
        if not ssh_host:
            raise TrainingError("ssh_host가 없어 원격 GPU에 붙을 수 없다")
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_key = ssh_key
        self.api_base = api_base.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout_s = timeout_s
        self.client = client or httpx.Client(timeout=30.0)

    @classmethod
    def from_config(cls, extra: dict[str, Any]) -> VastRemoteHost:
        return cls(
            ssh_host=as_str(extra, ("ssh_host",), ""),
            ssh_port=as_int(extra, ("ssh_port",), 22, minimum=1),
            ssh_user=as_str(extra, ("ssh_user",), "root"),
            ssh_key=as_str(extra, ("ssh_key",), ""),
            api_base=as_str(extra, ("api_base",), "https://console.vast.ai/api/v0"),
            api_key_env=as_str(extra, ("vast_api_key_env",), "VAST_API_KEY"),
            timeout_s=as_int(extra, ("ssh_timeout_s",), 120, minimum=1),
            client=extra.get("vast_client"),
        )

    def _ssh_argv(self, command: str) -> list[str]:
        argv = [
            "ssh",
            "-p",
            str(self.ssh_port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        if self.ssh_key:
            argv += ["-i", self.ssh_key]
        argv.append(f"{self.ssh_user}@{self.ssh_host}")
        argv.append(command)
        return argv

    def _ssh(
        self, command: str, *, input_bytes: bytes | None = None
    ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                self._ssh_argv(command),
                input=input_bytes,
                capture_output=True,
                timeout=self.timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RemoteHostError(f"원격 접속 실패: {type(exc).__name__}") from None

    def _check(self, proc: subprocess.CompletedProcess, what: str) -> str:
        if proc.returncode != 0:
            tail = (proc.stderr or b"").decode("utf-8", "replace").strip()[-400:]
            raise RemoteHostError(f"원격 {what} 실패(rc={proc.returncode}): {tail}")
        return (proc.stdout or b"").decode("utf-8", "replace")

    def sha256(self, path: str) -> str | None:
        proc = self._ssh(f"sha256sum {shlex.quote(path)}")
        if proc.returncode != 0:
            return None
        out = (proc.stdout or b"").decode("utf-8", "replace").strip()
        return out.split()[0] if out else None

    def put_chunk(self, path: str, data: bytes) -> None:
        parent = str(PurePosixPath(path).parent)
        cmd = f"mkdir -p {shlex.quote(parent)} && cat > {shlex.quote(path)}"
        self._check(self._ssh(cmd, input_bytes=data), "조각 전송")

    def concat(self, parts: list[str], dest: str) -> None:
        if not parts:
            raise RemoteHostError("합칠 조각이 없다")
        parent = str(PurePosixPath(dest).parent)
        joined = " ".join(shlex.quote(p) for p in parts)
        cmd = f"mkdir -p {shlex.quote(parent)} && cat {joined} > {shlex.quote(dest)}"
        cmd += " && rm -f " + joined
        self._check(self._ssh(cmd), "조각 합치기")

    def write_text(self, path: str, text: str) -> None:
        parent = str(PurePosixPath(path).parent)
        cmd = f"mkdir -p {shlex.quote(parent)} && cat > {shlex.quote(path)}"
        self._check(self._ssh(cmd, input_bytes=text.encode("utf-8")), "텍스트 쓰기")

    def read_text(self, path: str) -> str | None:
        cmd = f"if [ -f {shlex.quote(path)} ]; then cat {shlex.quote(path)}; else exit 3; fi"
        proc = self._ssh(cmd)
        if proc.returncode == 3:
            return None
        return self._check(proc, "텍스트 읽기")

    def run(self, argv: list[str]) -> str:
        return self._check(self._ssh(shlex.join(argv)), "명령 실행").strip()

    def fetch(self, remote: str, local: Any) -> None:
        argv = ["scp", "-P", str(self.ssh_port)]
        if self.ssh_key:
            argv += ["-i", self.ssh_key]
        argv += [f"{self.ssh_user}@{self.ssh_host}:{remote}", str(local)]
        try:
            proc = subprocess.run(argv, capture_output=True, timeout=self.timeout_s, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RemoteHostError(f"회수 실패: {type(exc).__name__}") from None
        self._check(proc, "파일 회수")

    def delete(self, path: str) -> None:
        self._check(self._ssh(f"rm -rf -- {shlex.quote(path)}"), "삭제")

    def _api_key(self) -> str:
        key = os.environ.get(self.api_key_env) if self.api_key_env else None
        if not key:
            raise TrainingError(f"환경변수 {self.api_key_env or '(없음)'}에 Vast API 키가 없다")
        return key

    def create_instance(self, offer_id: str, payload: dict[str, Any]) -> str:
        """Vast REST로 인스턴스를 만든다. 요청·응답 필드는 실제 호출 전 확인이 필요하다."""
        response = self.client.post(
            f"{self.api_base}/asks/{offer_id}/",
            json=payload,
            headers={"Authorization": f"Bearer {self._api_key()}"},
        )
        if response.status_code >= 400:
            raise RemoteHostError(f"Vast 인스턴스 생성 실패: HTTP {response.status_code}")
        data = response.json()
        for key in ("new_contract", "instance_id", "id"):
            if key in data:
                return str(data[key])
        raise RemoteHostError("Vast 인스턴스 생성 응답에 인스턴스 ID가 없다")

    def destroy_instance(self, instance_id: str) -> None:
        response = self.client.delete(
            f"{self.api_base}/instances/{instance_id}/",
            headers={"Authorization": f"Bearer {self._api_key()}"},
        )
        if response.status_code >= 400:
            raise RemoteHostError(f"Vast 인스턴스 삭제 실패: HTTP {response.status_code}")
