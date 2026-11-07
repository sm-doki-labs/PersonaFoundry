# 실제 에이전틱 공정 연결 계획

사용자의 2026-10-30 지시로 기존 설정·조회 연결을 실제 실행 연결로 확장한다. 기존 실행 엔진을 재사용한다. 새 엔진이나 화면 전용 가짜 상태는 만들지 않는다. 별도 승인 질문 없이 지시된 범위를 실행한다.

## 선택한 구조

기본 d-ops.html은 실제 운영 모드, ?mode=demo만 옛 시연 모드다. 실제 모드에서는 ops.js 시뮬레이터가 초기화되지 않는다. 창을 열거나 새로고침한 것만으로 생성 작업을 시작하지 않는다. 실제 루트만 사용하고 과거 실험 루트는 합치지 않는다. 유료 모델 실행·학습은 이번 코딩 검증에서 하지 않는다.

다른 접근: 옛 시뮬레이터의 분 단위 시간과 가상 과업을 실제 상태로 덮어쓰면 실제 공정과 다른 분할·관문·가짜 수치가 남는다. 새로운 실행 엔진을 만들면 백엔드와 규칙이 이중화된다. 따라서 백엔드 그래프/기록을 읽는 전용 렌더러를 기존 화면 슬롯과 시각 토큰에 연결한다.

| 담당 | 파일 | 구현 | 검증 |
|---|---|---|---|
| DeepSeek A | backend web/runtime.py, jobs.py, tests/test_web_runtime.py | 실제 그래프 API, 생성 요청 보존, 기본 실행기의 저장 브리프 복원 | 임시 루트·가짜 공급자, 중복 생성/경로/손상/재시작·실행 인자 검증 |
| DeepSeek B | studio shared/runtime.js, runtime.css, tests/runtime.test.cjs | 실제 목록·공장·결재함·결과·실행/재개, SSE 및 재접속 | Node 계약 및 브라우저용 인터페이스 |
| 메인 | backend app.py, studio d-ops.html/ops.js, 문서, 통합 검사 | 기본 live 모드 분기, 설치, 실제 Chrome와 전체 회귀 | 합성 입력 시작→관문→수정→새 revision→승인→다음 단계·새로고침 |

## API 계약

- GET /api/runtime/graph -> {stages:[{id,name,deps:gateIds[],needs:stageIds[],after:stageIds[],gate:string|null,implemented:boolean}],gates:[{id,title,stage}],mode:'live'}: pipeline.graph.STAGES가 유일한 정의다.
- POST /api/runtime/characters {slug:string,brief:string} -> 201 {characterId:string}. 브리프는 1~20000자, slug 기존 규칙, 충돌409. 생성 호출/승인 없이 state와 고정 creator-input/brief-r1.md를 만든다. JobManager 기본 러너가 같은 파일을 RunOptions.brief_text로 복원한다. 기존 캐릭터의 별도 CLI 입력은 그대로다.
- GET /api/projects -> {characters, jobs, totals}; 각 캐릭터에는 stages/gates/lanes/progress/pendingGates/queue/job/lastJob가 있다.
- GET /api/characters/{id} -> {id,state,stateError,summary,stages,gates,pendingGates,progress,job,lastJob,jobs,held}. held 원소는 {stage,providers}. 상태 손상은 실행 불가로 표시한다.
- POST /api/jobs {characterId,action:'run',until:'G6'|stage|gate,confirm:stageIds[]} -> 202 job; 중복409. confirm 없는 실행은 유료 단계를 held로 보존한다. 기존 유료 실행 확인 동작을 유지한다.
- GET /api/characters/{id}/gates/{gate} -> 기존 실제 후보/파일/review/기록. 관문은 /gate.html?character={id}&gate={gate}를 같은 화면 drawer iframe에 표시하여 기존 전체 관문 입력·검수·결정 API를 재사용한다. iframe은 synthetic/stateError/missing을 분명히 표시하는 기존 페이지다. 단순 링크만으로 연결 완료라 부르지 않는다.
- POST /api/characters/{id}/gates/{gate}/decision -> 기존 승인 API; auto_resume 설정에 따라 자동 재개한다.
- GET /api/events -> hello/state/gate/job SSE. 이벤트는 새 snapshot 재조회 신호이며 초기·재접속·주기적 복구 모두 서버를 재조회한다. 네트워크 오류는 시연 fallback 금지, 버튼 비활성화·마지막 기록 표시·재시도 제공.
- GET /api/text-pipeline/characters/{id}는 실제 텍스트 원장/산출물 원문 조회에 재사용한다. 현재 선택 모델로 옛 생성 출처를 덮어쓰지 않는다.

