#!/usr/bin/env bash
# 일회용 적재 확인용 PostgreSQL(docker/verify-postgres.compose.yml)을 올리고 내린다.
#   scripts/verify_db.sh up     # 올리고 준비될 때까지 기다린 뒤 관리자 DSN 환경변수 줄을 출력
#   scripts/verify_db.sh down   # 내린다(tmpfs라 데이터가 남지 않는다)
#   scripts/verify_db.sh env    # export ACF_PG_ADMIN_URL=... 줄만 출력
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose -f "$project_root/docker/verify-postgres.compose.yml")
dsn="postgresql://acf_admin:acf-verify-local@127.0.0.1:55439/postgres"

case "${1:-}" in
  up)
    "${compose[@]}" up -d --wait
    echo "export ACF_PG_ADMIN_URL=$dsn"
    ;;
  down)
    "${compose[@]}" down -v
    ;;
  env)
    echo "export ACF_PG_ADMIN_URL=$dsn"
    ;;
  *)
    echo "사용법: $0 up|down|env" >&2
    exit 2
    ;;
esac
