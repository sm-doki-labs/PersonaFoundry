# 텍스트 제작 공정 연결 계획표

**Goal:** 기존 글래스 시연 UI에 character-factory-poc의 모델 덱과 실제 텍스트 자료 상태를 연결한다.
**Architecture:** 기존 시뮬레이터는 보존한다. 같은 FastAPI 서버의 /studio에서 시연을 제공하고 /api/text-pipeline의 실제 설정·캐릭터·출처를 별도 텍스트 공정 패널에 표시한다.
**Tech Stack:** 기존 HTML/CSS/vanilla JavaScript, Python/FastAPI, pytest, Node·실제 Chrome 검사다.
**Spec:** design.md, character-factory-poc/docs/guides/text-model-deck.md, 이전 사용자 요청 및 이번 연결 요청을 따른다.

## 계획표

| 작업 | 담당 | 쓰기 범위 | 검증 |
|---|---|---|---|
| A. 모델 덱·실제 기록 API | DeepSeek v4.1 Flash A | 공장 web/text_pipeline.py, tests/test_web_text_pipeline.py | 설정 전환·미설정 test·상태·출처·경로 검증 |
| B. 글래스 텍스트 공정 패널 | DeepSeek v4.1 Flash B | shared/text-pipeline.js, shared/text-pipeline.css, tests/text-pipeline.test.cjs | 로딩/연결 끊김/선택/전환/탈출/출처 구분 |
| C. 앱과 시연 통합 | 메인 에이전트 | 공장 web/app.py 및 설정, d-ops.html, ops.js의 최소 연결부, plans·design.md | 실제 API·1280/1512 브라우저·기존 시연 회귀 검사 |

## 전역 제약

- 코드 작업자는 opencode-go/deepseek-v4.1-flash를 high로 사용한다. 기본 spawn 도구의 모델 목록에 없으므로 로컬 Codex CLI를 opencodex로 연결해 병렬 실행한다. 다른 모델로 조용히 대체하지 않는다.
- 기존 글래스 토큰·Pretendard·색·공장 배치·기록 토글을 보존한다. 새 UI는 구현 세부 대신 쉬운 이름을 먼저 보여 준다.
- 시연의 시간/비용/진행은 각본이다. 실제 캐릭터 상태나 실증으로 소급 표시하지 않는다. 패널은 실제 서버가 없으면 연결 안 됨을 보여 주며 임의로 실제 기록을 만들어 채우지 않는다.
- 모델 프로필과 호출 경로를 독립적으로 선택한다. 기본 opencodex/basic_test, demo/최종점검에서는 지정한 역할만 Argon이다. test 경로 미설정이면 선택하지 못한다.
- 모델 호출·학습·관문 승인은 자동으로 하지 않는다. 이번 구현 범위는 설정 전환, 실제 기록 읽기, 기존 워크숍으로 이동까지다. 실제 실행과 사람 관문은 기존 워크숍이 수행한다.
- API는 인증 값이나 원시 사용자 설정 전체를 반환하지 않는다. 안전한 모델 ID·추론 강도·프로필·경로명·가용 여부만 반환한다.
- 설정은 새 작업 문맥부터 적용한다. 과거 산출물은 actual model/profile을 보존하며 selectedConfiguration과 구분한다. 최종점검 프로필 선택은 검증 완료가 아니다.
- commit/push는 하지 않는다. 기존 미커밋 작업과 생성물을 보존한다. 다른 작업과 쓰기 범위를 겹치지 않는다.

## 고정 API 계약

A 작업자는 `install_text_pipeline_routes(app, root, conf, jobs)`를 제공한다. 메인이 create_app에서 한 번 설치한다.

### GET /api/text-pipeline

```json
{"enabled":true,"profile":"basic_test","route":"opencodex","completionCheck":"NOT_RUN","profiles":[{"id":"basic_test","label":"개발 확인"},{"id":"demo","label":"시연"},{"id":"pre_demo_completion_check","label":"시연 전 최종 점검"}],"routes":[{"id":"opencodex","label":"개발 연결","available":true,"reason":""},{"id":"test","label":"별도 테스트 서버","available":false,"reason":"주소·인증 설정이 필요합니다"}],"tasks":[{"id":"brief","label":"기본 설정 정리","model":"gpt-6.1-sol","reasoningEffort":"high"}],"activeJobs":0}
```

tasks는 기준 덱 순서 아홉 개다. task label은 원본 task 문구를 써도 된다. enabled=false일 때도 같은 shape를 유지하되 profile/route는 null, tasks는 빈 배열이다. 설정 미확인/깨짐은 명시적 HTTP 오류다.

### POST /api/text-pipeline/selection

본문 `{profile?: string, route?: string}`를 검증하고 공장 common.text_deck.select를 호출한 뒤 GET과 같은 shape로 반환한다. 둘 다 없거나 알 수 없는 필드는400, 미설정 test도400, activeJobs>0이면409다. 실제 모델 호출은 없다. 현재 선택을 실패 후 보존한다.

### GET /api/text-pipeline/characters

`{"characters":[{"id":"cf-...","name":"..."}]}`. 실제 runs/characters 하위만 대상으로 하며 경로를 안전하게 검증한다. 이름을 알 수 없으면 id를 쓴다.

### GET /api/text-pipeline/characters/{character_id}

