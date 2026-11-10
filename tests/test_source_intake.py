"""출처 접수부터 G0까지. 합성 원문과 가짜 모델·저장소만 쓴다."""

import hashlib
import io
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from character_factory_poc import cli
from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.source_store import MAX_BYTES, S3SourceStore
from character_factory_poc.contracts.source import SourceText, default_register
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.s0_source import parse
from character_factory_poc.stages.s0_source.run import _load_pack
from character_factory_poc.web.app import create_app
from tests.test_source_s0 import _good_digest

META = {"textId": "a1", "kind": "INTERVIEW", "subjectSpeaker": "선수"}
RAW = "기자: 오늘 어땠어요?\n선수: 재미있었어요.".encode()


def start(client):
    response = client.post(
        "/api/sources/drafts",
        json={
            "displayName": "선수",
            "subjectKind": "PUBLIC_FIGURE",
            "autoReview": False,
            "usageBasis": {"scope": "시험"},
        },
    )
    return "/api/sources/" + response.json()["characterId"]


def register(client, url, data=RAW):
    return client.post(
        url + "/files",
        json={
            "filename": "인터뷰.txt",
            "size": len(data),
            "contentType": "text/plain",
        },
    ).json()


def put(client, url, data=RAW):
    record = register(client, url, data)
    assert client.put(record["upload"]["url"], content=data).is_success
    return url + "/files/" + record["fileId"]


