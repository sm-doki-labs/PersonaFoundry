"""Signature reference upload and six-clip routing, synthetic inputs only."""

import hashlib

from fastapi.testclient import TestClient

from character_factory_poc.common.source_store import S3SourceStore
from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.origin import read_signature
from character_factory_poc.providers.fake_image import FakeImageModel, solid_png
from character_factory_poc.providers.fake_video import FakeVideoModel
from character_factory_poc.web.app import create_app
from tests.test_reference_frontend_flow import intake
from tests.test_source_intake import META, RAW, FakeS3
from tests.test_video_evidence_handoff import wait_idle


def pose_upload(client, url, data=None):
    data = data if data is not None else solid_png(90, 160, (30, 160, 90))
    response = client.post(
        url + "/files",
        json={
            "filename": "pose.png",
            "size": len(data),
            "contentType": "image/png",
            "photoRole": "signature",
        },
    )
    assert response.is_success, response.text
    reg = response.json()
    assert client.put(reg["upload"]["url"], content=data).is_success
    result = client.post(url + "/files/" + reg["fileId"] + "/complete", json={})
    assert result.is_success, result.text
    return result.json(), data


def test_pose_is_separate_preview_survives_reload_and_delete(tmp_path, monkeypatch):
    ctx, cid, url, _, client = intake(tmp_path, monkeypatch)
    record, data = pose_upload(client, url)
    assert record["photoRole"] == "signature"
    draft = client.get(url).json()
    assert draft["canFinalize"] is True
    saved = next(f for f in draft["files"] if f["fileId"] == record["fileId"])
    assert client.get(saved["previewUrl"]).content == data
    sig = draft["signaturePose"]
    # The upload is only a gesture reference; the keyframe is generated later.
    assert sig["poseReferencePath"] and not sig.get("middleFramePath")
    assert client.patch(
        url + "/settings",
        json={"videoTier": "light", "signaturePose": {"title": "새 이름", "motion": "손을 든다"}},
    ).is_success
    assert read_signature(ctx.character_dir(cid))["poseReferencePath"] == sig["poseReferencePath"]
    assert client.delete(url + "/files/" + record["fileId"]).is_success
    assert not client.get(url).json()["signaturePose"].get("poseReferencePath")
    assert client.get(saved["previewUrl"]).status_code == 404


def test_pose_does_not_replace_portrait_and_limits_apply(tmp_path, monkeypatch):
    _, _, url, _, client = intake(tmp_path, monkeypatch)
    record, data = pose_upload(client, url)
    again = client.post(
        url + "/files",
        json={
            "filename": "second.png",
            "size": len(data),
            "contentType": "image/png",
            "photoRole": "signature",
        },
    )
    assert again.status_code == 409
    identity = next(
        f
        for f in client.get(url).json()["files"]
        if f["fileType"] == "photo" and f["fileId"] != record["fileId"]
    )
    assert client.delete(url + "/files/" + identity["fileId"]).is_success
    draft = client.get(url).json()
    assert not draft["canFinalize"]
    assert any("인물 사진" in p for p in draft["problems"])
    assert (
        client.post(
            url + "/files",
            json={
                "filename": "bad.txt",
                "size": 10,
                "contentType": "text/plain",
                "photoRole": "signature",
            },
        ).status_code
        == 422
    )


def test_invalid_pose_has_no_preview_or_reference(tmp_path, monkeypatch):
    ctx, cid, url, _, client = intake(tmp_path, monkeypatch)
    record, _ = pose_upload(client, url, b"not an image")
    assert record["status"] == "problem"
    assert not record.get("previewUrl")
    assert not read_signature(ctx.character_dir(cid)).get("poseReferencePath")
    assert client.get(url + "/files/" + record["fileId"] + "/preview").status_code == 409


def test_generated_pose_seed_is_confirmed_and_only_it_reaches_signature_clip(tmp_path, monkeypatch):
    ctx, cid, url, jobs, client = intake(tmp_path, monkeypatch)
    image, video = FakeImageModel(), FakeVideoModel()
    ctx.use_image(image)
    ctx.use_video(video)
    record, data = pose_upload(client, url)
    assert client.post(url + "/finalize").is_success
    wait_idle(jobs, cid)
    root = ctx.character_dir(cid)
    assert len(read_json(root / "source-pack.json")["photos"]) == 1
    # Base master first, then a pose seed edited from that master with the gesture reference.
    assert len(image.requests) == 2
    base_req, pose_req = image.requests
    assert len(base_req.reference_images) == 1
    assert len(pose_req.reference_images) == 2
    assert pose_req.reference_images[0].endswith("ch1/f1.png")
    assert open(pose_req.reference_images[1], "rb").read() == data
    assert "EXACTLY the same pose" in pose_req.prompt and "do not copy" in pose_req.prompt
    preview = client.get(url + "/reference").json()
    assert preview["status"] == "awaiting_confirmation"
    assert preview["signatureImageUrl"] and preview["signatureSha256"]
    seed = client.get(preview["signatureImageUrl"]).content
    assert (
        hashlib.sha256(seed).hexdigest()
        == preview["signatureSha256"]
        != hashlib.sha256(data).hexdigest()
    )
    base = {"revision": preview["revision"], "sha256": preview["sha256"]}
    # Approving only the base image must not approve an unseen pose seed.
    assert client.post(url + "/reference/confirm", json=base).status_code == 409
    wrong = base | {"signatureSha256": "0" * 64}
    assert client.post(url + "/reference/confirm", json=wrong).status_code == 409
    ok = base | {"signatureSha256": preview["signatureSha256"]}
    assert client.post(url + "/reference/confirm", json=ok).is_success
    wait_idle(jobs, cid)
    assert ctx.state(cid).stage("s6").status == "APPROVED", jobs.list(cid)
    rev = ctx.state(cid).stage("s6").currentRev
    inputs = read_json(root / "s6-actions" / rev / "inputs.json")
    actions = [a for chapter in inputs["chapters"] for a in chapter["actions"]]
    carrying = [a for a in actions if a.get("production", {}).get("middleFrame")]
    assert len(carrying) == 1 and carrying[0]["actionKey"] == "signature_good"
    assert len(video.submits) == 6
    keyed = [r for r in video.submits if r.keyframes]
    assert len(keyed) == 1 and keyed[0].keyframes[0][0] == 2.0
    assert all(r.first_frame == r.last_frame for r in video.submits)
    middle = carrying[0]["production"]["middleFrame"]
    assert middle["sha256"] == preview["signatureSha256"]
    assert (root / "s6-actions" / rev / middle["path"]).read_bytes() == seed
    assert client.delete(url + "/files/" + record["fileId"]).status_code == 409
    assert client.get(record["previewUrl"]).content == data


