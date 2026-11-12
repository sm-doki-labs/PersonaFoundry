#!/usr/bin/env bash
# Railway 시연 서버 배포(D-0208): 공장 HEAD 와 dev 배포판 chat-svc 를 한 묶음으로 올린다.
# GitHub 토큰 없이 로컬 chat-svc 체크아웃에서 git archive 로 넣는다.
#   CHAT_SVC_REPO(기본 ~/projects/_wt/chat-svc-live), CHAT_SVC_REV(기본 그 체크아웃의 HEAD)
set -euo pipefail

root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
chat_repo=${CHAT_SVC_REPO:-$HOME/projects/_wt/chat-svc-live}
chat_rev=${CHAT_SVC_REV:-$(git -C "$chat_repo" rev-parse HEAD)}
[[ -z $(git -C "$root" status --porcelain) ]] || { echo "먼저 변경 사항을 커밋하세요." >&2; exit 1; }
# 묶음은 임시 폴더에서 올리므로, 이 저장소에 이어 둔 Railway 프로젝트·환경을 먼저 읽는다(railway link).
read -r project env < <(cd "$root" && railway status --json | python3 -c 'import json,sys; d=json.load(sys.stdin); e=d["environments"]["edges"][0]["node"]; print(d["id"], e["name"])')
service=${RAILWAY_DEPLOY_SERVICE:-factory}

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
git -C "$root" archive HEAD | tar -x -C "$stage"
mkdir -p "$stage/vendor/chat-svc"
git -C "$chat_repo" archive "$chat_rev" pyproject.toml uv.lock README.md src data | tar -x -C "$stage/vendor/chat-svc"
echo "공장 $(git -C "$root" rev-parse --short HEAD) · chat-svc ${chat_rev:0:8}"
cd "$stage"
railway up --ci --path-as-root -p "$project" -e "$env" -s "$service" "$@" .