def test_round_trip(tmp_path):
    def runner(job, stream):
        ctx = Context.load(tmp_path, execute=True)
        model = FakeTextModel()
        model.add("AGENT", _good_digest)
        ctx.use_models(model)
        return run_until(ctx, job.character_id, RunOptions(until=job.until, web=True))

    client = TestClient(create_app(tmp_path, runner=runner))
    url = start(client)
    assert not client.get(url).json()["canFinalize"]
    target = put(client, url)
    assert client.post(url + "/finalize").status_code == 409
    record = client.post(target + "/complete", json=META).json()
    assert record["sha256"] == hashlib.sha256(RAW).hexdigest() and record["status"] == "ready"
    assert client.patch(
        target, json={"register": "CASUAL", "sourceUrl": "https://example.test"}
    ).is_success
    assert client.get(url).json()["canFinalize"]
    job = client.post(url + "/finalize").json()["jobId"]
    for _ in range(400):
        info = client.get("/api/jobs/" + job).json()
        if info["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.025)
    assert info["status"] == "succeeded", info["error"]
    folder = tmp_path / "runs/characters" / url.split("/")[-1]
    assert (folder / "s0-source/sp1/gate-G0.html").is_file()
    index = json.loads((folder / "s0-source/sp1/source-index.json").read_text())
    assert index["texts"][0]["register"] == "CASUAL"
    spec = json.loads((folder / "source-pack.json").read_text())["texts"][0]
    assert (
        spec["sourceUrl"] == "https://example.test" and (folder / spec["path"]).read_bytes() == RAW
    )
    assert not Path(spec["path"]).is_absolute()
    assert client.post(url + "/finalize").status_code == 409
    assert client.delete(url).is_success and not (folder / spec["path"]).exists()


@pytest.mark.parametrize(
    "suffix,head,body",
    [
        ("srt", "1\n00:00:01,000 --> 00:00:02,000", "<i>좋아요.</i>"),
        ("vtt", "WEBVTT\n\n첫 장면\n00:01.000 --> 00:02.000 align:start", "<v 선수>좋아요.</v>"),
    ],
)
def test_subtitles(suffix, head, body):
    spec = SourceText(textId="s", path="자막." + suffix, kind="TRANSCRIPT", subjectSpeaker="선수")
    msgs = parse.read_source(spec, head + "\n" + body + "\n", "선수")
    assert [(m.speaker, m.text) for m in msgs] == [("SUBJECT", "좋아요.")]


def test_defaults():
    assert [
        default_register(k) for k in ("INTERVIEW", "ARTICLE", "KAKAO_EXPORT", "TRANSCRIPT")
    ] == ["FORMAL", "FORMAL", "CASUAL", "CASUAL"]


def test_validation_and_import(tmp_path):
    client = TestClient(create_app(tmp_path))
    url = start(client)
    for name, size in [("../x.txt", 2), ("x.html", 2), ("x.txt", MAX_BYTES + 1)]:
        response = client.post(
            url + "/files", json={"filename": name, "size": size, "contentType": "text/plain"}
        )
        assert response.is_client_error and isinstance(response.json()["detail"], str)
    target = put(client, url, RAW + "\n무단전재 및 재배포 금지".encode())
    for field, invalid in [("textId", "bad/id"), ("kind", "TV"), ("register", "V")]:
        assert client.post(target + "/complete", json=META | {field: invalid}).status_code == 422
    record = client.post(target + "/complete", json=META).json()
    assert record["warnings"] and record["status"] == "ready"
    assert client.get(url).json()["canFinalize"]
    assert client.delete(target).is_success
    original = tmp_path / "외부.txt"
    original.write_bytes(RAW)
    item = client.post(url + "/import-path", json={"path": str(original)}).json()
    target = url + "/files/" + item["fileId"]
    assert client.post(target + "/complete", json=META).json()["status"] == "ready"
    folder = tmp_path / "runs/characters" / url.split("/")[-1]
    copy = next((folder / "s0-source/uploads").rglob("*.txt"))
    copy.write_bytes(b"x" * len(RAW))
    assert client.post(url + "/finalize").status_code == 409
    assert not client.get(url).json()["canFinalize"] and original.read_bytes() == RAW


def test_server_rejects_paths(tmp_path, monkeypatch):
    root = tmp_path / "factory"
    root.mkdir()
    config = tmp_path / "server.toml"
    config.write_text("[web]\nport=9000")
    monkeypatch.setenv("CFP_SERVER_MODE", "1")
    monkeypatch.setenv("CFP_ROOT", str(root))
    monkeypatch.setenv("CFP_CONFIG", str(config))
    client = TestClient(create_app(tmp_path))
    assert client.app.state.settings.port == 9000
    url = start(client)
    assert not client.get(url).json()["allowPathImport"]
    assert client.post(url + "/import-path", json={"path": str(config)}).status_code == 403
    with pytest.raises(SystemExit, match="source-pack"):
        cli.main(["--root", str(root), "run", "abc", "--source-pack", str(config)])
    with pytest.raises(SystemExit, match="루트 밖"):
        cli.main(["--root", str(root), "run", "abc", "--brief", str(config)])
    cid = url.split("/")[-1]
    ctx = Context.load(root, execute=False)
    path = ctx.character_dir(cid) / "source-pack.json"
    path.write_text(json.dumps({"texts": [{"path": str(config)}]}))
    with pytest.raises(CheckFailed, match="폴더 밖"):
        _load_pack(ctx, cid, None)
    with pytest.raises(ValueError, match="루트 밖"):
        create_app(tmp_path, jobs_dir=tmp_path / "jobs")


class FakeS3:
    def __init__(self):
        self.objects = {}

    def generate_presigned_url(self, action, **kw):
        assert action == "put_object" and kw["ExpiresIn"] == 900 and kw["HttpMethod"] == "PUT"
        assert (
            kw["Params"]["IfNoneMatch"] == "*" and kw["Params"]["ServerSideEncryption"] == "AES256"
        )
        self.key = kw["Params"]["Key"]
        return "https://example.test/upload"

    def get_object(self, Bucket, Key):
        data = self.objects[Key]
        return {"Body": io.BytesIO(data), "ContentLength": len(data)}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix):
        for k in list(self.objects):
            if k.startswith(Prefix):
                yield {"Contents": [{"Key": k}]}

    def delete_objects(self, Bucket, Delete):
        for obj in Delete["Objects"]:
            del self.objects[obj["Key"]]
        return {}


def test_s3_completion_and_purge(tmp_path, monkeypatch):
    fake = FakeS3()
    monkeypatch.setenv("CFP_SOURCE_STORE", "s3")
    monkeypatch.setenv("CFP_SOURCE_BUCKET", "private")
    monkeypatch.setattr(
        "character_factory_poc.web.sources.S3SourceStore",
        lambda bucket, prefix: S3SourceStore(bucket, prefix, fake),
    )
    client = TestClient(create_app(tmp_path))
    url = start(client)
    item = register(client, url)
    cid = url.split("/")[-1]
    assert fake.key == f"sources/{cid}/{item['fileId']}"
    assert item["upload"]["headers"]["x-amz-server-side-encryption"] == "AES256"
    fake.objects[fake.key] = RAW
    fake.objects["sources/other/file"] = RAW
    target = url + "/files/" + item["fileId"]
    assert client.put(target + "/content", content=RAW).status_code == 403
    assert client.post(target + "/complete", json=META).json()["status"] == "ready"
    folder = tmp_path / "runs/characters" / cid
    copy = folder / "s0-source/uploads" / item["fileId"] / "인터뷰.txt"
    assert not copy.exists()
    monkeypatch.setattr(client.app.state.jobs, "submit", lambda *a, **kw: {"jobId": "시험"})
    assert client.post(url + "/finalize").json() == {"jobId": "시험"}
    assert copy.read_bytes() == RAW
    assert client.delete(url).is_success and not copy.exists()
    assert list(fake.objects) == ["sources/other/file"]


