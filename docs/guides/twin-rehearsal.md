# 모티브 두 명을 같은 공장에서 리허설하기

목표는 SW마에스트로 최종 발표에서 손흥민 역은 학습 모델(TRAIN), 부모님 한 분의 역은 승인된 원문 말투를 담은 긴 프롬프트(PROMPT_ONLY)로 통화하는 것이에요. 아래에서 **계획 확인**까지는 공급자를 부르지 않아요. **승인 후**라고 표시한 명령은 실제 사진·대화 전송, 유료 생성, GPU 임대 또는 시연 DB 변경을 수반해요. 이번 준비에서 실제 호출이나 통화는 하지 않았어요.

## 준비물과 예상 비용

- 공인 자료는 기준 사진(PNG/JPEG), 인터뷰 질문과 본인 답, 기사의 본인 인용, 각 파일의 출처·날짜·사용 범위를 준비해요. 사진과 발화 자료를 공급자에게 보낼 수 있는지도 먼저 확인해요.
- 부모님 한 분의 기준 사진과 카톡 내보내기 파일을 준비해요. 대상 화자와 대화 상대를 구분하고, 외부 공급자 처리와 **발표 공개** 범위를 당사자와 확인해요. 동의한 사람·실제 날짜·범위를 적고 다른 참여자 정보는 가려요. 합성 예시에 적힌 동의는 실제 동의로 쓰지 않아요.
- 사진 사전 확인, 두 캐릭터 제작, 공인 학습·평가·통화용 서빙 비용을 따로 승인받아요. 각 단계의 자료와 예산이 준비된 뒤에만 실행해요.

| 무엇을 기준으로 잡나요? | 비용과 시간 |
|---|---|
| 사전 확인 한 번 | 설정이 없으면 이미지·영상 모두 fake, $0이에요. [예시 설정](../../factory.example.toml)의 Codex 구독 이미지는 API 추가비 추정 $0(구독 사용량은 소모), xAI lite 720p 6초는 코드 단가로 $0.19(6 × $0.03 + 입력 $0.01)예요. 실제 청구·시간은 미확인이에요. |
| 2026-11-07 창작 캐릭터 한 명 | 후보 이미지 10장·장면 이미지 3장·영상 2편 등이 포함된 시험이에요. 기계 생성 약 20분, S3의 429 대기 1시간 27분, 시작부터 앱 대화 확인까지 2시간 56분이었어요. 영상 한 편은 720p 6초, 약 $0.84, 46초~3분 33초였어요. 이미지·영상 합계 약 $3.6은 요청에 적힌 참고값이에요. [계획 §1의 실측 표](../product/2026-11-08-real-person-track-plan.md)와 [설계 인계](../status/handoffs/handoff-2026-11-08-real-person-track.md)에서 실행 경로는 확인했지만, [검증 기록](../status/verification.md)에서 $3.6 합산 단가나 청구액은 미확인이에요. 원기록은 메인 작업 트리의 `runs/testpath/20261107-seeds-r3-signature` 아래 `seeds/images`, `scenes/s07`, `videos/s07-b3`에 있어요. |
| 두 모티브의 제작 | [계획 §8·§13](../product/2026-11-08-real-person-track-plan.md)의 standard 2명은 S6 영상만 약 $50이라는 제안이에요. 실제 설정의 등급·해상도·모델·재시도에 따라 달라져요. S5 일반 기본은 2편 × 8초이지만 사전 확인은 1편 × 6초예요. 두 모티브의 총액·사람 대기·완주 시간은 미확인이에요. |
| 학습과 평가 | 예시 설정에서 학습·선별 상한은 $6, 평가 GPU 예산은 $5예요. 발표 중 모델을 띄워 두는 비용은 별도예요. 학습 시간·실제 청구는 데이터 확정 뒤 `train plan`에서 추정하고 회수 뒤 장부로 확인해요. 가족 역에는 학습 GPU를 빌리지 않아요. |

명령별 기본 상한(200회·$20)은 두 캐릭터의 누적 예산이 아니에요. 한도를 넘으면 먼저 분량·등급·예산을 다시 결정해요. 호출 결과나 시간은 다른 인물이나 모델에 그대로 적용되지 않아요.

## 1. 기준 사진 한 장으로 공급자를 확인해요

