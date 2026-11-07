"""python -m character_factory_poc.web --root <공장 루트> --port 8765."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from character_factory_poc.web import create_app
from character_factory_poc.web.settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m character_factory_poc.web",
        description="캐릭터 공장 워크숍 웹앱(로컬). 관문과 작업 큐를 화면으로 다룬다.",
    )
    parser.add_argument("--root", default=".", help="공장 루트(factory.toml, runs/)")
    parser.add_argument("--config", default=None, help="factory.toml 경로(다른 위치일 때)")
    parser.add_argument("--host", default=None, help="기본은 [web] host")
    parser.add_argument("--port", type=int, default=None, help="기본은 [web] port")
    parser.add_argument("--jobs-dir", default=None, help="이번 서버의 작업 큐 경로만 별도로 지정")
    parser.add_argument("--log-level", default="info")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    config_path = Path(args.config) if args.config else None
    try:
        conf = load_settings(root, config_path)
    except ValueError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 2
    app = create_app(root, config_path, jobs_dir=Path(args.jobs_dir) if args.jobs_dir else None)
    conf = app.state.settings
    host = args.host or conf.host
    port = args.port or conf.port
    print(f"워크숍: http://{host}:{port}  (공장 루트 {conf.root}, 작업 기록 {conf.jobs_path})")
    uvicorn.run(app, host=host, port=port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