```json
{"characterId":"cf-...","name":"...","stages":[{"id":"s3","label":"기획","status":"APPROVED","revision":"pr1"}],"gates":[{"id":"G3","status":"APPROVED","revision":"pr1"}],"calls":[{"task":"voice","stage":"s7","model":"actual-model","profile":"basic_test","route":"opencodex","ok":true,"ref":"..."}],"artifacts":[{"label":"페르소나 프롬프트","revision":"pv1","text":"...","sourceModel":"actual-model or null","sourceProfile":"basic_test or null","completionCheck":"NOT_RUN"}],"workshopUrl":"/c-glass.html?character=cf-..."}
```

stages는 s3/s7/s8/s9s/s9, gates는 G3/G6/G7a/G7만 담는다. calls는 최근 최대50건으로 제한하며 ledger의 실제 model·textBinding을 읽는다. 본문은 알려진 텍스트 자료만 길이를 제한해 읽고 누락은 null/빈 목록으로 보존한다. 임의 파일 경로나 인증 값은 노출하지 않는다. workshopUrl은 같은 서버의 기존 워크숍 연결이다.

## UI 계약

- B 작업자는 `window.FactoryTextPipeline`을 제공한다. `mount({root, apiBase:''})`가 지정한 root에 패널을 삽입하고 `open()`/`close()`가 있는 컨트롤러를 반환한다. HTML 선택자에 충돌하지 않도록 ftp- 접두사를 쓴다.
- 메인은 d-ops.html에서 스크립트/CSS를 읽고 버튼 `[data-text-pipeline-open]`과 패널 루트 `[data-text-pipeline-root]`를 추가한다. B 작업자는 HTML이나 ops.js를 수정하지 않는다.
- 새 텍스트 공정은 dialog 또는 독립 패널로 연다. 기존 시뮬레이터를 멈추거나 상태를 바꾸지 않는다. 실제 기록 보기와 시연 각본을 분명하게 구분한다.
- 기본 화면은 프로필/경로 선택과 아홉 역할의 모델을 보여 준다. 모델의 상세 ID/추론 강도는 펼치기로 확인한다. 캐릭터를 선택하면 실제 단계·관문·최근 호출·원천 모델이 표시된다.
- 접근성: 명확한 label, focus-visible, Esc/닫기, 포커스 복귀, 오류 aria-live, reduced-motion, 1280·1512에서 가림/가로 넘침 없음.

## 실행 단계

- [x] 현재 프로젝트·모델 경로를 확인하고 계약과 계획표를 작성한다.
- [x] A/B 각각 실패 테스트를 먼저 작성하고 구현·집중 검사를 수행했다.
- [x] 메인이 모듈 설치·정적 시안 서빙·진입 버튼을 연결했다.
- [x] 실제 Chrome에서 새 패널과 기존 시연을 검증했다. 캐릭터 공정의 실제 생성은 수행하지 않았다.
- [x] 최종 코드/문서 검토와 인계를 남겼다.


## 실행 결과

- A/B 모두 로컬 opencodex의 `opencode-go/deepseek-v4.1-flash`, high를 명시한 별도 Codex CLI 세션으로 병렬 실행했다. 기본 서브에이전트 도구에는 해당 모델이 없어 CLI를 썼다. 다른 모델로 대체하지 않았다.
- A는 API와 집중 테스트를, B는 UI 모듈·CSS·순수 함수 검사를 작성했다. 메인은 정적 시안 서빙·화면 진입·모델 배정 스냅샷·작업대 상세 연결과 실제 브라우저 검사를 수행했다.
- 서브에이전트의 제약으로 A는 기존 .venv를 사용했고 B의 Chrome은 격리된 실행 환경에서 종료됐다. 메인 환경의 실제 Chrome에서 1280/1512, 키보드·포커스·넘침 및 기록/오류 상태를 별도로 검증했다.
- 최종 공장 검사838 passed/1 skipped, 기존 deprecation warning1개다. Ruff lint/format355개 파일·diff 검사 통과다. UI Node15개와 Chrome의 두 화면 크기 및 선택 실패/출처 보존/오프라인 검사를 통과했다.
- 기존 시연 `runs1.js 1512 982`는 오류0, 벨트 경로45표본/잘못된 경로0, G9 출시까지 통과했다.
- 공장 현장의 시간·비용·호출·진행은 계속 시연 각본이다. 아홉 역할 배정은 새 덱 스냅샷으로 맞췄고 S8은 호출0회다. 실제 기록은 새 API 패널에서 읽는다.
- 현재 공장 루트에는 runs/characters가 없어 실제 캐릭터 목록은0건이다. 이전 agentic-character-factory와 실험별 루트의 자료를 복사하거나 새 덱의 결과로 합치지 않았다.
- 캐릭터 생성·학습·관문 승인은 실행하지 않았다. 개발용 DeepSeek 코딩 세션2개와 공정 생성 호출을 구분한다.
- 검토용 화면은 `http://127.0.0.1:8776/studio/d-ops.html?panel=text#job/seoha-new/floor`다. 공장 소스는 기존 root, 작업 큐만 work/studio-web-jobs-20261030으로 분리해 기존 서버와 실행 기록을 방해하지 않았다.

최종 통합에서 설정 파일 복사본을 제거했다. 검토 서버도 실제 factory.toml의 후속 변경을 직접 읽고 큐 경로만 실행 옵션으로 분리한다.

추가 독립 검토도 같은 DeepSeek 모델로 요청했으나 10분 안에 응답을 받지 못해 중단했다. 완료된 검토나 승인으로 집계하지 않는다. 병렬 구현2개는 완료됐으며 최종 근거는 전체838개·UI15개·실제 Chrome 검사와 메인 코드 검토다.