공장 작업 트리에서 시작해요. `CFP_*_REPO`는 [최신 인계](../status/handoffs/handoff-2026-11-08-twin-remaining.md)의 새 브랜치 경로예요. `factory.toml`의 `[export.doki_app]`에 경로가 있으면 환경변수보다 먼저 쓰므로 같은 위치인지 확인해요.

```sh
cd /Users/johnhuh619/projects/character-factory-poc-wt/twin-track
export CFP_API_SVC_REPO=/Users/johnhuh619/projects/_wt/api-svc-twin-labels
export CFP_CHAT_SVC_REPO=/Users/johnhuh619/projects/_wt/chat-svc-twin-models
PHOTO='/승인받은/기준사진.png'
uv run --locked cfp motif precheck --photo "$PHOTO"
```

출력에서 공급자·모델, 참조할 사진, 요청 수, 예상 비용과 저장 위치를 확인해요. 계획은 사진이 아직 없어도 볼 수 있어요. 실제 전송 전 해당 공급자의 실존 얼굴 이용 조건과 자료 사용 범위를 사람이 확인해요. 선택한 모델이 `fake`이면 실제 공급자의 허용 여부는 알 수 없어요.

```sh
# 승인 후: 사진 한 장을 편집한 뒤, 그 결과로 영상 한 편을 만들어요.
uv run --locked cfp motif precheck --photo "$PHOTO" --execute
```

`--image-only`는 사진 편집만, `--video-only`는 입력 사진을 첫 프레임으로 영상만 요청해요. 두 옵션을 함께 쓸 수 없어요. 결과는 출력된 `runs/characters/precheck-…/precheck-result.json`에 남아요. `SUCCESS`는 파일 수신, `REFUSED`는 명시적 거절, `SAFETY_BLOCKED`는 정책 차단이에요. `ERROR`는 원인을 단정할 수 없는 오류이고 `SKIPPED`는 앞선 이미지가 없어 영상 제출을 건너뛴 경우예요. 정책 차단·거절이면 여기서 멈춰요. 영상 수집이 끊기면 기록의 `jobId`로 기존 작업과 청구 상태를 확인해요. 명령을 다시 실행하면 새 작업이에요. 성공해도 얼굴 유지·영상 재생·발표 사용 가능 여부는 따로 살펴봐요.

## 2. 출처 묶음을 만들고 병렬 계획을 확인해요

```sh
umask 077
mkdir -p runs/twin-rehearsal
cp -Rn examples/twin/. runs/twin-rehearsal/
SPEC=runs/twin-rehearsal/batch.json
uv run --locked cfp batch run --spec "$SPEC"
```

[예시](../../examples/twin/batch.json)는 합성 입력이에요. `public-demo`·`family-demo`를 서로 다른 영문 소문자 slug로 바꾸고, 두 pack의 사진·본문 경로, 화자명, 출처·동의 기록을 실제 값으로 채워요. 자료는 `examples` 대신 Git 밖 `runs`에 둬요. 배치의 pack 경로는 배치 파일 기준, 사진·본문은 pack 파일 기준이에요. 기사는 따옴표를 본인 인용으로 읽으므로 다른 사람의 인용을 먼저 분리해요. 학습·비교에 쓸 만큼 날짜가 다른 대화를 준비하고, 필수 사실이 원문에 없으면 확인한 값만 `knownFacts`에 적어요. 사진·동의·원문을 검토한 뒤 계획 명령을 다시 실행해요. 배치 계획은 자료 내용까지 검증하지 않아요.

## 3. 승인 후: 배치를 시작하고 사람 관문을 통과해요

```sh
uv run --locked cfp batch run --spec "$SPEC" --execute
uv run --locked cfp web --port 8765
```

로컬 워크숍에서 각 캐릭터의 G0 출처·가림·비교 세트 분리, G1s 기준 사진, G3 근거와 말투를 확인해요. 이어 장면·자세(G4a·G4b), 합성 장면(G4), 소개·동작 영상(G5·G5b), 프롬프트(G6)를 살펴봐요. 워크숍 자동 재개가 켜져 있으면 이미 실행 중인지 먼저 확인해요. 새 slug로 같은 배치를 다시 만들지 않아요. 출력된 두 ID를 보관하고 재개용 파일을 만들어요.

