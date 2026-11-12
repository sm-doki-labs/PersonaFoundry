# 주제별 통화 영상 표준과 idle — 2026-11-12

## 지금 상태 한눈에

- 모티브 Lite 신규 생성은 idle1 + 기본 행동4 + 시그니처1, 총6편이다(D-0191).
- 같은6초 무음 원본을 생성하고 idle/말하기는 무편집, 반응/시그니처는 복귀 후보를 찾아 자른다.
- 주제별 장면 설정·선택적 중간 사진·원본 복구를 공장 S6에 연결했다.
- 기존8776서버에 반영했고 기존2,101파일 변화0, 익준pv6·손흥민pv2 ready를 확인했다.
- 새 프롬프트의 실제 유료 영상 생성·품질 검증은 하지 않았다. 미커밋이며 외부 배포도 없다.

## 이번 세션에서 한 일

사용자 제공 규칙을 분석해 공통 보존 조건 → 장면 → 행동 → 시간 → 후처리로 분리했다. 손흥민 옷·손을 뒤로 둔 자세는 공통 강제가 아니며 기준 사진/명시 설정에만 따른다. 기존 로고를 삭제하는 금지문과 여성·앉은 자세를 강제하는 구형 행동 프롬프트를 신규 Lite 경로에서 제외했다. 대화 페르소나 pv6나 예시 금지 규칙은 바꾸지 않았다.

`stages/s6_actions/call_loop.py`에6개 레시피와 VideoScene을 정의하고 catalog/run/contracts에 연결했다. 기본 통화 목적은 source-pack.chapterTemplate에서 가져오며 videoScene의 부분 지정만 덮어쓴다. signaturePose.template은 custom/camera_click이다. middleFramePath/AtS는 선택 사항이며 실제 사진 경로가 없으면 전달했다고 표현하지 않는다. 사진 복사본과 해시를 revision에 고정한다. 현재 화면은 기존 사용자 동작 설명을 계속 받으며 구조화된 주제·프리셋·중간사진 설정은 생성/설정 API에서 받는다.

`providers/base.py`와 `xai_video.py`에 keyframes를 추가했다. model1.5, 720p이하, 내부시점 최대4개와1/3초 격자 중복을 사전 검증한다. Lite 상품과1.5-lite 모델은 별개이며 현재 기본 모델을 유지했다. 공식 keyframes 문서를 확인했지만 이번 신규 중간사진 경로로 실제 호출하지 않았다.

`postprocess.py`는 첫 프레임/기준 사진과 중앙부·타일 차이 및 짧은 안정 구간을 비교한다. 움직임 없는 영상·복귀 없는 영상은 절단하지 않는다. 모두 qualityApproved=false이며 사람이 의미·얼굴·손·이음매를 봐야 한다. ffmpeg -an 뒤 ffprobe로 오디오가 없음을 검사한다. 도구 부재는 유료 생성 전에 차단한다. 실제 길이는 승인 내보내기에 반영한다.

원본 raw/와 receipt를 먼저 보존한다. 완전한 원본 캐시는 공급자 재개 지원 여부와 무관하게 재제출하지 않고 비용 계획에서도 제외한다. 원본/receipt 중 하나만 남았다면 자동 재제출 없이 명시적으로 중단한다. 이미지·시각·주제·생산 프로필에 따른 재사용 범위를 확인한다. 시그니처만 바뀌면 승인/반려 경로 모두 다른5편을 재사용하며 중간사진·원본·receipt도 함께 복사한다.

대기·말하기를 반응과 구분하고 앱 export에 speaking 슬롯을 연결했다. 현재 로컬 채팅 플레이어는 기존 idle↔반응 재생을 유지한다. 별도 음성 길이에 맞춘 speaking 반복/시그니처 후 음성 재생 순서는 이번에 구현하지 않았다. idle 없는 승인본에는 말하기 첫 프레임 정지 호환을 제공한다. 강한 행동과 인사·시그니처는 임의 대체 반응에서 제외했다.

