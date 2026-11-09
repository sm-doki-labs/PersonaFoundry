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



## 3차: 사용성 QA 반영 (2026-11-10)

QA 원문: ~/Documents/Codex/2026-11-07/new-chat/ux-qa/{create,review,chat}/ (스크린샷). 핵심: 상태가 화면마다 다름(P0: 진행 화면 "대화해 보기" → 대화 화면 막힘), 쓰지 않는 단계·개발 용어 과다, 목록에서 캐릭터를 못 찾음, 원문 화면 스위치 깨짐·개발용 오류, 기록 시트가 결정 화면처럼 보임.

| 묶음 | 브랜치 | 쓰기 경계 |
|---|---|---|
| J 상태·목록 백엔드 | codex/qa-api | web/reads.py, web/app.py(라우트만), web/sources.py, web/demo_chat.py, common/demo_chat.py(meta·목록만), pipeline/origin.py(보관 표시만), tests/test_qa_*.py |
| K 진행 화면 | codex/qa-flow | studio/shared/flow.js·flow.css, studio/factory.html, studio/shared/appbar.js, studio/tests/flow*.cjs |
| L 검토 기록 화면 | codex/qa-gate | src/character_factory_poc/web/static/shared/gate.js·gate*.css, web/gate_items.py(표시용 필드만), tests/test_web_*gate*.py |
| M 원문·대화·안내 화면 | codex/qa-pages | studio/sources.html·shared/sources.js·sources.css, studio/chat.html·shared/chat.js·chat.css, studio/help.html, studio/tests/sources*·chat*·help* |

### 약속 3. 캐릭터 상태 (J가 만들고 K·M이 쓴다)

- GET /api/projects의 캐릭터 항목과 GET /api/characters/{id}에 다음을 싣는다.
  - displayName: 표시 이름. 기획 이름 → 출처 초안의 표시 이름(intake subject.displayName) 순. 둘 다 없을 때만 "이름 미정".
  - status: draft(원문만 올림, 시작 전) | running | needs_review(사람 결정 대기) | chat_ready | failed | stopped. statusLabel: 시작 전 / 만드는 중 / 확인 필요 / 대화 가능 / 실패 / 멈춤.
  - chatReady: 대화 화면 meta의 ready와 같은 함수로 계산한다(한 곳에서만 판정).
  - goal: {label, done, total}. 모티브는 대화 가능까지 필요한 단계만 센다(그 모드의 그래프에서 s0→s3→s7→s8→s8c, 학습 모드면 학습 단계 포함). 오리지널은 지금 계산 그대로.
  - createdAt(ISO), archived(bool).
- POST /api/characters/{id}/archive 본문 {archived: bool}. 보관한 캐릭터는 목록 기본 보기에서 숨긴다(지우지 않는다).
- GET /api/chat/characters → 대화 가능한 캐릭터만 [{characterId, displayName, createdAt, origin}] 최신순.
- chat/meta가 ready=false일 때: reason은 빠진 것과 할 일을 쉬운 말로("팬 통화 장면이 아직 없어요. 진행 화면에서 만들어 주세요"), running이면 "만드는 중이에요", missing:["prompt"|"scene"], nextHref.

### 약속 4. 원문 받기 (J가 만들고 M이 쓴다)

- complete·PATCH 응답 FileRecord에 detectedSpeakers:[{name, lines}](원문 화자 이름, 줄 수 많은 순)와 suggested:{subjectSpeaker, userSpeaker, kind, register}를 싣는다. 대상 화자를 비워 보내면 서버가 suggested.subjectSpeaker(표시 이름과 가장 비슷하거나 가장 많이 말한 화자)를 쓴다. textId를 비워 보내면 파일 이름으로 만든다(겹치면 뒤에 번호).
- problems 문구는 해요체 한 문장, 필드 이름 없이 쓴다(예: "원문에서 '손흥민'이라는 화자를 찾지 못했어요. 원문에 있는 이름: 손흥민(진행), 상대").
- GET /api/sources/drafts → 시작하지 않은 초안 [{characterId, displayName, createdAt, files}] 최신순.
- 화면 이름은 "대화해 보기"로 통일한다("대화 테스트" 쓰지 않음).



## 4차: 영상 통화 대화와 영상 등급 (2026-11-10)

사용자 지시: "테스트 대화는 영상도 뽑아서 현행 서비스마냥 대화 중에 적절한 걸 뽑아서 보여주는 식", "영상 개수(5개·20개·60개) 대신 light·standard·pro·max 선택지".