```sh
PUBLIC='<공인 캐릭터 ID>'
FAMILY='<가족 캐릭터 ID>'
jq --arg p "$PUBLIC" --arg f "$FAMILY" \
  '.characters[0] += {character_id:$p} | .characters[1] += {character_id:$f}
   | del(.characters[].slug)' "$SPEC" > runs/twin-rehearsal/resume.json
uv run --locked cfp video intro "$PUBLIC"
uv run --locked cfp video actions "$PUBLIC"
uv run --locked cfp video intro "$FAMILY"
uv run --locked cfp video actions "$FAMILY"
# 열린 관문에서 결정한 뒤, 승인받은 범위만 재개해요.
uv run --locked cfp batch run --spec runs/twin-rehearsal/resume.json --execute
```

각 호출 뒤 `runs/batches/<id>/batch-report.json`에서 캐릭터별 시작·종료·대기 관문을 확인해요. `ledger/provider-waits.jsonl`은 공급자 대기 기록이에요. TRAIN은 G7a·G7에서 데이터와 분할을 사람에게 확인받아요. PROMPT_ONLY는 이 과정을 건너뛰고 G8에서 긴 프롬프트를 검토해요.

## 4. 공인 학습만 제출·회수하고 채택 결과를 확인해요

```sh
uv run --locked cfp train plan "$PUBLIC" --providers gemma_qlora
# 승인 후: 위 계획의 데이터·예상 비용·GPU 시간을 확인한 다음 제출해요.
uv run --locked cfp train submit "$PUBLIC" --providers gemma_qlora --execute
# 원격 학습이 끝나면 같은 판에서 회수해요.
uv run --locked cfp train collect "$PUBLIC" --providers gemma_qlora --execute
uv run --locked cfp status "$PUBLIC"
uv run --locked cfp run "$PUBLIC" --until G8 --execute
```

계획을 이미 고정했다면 그 판의 `plan.json`을 확인해요. 제출한 뒤 새 계획을 만들지 않아요. 결과의 `training-run.json`에서 성공 상태, 선택한 체크포인트와 모델 연결을 확인하고 학습용 GPU 반납도 확인해요. 실패·중단 때 잔여 임대를 확인한 뒤 필요하면 `cfp train cleanup "$PUBLIC" --providers gemma_qlora --execute`를 사용해요. G8에서 승인한 모델이 학습 결과와 같아야 TRAIN 통화로 볼 수 있어요. 비교 평가용 모델과 앱용 서빙은 별도이며, 공장이 통화용 모델 서버를 자동으로 띄워 주지는 않아요.

가족 판정은 **가족 역 G8이 열려 있을 때만** 들여올 수 있어요. 가족에게 먼저 블라인드 화면을 보여 주고 답을 들여온 뒤 G8에서 채택해요. 통화 뒤에는 완성된 비교 화면을 열어 봐요.

```sh
find "runs/characters/$FAMILY" -name 'twin-blind-*.html'
# 가족은 정답을 보기 전 블라인드 화면에서 답을 저장해요.
uv run --locked cfp eval import-blind "$FAMILY" '/비공개/가족답안.json'
```

## 5. 모델 경로를 등록하고 시연 DB에 두 캐릭터를 적재해요

```sh
# 각 G8 결정 후 패키지를 만들고 워크숍 G9에서 증거와 발표 점검을 검토해요.
uv run --locked cfp release build "$PUBLIC"
uv run --locked cfp release build "$FAMILY"
# 각 G9 승인 후: CFP_PG_ADMIN_URL은 일회용 DB를 만들 수 있는 로컬 주소로 준비해요.
uv run --locked cfp export doki-app "$PUBLIC" --verify
uv run --locked cfp export doki-app "$FAMILY" --verify
```

`--verify`는 임시 DB에 넣고 지워요. 이 성공만으로 시연 앱에 적재되지는 않아요. 학습된 정확한 체크포인트를 호환 서버에 올려요. 내보낸 `doki-app/chat-svc/models/*.json`의 `servingRoute`를 [환경변수 예시](../../examples/twin/chat-routes.env.example)의 JSON 키로 쓰고 `model`과 `apiKeyEnv`를 그대로 맞춰요. `baseUrl`에는 실제 서빙 주소를, 키 값은 chat-svc 비밀 설정에 따로 넣고 서비스를 다시 시작해요. PROMPT_ONLY는 기존 긴 프롬프트 경로를 써요. 경로 누락 시 `503 PROVIDER_UNCONFIGURED`가 나오면 서빙 설정을 확인해요.

