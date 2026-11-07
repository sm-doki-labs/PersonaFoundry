"""S10 평가용 학습 어댑터 추론 세션 (D-0077, LLD §8.9).

GpuInferenceSession은 학습과 같은 GPU 설정([providers.gemma_qlora]·[stages.s10t].gemma_qlora)으로
원격 GPU에 어댑터를 올리고 serve_qlora.py를 띄운 뒤 SSH 포트 전달로 붙는다. ssh_host(또는 테스트의
remote_host)가 있으면 그 호스트를 쓰고, 없으면 Vast에서 한 대를 빌려(기록 폴더/lease.json) 닫을 때
지운다. 닫을 때는 오류가 나도 터널 종료 → 서버 기록 회수 → 서버 종료 → 임대 삭제 순서를 지킨다.

GemmaAdapterChat은 S10 평가의 ChatModel 포트를 구현한다. 요청마다 seed·어댑터·토큰 수·종료 이유를
기록 폴더의 responses.jsonl에 남긴다(QLoRA 평가 규격 03 §생성 기록). 공장은 이 모듈을 테스트에서
가짜 호스트·가짜 터널·httpx.MockTransport로만 돌렸다. 실제 GPU 왕복은 아직 확인하지 않았다.
"""

from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.contracts.training import Transfer
from character_factory_poc.providers.training.errors import (
    RemoteHostError,
    TrainingError,
    TrainingIntegrityError,
)
from character_factory_poc.providers.training.gemma_qlora import (
    GemmaSettings,
    _safe_segment,
    _sync_file,
    ensure_scripts,
)
from character_factory_poc.providers.training.hosts import RemoteHost, VastRemoteHost
from character_factory_poc.providers.training.settings import as_float, as_int
from character_factory_poc.providers.training.vast import VastLease

ADAPTER_FILES = ("adapter_config.json", "adapter_model.safetensors")
DEFAULT_SERVE_PORT = 18123
EVAL_MAX_NEW_TOKENS = 400
EVAL_TEMPERATURE = 0.7
EVAL_TOP_P = 0.9
EVAL_TOP_K = 50


class Tunnel(Protocol):
    def close(self) -> None: ...


TunnelFactory = Callable[[RemoteHost, int, int], Tunnel]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def is_adapter_dir(path: Path) -> bool:
    """학습 결과 폴더에 LoRA 어댑터 두 파일이 모두 있는가."""
    try:
        return path.is_dir() and all((path / name).is_file() for name in ADAPTER_FILES)
    except OSError:
        return False


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class SshTunnel:
    """ssh -N -L 하위 프로세스. close()는 여러 번 불러도 된다."""

    def __init__(self, proc: subprocess.Popen):
        self.proc = proc

    def close(self) -> None:
        if self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


def open_ssh_tunnel(
    host: RemoteHost, local_port: int, remote_port: int, *, timeout_s: float = 30.0
) -> SshTunnel:
    """127.0.0.1:local → 원격 127.0.0.1:remote. 로컬 포트가 열릴 때까지 기다린다."""
    ssh_host = getattr(host, "ssh_host", "")
    if not ssh_host:
        raise RemoteHostError("포트 전달에 쓸 SSH 호스트 정보가 없다")
    argv = [
        "ssh",
        "-N",
        "-L",
        f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}",
        "-p",
        str(getattr(host, "ssh_port", 22)),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
    ]
    key = getattr(host, "ssh_key", "")
    if key:
        argv += ["-i", os.path.expanduser(key)]
    argv.append(f"{getattr(host, 'ssh_user', 'root')}@{ssh_host}")
    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
    except OSError as exc:
        raise RemoteHostError(f"SSH 포트 전달 실행 실패: {type(exc).__name__}") from None
    tunnel = SshTunnel(proc)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            tail = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", "replace")
            raise RemoteHostError(f"SSH 포트 전달이 끝났다(rc={proc.returncode}): {tail[-300:]}")
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=1.0):
                return tunnel
        except OSError:
            time.sleep(0.5)
    tunnel.close()
    raise RemoteHostError("SSH 포트 전달이 제한 시간 안에 열리지 않았다")


def _messages(messages: Sequence[Any]) -> list[dict[str, str]]:
    return [{"role": str(m.role), "content": str(m.content)} for m in messages]


