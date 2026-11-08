"""G9 승인 패키지 → 우리 앱(doki-app) 적재물 (LLD §8.11, D-0044).

두 저장소는 읽기만 한다. 적재는 그 저장소의 명령을 그 저장소 환경에서 부르고(`export/verify.py`),
여기서는 변환 결과 파일과 `export-result-v1` 기록만 쓴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_of
from character_factory_poc.common.errors import CheckFailed, FactoryError
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import next_rev, write_once_json
from character_factory_poc.contracts.common import ArtifactRef
from character_factory_poc.contracts.release import (
    ExportOutput,
    ExportResult,
    MappingRow,
    Verification,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.export.doki_app import api_svc, chat_svc
from character_factory_poc.stages.export.doki_app.naming import character_uid
from character_factory_poc.stages.export.pg_admin import CommandResult, Runner, SubprocessRunner
from character_factory_poc.stages.export.settings import (
    API_SVC_HEAD,
    CHAT_SVC_HEAD,
    ExportSettings,
    load_export_settings,
)
from character_factory_poc.stages.s11_release.package import (
    load_package,
    now_iso,
    verify_package_files,
)

_HEAD = re.compile(r"^(\S+) \(head\)$")


@dataclass(frozen=True)
class TargetHeads:
    api_svc: str
    chat_svc: str
    api_svc_commit: str = ""
    chat_svc_commit: str = ""

    def versions(self) -> dict[str, str]:
        return {
            "api-svc": f"{self.api_svc}@{self.api_svc_commit}".rstrip("@"),
            "chat-svc": f"{self.chat_svc}@{self.chat_svc_commit}".rstrip("@"),
        }


def _python(repo: Path) -> list[str]:
    venv = repo / ".venv" / "bin" / "python"
    return [str(venv)] if venv.is_file() else ["uv", "run", "python"]


def read_repo_head(repo: Path, kind: str, runner: Runner) -> str:
    """대상 저장소의 alembic head 하나를 읽는다. 여러 head면 거절한다."""
    env = {"RQC_ENV": "local"} if kind == "chat-svc" else {"DEBUG": "true"}
    result = runner.run([*_python(repo), "-m", "alembic", "heads"], cwd=repo, env=env)
    if not result.ok:
        raise FactoryError(f"{kind} 저장소의 alembic heads를 읽지 못했다: {_tail(result)}")
    heads = [m.group(1) for line in result.stdout.splitlines() if (m := _HEAD.match(line.strip()))]
    if len(heads) != 1:
        raise FactoryError(f"{kind} 저장소의 alembic head가 하나가 아니다: {heads}")
    return heads[0]


def read_repo_commit(repo: Path, runner: Runner) -> str:
    result = runner.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo)
    return result.stdout.strip() if result.ok else ""


def read_heads(settings: ExportSettings, runner: Runner) -> TargetHeads:
    return TargetHeads(
        api_svc=read_repo_head(settings.api_svc_repo, "api-svc", runner),
        chat_svc=read_repo_head(settings.chat_svc_repo, "chat-svc", runner),
        api_svc_commit=read_repo_commit(settings.api_svc_repo, runner),
        chat_svc_commit=read_repo_commit(settings.chat_svc_repo, runner),
    )


def ensure_heads(heads: TargetHeads) -> None:
    """변환기가 아는 head와 다르면 적재 전에 멈춘다(LLD §8.11)."""
    problems: list[str] = []
    if heads.api_svc != API_SVC_HEAD:
        problems.append(f"api-svc head가 다르다: {heads.api_svc} != {API_SVC_HEAD}")
    if heads.chat_svc != CHAT_SVC_HEAD:
        problems.append(f"chat-svc head가 다르다: {heads.chat_svc} != {CHAT_SVC_HEAD}")
    if problems:
        raise FactoryError(
            "대상 저장소의 마이그레이션 head가 변환기가 아는 값과 다르다. 적재 전에 멈춘다: "
            + "; ".join(problems)
        )


def _tail(result: CommandResult) -> str:
    lines = (result.stderr or result.stdout).strip().splitlines()
    return lines[-1][:200] if lines else "이유 없음"


def _tree_digest(digests: dict[str, str]) -> str:
    return sha256_of(digests)


def export_doki_app(
    ctx: Context,
    cid: str,
    *,
    verify: bool = False,
    settings: ExportSettings | None = None,
    runner: Runner | None = None,
    heads: TargetHeads | None = None,
    sql=None,
) -> tuple[ExportResult, Path]:
    """G9 승인 패키지를 api-svc 시드 묶음과 chat-svc 콘텐츠 트리로 바꾼다."""
    settings = settings or load_export_settings(ctx)
    runner = runner or SubprocessRunner(settings.timeout_s)
    package, package_dir = load_package(ctx, cid)
    state = ctx.state(cid)
    if state.gate("G9").status != "APPROVED":
        raise FactoryError(f"{cid}: G9 승인 뒤에만 변환한다(현재 {state.gate('G9').status})")
    problems = verify_package_files(package, package_dir)
    if problems:
        raise CheckFailed("sx", ["패키지 해시가 맞지 않는다: " + "; ".join(problems[:5])])

    heads = heads or read_heads(settings, runner)
    ensure_heads(heads)

    seed = api_svc.build_seed(
        package,
        package_dir,
        exported_at=now_iso(),
        alembic_revision=API_SVC_HEAD,
        default_voice_id=settings.default_voice_id,
    )
    tree = chat_svc.build_tree(package, package_dir)
    problems = [
        *api_svc.validate_seed_bundle(seed.bundle),
        *chat_svc.validate_content_tree(tree.files),
    ]
    if problems:
        raise CheckFailed("sx", problems)

    char_dir = ctx.character_dir(cid)
    rev = next_rev(char_dir / "sx-export", "ex")
    rev_dir = char_dir / "sx-export" / rev
    state.transition("sx", "RUNNING", rev=rev)
    seed_path = rev_dir / "doki-app" / "api-svc" / "seed.json"
    tree_dir = rev_dir / "doki-app" / "chat-svc"
    api_svc.write_seed(seed_path, seed.bundle)
    digests = chat_svc.write_tree(tree_dir, tree)

    verification: Verification = Verification(
        status="NOT_RUN",
        disposableDb=True,
        steps=[],
    )
    if verify:
        from character_factory_poc.stages.export.verify import verify_databases

        verification = verify_databases(
            settings=settings,
            heads=heads,
            package=package,
            seed_path=seed_path,
            tree_dir=tree_dir,
            runner=runner,
            sql=sql,
        )

    mapping = [
        *(MappingRow(source=s, target=t, note=n) for s, t, n in seed.mapping),
        *(MappingRow(source=s, target=t, note=n) for s, t, n in tree.mapping),
    ]
    result = ExportResult(
        characterId=cid,
        package=ArtifactRef(
            ref=f"s11-release/{package.packageRev}/package.json",
            sha256=sha256_file(package_dir / "package.json"),
        ),
        target="doki-app",
        targetVersions=heads.versions(),
        outputs=[
            ExportOutput(
                system="api-svc",
                kind="seed-bundle",
                path="doki-app/api-svc/seed.json",
                sha256=sha256_file(seed_path),
            ),
            ExportOutput(
                system="chat-svc",
                kind="content-tree",
                path="doki-app/chat-svc",
                sha256=_tree_digest(digests),
            ),
        ],
        mapping=mapping,
        unmapped=[*seed.unmapped, *tree.unmapped],
        verification=verification,
    )
    write_once_json(rev_dir / "export-result.json", dump(result))
    state.transition(
        "sx",
        "APPROVED" if verification.status != "FAILED" else "CHECK_FAILED",
        rev=rev,
        error=None if verification.status != "FAILED" else _failed_detail(verification),
    )
    if verification.status == "FAILED":
        raise CheckFailed("sx", [_failed_detail(verification)])
    return result, rev_dir


def _failed_detail(verification: Verification) -> str:
    failed = [f"{step.name}: {step.detail}" for step in verification.steps if not step.ok]
    return "적재 확인 실패 — " + "; ".join(failed[:5])


def character_uid_for(cid: str) -> str:
    return str(character_uid(cid))


__all__ = [
    "TargetHeads",
    "character_uid_for",
    "ensure_heads",
    "export_doki_app",
    "read_heads",
    "read_repo_commit",
    "read_repo_head",
]