서비스 기준(api-svc, 읽기만): 대기 영상(idle_good/idle_bad)이 돌고, 캐릭터가 한 마디 하면 앱이 POST /followup-clip에 유저 직전 한 마디 + 캐릭터가 방금 한 말을 보낸다. 서버는 감정(emotion) 클립 전부의 use_when을 보고 모델이 상위 3개를 점수와 함께 고르며, 반복 회피 규칙이 최종 결정하고, 딱 맞는 게 없으면 none(대기 유지). 앱은 none이면 옅은 반응(미소·끄덕 류)을 대신 튼다(frontend WEB/src/domain/fallbackClip.ts). 공장 등급은 stages/s6_actions/catalog.py VIDEO_TIERS.

| 묶음 | 브랜치 | 쓰기 경계 |
|---|---|---|
| N 영상 만들기 백엔드 | codex/v-make | contracts/source.py(사진 형식만), web/sources.py, pipeline/origin.py, pipeline/orchestrator.py, pipeline/graph.py, web/jobs.py, web/reads.py(영상 필드만), stages/s6_actions/run.py(캐릭터별 등급 읽기만), stages/s2_hero/twin.py·s4*(자동 고르기 연결이 꼭 필요할 때만), tests/test_v_make*.py |
| O 영상 고르기 백엔드 | codex/v-clip | common/clip_pick.py(새), web/demo_chat.py(clips·clip 라우트), common/demo_chat.py(영상 목록 읽기만), web/app.py(라우트 한 줄), resources/clip-pick-*(새), tests/test_v_clip*.py |
| P 영상 통화 화면 | codex/v-chat-ui | studio/chat.html·shared/chat.js·chat.css, studio/tests/chat*.cjs |
| Q 생성·진행 화면 | codex/v-make-ui | studio/sources.html·shared/sources.js·sources.css, studio/shared/flow.js·flow.css, studio/help.html, studio/tests/sources*·flow*·help* |

### 약속 5. 영상 등급과 사진 (N이 만들고 Q가 쓴다)

- 영상 등급 값: "none" | "light" | "standard" | "pro" | "max". 화면 이름은 영상 없이 / 라이트 / 스탠다드 / 프로 / 맥스. 화면에는 개수를 쓰지 않는다.
- POST /api/sources/drafts 본문에 videoTier(기본 "none")를 더한다. PATCH /api/sources/{cid}/settings 본문 {videoTier}로 시작 전·대화 가능 뒤에도 바꿀 수 있다.
- 원문 업로드는 사진(.jpg .jpeg .png .webp, 15MB 이하)도 받는다. FileRecord에 fileType: "text" | "photo"를 싣는다. 사진은 출처 묶음 photos로 들어간다. videoTier가 none이 아니면 사진이 1장 이상 있어야 시작할 수 있다(problems에 쉬운 말로).
- 자동 진행에서 videoTier가 none이 아니면 대화 가능 뒤에도 이어서 기준 사진(G1s 첫 사진), 장면 이미지(G4a·G4b·G4 첫 후보), 동작 영상(G5b 승인)을 등급의 장면만 자동으로 돈다. 등급을 고른 것이 유료 실행 확인을 대신한다. 소개 영상(S5)과 학습은 돌리지 않는다.
- POST /api/characters/{id}/videos 본문 {videoTier} → 대화 가능한 캐릭터에 영상 만들기를 건다({jobId}).
- 캐릭터 상세·목록에 videoTier, videoStatus("none" | "making" | "ready" | "failed"), videoLabel(쉬운 말)을 싣는다.

### 약속 6. 대화 중 영상 고르기 (O가 만들고 P가 부른다)

- GET /api/characters/{cid}/chat/clips?chapter=ch1 → {ready, chapter, idle:{good:{clipKey,url}, bad:{clipKey,url}}, emotion:[{clipKey, url, mood, title, useWhen}], special:[...]}. 승인된 S6 영상(최신 승인 판)만 쓴다. 영상이 없으면 ready=false.
- POST /api/characters/{cid}/chat/clip 본문 {userMessage, replyText, recent:[clipKey], chapter?} → {clip:{clipKey,url,mood,title}|null, kind:"emotion"|"none", mood}. api-svc app/services/character/clip_picker.py의 고르기(상위 3개 점수, 반복 회피, none 허용)를 옮긴다. 모델은 [providers.demo_chat].
- 화면(P)은 none이면 api-svc 앱과 같은 옅은 반응 대체 규칙(fallbackClip.ts)을 쓴다. 대화 내용은 저장하지 않는다.

