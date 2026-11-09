"""모티브 출처 초안과 원본 업로드. 확정한 묶음만 S0 작업에 넘긴다."""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from difflib import SequenceMatcher
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
    default_register,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import (
    SOURCE,
    read_auto_review,
    write_model_mode,
    write_origin,
)
from character_factory_poc.stages.s0_source import parse
from character_factory_poc.stages.s3_plan.common import new_character
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError

EXTENSIONS = {".txt", ".srt", ".vtt", ".csv", ".json"}
FIELDS = ("textId", "kind", "register", "subjectSpeaker", "userSpeaker", "date", "sourceUrl")


class KnownFacts(Strict):
    """S3 기획이 인물 소개 첫 줄로 쓰는 기본 정보(source-pack-v1 knownFacts)."""

    age: str = Field(default="", max_length=20)
    gender: str = Field(default="", max_length=20)
    job: str = Field(default="", max_length=60)
    background: str = Field(default="", max_length=400)


class Draft(Strict):
    displayName: str = Field(min_length=1)
    subjectKind: SubjectKind
    usageBasis: UsageBasis = Field(default_factory=UsageBasis)
    modelMode: Literal["PROMPT_ONLY", "BIND_EXISTING", "TRAIN"] = "PROMPT_ONLY"
    autoReview: bool = True
    chapterTemplate: Literal["FAN_CALL", "FAMILY_CALL"] | None = None
    knownFacts: KnownFacts = Field(default_factory=KnownFacts)


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
            except SourcePathError:
                raise WebError(403, "이 위치의 파일은 열 수 없어요.") from None
            except RequestValidationError:
                raise WebError(422, "입력한 내용과 파일 크기를 확인해 주세요.") from None

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
        raise WebError(400, "원문 파일 이름과 형식을 확인해 주세요.")
    return dict(
        fileId=uuid4().hex,
        filename=name,
        size=spec.size,
        sha256=None,
        status="pending",
        detectedSpeakers=[],
        suggested=dict(subjectSpeaker=None, userSpeaker=None, kind=None, register=None),
        problems=[],
        **dict.fromkeys(FIELDS),
    )


def find_file(draft, fid):
    for item in draft["files"]:
        if item["fileId"] == fid:
            return item
    raise WebError(404, "등록한 파일을 찾을 수 없어요.")


def summary(draft):
    problems = []
    files = draft["files"]
    ids = [f["textId"] for f in files if f["textId"]]
    if len(ids) != len(set(ids)):
        problems.append("원문 이름이 겹쳐요.")
    for f in files:
        problems.extend(f"{f['filename']}: {p}" for p in f["problems"])
    ready = bool(files) and all(f["status"] == "ready" for f in files)
    return problems, ready and not problems and not draft.get("jobId")


def source_text(folder, item):
    return SourceText(
        **{k: item[k] for k in FIELDS},
        path=str(local_copy(folder, item["fileId"], item["filename"]).relative_to(folder)),
    )


def suggested_kind(filename, raw):
    hint = filename.lower() + " " + raw[:180].lower()
    if re.search(
        r"카카오톡|카톡|kakao|date,\s*user,\s*message|\[(?:오전|오후) \d|오[전후] \d+:\d+,", hint
    ):
        return "KAKAO_EXPORT"
    if Path(filename).suffix.lower() in {".vtt", ".srt"} or re.search(
        r"브이로그|vlog|녹취|자막|일상", hint
    ):
        return "TRANSCRIPT"
    if re.search(r"기사|article|보도자료", hint):
        return "ARTICLE"
    return "INTERVIEW"


def auto_text_id(item, files):
    stem = Path(item["filename"]).stem
    base = (
        re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-")
        or "source-" + hashlib.sha256(stem.encode()).hexdigest()[:8]
    )
    taken = {f.get("textId") for f in files if f["fileId"] != item["fileId"]}
    result, n = base, 1
    while result in taken:
        n += 1
        result = f"{base}-{n}"
    return result


