# 공장 영상·프롬프트 병렬 실행 — 2026-11-12

## 지금 상태 한눈에

- 요청대로 영상 작업은 프로세스 전체 최대 6개, 생성 POST 시작 간격은 최소 1초다(D-0190).
- 현재 프론트의 영상 포함 생성은 영상·프롬프트 분기를 함께 실행하며 기본 단계 동시 수는 3이다.
- 기존 8776 로컬 서버에 반영했다. 익준 pv6·손흥민 pv2 및 기존 파일 2,101개를 보존했다.
- 실제 S6 영상 6/6 생성, 전체 회귀 2,204 passed·6 skipped·46 subtests passed다.
- 중단한 페르소나·품질 검토 변경은 실행본에서 제외했다. 커밋·외부 배포는 하지 않았다.

## 이번 세션에서 한 일

`providers/video_concurrency.py`에서 전체 작업 수와 제출 속도를 따로 제한한다. S5/S6는 제출·조회·저장까지 슬롯을 유지하며, 생성 POST 재시도에도 1초 간격을 적용한다. 429의 Retry-After는 같은 API 주소의 제출 대기에 반영한다. 브라우저 방식 grok_web은 공유 브라우저 때문에 전체 1개로 유지한다. 실패 시 이미 시작한 작업을 수습하고 아직 시작하지 않은 작업은 취소한다. 완료 파일과 제출한 작업 ID는 재개에 활용한다.

스케줄러는 어떤 단계든 끝나면 준비된 후속 단계를 즉시 시작한다. 영상이 오래 걸려도 준비된 프롬프트 후속 단계를 기다리게 하지 않는다. 프론트 videos-with-chat 생성은 두 분기를 같은 실행 범위에 넣으며, 프롬프트 검토 대기 중에도 영상은 끝까지 진행한다. 검토 승인 규칙은 유지한다.

병렬 실행 중 비용 예약을 합산한다. S5/S6는 알려진 계획 비용, 다른 실제 단계는 기본 최대 $10의 단계별 계획 한도를 적용한다. 이는 추정 기반 제어이며 실제 청구액의 절대 상한 보장은 아니다. 명시한 max_parallel=1 설정도 존중한다.

### 검증 결과

- 전체 `.venv/bin/pytest -q`: **2,204 passed, 6 skipped, 3 warnings, 46 subtests passed**, 118.67초. 첫 실행의 기존 순차 가정 테스트 1건을 수정해 영상 준비를 막아 둔 동안 채팅 준비가 완료되는지 확인하고 전체 재실행했다.
- 실제 실행본에 대해 PYTHONPATH를 별도 src로 지정한 병렬·관문·demo·기존 근거 격리 검사: **63 passed**, 3 warnings.
- 변경 Python 파일 ruff 및 diff 공백 검사 통과. 전체 ruff의 기존/중단 작업 E501 6건은 이번 범위 밖으로 보존했다(quality_status.py, test_web_evidence_review.py, test_web_gate_record.py, test_web_quality_status.py).
- `work/video-factory-parallel-live/run.py --execute`: 합성 캐릭터, 공장 OAuth, 1.5·720p·2초 × 6편. **HTTP 200 6/6, 39.62초**, POST 간격 1.0002~1.0068초, 추정 $1.80. 모두 720×1280, 실제 길이 2.04초. G5b AWAITING_HUMAN으로 끝났으며 품질 승인이 아니다. 최초 사전 계획은 상한 초과로 제출 없이 중단한 뒤 6편 범위로 실행했다.
- 프론트 생성 API의 영상·프롬프트 중첩 및 G6 대기/재개는 합성 공급자 검사로 확인했다. 실제 모델로 전체 프롬프트와 영상을 함께 새로 생성하는 시험은 하지 않았다.
- 8776 factory/chat/sources 화면 HTTP 200, runtime graph maxParallel=3·autoResume=false, 익준 pv6와 손흥민 pv2 ready=true.
- 이전 보존 목록 2,101개 모두 해시 변화·누락 없음.

## 결정

D-0190. 영상 최대 6개·1초 제출 간격 및 영상/프롬프트 분기 병렬 실행을 공장에 적용한다.

## 확인한 사실과 정정

직전 1초 간격 6건 실험은 별도 도구에서 가능성만 확인했다. 이번에는 실제 공장 S6 및 프론트 생성 실행 경로에 구현했다. 제공사 내부 GPU의 동시 실행 수는 관측하지 않았으며, 클라이언트의 요청·조회 중첩과 완료를 검증했다.

기존 중단 작업이 섞인 작업 트리를 그대로 서버에 올리지 않았다. `work/parallel-factory-runtime/build.py`로 승인된 실행본을 구성했다. evidence-pipeline-v4, evidence_compiler, gate_items, reads, gate.js는 HEAD 2fbbe55 기준으로 복원하고 미완료 evidence_review/quality_status는 제외했다. evidence_tendencies의 기존 D-0186 격리 처리는 보존하고 중단한 excludedClaims 전파만 제외했다. 원본 작업 파일은 수정하거나 삭제하지 않았다. 실행본의 승인된 병렬 소스와 현재 작업 트리는 일치한다.

## 미결

K-0122의 무간격 6건 실패에 대한 제출 간격 제어를 구현했다. 긴 영상·반복 부하 안정성과 여러 서버 프로세스 사이의 공통 제한은 미검증이다. 현재 제한은 단일 서버 프로세스 전체에 적용된다. 기존 중단한 페르소나 작업은 중단 상태다.

## 다음 할 일

현재 공장 화면에서 새 캐릭터 생성 시 영상/프롬프트 진행을 확인할 수 있다. 추가 요청 전에는 기존 캐릭터 재생성이나 중단한 변경의 반영을 하지 않는다. 커밋 시 작업 트리에 섞인 기존 변경과 이번 승인 범위를 구분해야 한다.

## 떠 있는 것

- 로컬 서버 PID 23414, http://127.0.0.1:8776/studio/factory.html
- 실행 진입: `work/parallel-factory-runtime/serve.py`; 설정: 같은 폴더 `factory-web.toml` (max_parallel=3, parallel_stage_cost_cap_usd=10, auto_resume=false).
- 원래 데이터 루트와 작업 기록 루트를 그대로 사용한다. 기존 서버 PID 80506 및 임시 검증 서버 21225는 종료했다.
- 실행본 재구성: 저장된 `build.py`와 `snapshot.json`의 제외 목록을 확인해야 한다. 작업 트리 전체를 무조건 복사하면 중단한 변경이 활성화될 수 있다.
- 실측 산출물: `work/video-factory-parallel-live/`의 result.json/http.json/run.log 및 실제 영상 6편.
- 사용자 보고서·검증 사본: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/factory-parallel-20261112/`.