산출물: `docs/guides/call-loop-video.md`, `docs/research/2026-11-12-call-loop-plan.md`, `tests/test_call_loop.py`. 사용자 출력 폴더에는 인터뷰/친구 장면별 프롬프트6개와 JSON 레시피, 표준 문서, 검증 로그를 보관한다. 두 예시 모두 사용자 제공 찰칵 시그니처를 장면만 바꿔 조립한 예시이며 새 인물 특성을 추출한 결과는 아니다.

### 최종 검증

전체 `.venv/bin/pytest -q`: **2,217 passed, 6 skipped, 3 warnings, 46 subtests passed**, 120.94초. 활성 프론트178 passed(중단 quality-status 테스트 제외). 실제 실행본 src 지정 검사23 passed. 신규 call-loop 검사13 passed. 변경 범위 ruff·git diff --check 통과. 실제 모델 호출은0회다.

## 결정

D-0191. 최초 요청의4행동+시그니처에 사용자가 idle 추가를 요청하여 총6편으로 확정했다. 기존 상위 등급은 legacy 카탈로그를 유지하며 신규 Lite 프로필과 조용히 섞어 재사용하지 않는다.

## 확인한 사실과 정정

- 자동 절단은 복귀 후보 제안이며 자동 품질 승인이 아니다. 구간은 반응2.5~3.5초·시그니처4~5초이고 3.5/3.1/2.7/5초를 고정 절단값으로 쓰지 않는다.
- 최초 전체 Node 검사에서 새 Lite 안내의 과거 문구 기대1건과 중단 작업 quality-status 테스트4건이 실패했다. 안내 검사/화면두곳을 갱신했다. 중단 작업은 재개하지 않았다. quality-status 파일을 제외한 활성 프론트178개가 통과했다.
- 독립 검토가 지적한 캐시 재제출·원본 복사·부분 장면 기본값·시그니처 시각/사진 재사용·격자 문제를 수정했다. 최종 재검토에서 high/medium 잔여 없음, 관련13검사 통과를 확인했다.
- 실제 실행본은 work/call-loop-runtime/build.py로 구성한다. 이전 paused 제외 목록과 D0186 격리 처리를 유지하고 reads.py에는 이번 signature_matches의 folder 인자 변경1개만 추가한다. 미완료 페르소나/quality-review 파일을 활성화하지 않았다.

## 미결

K-0123: 실제 인물6편의 동작·얼굴·손·이음새 품질, 중간사진 실전송, 로컬 음성 길이에 맞춘 speaking 재생은 미검증/미구현이다. K-0122 장시간 반복부하 미검증은 유지한다. 원본/receipt 불완전 상태는 보존한 작업기록을 확인한 뒤 복구해야 하며 자동 재제출하지 않는다.

## 다음 할 일

사용자가 실제 생성을 요청하면 현재 input과 예산을 확인하고 새 revision으로6편을 생성하여 G5b에서 얼굴·손·인사 깊이·입모양·이음매를 직접 평가한다. 기존 캐릭터/채팅/승인 영상은 덮어쓰지 않는다. 커밋 시 다른 세션의 dirty 변경 및 중단 작업과 이번 범위를 구분한다.

## 떠 있는 것

- 서버 PID37952, http://127.0.0.1:8776/studio/factory.html
- 실행본: `/Users/johnhuh619/projects/character-factory-poc-wt/oneclick/work/call-loop-runtime/serve.py`, 설정은 같은 폴더 factory-web.toml. maxParallel3·autoResumefalse·영상6개/1초를 유지한다.
- 이전 PID23414와 임시 smoke PID36055는 종료했다. server.json·health.json·preservation.json을 새 실행본 및 사용자 출력에 남겼다.
- 사용자 출력: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/call-loop-standard-20261112/`.
