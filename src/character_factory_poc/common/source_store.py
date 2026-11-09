"""출처 원본을 보관하고, S0가 읽을 사본을 캐릭터 폴더 안에 둔다."""

from __future__ import annotations

import os
import shutil
from contextlib import closing
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

MAX_BYTES = 20 * 1024 * 1024


class SourcePathError(ValueError):
    """원본 경로가 제출된 캐릭터 영역 밖을 가리킨다."""


def inside(folder: Path, *parts: str) -> Path:
    path = folder.joinpath(*parts)
    if path.resolve() != path or not path.is_relative_to(folder):
        raise SourcePathError("출처 경로가 캐릭터 폴더 밖이거나 심볼릭 링크다")
    return path


def local_copy(folder: Path, fid: str, filename: str) -> Path:
    return inside(folder, "s0-source", "uploads", fid, filename)


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        try:
            tmp.write(data)
            tmp.flush()
            os.replace(tmp.name, path)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


class SourceStore(Protocol):
    def upload(self, folder: Path, fid: str, size: int, mime: str) -> dict: ...
    def read(self, folder: Path, fid: str, filename: str, size: int) -> bytes: ...
    def delete(self, folder: Path, fid: str | None = None) -> None: ...


class LocalSourceStore:
    def upload(self, folder: Path, fid: str, size: int, mime: str) -> dict:
        return {
            "method": "PUT",
            "url": f"/api/sources/{folder.name}/files/{fid}/content",
            "headers": {"Content-Type": mime},
        }

    def read(self, folder: Path, fid: str, filename: str, size: int) -> bytes:
        path = local_copy(folder, fid, filename)
        if not path.is_file() or path.stat().st_size != size or size > MAX_BYTES:
            raise ValueError("원문이 없거나 등록한 크기와 다르다")
        with path.open("rb") as stream:
            data = stream.read(size + 1)
        if len(data) != size:
            raise ValueError("읽은 원문 크기가 다르다")
        return data

    def delete(self, folder: Path, fid: str | None = None) -> None:
        path = inside(folder, "s0-source", "uploads", fid or "")
        if path.exists():
            shutil.rmtree(path)


class S3SourceStore(LocalSourceStore):
    def __init__(self, bucket: str, prefix: str, client=None):
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3", region_name=os.getenv("AWS_REGION"), config=Config(signature_version="s3v4")
            )
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""

    def key(self, folder: Path, fid: str = "") -> str:
        return f"{self.prefix}{folder.name}/{fid}"

    def upload(self, folder: Path, fid: str, size: int, mime: str) -> dict:
        url = self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": self.key(folder, fid),
                "ServerSideEncryption": "AES256",
                "ContentType": mime,
                "ContentLength": size,
                "IfNoneMatch": "*",
            },
            ExpiresIn=900,
            HttpMethod="PUT",
        )
        return {
            "method": "PUT",
            "url": url,
            "headers": {
                "Content-Type": mime,
                "x-amz-server-side-encryption": "AES256",
                "If-None-Match": "*",
            },
        }

    def read(self, folder: Path, fid: str, filename: str, size: int) -> bytes:
        from botocore.exceptions import ClientError

        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self.key(folder, fid))
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                raise ValueError("아직 업로드한 원문이 없다") from None
            raise
        with closing(obj["Body"]) as stream:
            if size > MAX_BYTES or obj["ContentLength"] != size:
                raise ValueError("등록한 원문 크기와 다르다")
            data = stream.read(size + 1)
        if len(data) != size:
            raise ValueError("읽은 원문 크기가 다르다")
        return data

    def delete(self, folder: Path, fid: str | None = None) -> None:
        if fid:
            self.client.delete_object(Bucket=self.bucket, Key=self.key(folder, fid))
        else:
            pages = self.client.get_paginator("list_objects_v2")
            for page in pages.paginate(Bucket=self.bucket, Prefix=self.key(folder)):
                keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if keys:
                    result = self.client.delete_objects(
                        Bucket=self.bucket, Delete={"Objects": keys}
                    )
                    if result.get("Errors"):
                        raise OSError("일부 원본을 저장소에서 삭제하지 못했다")
        super().delete(folder, fid)
