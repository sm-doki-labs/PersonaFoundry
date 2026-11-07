"""실제 실행 그래프와 생성 요청 API (2026-10-30 연결 계획, backend A).

STAGES를 유일한 그래프 정의로 노출하고, 생성 요청은 state와 고정 브리프만 만든다. 모델·공급자
호출이나 승인은 여기서 하지 않는다. 캐릭터 폴더는 임시 폴더에서 완성한 뒤
같은 slug의 생성 잠금 아래 게시해 기존 state를 덮어쓰지 못하게 한다.
"""

from __future__ import annotations

import fcntl
import os
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI

from character_factory_poc.common.config import load_config
from character_factory_poc.common.ids import character_id, check_slug
from character_factory_poc.pipeline.graph import GATES, STAGES
from character_factory_poc.pipeline.state import StateFile
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError
from character_factory_poc.web.jobs import MAX_CREATOR_BRIEF_CHARS


def install_runtime_routes(app: FastAPI, root: Path, conf: Any, jobs: Any) -> None:
    """create_app이 한 번 설치한다. jobs는 서명 호환을 위해 받고 생성 요청에는 쓰지 않는다."""
    del jobs
    factory = Path(root).expanduser().resolve()

    @app.get("/api/runtime/graph")
    def runtime_graph() -> dict[str, Any]:
        return _graph()

    @app.post("/api/runtime/characters", status_code=201)
    def create_runtime_character(
        body: Annotated[dict[str, Any], Body()],
    ) -> dict[str, str]:
        slug, brief = _creator_input(body)
        return {"characterId": _create_character(factory, conf, slug, brief)}


def _graph() -> dict[str, Any]:
    gate_stage = {stage.gate: sid for sid, stage in STAGES.items() if stage.gate}
    return {
        "stages": [
            {
                "id": sid,
                "name": stage.name,
                "deps": sorted(stage.deps),
                "needs": sorted(stage.needs),
                "after": sorted(stage.after),
                "gate": stage.gate,
                "implemented": stage.implemented,
            }
            for sid, stage in STAGES.items()
        ],
        "gates": [
            {
                "id": gid,
                "title": reads.GATE_TITLES.get(gid, gid),
                "stage": gate_stage.get(gid),
            }
            for gid in GATES
        ],
        "mode": "live",
        "lanes": [
            {"id": lane["id"], "label": lane["label"], "stages": list(lane["stages"])}
            for lane in reads.LANES
        ],
    }


def _creator_input(body: Any) -> tuple[str, str]:
    if not isinstance(body, dict):
        raise WebError(400, "생성 요청 본문은 JSON 객체여야 한다")
    unknown = sorted(set(body) - {"slug", "brief"})
    if unknown:
        raise WebError(400, f"알 수 없는 생성 필드다: {', '.join(unknown)}")
    slug = body.get("slug")
    brief = body.get("brief")
    if not isinstance(slug, str):
        raise WebError(400, "slug는 문자열이어야 한다")
    if not isinstance(brief, str):
        raise WebError(400, "brief는 문자열이어야 한다")
    try:
        check_slug(slug)
    except ValueError as exc:
        raise WebError(400, str(exc)) from exc
    if not brief.strip() or not 1 <= len(brief) <= MAX_CREATOR_BRIEF_CHARS:
        raise WebError(400, f"brief는 1~{MAX_CREATOR_BRIEF_CHARS}자여야 한다")
    return slug, brief


def _create_character(root: Path, conf: Any, slug: str, brief: str) -> str:
    """숨긴 임시 폴더에서 준비한 뒤 완성된 요청만 같은 파일시스템에서 publish한다."""
    cid = character_id(slug)
    characters = root / "runs" / "characters"
    if not characters.resolve().is_relative_to(root):
        raise WebError(400, "캐릭터 폴더가 공장 루트 밖을 가리킨다")
    load_config(root, conf.config_path)
    try:
        characters.mkdir(parents=True, exist_ok=True)
        target = characters / cid
        # 잠금 파일을 지우지 않아 대기 중인 다른 프로세스와 inode를 공유한다.
        lock_path = characters / f".create-{cid}.lock"
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if target.exists() or target.is_symlink():
                raise WebError(409, f"같은 slug의 캐릭터가 이미 있다: {cid}")
            with tempfile.TemporaryDirectory(prefix=".create-", dir=characters) as staging:
                prepared = Path(staging) / "ready"
                folder = prepared / "creator-input"
                folder.mkdir(parents=True)
                with (folder / "brief-r1.md").open("x", encoding="utf-8") as handle:
                    handle.write(brief)
                StateFile(prepared / "state.json", cid).save()
                prepared.rename(target)
    except OSError as exc:
        raise WebError(503, "캐릭터 요청을 저장하지 못했다") from exc
    return cid