class GemmaAdapterChat:
    """S10 ChatModel 포트. 원격 serve_qlora.py의 /v1/generate를 부른다."""

    name = "gemma_qlora"

    def __init__(
        self,
        base_url: str,
        adapter: str,
        *,
        model: str = "",
        expected_sha256: str = "",
        client: httpx.Client | None = None,
        max_new_tokens: int = EVAL_MAX_NEW_TOKENS,
        temperature: float = EVAL_TEMPERATURE,
        top_p: float = EVAL_TOP_P,
        top_k: int = EVAL_TOP_K,
        timeout_s: float = 900.0,
        log_path: Path | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.adapter = adapter
        self.model = model or adapter
        self.expected_sha256 = expected_sha256
        self._own_client = client is None
        self.client = client or httpx.Client(timeout=timeout_s)
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.timeout_s = timeout_s
        self.log_path = log_path
        self.calls = 0
        self.truncated = 0

    def reply(self, messages: Sequence[Any], *, seed: int, ref: str) -> str:
        body = {
            "adapter": self.adapter,
            "messages": _messages(messages),
            "seed": int(seed),
            "max_new_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "ref": ref,
        }
        self.calls += 1
        try:
            response = self.client.post(
                f"{self.base_url}/v1/generate", json=body, timeout=self.timeout_s
            )
        except httpx.HTTPError as exc:
            self._log(ref, seed, body, error=type(exc).__name__)
            raise FactoryError(f"추론 서버 요청 실패({ref}): {type(exc).__name__}") from None
        if response.status_code != 200:
            try:
                reason = str(response.json().get("error") or "")
            except (ValueError, AttributeError):
                reason = response.text
            self._log(ref, seed, body, error=f"HTTP {response.status_code}: {reason[:300]}")
            raise FactoryError(
                f"추론 서버가 HTTP {response.status_code}를 돌려줬다({ref}): {reason[:300]}"
            )
        try:
            data = response.json()
        except ValueError:
            self._log(ref, seed, body, error="JSON 아님")
            raise FactoryError(f"추론 서버 응답이 JSON이 아니다({ref})") from None
        text = str(data.get("text") or "").strip()
        served = str(data.get("adapterSha256") or "")
        if self.expected_sha256 and served != self.expected_sha256:
            self._log(ref, seed, body, data=data, error="어댑터 sha256 불일치")
            raise TrainingIntegrityError(
                f"추론 서버가 다른 어댑터로 답했다({ref}): {served[:12] or '없음'}"
            )
        if not text:
            self._log(ref, seed, body, data=data, error="빈 답")
            raise FactoryError(f"추론 서버가 빈 답을 돌려줬다({ref})")
        if data.get("finish") == "length":
            self.truncated += 1
        self._log(ref, seed, body, data=data, text=text)
        return text

    def _log(
        self,
        ref: str,
        seed: int,
        body: dict[str, Any],
        *,
        data: dict[str, Any] | None = None,
        text: str = "",
        error: str = "",
    ) -> None:
        if self.log_path is None:
            return
        data = data or {}
        row = {
            "time": _now(),
            "ref": ref,
            "seed": int(seed),
            "adapter": self.adapter,
            "adapterSha256": data.get("adapterSha256", ""),
            "messages": len(body["messages"]),
            "requestSha256": sha256_text(json.dumps(body, ensure_ascii=False, sort_keys=True)),
            "maxNewTokens": body["max_new_tokens"],
            "finish": data.get("finish", ""),
            "inputTokens": data.get("inputTokens"),
            "outputTokens": data.get("outputTokens"),
            "seconds": data.get("seconds"),
            "replySha256": sha256_text(text) if text else "",
            "error": error,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def close(self) -> None:
        if self._own_client:
            self.client.close()


class GpuInferenceSession:
    """원격 GPU에 어댑터를 올리고 추론 서버를 띄우는 컨텍스트 매니저."""

    def __init__(
        self,
        cfg: ProviderConfig,
        record_dir: Path,
        adapters: Mapping[str, Path],
        settings: GemmaSettings | None = None,
        *,
        run_ref: str = "eval",
        estimate_usd: float = 0.0,
        max_wall_seconds: float | None = None,
        tunnel_factory: TunnelFactory | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        if not adapters:
            raise TrainingError("추론 세션에 올릴 어댑터가 없다")
        for name, folder in adapters.items():
            if not name or name == "base" or _safe_segment(name) != name:
                raise TrainingError(f"어댑터 이름이 안전하지 않다: {name!r}")
            if not is_adapter_dir(Path(folder)):
                raise TrainingError(f"어댑터 폴더에 {', '.join(ADAPTER_FILES)}가 없다: {folder}")
        self.cfg = cfg
        extra = cfg.extra
        self.settings = settings or GemmaSettings.from_extra(extra, cfg.model)
        self.record_dir = Path(record_dir)
        self.adapters = {name: Path(folder).resolve() for name, folder in adapters.items()}
        self.run_ref = run_ref
        self.estimate_usd = estimate_usd
        self.max_wall_seconds = max(
            60, int(max_wall_seconds or self.settings.max_gpu_hours * 3600.0)
        )
        self.remote_port = as_int(extra, ("serve_port",), DEFAULT_SERVE_PORT, minimum=1)
        self.ready_timeout_s = as_float(extra, ("serve_ready_timeout_s",), 1800.0, minimum=1.0)
        self.poll_s = as_float(extra, ("serve_poll_s",), 10.0, minimum=0.0)
        self.request_timeout_s = as_float(extra, ("request_timeout_s",), 900.0, minimum=1.0)
        # LONG200(200턴 자기 이력)은 12,288토큰을 넘는다. L40S 48GB에서 32k가 버티는지는 미검증이다.
        self.max_seq_length = extra.get("serve_max_seq_length", 32768)
        self.local_port = extra.get("local_port")
        self.tunnel_factory = tunnel_factory or extra.get("tunnel_factory") or open_ssh_tunnel
        self.sleep = sleep or extra.get("serve_sleep") or time.sleep
        self.clock = clock or extra.get("serve_clock") or time.monotonic
        self.client: httpx.Client | None = extra.get("inference_client")
        self._own_client = False
        self.uses_lease = "remote_host" not in extra and not extra.get("ssh_host")
        self.remote_dir = f"{self.settings.remote_root.rstrip('/')}/infer/{_safe_segment(run_ref)}"
        self.host: RemoteHost | None = None
        self.lease: VastLease | None = None
        self.tunnel: Tunnel | None = None
        self.base_url = ""
        self.server_started = False
        self.chats: list[GemmaAdapterChat] = []
        self.local_sha: dict[str, str] = {}
        self.record: dict[str, Any] = {}

    # ---- 기록 -----------------------------------------------------------------------------

    @property
    def record_path(self) -> Path:
        return self.record_dir / "inference-session.json"

    @property
    def responses_path(self) -> Path:
        return self.record_dir / "responses.jsonl"

    def _save(self, **update: Any) -> None:
        self.record.update(update, updatedAt=_now())
        self.record_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.record_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.record, ensure_ascii=False, indent=2) + "\n", "utf-8")
        os.replace(tmp, self.record_path)

    # ---- 열기 -----------------------------------------------------------------------------

    def __enter__(self) -> GpuInferenceSession:
        try:
            self._open()
        except BaseException as exc:
            errors = self.close(error=f"{type(exc).__name__}: {exc}")
            if errors:
                self._save(cleanupErrors=errors)
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        error = f"{exc_type.__name__}: {exc}" if exc_type is not None else ""
        errors = self.close(error=error)
        if errors and exc_type is None:
            raise RemoteHostError("추론 세션 정리 실패: " + "; ".join(errors))

    def _acquire_host(self) -> RemoteHost:
        extra = self.cfg.extra
        if not self.uses_lease:
            host = extra.get("remote_host")
            return host if host is not None else VastRemoteHost.from_config(extra)
        self.lease = VastLease.from_extra(self.record_dir / "lease.json", extra)
        self.lease.acquire(self.estimate_usd)
        host = self.lease.wait_ready()
        self._save(
            lease={
                "lease": "vast",
                "instanceId": self.lease.instance_id,
                "gpu": self.lease.data.get("gpu"),
                "dphTotal": self.lease.data.get("dphTotal"),
            }
        )
        return host

    def _upload(self, host: RemoteHost) -> dict[str, Any]:
        uploaded: dict[str, Any] = {}
        for name, folder in self.adapters.items():
            files = []
            for filename in ADAPTER_FILES:
                local = folder / filename
                rel = f"adapters/{name}/{filename}"
                transfer = Transfer(path=rel, bytes=local.stat().st_size, sha256=sha256_file(local))
                done = _sync_file(
                    host,
                    local,
                    f"{self.remote_dir}/{rel}",
                    self.settings.chunk_bytes,
                    transfer,
                )
                files.append(done.model_dump(mode="json", exclude_none=True))
                if filename == "adapter_model.safetensors":
                    self.local_sha[name] = done.sha256
            uploaded[name] = {"localDir": str(folder), "files": files}
        return uploaded

    def _pattern(self) -> str:
        # [s] 묶음: 명령줄에 이 패턴 글자 자체가 있어도 pkill/pgrep이 자기 셸을 잡지 않는다.
        return shlex.quote(f"[s]erve_qlora\\.py .*--port {self.remote_port}")

    def _kill_command(self) -> str:
        return f"pkill -f {self._pattern()} || true"

    def _start_command(self) -> str:
        s = self.settings
        versions = {} if s.allow_version_drift else s.expected_versions
        serve = [s.remote_python, "serve_qlora.py"]
        for name in self.adapters:
            serve += ["--adapter", f"{name}=adapters/{name}"]
        serve += [
            "--base-model", s.base_model,
            "--revision", s.revision,
            "--chat-template", s.chat_template,
            "--expected-versions", json.dumps(versions, sort_keys=True),
            "--port", str(self.remote_port),
        ]  # fmt: skip
        if self.max_seq_length is not None:
            serve += ["--max-seq-length", str(int(self.max_seq_length))]
        body = (
            "export HF_HOME=/workspace/hf-cache HF_HUB_DISABLE_TELEMETRY=1 "
            "TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1\n"
            f"exec {shlex.join(serve)}\n"
        )
        folder = shlex.quote(self.remote_dir)
        launch = f"nohup timeout {self.max_wall_seconds}s bash serve.sh > serve.log 2>&1 &"
        return (
            f"cd {folder} && "
            "rm -f serve-state.json serve-requests.jsonl && "
            f"printf %s {shlex.quote(body)} > serve.sh && "
            f"({launch}) && echo started"
        )

    def _alive(self, host: RemoteHost) -> bool:
        command = f"pgrep -f {self._pattern()} >/dev/null && echo up || echo down"
        out = host.run(["bash", "-lc", command])
        return "down" not in out

    def _log_tail(self, host: RemoteHost) -> str:
        try:
            text = host.read_text(f"{self.remote_dir}/serve.log") or ""
        except RemoteHostError:
            return ""
        return text[-500:]

    def _wait_ready(self, host: RemoteHost) -> dict[str, Any]:
        deadline = self.clock() + self.ready_timeout_s
        down = 0
        while True:
            raw = host.read_text(f"{self.remote_dir}/serve-state.json")
            data: dict[str, Any] = {}
            if raw:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {}
            phase = data.get("phase")
            if phase == "ready":
                return data
            if phase == "failed":
                raise RemoteHostError(f"추론 서버 시작 실패: {str(data.get('error') or '')[:500]}")
            down = 0 if self._alive(host) else down + 1
            if down >= 2:
                raise RemoteHostError("추론 서버가 준비 기록 없이 끝났다: " + self._log_tail(host))
            if self.clock() >= deadline:
                raise RemoteHostError(
                    f"추론 서버가 {self.ready_timeout_s:g}초 안에 준비되지 않았다(phase {phase})"
                )
            self.sleep(self.poll_s)

    def _check_ready(self, data: dict[str, Any]) -> None:
        served = data.get("adapters") if isinstance(data.get("adapters"), dict) else {}
        for name, sha in self.local_sha.items():
            if served.get(name) != sha:
                raise TrainingIntegrityError(
                    f"추론 서버가 올린 어댑터 {name}의 sha256이 로컬과 다르다"
                )
        s = self.settings
        if not s.allow_version_drift and s.expected_versions:
            versions = data.get("versions") if isinstance(data.get("versions"), dict) else {}
            drift = {
                k: [v, versions.get(k)]
                for k, v in s.expected_versions.items()
                if versions.get(k) != v
            }
            if drift:
                raise TrainingIntegrityError(f"추론 서버 실행 환경 버전이 고정값과 다르다: {drift}")

    def _open(self) -> None:
        s = self.settings
        self._save(
            status="OPENING",
            runRef=self.run_ref,
            mode="lease" if self.uses_lease else "host",
            remoteDir=self.remote_dir,
            baseModel=s.base_model,
            revision=s.revision,
            chatTemplate=s.chat_template,
            expectedVersions=dict(s.expected_versions),
            estimateUsd=self.estimate_usd,
            maxWallSeconds=self.max_wall_seconds,
            startedAt=_now(),
            error="",
        )
        host = self._acquire_host()
        self.host = host
        self._save(adapters=self._upload(host))
        ensure_scripts(host, self.remote_dir, ("serve_qlora.py",))
        self.server_started = True
        # 같은 포트에 남은 이전 서버를 먼저 끈다(시작 명령과 따로 불러 자기 셸을 잡지 않는다).
        host.run(["bash", "-lc", self._kill_command()])
        host.run(["bash", "-lc", self._start_command()])
        self._save(status="STARTING", serverStartedAt=_now())
        state = self._wait_ready(host)
        self._check_ready(state)
        local_port = int(self.local_port) if self.local_port else free_port()
        self.tunnel = self.tunnel_factory(host, local_port, self.remote_port)
        self.base_url = f"http://127.0.0.1:{local_port}"
        if self.client is None:
            self.client = httpx.Client(timeout=self.request_timeout_s)
            self._own_client = True
        self._save(
            status="READY",
            readyAt=_now(),
            gpu=state.get("gpu"),
            versions=state.get("versions") or {},
            servedAdapters=state.get("adapters") or {},
            localPort=local_port,
            remotePort=self.remote_port,
        )

    def chat(
        self,
        adapter: str,
        *,
        model: str = "",
        max_new_tokens: int = EVAL_MAX_NEW_TOKENS,
        temperature: float = EVAL_TEMPERATURE,
        top_p: float = EVAL_TOP_P,
        top_k: int = EVAL_TOP_K,
    ) -> GemmaAdapterChat:
        if not self.base_url or self.client is None:
            raise TrainingError("추론 세션이 열리지 않았다")
        if adapter not in self.adapters:
            raise TrainingError(f"세션에 올리지 않은 어댑터: {adapter}")
        chat = GemmaAdapterChat(
            self.base_url,
            adapter,
            model=model,
            expected_sha256=self.local_sha.get(adapter, ""),
            client=self.client,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            timeout_s=self.request_timeout_s,
            log_path=self.responses_path,
        )
        self.chats.append(chat)
        return chat

    # ---- 닫기 -----------------------------------------------------------------------------

    def close(self, error: str = "") -> list[str]:
        """터널 → 기록 회수 → 서버 종료 → 임대 삭제. 정리 오류는 모아서 돌려준다."""
        errors: list[str] = []
        cleanup: dict[str, Any] = {}
        if self.tunnel is not None:
            try:
                self.tunnel.close()
                cleanup["tunnelClosed"] = True
            except Exception as exc:  # noqa: BLE001
                errors.append(f"터널 종료: {type(exc).__name__}")
            self.tunnel = None
        if self._own_client and self.client is not None:
            self.client.close()
            self.client = None
        host = self.host
        if host is not None and self.server_started:
            fetched = []
            folder = self.record_dir / "remote"
            for name in ("serve-requests.jsonl", "serve-state.json", "serve.log"):
                try:
                    text = host.read_text(f"{self.remote_dir}/{name}")
                except RemoteHostError as exc:
                    errors.append(f"{name} 회수: {exc}")
                    continue
                if text is None:
                    continue
                folder.mkdir(parents=True, exist_ok=True)
                (folder / name).write_text(
                    text[-200_000:] if name == "serve.log" else text, "utf-8"
                )
                fetched.append(name)
            cleanup["fetched"] = fetched
            try:
                host.run(["bash", "-lc", self._kill_command()])
                cleanup["serverStopped"] = True
            except RemoteHostError as exc:
                errors.append(f"서버 종료: {exc}")
        if self.lease is not None:
            try:
                self.lease.destroy()
                cleanup["leaseDestroyed"] = self.lease.status == "DESTROYED" or not (
                    self.lease.instance_id
                )
            except RemoteHostError as exc:
                errors.append(f"GPU 삭제: {exc}")
                cleanup["leaseDestroyed"] = False
        self.server_started = False
        self.host = None
        self._save(
            status="FAILED" if error else "CLOSED",
            error=error[:1000],
            closedAt=_now(),
            requests=sum(c.calls for c in self.chats),
            truncated=sum(c.truncated for c in self.chats),
            cleanup=cleanup,
            cleanupErrors=errors,
        )
        return errors