def speaker_suggestions(messages, display):
    counts = Counter(m.name for m in messages)
    ranked = counts.most_common()

    def score(name):
        similarity = SequenceMatcher(None, display, name).ratio()
        return (
            name == display,
            name in display or display in name,
            similarity if similarity >= 0.5 else 0,
            counts[name],
        )

    subject = max(counts, key=score, default=None)
    user = next((name for name, _ in ranked if name != subject), None)
    return [dict(name=name, lines=n) for name, n in ranked], subject, user


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
            return JSONResponse({"detail": "원문 저장소에 연결하지 못했어요."}, status_code=502)

        for error in (BotoCoreError, ClientError):
            app.add_exception_handler(error, storage_error)
    allow_import = not conf.server_mode and conf.source_store == "local"

    @contextmanager
    def opened(cid, *, edit=False, purge=False):
        try:
            folder = reads.character_dir(conf.root, cid)
        except WebError as exc:
            raise WebError(exc.status, "만들던 초안을 찾을 수 없어요.") from None
        try:
            state = inside(folder, "s0-source", "intake.json")
            lock = inside(folder, "s0-source", "intake.lock")
        except ValueError:
            raise WebError(403, "이 위치의 파일은 열 수 없어요.") from None
        if not folder.is_relative_to(conf.root) or not state.is_file():
            raise WebError(404, "만들던 초안을 찾을 수 없어요.")
        with lock.open("a") as fp:
            fcntl.flock(fp, fcntl.LOCK_EX)
            draft = json.loads(state.read_text("utf-8"))
            if edit and (jobs.active_for(cid) or (draft.get("jobId") and not purge)):
                raise WebError(409, "이미 만들기를 시작해서 원문을 바꿀 수 없어요.")
            yield folder, draft
            if edit:
                save(state, draft)

    @router.post("/drafts")
    def create(body: Draft):
        inside(conf.root, "runs", "characters")
        ctx = Context(config=load_config(conf.root, conf.config_path), execute=False)
        cid = new_character(ctx, f"motif-{uuid4().hex[:16]}")
        folder = ctx.character_dir(cid)
        write_origin(folder, SOURCE, auto_review=body.autoReview)
        write_model_mode(folder, body.modelMode)
        subject = SourceSubject(displayName=body.displayName, kind=body.subjectKind)
        save(
            inside(folder, "s0-source", "intake.json"),
            dict(
                characterId=cid,
                createdAt=datetime.now(UTC).isoformat(),
                subject=subject.model_dump(),
                usageBasis=body.usageBasis.model_dump(),
                chapterTemplate=body.chapterTemplate,
                knownFacts={
                    k: v.strip() for k, v in body.knownFacts.model_dump().items() if v.strip()
                },
                files=[],
            ),
        )
        return {"characterId": cid}

    @router.get("/drafts")
    def drafts():
        result = []
        for folder in reads.visible_folders(conf.root):
            draft = reads.read_json_file(folder / "s0-source/intake.json")
            if not draft or draft.get("jobId") or jobs.active_for(folder.name):
                continue
            state, _ = reads.read_state(folder)
            if reads.is_draft(draft, state.get("stages", {}).values()):
                result.append(
                    dict(
                        characterId=folder.name,
                        displayName=reads.display_name(reads._persona(folder), draft),
                        createdAt=reads.created_at(folder, draft),
                        files=len(draft["files"]),
                    )
                )
        return sorted(result, key=lambda r: r["createdAt"], reverse=True)

    @router.get("/{cid}")
    def detail(cid: str):
        with opened(cid) as (_, draft):
            problems, ready = summary(draft)
            return {k: draft[k] for k in ("characterId", "subject", "usageBasis", "files")} | {
                "knownFacts": draft.get("knownFacts", {}),
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
            raise WebError(403, "파일을 올릴 때 받은 주소를 이용해 주세요.")
        with opened(cid) as (_, draft):
            size = find_file(draft, fid)["size"]
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > size:
                raise WebError(413, "처음 고른 파일보다 크기가 커요.")
            data.extend(chunk)
        if len(data) != size:
            raise WebError(400, "처음 고른 파일과 크기가 달라요.")
        with opened(cid, edit=True) as (folder, draft):
            item = find_file(draft, fid)
            path = local_copy(folder, fid, item["filename"])
            if path.exists():
                raise WebError(409, "이미 올린 파일이에요.")
            atomic_write(path, data)
            item["sha256"] = hashlib.sha256(data).hexdigest()
        return {"fileId": fid}

    def check(folder, draft, item, body):
        if body.keys() - set(FIELDS):
            raise WebError(422, "바꿀 수 없는 항목이 있어요.")
        candidate = item | body
        display = draft["subject"]["displayName"]
        problems = []
        raw = ""
        try:
            data = store.read(folder, item["fileId"], item["filename"], item["size"])
            digest = hashlib.sha256(data).hexdigest()
            if item["sha256"] and item["sha256"] != digest:
                raise ValueError
            raw = data.decode("utf-8-sig")
            candidate["sha256"] = digest
        except UnicodeError:
            problems.append("한글을 읽을 수 있도록 파일을 UTF-8로 저장해 주세요.")
        except (ValueError, OSError):
            problems.append("원문을 확인할 수 없어 파일을 다시 올려야 해요.")

        kind = suggested_kind(item["filename"], raw)
        candidate["kind"] = candidate["kind"] or kind

        if (
            not candidate["textId"]
            or isinstance(candidate["textId"], str)
            and not candidate["textId"].strip()
        ):
            candidate["textId"] = auto_text_id(item, draft["files"])
        try:
            spec = source_text(folder, candidate)
        except ValidationError:
            raise WebError(422, "원문 이름과 선택한 종류, 말한 자리를 확인해 주세요.") from None
        if spec.register is None:
            candidate["register"] = default_register(spec.kind)
        detected, subject, user = [], None, None
        if not problems:
            try:
                messages = parse.source_messages(spec, raw, display)
                detected, subject, user = speaker_suggestions(messages, display)
                if not (spec.subjectSpeaker or "").strip():
                    spec.subjectSpeaker = candidate["subjectSpeaker"] = subject
                names = [s["name"] for s in detected]
                if not subject and spec.kind != "ARTICLE":
                    problems.append("원문에 누가 말했는지 이름을 적어 주세요.")
                for name in (spec.subjectSpeaker, spec.userSpeaker):
                    if spec.kind != "ARTICLE" and name and name not in names:
                        problems.append(
                            f"‘{name}’ 대신 원문에 있는 이름({', '.join(names)})을 골라 주세요."
                        )
            except (ValueError, KeyError, TypeError):
                problems.append("원문을 읽을 수 없어 날짜와 파일 종류, 화자 표기를 확인해 주세요.")
        candidate.update(
            detectedSpeakers=detected,
            suggested=dict(
                subjectSpeaker=subject, userSpeaker=user, kind=kind, register=default_register(kind)
            ),
            warnings=[
                f"원문에 ‘{warning.split(': ', 1)[-1]}’ 안내가 있어요."
                for warning in parse.restriction_problems(raw)
            ],
        )
        item.update(candidate, status="problem" if problems else "ready", problems=problems)
        return item

    @router.post("/{cid}/files/{fid}/complete")
    @router.patch("/{cid}/files/{fid}")
    def complete(cid: str, fid: str, body: dict):
        with opened(cid, edit=True) as (folder, draft):
            return check(folder, draft, find_file(draft, fid), body)

    @router.post("/{cid}/import-path")
    def import_path(cid: str, body: ImportPath):
        if not allow_import:
            raise WebError(403, "이 컴퓨터에 저장할 때만 파일 위치로 가져올 수 있어요.")
        path = Path(body.path).expanduser()
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise WebError(400, "가져올 파일의 위치와 크기를 확인해 주세요.")
        item = record(
            Upload(filename=path.name, size=path.stat().st_size, contentType="text/plain")
        )
        with opened(cid, edit=True) as (folder, draft):
            with path.open("rb") as fp:
                data = fp.read(item["size"] + 1)
            if len(data) != item["size"]:
                raise WebError(409, "원문 파일의 크기가 바뀌었어요.")
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
                raise WebError(409, "; ".join(problems) or "올린 원문을 모두 확인해 주세요.")
            texts = []
            for item in draft["files"]:
                try:
                    data = store.read(folder, item["fileId"], item["filename"], item["size"])
                    if hashlib.sha256(data).hexdigest() != item["sha256"]:
                        raise ValueError("확인한 원본 해시와 다르다")
                except (ValueError, OSError):
                    message = "확인한 원문과 달라서 파일을 다시 올려야 해요."
                    item.update(status="problem", problems=[message])
                    save(inside(folder, "s0-source", "intake.json"), draft)
                    raise WebError(409, message) from None
                if conf.source_store == "s3":
                    atomic_write(local_copy(folder, item["fileId"], item["filename"]), data)
                texts.append(source_text(folder, item))
            opts = {"chapterTemplate": draft["chapterTemplate"]} if draft["chapterTemplate"] else {}
            pack = SourcePack(
                subject=draft["subject"],
                knownFacts=draft.get("knownFacts", {}),
                usageBasis=draft["usageBasis"],
                texts=texts,
                **opts,
            )
            save(inside(folder, "source-pack.json"), pack.model_dump(mode="json"))
            draft["jobId"] = jobs.submit(cid, until="s8c" if read_auto_review(folder) else "G0")[
                "jobId"
            ]
            return {"jobId": draft["jobId"]}

    app.include_router(router)