def test_server_job_rejects_linked_runs(tmp_path, monkeypatch):
    root = tmp_path / "factory"
    root.mkdir()
    outside = tmp_path / "outside"
    (outside / "characters" / "test").mkdir(parents=True)
    (root / "runs").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("CFP_SERVER_MODE", "1")
    client = TestClient(create_app(root))
    response = client.post("/api/jobs", json={"characterId": "test"})
    assert response.status_code == 403


def test_pending_files_duplicate_ids_and_short_upload(tmp_path):
    client = TestClient(create_app(tmp_path))
    url = start(client)
    first = register(client, url)
    upload = first["upload"]["url"]
    assert client.put(upload, content=RAW[:-1]).status_code == 400
    assert client.put(upload, content=RAW + b"x").status_code == 413
    assert client.put(upload, content=RAW).is_success
    assert client.put(upload, content=RAW).status_code == 409
    target = url + "/files/" + first["fileId"]
    assert client.post(target + "/complete", json=META).json()["status"] == "ready"
    second = put(client, url)
    assert client.post(second + "/complete", json=META).is_success
    assert not client.get(url).json()["canFinalize"]
    assert client.patch(second, json={"textId": "a2"}).is_success
    assert client.get(url).json()["canFinalize"]


KAKAO = (
    "--------------- 2026년 11월 1일 토요일 ---------------\n"
    + "[나] [오전 9:12] 밥은?\n[엄마] [오전 9:13] 먹었지\n" * 3
    + "[나] [오전 9:14] 응\n[나] [오전 9:15] 알겠어\n"
).encode()


def upload_as(client, display, data, filename="kakao-mom.txt"):
    response = client.post(
        "/api/sources/drafts",
        json={"displayName": display, "subjectKind": "PRIVATE_PERSON", "autoReview": False},
    )
    url = "/api/sources/" + response.json()["characterId"]
    record = client.post(
        url + "/files", json={"filename": filename, "size": len(data), "contentType": "text/plain"}
    ).json()
    assert client.put(record["upload"]["url"], content=data).is_success
    return url, url + "/files/" + record["fileId"]


def test_kakao_never_picks_the_exporter_or_the_busiest_speaker(tmp_path):
    """QA v5 A-03·A-23: 표시 이름과 맞는 화자가 없으면 고르게 하고, 카톡의 '나'는 상대로 권한다."""
    client = TestClient(create_app(tmp_path))
    url, target = upload_as(client, "손흥민", KAKAO)
    item = client.post(target + "/complete", json={}).json()
    assert item["subjectSpeaker"] is None and item["status"] == "problem"
    assert "누가 이 사람인지 골라 주세요" in item["problems"][0] and "엄마" in item["problems"][0]
    assert [s["name"] for s in item["detectedSpeakers"]] == ["엄마", "나"], "the exporter goes last"
    assert item["suggested"]["subjectSpeaker"] is None
    assert item["suggested"]["subjectChoices"] == ["엄마"], "'나' is never offered as the subject"
    assert item["suggested"]["userSpeaker"] == "나"
    assert not client.get(url).json()["canFinalize"]
    same = client.patch(target, json={"subjectSpeaker": "엄마", "userSpeaker": "엄마"}).json()
    assert same["status"] == "problem" and "다른 사람" in same["problems"][-1]
    fixed = client.patch(target, json={"subjectSpeaker": "엄마", "userSpeaker": "나"}).json()
    assert fixed["status"] == "ready" and client.get(url).json()["canFinalize"]

    _, target = upload_as(client, "엄마", KAKAO)
    item = client.post(target + "/complete", json={}).json()
    assert item["status"] == "ready" and item["subjectSpeaker"] == "엄마"
    assert item["suggested"]["userSpeaker"] == "나"

    raw = "기자: 하나\n기자: 둘\n선수: 셋".encode()
    _, target = upload_as(client, "손흥민", raw, "interview.txt")
    item = client.post(target + "/complete", json={}).json()
    assert item["subjectSpeaker"] is None and item["status"] == "problem", "no pick by line count"
    assert item["suggested"]["subjectChoices"] == ["기자", "선수"]
    picked = client.patch(target, json={"subjectSpeaker": "선수"}).json()
    assert picked["status"] == "ready" and picked["suggested"]["userSpeaker"] == "기자"