def test_without_pose_upload_only_one_image_and_old_confirm_contract(tmp_path, monkeypatch):
    ctx, cid, url, jobs, client = intake(tmp_path, monkeypatch)
    image = FakeImageModel()
    ctx.use_image(image)
    assert client.post(url + "/finalize").is_success
    wait_idle(jobs, cid)
    assert len(image.requests) == 1
    preview = client.get(url + "/reference").json()
    assert preview["signatureImageUrl"] is None and preview["signatureSha256"] is None
    assert client.post(
        url + "/reference/confirm",
        json={
            "revision": preview["revision"],
            "sha256": preview["sha256"],
        },
    ).is_success


def test_s3_pose_is_copied_for_pipeline_but_not_identity(tmp_path, monkeypatch):
    fake = FakeS3()
    monkeypatch.setenv("CFP_SOURCE_STORE", "s3")
    monkeypatch.setenv("CFP_SOURCE_BUCKET", "private")
    monkeypatch.setattr(
        "character_factory_poc.web.sources.S3SourceStore",
        lambda bucket, prefix: S3SourceStore(bucket, prefix, fake),
    )
    (tmp_path / "factory.toml").write_text('[providers.demo_chat]\nadapter="fake"\n')
    app = create_app(tmp_path)
    client = TestClient(app)
    cid = client.post(
        "/api/sources/drafts",
        json={
            "displayName": "선수",
            "subjectKind": "PUBLIC_FIGURE",
            "videoTier": "light",
            "referenceImage": {},
            "signaturePose": {"title": "인사", "motion": "손을 든다"},
        },
    ).json()["characterId"]
    url = "/api/sources/" + cid
    pose = solid_png(90, 160, (10, 30, 80))
    for name, data, role in [
        ("text.txt", RAW, "identity"),
        ("identity.png", solid_png(90, 160, (30, 40, 50)), "identity"),
        ("pose.png", pose, "signature"),
    ]:
        reg = client.post(
            url + "/files",
            json={
                "filename": name,
                "size": len(data),
                "contentType": "text/plain" if name.endswith("txt") else "image/png",
                "photoRole": role,
            },
        )
        assert reg.is_success, reg.text
        fake.objects[fake.key] = data
        target = url + "/files/" + reg.json()["fileId"]
        result = client.post(target + "/complete", json=META if name.endswith("txt") else {})
        assert result.json()["status"] == "ready"
    root = tmp_path / "runs/characters" / cid
    path = root / read_signature(root)["poseReferencePath"]
    assert not path.exists()
    assert client.get(result.json()["previewUrl"]).content == pose
    monkeypatch.setattr(app.state.jobs, "submit", lambda *a, **kw: {"jobId": "test-job"})
    assert client.post(url + "/finalize").is_success
    assert path.read_bytes() == pose
    assert len(read_json(root / "source-pack.json")["photos"]) == 1


def test_pose_tamper_is_blocked_before_preview_and_launch(tmp_path, monkeypatch):
    ctx, cid, url, _, client = intake(tmp_path, monkeypatch)
    record, data = pose_upload(client, url)
    path = ctx.character_dir(cid) / read_signature(ctx.character_dir(cid))["poseReferencePath"]
    path.write_bytes(data[:-1] + b"x")
    assert client.get(record["previewUrl"]).status_code == 409
    assert client.post(url + "/finalize").status_code == 409


def test_pose_upload_requires_reference_photo_flow(tmp_path, monkeypatch):
    import json

    ctx, cid, url, _, client = intake(tmp_path, monkeypatch)
    settings = ctx.character_dir(cid) / "video-settings.json"
    value = json.loads(settings.read_text())
    value.pop("referenceImage")
    settings.write_text(json.dumps(value))
    data = solid_png(20, 20, (10, 20, 30))
    body = {
        "filename": "pose.png",
        "size": len(data),
        "contentType": "image/png",
        "photoRole": "signature",
    }
    # Without the master-photo review there is no image to redraw the gesture onto.
    assert client.post(url + "/files", json=body).status_code == 409