아래는 두 서비스가 각각 **시연 전용 DB**를 보도록 환경변수를 설정하고 마이그레이션과 기본 시드를 준비한 뒤의 명령이에요. `PUBLIC_EXPORT`·`FAMILY_EXPORT`에는 이번 판의 절대 `doki-app` 경로를 넣어요. 두 서비스 저장소의 원본 `data/`에는 쓰지 않아요.

```sh
export PUBLIC_EXPORT='/공인/내보낸/판/doki-app'
export FAMILY_EXPORT='/가족/내보낸/판/doki-app'
# 새 임시 폴더에서 두 콘텐츠 트리와 포인터를 순서대로 합쳐요.
export MERGE_DIR="$(mktemp -d)"
uv run --locked python - <<'PY'
import os
from pathlib import Path
from character_factory_poc.stages.export.verify import _overlay_tree
base = Path(os.environ["CFP_CHAT_SVC_REPO"]) / "data"
for item in ("PUBLIC_EXPORT", "FAMILY_EXPORT"):
    dest = Path(os.environ["MERGE_DIR"]) / item
    _overlay_tree(base, Path(os.environ[item]) / "chat-svc", dest)
    base = dest
PY
(
  set -e
  cd "$CFP_CHAT_SVC_REPO"
  uv run --locked python -m scripts.db_ops.content_release publish --data-dir "$MERGE_DIR/FAMILY_EXPORT"
  uv run --locked python -m scripts.db_ops.content_release verify --data-dir "$MERGE_DIR/FAMILY_EXPORT"
)
(
  set -e
  cd "$CFP_API_SVC_REPO"
  for out in "$PUBLIC_EXPORT" "$FAMILY_EXPORT"; do
    uv run --locked python -m scripts.seed --file "$out/api-svc/seed.json" load
  done
)
```

두 character_uid와 각 클립·챕터가 같은 시연 DB에 남았는지 확인해요. 클립 URL을 에뮬레이터에서 열 수 있도록 실제 미디어도 시연 스토리지에 올려요. 시연 DB 접속값, 서빙 주소와 미디어 업로드 명령은 환경별로 달라 미확인이에요. 적재의 기존 근거와 한계는 [검증 인계](../status/handoffs/handoff-2026-11-08-twin-remaining.md)를 참고해요.

## 6. Android 통화와 비교 화면을 보고 발표 여부를 결정해요

```sh
(cd /Users/johnhuh619/projects/_wt/frontend-twin-labels/AND && ./gradlew :app:installDebug)
adb shell monkey -p com.dokilabs.android -c android.intent.category.LAUNCHER 1
```

에뮬레이터에서 API·게이트웨이·오디오 서비스가 시연 스택에 연결됐는지 확인해요. 같은 계정으로 공인의 팬 통화와 가족 안부 통화를 각각 시작하고, 실제 답 한 턴·올바른 영상·모델 경로·AI 표시를 기록해요. 인증·통화·화면 녹화 시간과 서빙 비용은 미확인이에요. 화면에 다른 캐릭터의 영상이나 연애 문구가 남으면 캡처와 함께 메인에게 전달해요.

```sh
find "runs/characters/$PUBLIC" "runs/characters/$FAMILY" -name 'twin-demo-*.html'
uv run --locked cfp ledger cost "$PUBLIC"
uv run --locked cfp ledger cost "$FAMILY"
```

G8의 비교 화면에서 실제 답과 생성 답, 학습 자료와 겹치는 답을 확인해요. 모델 점수와 가족 판정은 분모를 적어 따로 기록해요. 학습 모델 응답이 없는 조건은 미확인이에요. 가족 답안용 파일이나 원본 대화를 발표 패키지에 복사하지 않아요.

마지막으로 [D-0126](../status/decisions.md)의 네 항목을 최종 캡처와 함께 확인해요. ① 앱과 발표 화면에 **AI 생성 · 본인과 무관한 기술 시연**이 보여요. ② 본인의 추천·협력·참여처럼 보이는 표현이 없어요. ③ 공인 장면은 홍보물·SNS·앱 마케팅에 다시 쓰지 않으며, 녹화 공개 시 해당 구간을 가리거나 빼 달라고 요청해요. ④ 부모님 동의가 발표 공개까지 포함해요. 카톡의 다른 참여자와 연락처도 최종 화면에서 직접 가려요. 공인 측 허락과 법무 검토는 권장 사항이에요. 필수 항목 하나라도 확인하지 못하면 발표용으로 내지 않아요.