## 화면 계약

기존 헤더·지표·캐릭터 목록·진행 표/공장 현장·기록/결재함 슬롯과 Glass 색·Pretendard를 유지한다. 실제 그래프 작업대는 stage 단위이며 G7a 등 누락 없이 표시한다. 공장에서는 실제 deps/needs/after 경로만 연결한다. 그래프에 없는 시연 부가 작업을 실제로 표시하지 않는다. 수치가 없으면 미집계/미제공으로 표시한다. RUNNING은 불확정 상태이며 시계로 진행률을 올리지 않는다. 알려진 완료 단계 수는 서버 progress만 쓴다. 시작/승인/수정 중에는 중복 입력을 막고 실패 후 재조회한다. 모델 덱 설정 패널은 유지한다. 일시정지·취소 API가 없으므로 그 버튼은 실제 모드에서 숨긴다. 시연 속도·가상 예산·자동 승인도 실제 모드에서 숨긴다.

## 검증 순서와 경계

1. 새 API와 기본 모드 분기의 실패 검사를 먼저 작성한다.
2. A/B 병렬 구현을 읽고 통합한다.
3. 실제 FastAPI/JobManager/run_until과 가짜 공급자를 쓰는 임시 서버로 Chrome에서 시작·검수·재작업·새로고침을 확인한다. 다른 캐릭터 전환·빈 목록·오프라인·중복 시작도 확인한다.
4. Python 전체 회귀, Ruff/형식, Node, 브라우저 결과를 기록한다. 임시 검증 서버를 종료하고 기존8776은 내려 둔다.
5. PRD→spec→LLD, 현재 상태/알려진 문제/결정/검증/인계를 갱신한다. 실제 공급자 품질/생성 실행은 미검증으로 남긴다. commit/push는 하지 않는다.

## 최종 결과(2026-10-30)

A는 backend API/브리프 복원과20개 검사를 작성해 정상 종료했다. B는 runtime.js/.css·16개 Node검사와 자체 보완을 작성했고, 메인 통합 단계에서 CLI를 종료해 인수했다. B의 정상 완료 응답으로 집계하지 않는다. 메인이 실제 스키마·jobId·오래된 작업 주소·목록 갱신·8갈래 배치·관문 iframe/포커스·검증/문서를 통합했다. 같은 정확한 DeepSeek 모델의 독립 읽기 검토2회는 모두 완료했다.

| 작업 | 상태 | 근거 |
|---|---|---|
| 그래프·생성 요청 | 완료 | STAGES17개/GATES12개 및 기존 LANES8개. 요청은 staging에서 준비 후 파일 잠금/rename으로 게시한다. |
| 시작·재개·관문 | 완료 | 실제 JobManager/run_until, 고정 브리프 복원, iframe의 실제 후보·결정과 expectedRev 잠금 검사. |
| 실제 화면 | 완료 | 기본 live·명시적 demo, 단일 상태 원천, 모르는 수치 미집계·시계 진행 없음, 실제 원문/호출 조회. |
| 검증 | 완료 | Python868 passed/1 skipped(새30개), Node35개(새20개), 브라우저 텍스트 공정10항목·패널 회귀 통과, 페이지 오류0. |
| 실제 공급자 품질 | 미실행 | 이번 작업은 연결 코드 검증이며 실제 생성·미디어·학습은 하지 않았다. |

실제 브라우저 흐름은 등록→시작→G3 수정→pr2→후보 선택→S7/S8→G6/pv1이다. pr1 보존·새로고침·오프라인·작성 중 폼과 목록 갱신·최근20개 밖 작업 주소도 통과했다. 결과는 runtime-work/browser-results.json, 화면은 ../previews/runtime-floor-1280.png/-1512.png다. 입력/생성물은 임시 `/tmp/cf-runtime-browser-20261030-r3/`에만 있다.

실제 루트 캐릭터0건·opencodex/basic_test 유지. 실제 factory.toml에 auto_resume=true/max_parallel=3/resume_until=sx를 설정했다. 8776 및 임시8786/8787은 종료했다. 예전 아이소메트릭 벨트는 demo에 남기고 실제 화면은 백엔드의8갈래 그래프 작업대로 그린다. 신규 외모 입력/순위 수집 UI 및 취소/일시정지 API는 이번 범위에 없다. 실행 안내와 실제 인계는 character-factory-poc/docs/guides/agentic-studio.md 및 docs/status/handoffs/handoff-2026-10-30-agentic-studio-runtime.md다.
