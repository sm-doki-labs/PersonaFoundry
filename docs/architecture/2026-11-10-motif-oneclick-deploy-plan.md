# 모티브 원클릭 생성과 AWS 배포 계획 (2026-11-10)

## 목표

이름과 원문(인터뷰·캐주얼)만 넣으면 손흥민 시연판(V27)과 같은 수준의 대화 프롬프트가 자동으로 나온다.
사람은 세 번 확인한다: G0(출처와 사실 목록), G3(기획), G6(프롬프트). 공장은 AWS에서 로그인한 팀원만 쓴다.

기준 산출물: `work/son-motif-20261109/v5-casual/prompts/V27-fan.md`(공장 루트 기준).
공장 son-v6 자동 산출물과 V27의 칸별 차이가 이번 작업의 범위다.

## 작업 묶음과 쓰기 경계

각 묶음은 자기 worktree·브랜치에서만 커밋한다. `docs/status/decisions.md`는 통합 담당만 고친다.

| 묶음 | 브랜치 | 쓰기 경계 |
|---|---|---|
| A 출처 받기(백엔드) | codex/oc-intake | contracts/source.py, stages/s0_source/parse.py·run.py(_load_pack 주변), common/source_store.py(새), web/sources.py(새), web/settings.py, web/app.py(라우트 설치·화면 허용 목록 한 줄), cli.py(출처 관련 옵션만), tests/test_source_*.py |
| A2 출처 받기(화면) | codex/oc-intake-ui | studio/sources.html(새), studio/shared/sources.js·sources.css(새), studio/factory.html·studio/shared/appbar.js(진입 링크만), studio/tests/sources*.cjs |
| B 사실 수집·모티브 규칙 | codex/oc-facts | contracts/facts.py(새), stages/s0_source/facts.py(새), s0 run.py(사실 단계 호출 한 곳), s0 approve.py, pipeline/gates.py 또는 web/gate_items.py의 G0 사실 표시, resources/actor-system-rules-v4-motif.md(새), s8_prompts/actor_persona.py(load_actor_rules), s8_prompts/twin.py(motif_limits·motif_facts), s8_prompts/build.py(run_deck_s8 모티브 분기), s7_traits/choice_voice.py(규칙 파일 목록), tests/test_motif_facts*.py |
| C 말투 칸 | codex/oc-voice | stages/s3_plan/speech_profile.py, s3_plan/twin.py(말결 통계 호출부), s8_prompts/twin.py(voice_lines·approved_voice만), tests/test_speech_profile*.py |
| D 특질 빈칸·장면·출력 틀 | codex/oc-scene | stages/s7_traits/(sheet.py·ledger.py·formation.py와 S7 프롬프트), resources/motif-demo-situations-v1.json(새), s8_prompts/chapter_start.py·prompts/chapter_start.md, 대화 온도 기본값 설정, tests/test_motif_choices*.py·test_chapter_start*.py |
| E AWS 배포 | codex/oc-deploy | Dockerfile, .dockerignore, deploy/**(OpenTofu 스택·서버용 factory.toml·실행 스크립트), docs/guides/deploy-aws.md, tests/test_deploy_*.py |

## 묶음 사이 약속

### 1. 원문 종류와 말한 자리 (A가 만들고 B·C가 읽는다)

- `SourceText`에 `register: "FORMAL" | "CASUAL" | None`, `sourceUrl: str | None`을 더한다.
- `contracts/source.py`에 `default_register(kind) -> str`: INTERVIEW·ARTICLE → FORMAL, KAKAO_EXPORT·TRANSCRIPT → CASUAL.
- `TextStats`에 `register`를 싣는다. 읽는 쪽은 `getattr(t, "register", None) or default_register(t.kind)`로 읽어 A 머지 전에도 돈다.
- 자막 파일(.srt·.vtt)은 TRANSCRIPT로 받고 시간 표시를 지운다.

### 2. 출처 API (A가 만들고 A2가 부른다)

모든 응답은 JSON. 오류는 `{"detail": "..."}`.

- `POST /api/sources/drafts` 본문 `{displayName, subjectKind, usageBasis:{scope, notes}, chapterTemplate?}` → `{characterId}`. 모티브 캐릭터 폴더를 만든다.
- `GET /api/sources/{cid}` → `{characterId, subject, usageBasis, store:"local"|"s3", allowPathImport, files:[FileRecord], problems:[str], canFinalize}`
- `POST /api/sources/{cid}/files` 본문 `{filename, size, contentType}` → `{fileId, upload:{method:"PUT", url, headers}}`. local이면 url은 `/api/sources/{cid}/files/{fileId}/content`, s3면 1회용 서명 주소(15분).
- `PUT /api/sources/{cid}/files/{fileId}/content` (local 저장소일 때만)
- `POST /api/sources/{cid}/files/{fileId}/complete` 본문 `{textId, kind, register?, subjectSpeaker?, userSpeaker?, date?, sourceUrl?}` → FileRecord. 크기·해시·형식 검사와 이용 금지 문구 검사.
- `PATCH /api/sources/{cid}/files/{fileId}` 본문은 complete와 같은 필드 → FileRecord
- `DELETE /api/sources/{cid}/files/{fileId}`, `DELETE /api/sources/{cid}`(올린 원문 전부 삭제)
- `POST /api/sources/{cid}/import-path` 본문 `{path}` — `allowPathImport`일 때만(로컬 전용)
- `POST /api/sources/{cid}/finalize` → `{jobId}`. 캐릭터 폴더 안에 source-pack을 쓰고 S0부터 작업을 건다.
- FileRecord: `{fileId, filename, size, sha256, status:"pending"|"ready"|"problem", textId, kind, register, subjectSpeaker, userSpeaker, date, sourceUrl, problems:[str]}`
- 허용 형식: .txt .srt .vtt .csv .json, 파일 하나 20MB 이하.

### 3. 서버 설정 (A가 읽고 E가 넣는다)

- `CFP_SERVER_MODE=1`: 경로 가져오기를 끄고(`allowPathImport=false`), `--source-pack` 외부 경로도 막는다.
- `CFP_SOURCE_STORE=local|s3`(기본 local), `CFP_SOURCE_BUCKET`, `CFP_SOURCE_PREFIX`(기본 `sources/`), 지역은 `AWS_REGION`.
- `CFP_ROOT`: 공장 루트(서버에서는 EFS `/data/factory`). `CFP_CONFIG`: 서버용 factory.toml 경로.
- 키: `OPENAI_API_KEY`, `GEMINI_API_KEY` (Secrets Manager → 환경변수).

### 4. 사실 목록 (B)

- S0 정리 뒤, G0 전에 공인(PUBLIC_FIGURE)만 사실을 모은다. `s0-source/<rev>/facts.json`(`motif-facts-v1`).
- 명확한 사실만: 경력·결과·수상·기록·현재 상태. 날짜와 출처 주소가 있어야 남긴다. 사생활·소문은 넣지 않는다.
- 사실마다 원문에서 본인이 그 일을 말한 대목을 찾으면 `selfView`(근거 msgId·인용, 한 문장 풀어쓰기)를 붙인다. 인용은 코드가 원문에 있는지 확인한다.
- G0에서 사실 목록을 함께 보고, 뺄 사실을 고를 수 있다.
- S8 사실 칸 = 기존 신원 줄 + 승인 사실 + 본인 시점 줄. 한계 칸 = 기존 3줄 + 지난 경기 말하기 + 현재 상태 답 + 사생활 넘기는 말 2~3개.
- 모티브는 공통 규칙 `actor-system-rules-v4-motif.md`를 쓴다. 오리지널 규칙 파일은 바꾸지 않는다.

### 5. 시연 상황 (D)

- 모티브 장부는 장난·놀림, 고민 털어놓기, 비판, 모르는 질문, 사생활 질문마다 특질이 하나씩 있어야 한다.
- 원문 경향이 있으면 그걸로, 없으면 근거 표시(`basis: INFERRED`)를 달고 G6에서 사람이 본다.
- 팬 첫 통화 장면은 첫인사 때만 하루를 묻는다. 장면 경계 마지막 줄에 출력 틀("지금부터 너의 출력은 ~가 소리 내어 하는 말 그 자체다…")을 둔다.

## 완료 기준

1. 묶음마다 단위 시험 통과, 통합 후 전체 시험 통과.
2. 손흥민을 업로드 경로로 처음부터 실제 모델로 돌려 시연 시나리오 6개 × 2회 측정, V27과 비교.
3. Docker 이미지가 로컬에서 서버 모드로 뜨고 업로드 → S0까지 돈다. OpenTofu `validate` 통과.
4. 결정 기록 D-0150~ 과 PR.
5. AWS 적용은 위 1~3이 끝난 뒤.


## 2차: 팀 도구로 다듬기와 대화 테스트 (2026-11-10)

사용자 지시: "대화는 생성 이후에 해볼 수 있게, 완성되면 테스트해 볼 수 있는 페이지", "동의나 승인 같은 귀찮은 것들은 스킵(팀 3명 내부 도구)", "나머지는 병렬로 구축해서 연결".

| 묶음 | 브랜치 | 쓰기 경계 |
|---|---|---|
| F 대화 백엔드 | codex/oc2-chat-api | web/demo_chat.py(새), common/demo_chat.py 또는 stages/s8_prompts/demo_chat.py(새), resources/demo-scenarios-v1.json(새), web/app.py(라우트 설치 한 줄), web/gate_items.py(G6 표본·추론 특질 항목만), deploy/factory.server.toml([providers.demo_chat]만), factory.example.toml([providers.demo_chat]만), tests/test_demo_chat*.py |
| G 흐름 백엔드 | codex/oc2-flow | pipeline/graph.py, pipeline/orchestrator.py, pipeline/approve.py(자동 진행 기록만), web/jobs.py, web/sources.py, contracts/source.py(사용 근거 선택화), stages/s0_source/precheck.py·run.py(사용 근거 잠금만), stages/s8_prompts/chapter_start.py(단계 실행 연결만), web/reads.py(modelMode·autoReview 노출만), tests/test_oc2_flow*.py |
| H 대화 화면 | codex/oc2-chat-ui | studio/chat.html(새), studio/shared/chat.js·chat.css(새), studio/tests/chat*.cjs(새), web/app.py 화면 허용 목록에 chat.html 한 줄 |
| I 검토·생성 화면 | codex/oc2-review-ui | src/character_factory_poc/web/static/shared/gate.js·gate*.css(G0 사실·원문 표, G6 표본·추론 특질), studio/sources.html·shared/sources.js·sources.css, studio/shared/flow.js·flow.css(대화 테스트 진입, 사이드바 갈래 표시, 이름 통일), studio/help.html, studio/tests/*.cjs |

### 약속 1. 대화 API (F가 만들고 H·I가 부른다)

- GET /api/characters/{cid}/chat/meta → {characterId, name, origin, ready, reason, promptRev, chapterRev, model:{via, model}, temperature, scenarios:[{id, title, turns:[str]}], samples:[{scenarioId, title, turns:[{user, reply}]}]}
  - ready는 S8 프롬프트와 S8c 챕터 시작 설정이 모두 있을 때 true. 아니면 reason에 쉬운 한국어 이유.
  - scenarios는 resources/demo-scenarios-v1.json(인물에 매이지 않는 일반 시나리오: 첫인사·일상, 칭찬·장난, 고민, 모르는 것, 사생활)에 캐릭터 폴더의 demo/scenarios.json(있으면, 인물 전용)을 앞에 더한다.
- POST /api/characters/{cid}/chat 본문 {messages:[{role:"user"|"assistant", content}], via?:"studio"|"vertex"} → {reply, ms, rejected, model}
  - 시스템 프롬프트 = 최신 S8 long.md + 챕터 시작 ch1(관계·장면·장면 경계, V27-fan과 같은 배치). 메모 걸러내기(common/reply_guard.py)를 쓴다. 온도는 [stages.s8] motif_demo_chat_temperature(기본 0.8).
  - 대화 모델은 [providers.demo_chat](기본 AI Studio gemini-3.8-flash, GEMINI_API_KEY). via=vertex는 로컬에서만.
  - 대화 기록은 서버에 저장하지 않는다. 409: 프롬프트 없음.
- 함수 run_samples(ctx, cid) → s8-chapters/<rev>/samples.json(일반 시나리오마다 한 번). G가 S8c 단계 끝에서 부른다.
- G6 관문 항목에 samples와 inferredTraits:[{situation, situationKo, behavior, refs:[{msgId, quote}]}]를 싣는다(모티브만).

### 약속 2. 생성 설정 (G가 만들고 I가 부른다)

- POST /api/sources/drafts 본문에 modelMode("PROMPT_ONLY" 기본 | "BIND_EXISTING" | "TRAIN"), autoReview(기본 true)를 더한다. usageBasis는 선택(없으면 scope "팀 내부 사용").
- autoReview가 true면 오케스트레이터가 G0 승인, G3 첫 후보 선택, G6 승인을 사람 대신 기록하고(reviewer "자동 진행") 계속 돈다. 유료 단계(이미지·영상·학습)는 자동으로 돌리지 않는다.
- S8c(챕터 시작 설정)를 그래프 단계로 넣는다: 모티브는 s8 뒤, G6 앞에서 자동 실행하고 끝에 run_samples를 부른다(F가 없으면 건너뛴다). 오리지널 그래프는 바꾸지 않는다.
- 동의(consentBy·consentDate)와 사용 근거 누락은 더 이상 G0을 잠그지 않는다.
- finalize는 autoReview면 대화 준비(S8c 끝)까지, 아니면 G0까지 작업을 건다.
- 캐릭터 상세 응답에 modelMode, autoReview를 싣는다. 화면 이름은 PROMPT_ONLY="프롬프트만"으로 통일한다.

