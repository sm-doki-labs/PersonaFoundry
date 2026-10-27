"""한 번만 쓰기 저장소와 revision 폴더 (명세 §13, LLD §6.3)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import ImmutableWriteError


def write_once_bytes(path: Path, data: bytes) -> bool:
    """같은 바이트면 무시(False), 다른 바이트면 거절, 없으면 쓴다(True)."""
    path = Path(path)
    if path.exists():
        if path.read_bytes() == data:
            return False
        raise ImmutableWriteError(f"다른 내용이 이미 있다: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


def write_once_json(path: Path, obj: Any) -> bool:
    pretty = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    return write_once_bytes(path, pretty)


def write_once_text(path: Path, text: str) -> bool:
    return write_once_bytes(path, text.encode("utf-8"))


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_manifest(folder: Path) -> Path:
    """폴더 안 파일의 sha256 목록을 manifest.sha256으로 쓴다 (NFR-01)."""
    folder = Path(folder)
    lines = []
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.name != "manifest.sha256" and not p.name.endswith(".tmp"):
            lines.append(f"{sha256_file(p)}  {p.relative_to(folder).as_posix()}")
    out = folder / "manifest.sha256"
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return out


def verify_manifest(folder: Path) -> list[str]:
    folder = Path(folder)
    out = folder / "manifest.sha256"
    problems: list[str] = []
    if not out.exists():
        return [f"manifest 없음: {folder}"]
    for line in out.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        p = folder / rel
        if not p.exists():
            problems.append(f"파일 없음: {rel}")
        elif sha256_file(p) != digest:
            problems.append(f"해시 불일치: {rel}")
    return problems


_REV_RE = re.compile(r"^([a-z]+)(\d+)$")


def next_rev(parent: Path, prefix: str) -> str:
    """parent 아래 prefix<k> 폴더의 다음 번호를 돌려준다 (단조 증가)."""
    parent = Path(parent)
    k = 0
    if parent.exists():
        for p in parent.iterdir():
            m = _REV_RE.match(p.name)
            if m and m.group(1) == prefix:
                k = max(k, int(m.group(2)))
    return f"{prefix}{k + 1}"
