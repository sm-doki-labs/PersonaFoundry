"""모티브 출처 초안과 원본 업로드. 확정한 묶음만 S0 작업에 넘긴다."""

from __future__ import annotations

import fcntl
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import Field, ValidationError

from character_factory_poc.common.config import load_config
from character_factory_poc.common.source_store import (
    MAX_BYTES,
    LocalSourceStore,
    S3SourceStore,
    SourcePathError,
    SourceStore,
    atomic_write,
    inside,
    local_copy,
)
from character_factory_poc.contracts.common import Strict
from character_factory_poc.contracts.source import (
    SourcePack,
    SourceSubject,
    SourceText,
    SubjectKind,
    UsageBasis,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import SOURCE, write_origin
from character_factory_poc.stages.s0_source import parse
from character_factory_poc.stages.s3_plan.common import new_character
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError

EXTENSIONS = {".txt", ".srt", ".vtt", ".csv", ".json"}
FIELDS = ("textId", "kind", "register", "subjectSpeaker", "userSpeaker", "date", "sourceUrl")


class Draft(Strict):
    displayName: str = Field(min_length=1)
    subjectKind: SubjectKind
    usageBasis: UsageBasis
    chapterTemplate: Literal["FAN_CALL", "FAMILY_CALL"] | None = None


class Upload(Strict):
    filename: str
    size: int = Field(gt=0, le=MAX_BYTES)
    contentType: str = Field(min_length=1)


class ImportPath(Strict):
    path: str


class IntakeRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def checked(request):
            try:
                return await handler(request)
            except SourcePathError as exc:
                raise WebError(403, str(exc)) from None
            except RequestValidationError as exc:
                names = ", ".join(str(e["loc"][-1]) for e in exc.errors())
                raise WebError(422, f"입력 형식을 확인한다: {names}") from None

        return checked


def save(path: Path, data: dict) -> None:
    atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


def record(spec: Upload) -> dict:
    name = spec.filename
    if (
        Path(name).name != name
        or "\\" in name
        or len(name.encode()) > 255
        or any(ord(c) < 32 for c in name)
        or Path(name).suffix.lower() not in EXTENSIONS
    ):
        raise WebError(400, "원문 파일 이름이나 확장자를 확인한다")
    return dict(
        fileId=uuid4().hex,
        filename=name,
        size=spec.size,
        sha256=None,
        status="pending",
        problems=[],
        **dict.fromkeys(FIELDS),
    )


def find_file(draft, fid):
    for item in draft["files"]:
        if item["fileId"] == fid:
            return item
    raise WebError(404, "등록한 파일이 없다")


def summary(draft):
    problems = parse.basis_problems(
        SourceSubject(**draft["subject"]), UsageBasis(**draft["usageBasis"])
    )
    files = draft["files"]
    ids = [f["textId"] for f in files if f["textId"]]
    if len(ids) != len(set(ids)):
        problems.append("textId가 겹친다")
    for f in files:
        problems.extend(f"{f['filename']}: {p}" for p in f["problems"])
    ready = bool(files) and all(f["status"] == "ready" for f in files)
    return problems, ready and not problems and not draft.get("jobId")


def source_text(folder, item):
    return SourceText(
        **{k: item[k] for k in FIELDS},
        path=str(local_copy(folder, item["fileId"], item["filename"]).relative_to(folder)),
    )


def install_source_routes(app, conf, jobs):
    router = APIRouter(prefix="/api/sources", route_class=IntakeRoute)
    store: SourceStore = (
        S3SourceStore(conf.source_bucket, conf.source_prefix)
        if conf.source_store == "s3"
        else LocalSourceStore()
    )
    if conf.source_store == "s3":
        from botocore.exceptions import BotoCoreError, ClientError
        from fastapi.responses import JSONResponse

        async def storage_error(request, exc):
            return JSONResponse({"detail": "원본 저장소 요청에 실패했다"}, status_code=502)

        for error in (BotoCoreError, ClientError):
            app.add_exception_handler(error, storage_error)
    allow_import = not conf.server_mode and conf.source_store == "local"

    @contextmanager
    def opened(cid, *, edit=False, purge=False):
        folder = reads.character_dir(conf.root, cid)
        try:
            state = inside(folder, "s0-source", "intake.json")
            lock = inside(folder, "s0-source", "intake.lock")
        except ValueError as exc:
            raise WebError(403, str(exc)) from None
        if not folder.is_relative_to(conf.root) or not state.is_file():
            raise WebError(404, "출처 초안이 없다")
        with lock.open("a") as fp:
            fcntl.flock(fp, fcntl.LOCK_EX)
            draft = json.loads(state.read_text("utf-8"))
            if edit and (jobs.active_for(cid) or (draft.get("jobId") and not purge)):
                raise WebError(409, "이미 확정했거나 작업 중인 출처다")
            yield folder, draft
            if edit:
                save(state, draft)

    @router.post("/drafts")
    def create(body: Draft):
        inside(conf.root, "runs", "characters")
        ctx = Context(config=load_config(conf.root, conf.config_path), execute=False)
        cid = new_character(ctx, f"motif-{uuid4().hex[:16]}")
        folder = ctx.character_dir(cid)
        write_origin(folder, SOURCE)
        subject = SourceSubject(displayName=body.displayName, kind=body.subjectKind)
        save(
            inside(folder, "s0-source", "intake.json"),
            dict(
                characterId=cid,
                subject=subject.model_dump(),
                usageBasis=body.usageBasis.model_dump(),
                chapterTemplate=body.chapterTemplate,
                files=[],
            ),
        )
        return {"characterId": cid}

    @router.get("/{cid}")
    def detail(cid: str):
        with opened(cid) as (_, draft):
            problems, ready = summary(draft)
            return {k: draft[k] for k in ("characterId", "subject", "usageBasis", "files")} | {
                "store": conf.source_store,
                "allowPathImport": allow_import,
                "problems": problems,
                "canFinalize": bool(ready),
                "jobId": draft.get("jobId"),
            }

    @router.post("/{cid}/files")
    def presign(cid: str, body: Upload):
        with opened(cid, edit=True) as (folder, draft):
            item = record(body)
            upload = store.upload(folder, item["fileId"], body.size, body.contentType)
            draft["files"].append(item)
            return {"fileId": item["fileId"], "upload": upload}

    @router.put("/{cid}/files/{fid}/content")
    async def content(cid: str, fid: str, request: Request):
        if conf.source_store != "local":
            raise WebError(403, "원본 저장소의 업로드 주소를 사용한다")
        with opened(cid) as (_, draft):
            size = find_file(draft, fid)["size"]
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > size:
                raise WebError(413, "등록한 파일 크기를 넘었다")
            data.extend(chunk)
        if len(data) != size:
            raise WebError(400, "등록한 파일 크기와 다르다")
        with opened(cid, edit=True) as (folder, draft):
            item = find_file(draft, fid)
            path = local_copy(folder, fid, item["filename"])
            if path.exists():
                raise WebError(409, "이미 업로드한 파일이다")
            atomic_write(path, data)
            item["sha256"] = hashlib.sha256(data).hexdigest()
        return {"fileId": fid}

    def check(folder, draft, item, body):
        if body.keys() - set(FIELDS):
            raise WebError(422, "알 수 없는 원문 항목이다")
        candidate = item | body
        try:
            spec = source_text(folder, candidate)
        except ValidationError as exc:
            names = ", ".join(str(e["loc"][-1]) for e in exc.errors())
            raise WebError(422, f"원문 항목 형식을 확인한다: {names}") from None
        item.update(body)
        problems = []
        try:
            data = store.read(folder, item["fileId"], item["filename"], item["size"])
            digest = hashlib.sha256(data).hexdigest()
            if item["sha256"] and item["sha256"] != digest:
                raise ValueError("원본 해시가 다르다")
            item["sha256"] = digest
            raw = data.decode("utf-8-sig")
            problems.extend(parse.restriction_problems(raw))
            parse.read_source(spec, raw, draft["subject"]["displayName"])
        except UnicodeError:
            problems.append("원문은 UTF-8로 저장해야 한다")
        except (ValueError, OSError) as exc:
            problems.append(str(exc))
        item.update(status="problem" if problems else "ready", problems=problems)
        return item

    @router.post("/{cid}/files/{fid}/complete")
    @router.patch("/{cid}/files/{fid}")
    def complete(cid: str, fid: str, body: dict):
        with opened(cid, edit=True) as (folder, draft):
            return check(folder, draft, find_file(draft, fid), body)

    @router.post("/{cid}/import-path")
    def import_path(cid: str, body: ImportPath):
        if not allow_import:
            raise WebError(403, "경로 가져오기는 로컬 저장소에서만 허용한다")
        path = Path(body.path).expanduser()
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise WebError(400, "가져올 원문의 경로와 크기를 확인한다")
        item = record(
            Upload(filename=path.name, size=path.stat().st_size, contentType="text/plain")
        )
        with opened(cid, edit=True) as (folder, draft):
            with path.open("rb") as fp:
                data = fp.read(item["size"] + 1)
            if len(data) != item["size"]:
                raise WebError(409, "원본 크기가 바뀌었다")
            atomic_write(local_copy(folder, item["fileId"], path.name), data)
            item["sha256"] = hashlib.sha256(data).hexdigest()
            draft["files"].append(item)
            return item

    @router.delete("/{cid}/files/{fid}")
    def remove(cid: str, fid: str):
        with opened(cid, edit=True) as (folder, draft):
            item = find_file(draft, fid)
            store.delete(folder, fid)
            draft["files"].remove(item)
        return {"fileId": fid}

    @router.delete("/{cid}")
    def purge(cid: str):
        with opened(cid, edit=True, purge=True) as (folder, draft):
            store.delete(folder)
            draft["files"].clear()
        return {"characterId": cid}

    @router.post("/{cid}/finalize")
    def finalize(cid: str):
        with opened(cid, edit=True) as (folder, draft):
            problems, ready = summary(draft)
            if not ready:
                raise WebError(409, "; ".join(problems) or "모든 원문을 먼저 확인한다")
            texts = []
            for item in draft["files"]:
                try:
                    data = store.read(folder, item["fileId"], item["filename"], item["size"])
                    if hashlib.sha256(data).hexdigest() != item["sha256"]:
                        raise ValueError("확인한 원본 해시와 다르다")
                except (ValueError, OSError) as exc:
                    item.update(status="problem", problems=[str(exc)])
                    save(inside(folder, "s0-source", "intake.json"), draft)
                    raise WebError(409, str(exc)) from None
                if conf.source_store == "s3":
                    atomic_write(local_copy(folder, item["fileId"], item["filename"]), data)
                texts.append(source_text(folder, item))
            opts = {"chapterTemplate": draft["chapterTemplate"]} if draft["chapterTemplate"] else {}
            pack = SourcePack(
                subject=draft["subject"], usageBasis=draft["usageBasis"], texts=texts, **opts
            )
            save(inside(folder, "source-pack.json"), pack.model_dump(mode="json"))
            draft["jobId"] = jobs.submit(cid, until="G0")["jobId"]
            return {"jobId": draft["jobId"]}

    app.include_router(router)
