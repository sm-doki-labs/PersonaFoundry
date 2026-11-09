#!/usr/bin/env bash
set -euo pipefail

root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
stack="$root/deploy/aws"
mode=${1:-deploy}
case "$mode:$#" in
  deploy:0|deploy:1|bootstrap:1|rollback:2) ;;
  *) echo "사용법: $0 [deploy|bootstrap|rollback 이전커밋SHA]" >&2; exit 2 ;;
esac
repo=$(tofu -chdir="$stack" output -raw ecr_url)
registry=${repo%%/*}
region_suffix=${registry#*.dkr.ecr.}
export AWS_REGION=${region_suffix%%.*}
account=$(aws sts get-caller-identity --query Account --output text)
[[ ${registry%%.*} == "$account" ]] || { echo "상태 파일과 배포 계정이 다릅니다." >&2; exit 1; }
if [[ $mode != bootstrap ]]; then
  cluster=$(tofu -chdir="$stack" output -raw cluster)
  service=$(tofu -chdir="$stack" output -raw service)
fi
if [[ $mode == rollback ]]; then
  tag=$2
  [[ $tag =~ ^[a-f0-9]{40}$ ]] || { echo "40자리 커밋 SHA가 필요합니다." >&2; exit 2; }
else
  [[ -z $(git -C "$root" status --porcelain) ]] || { echo "먼저 변경 사항을 커밋하세요." >&2; exit 1; }
  tag=$(git -C "$root" rev-parse HEAD)
fi
lookup() {
  aws ecr batch-get-image --repository-name "${repo#*/}" --image-ids "imageTag=$1" --query "$2" --output text
}
digest=$(lookup "$tag" 'images[0].imageId.imageDigest')
if [[ $digest == None && $mode != rollback ]]; then
  aws ecr get-login-password | docker login --username AWS --password-stdin "$registry"
  docker buildx build --platform linux/arm64 --provenance=false --sbom=false --push -t "$repo:$tag" "$root"
  digest=$(lookup "$tag" 'images[0].imageId.imageDigest')
fi
[[ $digest == sha256:* ]] || { echo "지정한 커밋의 이미지가 없습니다." >&2; exit 1; }
if [[ $(lookup release 'images[0].imageId.imageDigest') != "$digest" ]]; then
  manifest=$(lookup "$tag" 'images[0].imageManifest')
  aws ecr put-image --repository-name "${repo#*/}" --image-tag release --image-manifest "$manifest" >/dev/null
fi
if [[ $mode != bootstrap ]]; then
  aws ecs update-service --cluster "$cluster" --service "$service" --force-new-deployment >/dev/null
  aws ecs wait services-stable --cluster "$cluster" --services "$service"
  task=$(aws ecs list-tasks --cluster "$cluster" --service-name "$service" --query 'taskArns[0]' --output text)
  actual=$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --query "tasks[0].containers[?name=='factory'].imageDigest | [0]" --output text)
  [[ $actual == "$digest" ]] || { echo "실행 중인 이미지가 요청한 이미지와 다릅니다." >&2; exit 1; }
fi
echo "배포 이미지: $tag ($digest)"
