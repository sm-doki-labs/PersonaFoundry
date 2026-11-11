# 에이전틱 캐릭터 공장 상세 설계 (LLD)

- 문서 버전: v1.42
- 작성일: 2026-10-14
- 수정일: 2026-11-11
- 상태: 초안, 사용자 검토 전
- 근거: [PRD v1.25](../product/prd.md), [시스템 명세 v1.37](spec.md). 이 문서는 명세를 코드로 옮기는 세부만 정하고 다른 결정을 담지 않는다. 절마다 근거가 되는 명세 절을 `(명세 §n)`으로 적는다.
- 이번 변경: v1.40 말투 사용 조건 추출 표준(D-0179). 이전: v1.39 기능·말투 분리, 혼합 근거 보존과 조건부 조립(D-0178). 이전:  v1.37 전체 생성용 원문 분할 분석·반례 대조·조건 보존(D-0176). 이전: v1.36 원문 근거 기반 무예시 8섹션 공장의 기본 S8·G6·시연·내보내기 연결(D-0174). 이전: v1.35 실제 문답을 이전 턴으로 넣는 선택 기능(D-0173). 이전: v1.34 모티브 대조 특질 검증(D-0171). 이전: v1.33 두 말차례의 관심과 대응(D-0170). 이전: v1.32 모티브 반응 특질의 독립 대조 실험(D-0169). 이전: v1.31 모티브 V3 조립(D-0163).
- 변경 이력: v0.1 최초 작성 / v0.2(2026-10-20) S1을 화제성 순위 → 외모 특징 프록시로 바꾸고 §2~§5·§8.1·§9~§13을 고쳤다(D-0017, D-0018) / v0.3(2026-10-20) 인물 인상 칸과 계약 v2(§5.2·§5.5·§8.1·§10, D-0020, D-0021) / v0.4(2026-10-21) G1 참조 사진·S2 구현(§2~§5·§5.7·§5.8·§8.1·§8.2·§9·§10·§12·§13, D-0022, D-0023) / v0.5(2026-10-21) S3 외모 연결, S4·G4 구현(§2~§5·§5.10·§8.3·§8.4·§12, D-0024~D-0026) / v0.6(2026-10-21) S5·G5와 xai_video·grok_web 어댑터(§2~§5·§5.11·§8.5·§9·§10·§12·§13, D-0028~D-0030) / v0.7(2026-10-21) 9:16 세로 첫 프레임과 `intro-inputs-v2`(§3·§4·§5.11·§8.5, D-0031), 실제 grok.com 화면에 맞춘 `grok_web`(§9, D-0032) / v0.8(2026-10-22) 씨앗 → 변형 기획, S3r 참고 자료, S4a·S4b·S4 배경 → 자세 → 완성 이미지, 갈래별 진행 오케스트레이터(§2~§6·§8.3·§8.3a·§8.4·§11·§12, D-0033~D-0035) / v0.9(2026-10-22) 이미지 자동 검사·수정 루프(§2·§3·§5.10b·§8.4a·§9·§11·§12, D-0036, D-0037) / v1.0(2026-10-22) S6 동작 영상 골격과 G5b(§2~§5·§5.11a·§6.1·§8.5a·§11·§12, D-0038, D-0039) / v1.1(2026-10-22) 앱 통화 영상 카탈로그, 무표정 첫 프레임, 계약 v2(§2~§4·§5.11a·§8.5·§11·§12, D-0040, D-0041) / v1.2(2026-10-27) 얼굴은 G1에서 한 장만 고르고 S2를 자동 기준 사진·동일인 검사로 바꿔 G2를 없앴다. 아직 코드에는 반영하지 않았다(§2~§4·§5.7·§5.8·§5.9·§5.17·§6.1·§8.1~§8.5·§11~§13, D-0042, D-0043) / v1.3(2026-10-27) 3일 PoC 계약: §4 명령(S1 수집·S9~S11·내보내기·웹앱), §5.14·§5.15·§5.17을 새 계약(`data-plan-v1` 등, `training-run-v2` 등, `character-package-v1`·`export-result-v1`)으로 바꾸고, §6.5 워크숍 API, §8.8~§8.11(S9 샘플·대량 두 단계와 G7a, S10 학습·평가 분리, 패키지, 우리 앱 내보내기), §9 어댑터(`grok_oauth`, 순위 수집기, `gemma_qlora`, `vertex_gemini`), §12 M8을 더했다(D-0044, D-0045) / v1.4(2026-10-28) 학습 없이 긴 프롬프트로 패키지까지 가는 G8 결정(§8.9), 학습 제출 분리(`--submit-training`), G8 답 형식(§6.5)(D-0048) / v1.5(2026-10-28) 에이전틱 실행: §3 설정, §4 명령, §5.16 관문 기록 선택 칸, §5.19~§5.21 새 계약, §6.6~§6.10 물결 실행·자동 재개·사전 검토·재작업·대기열, §11 시험, §12 M9(D-0049) / v1.6(2026-10-29) 한소민 근거로 정본 직접 보존·조건부 적용·사실 소유자 구분을 보완했다(D-0053·D-0054)

## 1. 범위와 기준

R0(PRD §7)에 필요한 전부와, R1 단계의 계약·명령·알고리즘 골격을 정한다. R1 어댑터의 세부 인자는 착수 때 확인한다(§13). 언어·도구는 Python 3.12, `uv`, `ruff`, `pytest`, 명령 이름 `cfp`다(D-0008).

## 2. 패키지 구조 (명세 §2)

```
character-factory-poc/
  pyproject.toml
  scripts/check.sh
  src/character_factory_poc/
    __init__.py, __main__.py, cli.py
    common/
      canonical.py     JSON 정규화·sha256
      store.py         한 번만 쓰기, revision 폴더, manifest.sha256
      ids.py           ID 형식·발급
      schema.py        계약 검증(pydantic v2, extra="forbid")
      ledger.py        calls.jsonl, human-time.jsonl
      budget.py        예상 호출 수·비용·상한
      config.py        factory.toml 로딩, 환경변수 이름만 보관
      textstats.py     n-gram, 길이 비율, 섹션 파싱
      face_crop.py     얼굴 검출·크롭(OpenCV 4.x, D-0027)
      aspect.py        비율 파싱·크기 힌트·가운데 자르기(9:16, D-0031·D-0034)
    providers/
      base.py          포트 Protocol과 요청·응답 dataclass
      openai_compat.py TextModel·VisionModel(`OpenAICompatVisionModel`, data URI 이미지)·ImageGen(OpenAI 호환)
      fake_vision.py   VisionModel 가짜(기본 모두 PASS, 응답 함수 주입)
      codex_exec.py    TextModel(codex exec, 접근 기록 검사)
      xai_video.py     VideoGen: xAI 공식 API(D-0028)
      grok_web.py      VideoGen: Playwright + 전용 Chrome 프로필(CDP), 기본 꺼짐(D-0029)
      fake_video.py    VideoGen 가짜
      grok_oauth.py    VideoGen: xAI 영상 API를 OAuth 접근 토큰으로(D-0044 (3))
      training/        TrainingProvider: gemma_qlora.py(임대 GPU), vertex_gemini.py, fake.py(D-0044)
      fake_image.py    ImageGen 가짜 어댑터(단색 PNG)
      codex_image.py   ImageGen: ChatGPT 구독 codex exec image_gen(D-0019)
      fake.py          모든 포트의 가짜 어댑터
      embed.py         Embedder: hash-v1(오프라인 글자 n-gram, D-0035). 실제 임베딩은 Q-0019
    pipeline/
      graph.py         단계·의존·관문 정의
      state.py         state.json 읽기·쓰기·전이
      orchestrator.py  run, resume, status
      stage.py         Stage runner
      agent.py         Agent runner(루프·재시도·작업 공간)
      gates.py         gate-record, 검토 페이지 export·import
    stages/
      s1_reference/    ranking.py, features.py, cluster.py, report.py, preview.py, leak.py, page.py, run.py, approve.py
      s2_hero/         prompt.py, run.py, approve.py   (기준 사진·동일인 검사·외모 명세 자동 고정, D-0042. page.py·G2 페이지와 compare는 없앤다)
      s3_plan/         seed.py, variants.py, own.py, check_v2.py, page.py, approve.py(새 흐름, D-0033), draft.py, check.py, importer.py(페르소나 우선 경로)
      s3r_refs/        index.py, select.py   (참고 자료 색인·선별, D-0035)
      s4a_backgrounds/ run.py, prompt.py, page.py, approve.py   (배경 후보·배경 사진, G4a)
      s4b_poses/       run.py, page.py, approve.py   (장면 사실·자세 후보, G4b)
      s4_frames/       prompt.py, run.py, page.py, approve.py   (완성 이미지·부분 재생성)
      image_qa.py      이미지 자동 검사 루프: 기준표(plate-v1, composite-v1), 판정 프롬프트, 생성 → 판정 → 수정 반복(D-0036)
      s5_intro/        prompt.py, run.py, probe.py, page.py, approve.py
      s6_actions/      app_clips.py(앱 표준 37편 사본), catalog.py, run.py, page.py, approve.py   (동작 영상·무표정 첫 프레임·G5b·동작별 부분 재생성, D-0038·D-0040. qa.py는 R1)
      s7_traits/       sheet.py, check.py
      s8_prompts/      build.py, align.py, probe.py
      s9_data/         plan.py, handoff.py, samples.py, build.py, checks.py, split.py, page.py, approve.py   (G7a·G7, §8.8)
      s10_train/       plan.py, submit.py, collect.py   (학습, 관문 없음, §8.9)
      s10_eval/        prereg.py, run.py, metrics.py, judge.py, page.py, approve.py   (G8, §8.9)
      s11_release/     package.py, page.py, approve.py   (G9, §8.10)
      export/          doki_app/api_svc.py, doki_app/chat_svc.py, verify.py   (§8.11)
    collectors/        순위 수집기: port.py(`RankingSource`), http.py(`FetchSettings`·`HttpFetcher`), rankify.py, fake.py, collect.py(`plan_collection`·`collect_ranking`), errors.py(§8.1, §9)
    web/               워크숍 웹앱: app.py, reads.py(읽기 모델·경로 탈출 차단), jobs.py, events.py(SSE), settings.py(`[web]`), errors.py, static/(§6.5)
    checks/
      vision_judge.py  항목별 일관성 판정
      pair_judge.py    정순·역순 짝 판정과 합의
      rules.py         규칙 검사(길이·금지 표현·섹션)
    prompts/           역할 프롬프트·판정 프롬프트(.md), 출력 계약 예시
    resources/
      appearance-tag-vocab-v1.json
      trait-sheet-template-v1.json
      prompt-sections-v1.json
  tests/
    common/, providers/, pipeline/, stages/, checks/
    support/synthetic.py, support/fake_providers.py
    test_offline_pipeline.py
  docs/, runs/(gitignored), work/(gitignored)
```

`stages/`는 `pipeline/`에 의존하지 않는다. `pipeline/stage.py`가 단계 모듈의 `plan()`·`run()`·`check()`를 부른다.

## 3. 설정 (명세 §11·§12)

`factory.toml`(gitignored, 예시는 `factory.example.toml`)은 다음을 담는다.

```toml
[providers.text]       adapter = "openai_compat"; base_url = "http://127.0.0.1:10100/v1"; model = "gpt-6.1-sol"; api_key_env = "CFP_TEXT_API_KEY"
[providers.judge]      adapter = "openai_compat"; model = "anthropic/claude-opus-5-5"; api_key_env = "CFP_TEXT_API_KEY"
[providers.vision]     adapter = "openai_compat"; base_url = "http://127.0.0.1:10100/v1"; model = "google-antigravity/gemini-3.1-pro"; api_key_env = "CFP_TEXT_API_KEY"   # 이미지 생성(gpt)과 다른 계열(D-0010). 중계의 이미지 입력은 Q-0020
[stages.image_qa]      enabled = true; max_fix_rounds = 2; fix_mode = "edit"; allow_same_family = false   # D-0037 제안
[providers.image]      adapter = "codex_image"; model = "gpt-6.1-sol"; reasoning_effort = "low"; timeout_s = 600   # D-0019. 테스트·데모는 "fake"
[providers.video]      adapter = "xai_video"; model = "grok-imagine-video-1.5-lite"; api_key_env = "XAI_API_KEY"; poll_interval_s = 5; timeout_s = 600   # 테스트는 "fake"
                       # 웹: adapter = "grok_web"; accept_terms_risk = true; cdp_url = "http://127.0.0.1:9222"; [providers.video.selectors] video_mode/option/audio/upload/uploaded/prompt/submit(기본값은 2026-10-21 화면, D-0032)
                       # 웹을 쓸 때 [stages.s5] duration = 6; resolution = "480p"(웹은 6/10/15초·480p/720p만, 무료 등급은 480p·6초)
[stages.s5]            candidates = 2; duration = 8; resolution = "720p"; generate_audio = false   # D-0030 제안
                       aspect_ratio = "9:16"; first_frame = "vertical"   # D-0031. "hero"면 기준 사진 그대로
[stages.s6]            preset = "l2"(6편) | "standard"(37편); actions = [](비우지 않으면 이 목록); candidates = 1   # D-0040·D-0041
                       resolution = "720p"; aspect_ratio = "9:16"; generate_audio = false; [stages.s6.durations] idle = 15; emotion = 10; special = 6   # 웹이면 480p
[providers.tuning]     adapter = "fake"            # R1에서 vertex_tuning
[budget]               max_calls_per_command = 200; max_cost_usd_per_command = 20.0
[stages.s1]            cluster_k = 4; min_members_per_cluster = 3; min_common_fields = 2; previews_per_cluster = 1; max_check_retries = 3; image_size = "1024x1024"; min_list_size_for_percentile = 3
[stages.s2]            base_photo = "generate"; image_size = "1024x1024"   # D-0043 제안. "picked"면 G1 얼굴을 그대로 기준 이미지로 고정(이미지·판정 호출 없음). 시도 상한은 [stages.image_qa] max_fix_rounds를 따르고 수정 방식은 항상 regenerate
[stages.s3]            variants = 3; max_check_retries = 3   # D-0034 확정(3안)
[stages.s3r]           top_k = 8; max_selected = 8   # 제안
[resources]            reference_index = "<Git 밖 색인 JSON>"   # 없으면 S3r SKIPPED
[stages.s4a]           candidates_per_chapter = 3; plates = true; aspect_ratio = "9:16"   # D-0034 확정
[stages.s4b]           candidates_per_chapter = 3   # D-0034 확정
[stages.s4]            aspect_ratio = "9:16"; reference_crop = "face"; face_crop_scale = 1.4   # 챕터당 1장(D-0034), D-0027
[stages.s8]            short_prompt_max_chars = 1500
[orchestrator]         max_parallel = 3; auto_resume = true; resume_until = "sx"   # D-0049 제안. max_parallel = 1이면 지금의 순차 실행(§6.6·§6.7)
[review]               enabled = true; vision = false; gates = ["G1", "G3", "G4a", "G4b", "G4", "G5", "G5b", "G6", "G7", "G9"]   # D-0049. vision은 Q-0020 확인 뒤 켠다(§6.8)
[rework]               max_rounds = 3; normalize = true   # D-0049 제안. normalize = false면 메모 원문을 지시로 그대로 쓴다(§6.9)
                       # 공급자 표에 paid = true를 두면 워크숍 실행에서 그 공급자를 쓰는 단계는 실행 확인을 받는다(§6.7). 예: [providers.video] paid = true. fake 공급자는 무시한다
```

모델 이름·수치는 전부 제안이다. 키는 `api_key_env`에 적힌 환경변수 이름으로만 읽는다. 생성(`text`)과 판정(`judge`)의 모델 계열이 같으면 시작 시 경고한다(D-0010).

## 4. 명령 (명세 §2·§7)

모든 명령은 기본이 dry run이다. 외부 호출이 있는 명령은 `--execute`가 없으면 호출 계획(호출 수·예상 비용·입력 revision)만 출력한다.

| 명령 | 동작 |
|---|---|
| `cfp brief new <slug> --from brief.md` | 브리프 Markdown을 `brief-v1`로 변환·검증·고정한다. 미정 항목은 `assumptions`에 기록한다. |
| `cfp run <character_id> [--new-slug <slug>] --until <stage|gate> [--brief brief.md] [--seed seed.json] [--probes probes.txt] [--auto-approve G3] [--execute]` | 그래프를 따라 관문까지 연속 실행한다. 외모 축 캐릭터는 s1 → s2 → s3(씨앗·변형) → s5 → s3r → s4a → s4b → s4 → s7 → s8 순서이고, 한 갈래가 관문·씨앗을 기다리면 다른 갈래를 계속 돈다(D-0035). 이미 끝난 단계는 건너뛰고, 관문 대기나 CHECK_FAILED에서 멈춘다. `--auto-approve`는 실험 전용이며 기록에 남는다(D-0015). |
| `cfp plan draft <slug> --brief brief.md [--execute]` | 브리프 원문을 씨앗 notes로 고정하고(성격·나이·성별·직업은 표시된 줄에서 추출) 변형 경로로 기획 3안을 만들어 G3 대기로 둔다(D-0080). `cfp run --brief`와 같은 함수(`variants.run_s3_from_brief`)를 쓴다. |
| `cfp check <stage> <workspace>` | 작업 공간의 output.json을 계약·단계 검사로 확인한다. 에이전트가 `./check.sh`로 호출한다. |
| `cfp status <id>` | 단계·관문 상태, 최신 revision, 대기 중인 관문을 표로 낸다. |
| `cfp gate export <id> G<n>` | 검토 페이지 HTML을 만든다. |
| `cfp gate import <id> G<n> --answer answer.json` | 결정을 기록하고 상태를 전이한다. 사람 시간을 함께 받는다. |
| `cfp ref run <character_id> --ranking ranking.json [--new-slug <slug>] [--execute]` | S1 전체를 돈다: 순위 목록 고정 → 인물 묶기 → Scout 특징 태깅 → 정규화 → 군집 → 보고서 → 이름 유출 검사 → 미리보기 → G1 페이지. 결과는 G1 대기다. `cfp run ... --ranking ranking.json`도 s1부터 돈다. `--ranking`이 없으면 `cfp run`은 s1을 건너뛴다(페르소나 우선 경로, D-0013). |
| `cfp gate import <id> G1 --answer answer.json` | G1 결정. `{"decision": "SELECT", "selections": ["c2"], "referencePreviews": ["c2-1"], "reviewer": ..., "minutes": ..., "reasons": ...}`. `referencePreviews`는 정확히 한 장이고 `selections`의 외모군 미리보기여야 한다(외모군은 고른 얼굴에서 정한다, D-0042). `selections`를 비우면 얼굴의 외모군으로 채운다. `--auto-approve G1`은 정렬 1위 외모군의 첫 얼굴을 고른다. `REQUEST_CHANGES`는 `note`(고칠 점)를 받고, 다음 `cfp ref faces`가 얼굴만 다시 만든다. `REJECT`이면 다음 `ref run`이 새 `rf<k>`를 만든다. `s2`가 아직 `APPROVED`가 아니면(대기·`CHECK_FAILED`) G1을 다시 받아 다른 얼굴로 바꿀 수 있다. |
| `cfp ref faces <character_id> [--execute]` | 얼굴 다시 만들기(D-0043). 직전 G1이 `REQUEST_CHANGES`일 때만 돈다. 같은 rf의 순위·인물·특징·보고서를 바이트 그대로 가져와 새 `rf<k>`를 만들고, 얼굴 미리보기만 메모를 붙여 다시 만든다. Scout를 부르지 않는다. 결과는 G1 대기다. |
| `cfp hero run <character_id> [--execute]` | S2 기준 사진(D-0042, D-0043). G1 승인이 필요하다. G1 얼굴을 rev 폴더로 복사한다. `generate`면 기준 사진을 만들고 동일인 검사를 돌려 통과하면 외모 명세를 고정하고 `s2`를 `APPROVED`로 둔다. 끝까지 통과하지 못하면 `CHECK_FAILED`다. `picked`면 이미지 호출 없이 G1 얼굴로 바로 고정한다. 기본은 호출 계획(`generate`: 이미지 최대 3회, 판정 최대 6회)만 낸다. `cfp run ... --until s2`도 s2를 돈다(외모 축을 탄 캐릭터만). |
| `cfp gate import <id> G2 ...` | 없앴다(D-0042). "G2는 결번이다. 외모는 G1에서 고르고 S2는 자동으로 고정된다"는 오류를 낸다. `--auto-approve G2`도 받지 않는다. |
| `cfp plan seed <character_id> [--file seed.json] [--personality ..] [--job ..] [--age N] [--gender female|male|other] [--background ..]` | 기획 씨앗을 `sd<k>`로 고정한다(D-0033). 대표 성격은 필수, 나머지는 비우면 에이전트가 채운다. |
| `cfp plan variants <character_id> [--execute]` | S3 변형. 외모 명세(`s2` 승인)와 씨앗이 필요하다. 변형 3안과 G3 페이지를 만든다. |
| `cfp plan own <character_id> --file mine.md [--execute]` | 직접 쓴 상세안을 Normalizer가 `u1` 하나로 정리하고 G3 대기로 둔다. |
| `cfp gate import <id> G3 --answer answer.json` | 새 흐름 G3 결정. `{"decision": "SELECT", "selections": ["v2"], "edits": {"tagline": "..."}, ...}`. `APPROVE`는 첫 안. |
| `cfp refs index --out index.json [--stanford catalog.json] [--personas <dir>] [--jsonl path:SNS14 ...]` | 참고 자료 색인을 `hash-v1`로 만든다(Git 밖 경로에 쓴다). |
| `cfp refs select <character_id> [--execute]` | S3r. G3 승인이 필요하다. 색인이 없으면 건너뛴다. |
| `cfp scene backgrounds <character_id> [--execute]` | S4a. 배경 후보와 배경 사진, G4a 페이지. |
| `cfp gate import <id> G4a --answer answer.json` | `{"decision": "SELECT", "picks": {"ch1": "ch1-b2", "ch2": "ch2-b1"}, "custom": {"ch3": "한강 공원 벤치, 해질녘"}, ...}`. `APPROVE`는 챕터마다 b1. |
| `cfp scene poses <character_id> [--execute]` | S4b. 장면 사실 작성(직접 정의 배경의 배경 사진 포함)과 자세 후보, G4b 페이지. |
| `cfp gate import <id> G4b --answer answer.json` | `{"decision": "SELECT", "picks": {"ch1": "ch1-p2", "ch2": "ch2-p1"}, "custom": {"ch3": "..."}, "tweaks": {"ch1": {"hands": "..."}}, ...}`. `APPROVE`는 챕터마다 p1. |
| `cfp frames run <character_id> [--execute]` | S4. 외모 명세(`s2` 승인)와 G4b 승인이 필요하다. 챕터마다 완성 이미지 1장(9:16). 직전 G4가 챕터별 수정 요청이면 그 챕터만 다시 만든다. |
| `cfp gate import <id> G4 --answer answer.json` | `{"decision": "APPROVE"}` 또는 `{"decision": "REQUEST_CHANGES", "requestedChanges": [{"field": "ch2", "note": "..."}]}`. 승인하면 `approved-frames.json`을 쓴다. |
| `cfp video intro <character_id> [--execute]` | S5. 외모 명세(`s2` 승인)가 필요하다. 기본은 후보 수·모델·해상도·길이와 예상 비용(USD)만 보여 준다. dry run에는 세로 첫 프레임 이미지 1장도 함께 나온다. 실행하면 세로 첫 프레임을 만들어 고정하고 후보를 제출·수집해 G5 대기로 둔다. 직전 실행이 원격 대기·실패로 멈췄으면 같은 rev에서 이어 간다. |
| `cfp gate import <id> G5 --answer answer.json` | G5 결정. `{"decision": "SELECT", "selections": ["v2"], ...}`. SELECT면 `approved-intro.json`을 쓴다. |
| `cfp video web-setup [--port 9222] [--profile ~/.cfp/grok-chrome]` | `grok_web` 준비 안내: 전용 프로필 Chrome 실행 명령, 한 번 로그인, 설정 항목, `uv sync --extra web`. |
| `cfp video actions <character_id> [--execute]` | S6. G4 승인이 필요하다. 기본은 무표정 첫 프레임 이미지 수와 동작 영상 편수(3챕터 × 동작 수 × 후보 수, 수정 요청 뒤에는 다시 만들 동작만)·모델·해상도·길이별 예상 비용만 보여 준다. 실행하면 G4 승인 이미지를 미소 첫 프레임으로 복사하고, 무표정 출발 영상이 있으면 챕터마다 무표정 첫 프레임을 만든 뒤 동작마다 제출·수집해 G5b 대기로 둔다. 직전 실행이 원격 대기·실패로 멈췄으면 같은 rev에서 이어 간다. |
| `cfp gate import <id> G5b --answer answer.json` | G5b 결정. `{"decision": "SELECT", "picks": {"ch1-idle_good": "v1", ...}, "excluded": ["ch2-shy_good"]}` 또는 `{"decision": "REQUEST_CHANGES", "requestedChanges": [{"field": "ch1-glad_good", "note": "..."}]}`. `APPROVE`(자동 승인)는 모든 동작의 v1을 고른다. SELECT면 `approved-actions.json`을 쓴다. |
| `cfp plan import <slug> --from plan.json [--brief id] [--execute]` | character-plan-v2 기획서는 씨앗을 만들고 검증·고정한 뒤 G3를 `reviewer=user, decision=APPROVE, manual-plan`으로 기록한다(D-0013). 구형 character-plan-v1은 형식만 확인하고, `--execute`가 있으면 원문을 user-text로 보존해 기획 정리(`plan_normalizer`)로 v2 후보 `u1`을 만든 뒤 G3를 기다린다(D-0080). |
| `cfp persona traits [--references refs.json] [--reference-doc card.json ...]` | S7. 참조 ID 목록과 카드 본문을 에이전트 입력에 넣는다. |
| `cfp persona prompts --probes probes.txt` | S8. 프롬프트 쌍·말투 확인 표본·G6 페이지. 직전 실행이 표본 단계에서 끊겼으면 같은 rev에서 이어 간다. |
| `cfp persona probe --probes probes.txt` | 고정된 프롬프트 쌍은 두고 표본만 다시 돌린다. 결과는 `prompt-probe-r<k>.json`으로 누적되고 G6 페이지는 다시 만든다. |
| `cfp ref collect --source <source_id> [--categories female,male] [--execute]` | S1 실제 순위 수집(D-0044 (4)). 기본은 호출 계획(어떤 URL을 몇 번)만 낸다. 실행하면 `popularity-ranking-v2`를 쓰고 출처·수집 시각·이용 조건 확인 기록을 남긴다. 이용 조건이 자동 수집을 허용하지 않는 출처는 거절한다. |
| `cfp data plan|samples|build <character_id> [--execute]` | S9(§8.8). `plan`은 G6 승인 프롬프트 쌍으로 `data-plan-v1`을 고정한다. `samples`는 클러스터별 인계안(`data-handoff-v1`)과 샘플(`data-sample-v1`)을 만들고 G7a 대기로 둔다. `build`는 G7a 승인 뒤 나머지를 작성·검사·분할해 `dataset-rev-v2`를 만들고 G7 대기로 둔다. 기본은 호출 계획만, `--execute`로 작성 모델을 부른다. |
| `cfp train plan|submit|collect <character_id> --provider gemma_qlora|vertex_gemini` | S10 학습(§8.9). `plan`은 `training-run-v2`(`dryRun=true`: 요청 설정·전송 파일·비용 추정)을 쓴다. PoC는 여기까지다(D-0044 (9)). `submit`·`collect`는 `--execute`와 사용자 지시가 있어야 하고, 비용 추정이 상한을 넘으면 제출하지 않는다. |
| `cfp eval prereg|run|judge|report <character_id>` | S10 평가(§8.9). 사전 등록 → 조건별 응답 수집(`eval-run-v1`) → LLM 짝 판정 → 보고서(`eval-report-v2`) → G8 대기. |
| `cfp release build <character_id>` | S11(§8.10). 승인된 revision으로 `character-package-v1` 패키지를 만들고 G9 대기로 둔다. |
| `cfp export doki-app <character_id> [--verify]` | 우리 앱 변환(§8.11). G9 승인 패키지를 api-svc 시드 묶음과 chat-svc 콘텐츠 트리로 바꾸고 `export-result-v1`을 쓴다. `--verify`는 일회용 PostgreSQL 두 개에 적재해 확인한다. |
| `python -m character_factory_poc.web --root <공장 루트> [--port 8765]` | 워크숍 웹앱(§6.5). |
| `cfp run <character_id> ... [--parallel N]` | 동시에 돌릴 단계 수 상한(§6.6). 기본은 `[orchestrator] max_parallel`이고 `1`이면 지금의 순차 실행이다(D-0049). |
| `cfp review <character_id> <gate> [--execute]` | 열린 관문의 사전 검토(§6.8). 기본은 호출 계획만 낸다. 그 관문 revision의 검토 기록이 이미 있으면 그대로 둔다. G7a·G8은 거절한다(D-0049). |
| `cfp report hil <character_id>` | 사람 관문 보고서 `hil-report-v1`(§5.21, §6.10)을 표로 출력하고 `runs/characters/<id>/reports/hil-<UTC 시각>.json`에 쓴다. 외부 호출이 없다(D-0049). |
| `cfp ledger report <id>` | 원장으로 비용·시간 보고서를 만든다. |
| `cfp verify <id>` | 모든 revision 폴더의 manifest.sha256을 확인한다. |

## 5. 파일 형식 (명세 §5)

모든 JSON은 `schemaVersion` 필드를 가지며 알 수 없는 필드는 거절한다. 해시는 정규화 JSON의 sha256이다.

### 5.1 `brief-v1`

`{schemaVersion, briefId, createdAt, scope{service, target{gender, ageRange, taste[]}, artStyle, characterGender, characterAge, moodKeywords[], avoid[]}, sources[{kind, location, period, exclusions[]}], chapters[{chapterId, scene, relationStage}], actions[{chapterId, actionSlug, description}], persona{coreTraits[], contrastTrait, referenceTypes[], voiceProbes[]}, constraints{budgetUsd, reviewMinutes, videoResolution, videoSeconds}, assumptions[{field, value, reason}], sourceMarkdownSha256}`

### 5.2 `popularity-ranking-v2`

`{schemaVersion, scope{characterGender: female|male|any, ageRange, artStyle, appearanceOrigin: korean|east-asian|unspecified, moodHints[]}, lists[{listId, source, category, period, retrievedAt, url, entries[{rank, name, score|null}]}], notes}`. `listId`는 slug이고 목록끼리 겹치지 않는다. 한 목록 안에서 `rank`와 이름(공백·대소문자 무시)은 겹치지 않는다. 양식 예시는 [popularity-ranking-example.json](../templates/popularity-ranking-example.json)(합성 이름)이다.

### 5.3 `ranking-people-v1` / `appearance-features-v1`

인물 묶음: `{schemaVersion, rankingSha256, people[{personId, name, appearances[{listId, category, rank, listSize, percentile|null}]}]}`. `personId`는 `p001`부터 목록 순서·순위 순서로 처음 나온 차례대로 붙는다. 이름을 담으므로 Scout 작업 공간과 G1 페이지 밖으로 넘기지 않는다.

특징: `{schemaVersion, vocabVersion, features[{personId, recognized, tags{faceShape, eyeShape, hairLength, hairColor, hairStyle, bangs, skinTone, styling[], mood[]}, confidence{<field>: 0..1}, note}], notes}`. 단일값 7개는 어휘 값 또는 `unknown`, 복수값 2개는 어휘 값 0~3개다. 어휘는 `resources/appearance-tag-vocab-v1.json`(값마다 한국어 표기와 이미지 프롬프트용 영어 구절)이다.

### 5.4 `appearance-cluster-v1`

`{schemaVersion, clusterId, members[personId], memberCount, commonTags{<field>: value | [values]}, tagShares{<field>: {<value>: share}}, listCount, popularity{medianPercentile, iqr, normalizedCount, unnormalizedCount}, limitations[]}`. 이름 필드가 없다.

### 5.5 `reference-report-v2`

`{schemaVersion, subjectId, referenceRev, rankingSha256, featuresSha256, vocabVersion, scope, settings{clusterK, minMembers, minCommonFields, previewsPerCluster, minListSizeForPercentile, linkage, distance}, normalization, candidates[appearance-cluster-v1], ordering[{clusterId, rationale}], dropped[{members[], reason}], excludedPeople[{personId, reason}], cautions[], reproducibility{previousRev, agreementWithPrevious, comparedPeople}}`. `cautions`에는 대리 지표·모델 기억·활동 효과 미분리 세 문장이 항상 들어간다. 후보가 없거나 근거 필드가 비면 보고서를 만들지 않는다.

### 5.6 `reference-preview-v1`

`{schemaVersion, previewId, clusterId, prompt, negativePrompt, model, provider, settings{size, variation}, fileSha256, filePath}`. `previewId`는 `<clusterId>-<n>`, `filePath`는 rev 폴더 기준 `previews/<previewId>.png`다. 묶음은 `previews.json`(목록)에 둔다.

### 5.7 `hero-inputs-v1` / `hero-candidate-v1` / `hero-comparison-v1`

입력: `{schemaVersion, sourceReferenceRev, clusterId, commonTags, scope, referencePreviews[{id, path, sha256}], basePhoto: generate|picked}`. `referencePreviews`는 G1에서 고른 얼굴 정확히 한 장이다(D-0042). 기준 사진: `{schemaVersion, candidateId: h1, clusterId, sourceReferenceRev, referencePreviews[previewId], prompt, negativePrompt, model, provider, settings{size}, fileSha256, filePath, qa{rubric: identity-v1, status: PASS|FAIL, attempts, report}}`. 시도 파일은 `attempts/`, 판정 보고서(`image-qa-v1`)는 `qa/`에 있고, `filePath`는 통과한 시도를 복사한 `candidates/h1.png`다. 묶음은 `candidates.json`(항목 하나). `qa`는 선택 칸이라 옛 기록(후보 4장, `qa` 없음)도 읽힌다. `picked` 모드는 기준 사진 기록을 만들지 않는다. 비교 `hero-comparison-v1`은 쓰지 않는다(D-0043).

### 5.8 `appearance-spec-v1`

`{schemaVersion, characterId, appearanceRev, sourceReferenceRev, clusterId, scope, tags{<field>: value | [values]}, descriptionKo, descriptionEn, referenceImage{id, path, sha256}, referencePreviews[{id, path, sha256}], heroPrompt, forbidden[], notes, basePhoto?, identityCheck?{rubric, status: PASS|SKIPPED, attempts, report}}`. `referenceImage`는 동일인 검사를 통과한 기준 사진(`h1`)이고, `picked` 모드면 G1 얼굴(`id` = 미리보기 ID, `identityCheck.status = SKIPPED`)이다. `referencePreviews`는 G1 얼굴 한 장이다. 경로는 `s2-hero/ar<k>/` 기준이다. `load_appearance_spec(ctx, cid)`가 명세와 기준 이미지 경로를 돌려준다. 이 함수는 G2 관문 대신 `s2` 단계가 `APPROVED`인지와 그 `currentRev`를 본다(D-0042). 옛 캐릭터(G2 승인 ar2)는 `s2`가 이미 `APPROVED`라 그대로 읽힌다.

### 5.9 `character-plan-v1`

`{schemaVersion, characterId, planRev, name, age, job, coreTraits[], contrastTrait, chapters[{chapterId, scene, relationStage, lighting, composition}], evidence{<field>: [{kind: BRIEF|APPEARANCE|USER|PRESET, ref, quote}]}, appearanceRev}`. 외모 명세가 고정된 캐릭터(`s2` 승인)의 초안은 `appearanceRev`가 `s2` rev와 같고 챕터마다 `lighting`·`composition`이 비어 있지 않아야 한다(D-0024). `coreTraits`·`contrastTrait`의 evidence는 `BRIEF`만 허용한다(D-0005 검사).

### 5.9a `plan-seed-v1` / `character-plan-v2` / `plan-variants-v1` / `plan-selection-v1` (D-0033)

씨앗: `{schemaVersion, characterId, seedRev: sd<k>, personality(필수), job, age|null, gender: female|male|other|null, background, notes}`. 기획서 v2: `{schemaVersion, characterId, planRev, variantId: v<k>|u<k>, seedRev, name, age, gender, job, tagline(≤200), background, coreTraits[1..4], contrastTrait, choices[{situation, firstMove}] × 3..5, lifeAndTastes[3..8], wantsAndFears[1..4], misreadings[1..3], voiceSummary, voiceExamples[2..3], boundaries[1..4], profileCard{hobby, likes, dislikes, favoriteFoods, favoriteDrink, idealDate, everydayHabit, mbti|null, tags[≤4, 1~12자, # 없음], tmi[{text, revealStage 0..3}]}, chapterArc[{chapterId, slot, title, entryStage, targetStage, arc}] × 3, evidence{<field>: [{kind: SEED|USER|AGENT|PRESET|REFERENCE|APPEARANCE, ref, quote}]}, appearanceRev, notes}`. 챕터 자리는 ch1 친해지기(STRANGER→ACQUAINTANCE), ch2 썸타기(ACQUAINTANCE→FLIRTING), ch3 고백하기(FLIRTING→DATING)로 고정이다. 성격 칸(`coreTraits`·`contrastTrait`·`choices`·`wantsAndFears`·`misreadings`·`voiceSummary`)의 근거에 `APPEARANCE`가 있으면 실패한다(D-0005). 프로필 카드 칸은 api-svc `character_profile_card`, 나머지 성격 칸은 chat-svc `character-persona-v6`의 칸으로 옮겨 쓴다. 에이전트 출력 `plan-variants-output-v1` = `{variants[], axisNote}`, 저장본 `plan-variants-v1` = `{characterId, planRev, seedRev, seedSha256, mode: variants|own, axisNote, candidates[]}`, 선택 `plan-selection-v1` = `{planRev, selected, editedFields[]}`.

### 5.10 장면 계약 / `chapter-frame-v1` / `consistency-report-v1`

배경(`contracts/scene.py`): 에이전트 출력 `background-candidates-output-v1` = `{chapters[{chapterId, candidates[{candidateId: ch<n>-b<k>, place, timeOfDay, why, props[], mood, sceneFactsDraft[2..4], boundariesDraft[], plateBrief}]}] × 3}`. 저장본 `background-candidates-v1` = `{characterId, backgroundRev: bg<k>, planRev, appearanceRev, aspectRatio, chapters[{chapterId, title, arc, candidates[... + plate{id, path, sha256}|null]}]}`. G4a 선택 `background-selection-v1` = `{backgroundRev, picks{ch<n>: 후보 ID}, custom{ch<n>: 한두 줄}}`(챕터마다 둘 중 하나).

장면 사실: 에이전트 출력 `scene-writer-output-v1`, 저장본 `scene-plan-v1` = `{characterId, sceneRev: ps<k>, backgroundRev, planRev, aspectRatio, chapters[{chapterId, source: CANDIDATE|USER, candidateId, place, timeOfDay, props[], mood, sceneFacts[2..5], meetingContext, relationshipCanon[], sceneBoundaries[1..5], plateBrief, plate}] × 3}`. 칸 이름은 chat-svc 챕터 콘텐츠(`sceneFacts`·`meetingContexts`·`relationshipCanon`·`sceneBoundaries`)와 맞춘다.

자세: `pose-candidates-output-v1`/`pose-candidates-v1` = `{chapters[{chapterId, candidates[{poseId: ch<n>-p<k>, title, body, hands, props, gaze, expression, shot, outfit, motionHint, animatable}]}] × 3}`. G4b 선택 `pose-selection-v1` = `{sceneRev, picks{}, custom{}, tweaks{ch<n>: {<자세 칸>: 값}}}`, 결과 `pose-plan-v1` = `{chapters[{chapterId, source, poseId, <자세 칸>, customText, tweaked[]}] × 3}`.

완성 이미지 입력 `frames-inputs-v2` = `{appearanceRev, planRev, sceneRev, aspectRatio, referenceImage, identityReference, referenceCrop: face|full, cropNote, regenerate[ch<n>], carriedFrom: fr<k>|null, revisionNotes{ch<n>: 메모}}`. 이미지 기록은 `chapter-frame-v1`(`frameId: ch<n>-f1`, 가져온 챕터는 `settings.carriedFrom`), 묶음은 `frames.json`. 승인: `{schemaVersion, characterId, frameRev, appearanceRev, planRev, frames[{chapterId, frameId, path, sha256, prompt}] × 3, notes}`(`approved-frames.json`, `load_approved_frames`). 일관성(보류, D-0026): `{schemaVersion, target{kind: FRAME|VIDEO, ref}, judgeModel, items{<spec item>: {verdict: MATCH|MISMATCH|UNSURE, reason}}, embeddingSimilarity: null|number, humanVerdict: null|PASS|FAIL}`

### 5.10b `vision-verdict-v1` / `image-qa-v1` / 자동 검사 요약 (D-0036)

판정: `{schemaVersion, items[{id, verdict: PASS|FAIL|UNSURE, reason}], fixHint}`. 항목 ID는 기준표와 정확히 같아야 한다(빠지거나 남으면 형식 오류로 한 번 더 묻고, 그래도 틀리면 `CheckFailed`). 보고서(`qa/<이미지 ID>.json`): `{schemaVersion, imageId, stage, rubric, generatorProvider, generatorModel, judgeProvider, judgeModel, sameFamilyWarning, rounds[{attempt, filePath: attempts/<id>-a<k>.png, sha256, mode: generate|edit|regenerate, fixApplied, items[], failed[], unsure[], fixHint}], finalAttempt, status: PASS|FAIL}`. 요약 `QaSummary` = `{status, attempts, failed[], unsure[], reasons[], report}`는 `background-candidates-v1`의 후보, `scene-plan-v1`의 챕터, `chapter-frame-v1`에 선택 칸 `qa`로 붙는다(없으면 검사를 끈 것이다).

### 5.11 `intro-inputs-v2` / `video-job-v1` / `video-asset-v1` / `intro-video-approved-v1` / `video-qa-v1`

설정: `{prompt, duration 1~15, resolution 480p|720p|1080p, aspectRatio|null, generateAudio}`. 입력: `{schemaVersion, appearanceRev, planRev|null, firstFrame{id, path, sha256}, firstFrameSource{mode: hero|generated, hero{id, path, sha256}, prompt, negativePrompt, provider, model, rawSize[w,h]|null, croppedSize[w,h]|null}, provider, model, settings, candidates}`. v1(대표 이미지 그대로, 출처 칸 없음)은 실제 산출물 없이 v2로 바뀌었다(D-0031). 작업: `{schemaVersion, videoId, candidateId: v<n>, stage, provider, model, jobId, status: SUBMITTED|DONE|FAILED, settings, firstFrameSha256, estCostUsd, error}`(상태가 바뀌므로 원자적으로 덮어쓴다). 자산: `{schemaVersion, videoId, candidateId, jobId, provider, model, filePath, fileSha256, bytes, settings, probe{tool, durationS, width, height, note}, estCostUsd}`. 승인: `{schemaVersion, characterId, introRev, appearanceRev, videoId, video{id, path, sha256}, notes}`. 검사: `{schemaVersion, videoId, sampledFrames[], consistency: ref, hands: PASS|FAIL|UNSURE, loopSeam: PASS|FAIL|NA, verdict, retryCount}`

### 5.11a `action-inputs-v2` / `action-clip-v2` / `action-videos-approved-v2` (D-0038, D-0040, D-0041)

v1(동작 카탈로그 8개, D-0039)은 실제 산출물 없이 v2로 바뀌었다. `video_id`는 S6 `...-ch<N>-<clip_key>-va<k>-<n>`을 받는다(밑줄 허용, S5 `...-intro-vi<k>-<n>`은 그대로). 동작: `{actionId: ch<N>-<clip_key>, actionKey: clip_key, playType: idle|reaction, pickRole: null|emotion|special, actionCategory: null|aegyo|touch, mood: good|bad, title, description, useWhen, duration 1~15, prompt, reviewNote}`. 대기만 `pickRole`이 없고, 특별 행동만 `actionCategory`를 가진다(sexy·private 없음). 챕터: `{chapterId, frameId, stageNote, goodFrame{id, path, sha256}, badFrame|null, badFrameSource|null{source, prompt, negativePrompt, provider, model, rawSize, croppedSize, reusedFrom}, actions[]}`. 무표정 출발 동작이 있을 때만 `badFrame`이 있다. 입력: `{schemaVersion, frameRev, appearanceRev, planRev, provider, model, preset: l2|standard|custom, resolution, aspectRatio, generateAudio, candidates 1~4, previousRev|null, regenerate[actionId], chapters[3]}`. 후보: `{schemaVersion, actionId, chapterId, actionKey, playType, pickRole, actionCategory, mood, title, frameId, asset: video-asset-v1, reusedFrom|null}`. 승인: `{schemaVersion, characterId, actionRev: va<k>, frameRev, appearanceRev, planRev, clips[]{actionId, chapterId, stage(=챕터 번호), clipKey, playType, pickRole, actionCategory, mood, title, description, useWhen, duration, videoId, video{id, path, sha256}}, excluded[actionId], notes}`. 승인은 세 챕터가 모두 하나 이상 있어야 하고 한 동작에서 영상은 하나만 고른다. 작업·자산은 S5와 같은 `video-job-v1`(stage `s6`)·`video-asset-v1`이다.

### 5.12 `trait-sheet-v1`

`{schemaVersion, characterId, planRev, choice{attention, interpretationPriority, primaryResponse, expressionIntensity, switchConditions[]}, card{stance, bigFiveNotes, expressedTraits{core[], contrast}, judgmentPriorities[{value, dilemma, choice, reason, switch}], dialogueHabits{order, directness, questions, evidence, lexicon}, situational[{condition, reaction, return}], experiences[{event, interpretation, habitLink}]}, references[{kind: SNS14|STANFORD|OTHER, id, version}], unresolved[field]}`. `resources/trait-sheet-template-v1.json`이 필수 칸과 "형용사만 적힘" 검사용 패턴을 정의한다.

### 5.12a `reference-index-v1` / `reference-curation-output-v1` / `reference-set-v1` (D-0035)

색인: `{indexId, embedder, dim, sources[], items[{itemId, source: AUTHORED|STANFORD|SNS14|NIKL|OTHER, version, label, uses[TRAITS|VOICE|DATA], text, vector[]}]}`. 에이전트 출력: `{selected[{itemId, use, why}]}`. 선별 결과: `{characterId, refRev: rs<k>, planRev, indexId, indexSha256, embedder, queries{<use>: 질의}, retrieved[{itemId, use, score}], selected[{itemId, source, version, label, use, why}]}`(원문 없음).

### 5.13 `prompt-pair-v1` / `prompt-probe-v1`

쌍: `{schemaVersion, characterId, personaVersion, sections[name], long{text, sha256, chars}, short{text, sha256, chars}, systemRulesRef, shortAdopted: false}`. 표본: `{schemaVersion, personaVersion, probes[{sentence, longResponse, shortResponse, judge{pick, reasons}}]}`

### 5.14 S9 데이터셋 계약 (D-0044, D-0045)

코드는 `src/character_factory_poc/contracts/dataset.py`다. `dataset-rev-v1`·`data-qa-v1`을 대체한다(실제 산출물 없이 바뀜).

| 계약 | 내용 |
|---|---|
| `data-plan-v1` | `{characterId, personaVersion, promptPairSha256, targetTrainConversations, clusters[{clusterId: base|situation|history|ownership|conflict, label, share, targetConversations, materials[SNS_REWRITE|SYNTH|NIKL], sampleSize}], validation{baseConversations, augmentedShare}, guideRef, writerModel, judgeModel}`. 기본값은 학습 가이드 §6의 소민 기준 배합(640대화, 56:8:22:7:7, 샘플 12, 검증 기반 60 + 보강 10%) |
| `data-handoff-v1` | 클러스터별 인계안: `behaviorTable[{situation, attention, choice, voice}]`, `voiceExamples`, `forbidden`, `notes` |
| `conversation-v1` | 학습 예시 한 개: `conversationId, clusterId, material, skeletonId, system, messages[{role: user|assistant, content}], checks{blocking{<검사 이름>: bool}, warnings}, provenance{writerModel, requestRef, sourceRef, editedBy}`. `system`은 짧은 system(성격 + 관계 + 채널 + 시작 장면), 프리필 없음 |
| `data-sample-v1` | G7a에 올리는 클러스터별 샘플 묶음(`conversations[{ref, sha256}]`) |
| `data-qa-v2` | G7a·G7 사람 판정: `gate, subjectSha256, verdicts{conversationId: ADOPT|FIX|REJECT}, notes, reviewer, minutes` |
| `dataset-rev-v2` | G7에서 고정: `datasetRev(ds<k>), planSha256, sampleQaRefs, clusterCounts{clusterId: {conversations, replies, supervisedTokens}}, files[{split, path, sha256, conversations}], blockingFailures, warnings, digest` |

저장 위치: `runs/characters/<id>/s9-data/ds<k>/` 아래 `plan.json`, `handoffs/<cluster>.json`, `samples/<cluster>.json`, `conversations/<conversationId>.json`, `train.jsonl`, `validation-base.jsonl`, `validation-augmented.jsonl`, `eval.jsonl`, `index.jsonl`, `dataset.json`. JSONL 한 줄은 `{"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}`이다. Vertex 형식(`systemInstruction` + `contents[{role, parts}]`)은 제출 때 변환한다.

### 5.15 S10 학습·평가 계약 (D-0044, D-0045)

코드는 `src/character_factory_poc/contracts/training.py`다. `training-run-v1`·`eval-prereg-v1`·`eval-report-v1`을 대체한다.

| 계약 | 내용 |
|---|---|
| `training-run-v2` | `{characterId, datasetRev, datasetDigest, provider: gemma_qlora|vertex_gemini|fake, baseModel, baseModelRevision, requestedConfig, appliedConfig, dryRun, estimate{usd, gpuHours, billableTokens, basis}, budgetUsd, status: PLANNED|SUBMITTED|RUNNING|SUCCEEDED|FAILED|CANCELLED, jobId, transfers[{path, bytes, sha256, remoteSha256}], checkpoints[{checkpointId, epoch, step, ref}], modelBinding{provider, ref, checkpointId}}`. `dryRun=true`이면 `jobId`가 없다 |
| `eval-prereg-v2` | `{characterId, personaVersion, arms[{armId: LONG_BASE|SHORT_GEMMA_SFT|SHORT_GEMINI_SFT, promptRef, model}], sets[{setId: OE|SE|APOLOGY|LONG200, ref, seeds, perTurnSeed, personas}], judge{model, family, orderSwap}, humanPairs, criteria[{id, metric, comparator, threshold, appliesTo}], frozenAt}`. 기본 기준(D-0045 (3)): `repeat_rate_101_200 <= 0.05`, `memory_recall_200 >= 0.9`, `apology_recovery >= 4/6`, `appliesTo = SFT_ANY` |
| `eval-run-v1` | 한 조건·한 세트의 응답: `{preregSha256, armId, setId, model, items[{itemId, personaId, turns[{user, reply, seed}]}]}` |
| `eval-report-v2` | `{preregSha256, runRefs, metrics[{armId, metric, value, detail}], criteriaResults[{id, armId, value, passed}], llmPairs[{pairId, armA, armB, forward, reverse, consensus}], humanPicks[{pairId, pick}], llmHumanAgreement, recommendation}` |

저장 위치: `runs/characters/<id>/s10-train/tr<k>/<provider>/training-run.json`(어댑터·체크포인트는 Git 밖), `runs/characters/<id>/s10-eval/ev<k>/{prereg.json, runs/<arm>-<set>.json, pairs.json, report.json}`.

### 5.16 `gate-record-v1`

`{schemaVersion, characterId|briefId, gate, shownArtifacts[{ref, sha256}], decision, selections[], reasons, requestedChanges[{field, note}], reviewer, minutes, decidedAt, reviewRef?, followedReview?}`. `reviewRef`·`followedReview`는 D-0049(§6.8)에서 더한 선택 칸이고, 옛 기록은 두 칸 없이 읽힌다.

### 5.17 `character-package-v1` / `export-result-v1` (D-0011, D-0044)

코드는 `src/character_factory_poc/contracts/release.py`다. `release-manifest-v1`을 대체한다.

패키지(형식 중립): `{characterId, packageRev(pk<k>), locale: ko, builtAt, profile{name, gender, age, job, tagline, description, hobby, likes, dislikes, mbti, tags[≤4], tmiItems[{text, revealStage}]}, appearance{appearanceRev, heroImage, spec}, chapters[{chapterNo, chapterId, title, relationshipStage, intro, goal, facts, frame, background}], videos[{videoId, kind: INTRO|ACTION, chapterNo, clipKey, title, description, useWhen, expression, durationS, file, provider, synthetic}], persona{personaVersion, traitSheet, longPrompt, shortPrompt}, sft{datasetRev, datasetDigest, trainingRuns, evalReport, adoptedBinding}, gates[{gate, rev, decision, recordRef}], files[{path, sha256, bytes}]}`. 경로는 모두 패키지 루트 기준 상대 경로이고 `files`에 있어야 한다. G2는 결번이다(D-0042). 옛 캐릭터의 G2 기록이 있으면 `gates`에 함께 담는다.

패키지 폴더: `runs/characters/<id>/s11-release/pk<k>/` 아래 `package.json`, `appearance/`, `chapters/ch<n>/`, `videos/`, `persona/`, `sft/`, `gates/`.

내보내기 기록: `{characterId, package{ref, sha256}, target: doki-app, targetVersions{api-svc: <alembic head>@<commit>, chat-svc: ...}, outputs[{system: api-svc|chat-svc, kind: seed-bundle|content-tree, path, sha256}], mapping[{source, target, note}], unmapped[], verification{status: NOT_RUN|PASSED|FAILED, disposableDb, steps[{name, ok, detail}]}}`.

### 5.18 원장

`calls.jsonl` 한 줄: `{callId, at, stage, kind, provider, model, inputTokens, outputTokens, images, seconds, ms, ok, estCostUsd, ref}`. `human-time.jsonl` 한 줄: `{at, gate, minutes, ref}`.

### 5.19 `gate-review-v1` (D-0049, 명세 §7.2)

`{schemaVersion, subjectId, gate, rev, reviewer{provider, model, family}, mode: "llm"|"vision"|"deterministic", shownArtifacts[{ref, sha256}], items[{candidateId, chapterId?, rank?, verdict: "RECOMMEND"|"OK"|"CONCERN", reasons[], defects[{field, note}]}], summary, createdAt}`. 저장 위치는 `<캐릭터 폴더>/reviews/<gate>-<rev>.json`이고 한 번만 쓴다. 단계 revision 폴더 안에 두면 매니페스트·패키지 파일 목록에 없는 파일이 생겨 해시 검사가 깨진다(통합 시험에서 G9 검토가 내보내기 해시 검사를 깨뜨려 옮겼다). `candidateId`는 관문 화면 항목 ID(`web/gate_items.py`가 만드는 ID)와 같다. 고르기 관문은 챕터(또는 동작)마다 `rank` 1이 정확히 하나다. 승인 관문(G4·G6·G7·G9)은 `rank` 없이 `verdict`·`defects`만 쓴다. G5b는 후보 ID가 동작마다 겹쳐 `candidateId`를 `<actionId>:<candidateId>`로 쓴다(관문 기록 `selections`와 같은 형식). G9는 화면 후보가 없어 `items`를 비우고 `summary`에 패키지 검사 결과를 요약한다.

### 5.20 `rework-brief-v1` (D-0049, 명세 §7.3)

`{schemaVersion, subjectId, gate, stage, fromRev, round, recordRef, targets[{field, note}], keep[], instructions, normalizedBy{provider, model}|null, createdAt}`. `targets[].note`는 관문 기록의 `requestedChanges[].note` 원문 그대로다. `instructions`는 `[rework] normalize = true`면 텍스트 모델이 단계 지시로 바꾼 문장이고, 꺼져 있거나 그 호출이 실패하면 메모 원문을 줄마다 이은 문장이다. 저장 위치는 `<캐릭터 폴더>/rework/<gate>-<fromRev>.json`이고 한 번만 쓴다. `round`는 그 관문의 `REQUEST_CHANGES` 관문 기록 수다(이번 것 포함).

### 5.21 `hil-report-v1` (D-0049, 명세 §7.4)

`{schemaVersion, subjectId, createdAt, gates[{gate, rounds[{rev, openedAt?, decidedAt?, waitMinutes?, reviewMinutes, decision?, followedReview?, reviewRef?}], requestChangesCount, reworkCapReached}], totals{gatesDecided, waitMinutes, reviewMinutes, requestChanges, followedReviewRate?}}`. 열린 시각·결정 시각은 원장 `ledger/gate-events.jsonl`(§6.6)에서, 검토 시간·결정·일치 여부는 관문 기록에서 읽는다. G7a·G8의 `followedReview`는 늘 비어 있다.

## 6. 오케스트레이터 (명세 §2·§7)

### 6.1 단계 그래프

외모 축 캐릭터의 순서는 S1 → G1 → S2(자동, 관문 없음, D-0042) → (S3 씨앗·변형 → G3, S5 → G5) → (S3r, S4a → G4a → S4b → G4b → S4 → G4, S7 → S8 → G6)이다(D-0033). `STAGES` 순서는 s1, s2, s3, s5, s3r, s4a, s4b, s4, s6, s7, s8, s9~s11이다. S6은 G4 승인 뒤 돌고 관문 G5b에서 기다린다(D-0038). 외모 축 단계(`APPEARANCE_STAGES`)에 S6이 들어간다. 오케스트레이터는 한 갈래가 관문이나 사람 입력(`NeedsInputError`, 예: 씨앗 없음)을 기다리면 그 갈래만 멈추고 의존이 풀린 다음 단계를 계속 돈다. 더 진행할 단계가 없으면 기다리는 관문(`RunLog.waiting`)과 시작하지 못한 단계(`RunLog.blocked`)를 보고하고, `stopped_at`은 첫 대기 관문이다(D-0035). `RunOptions.seed`가 있고 저장된 씨앗이 없으면 S3 전에 씨앗을 고정한다. **외모 명세 의존(D-0042, D-0043).** `Stage`에 `needs: frozenset[str]`(`APPROVED`여야 하는 단계)를 더한다. `after`(`AWAITING_HUMAN` 이상이면 됨)와 다르다. s2는 `deps={G1}`, `gate=None`이다. s5는 `needs={s2}`, s4a는 `deps={G3}, needs={s2}`, s4는 `deps={G4b}, needs={s2}`이고, S3 변형은 실행 함수가 `s2` 승인을 직접 본다. `GATES` 목록에서 G2를 뺀다. 옛 `state.json`의 G2 칸은 읽기만 하고 쓰지 않는다. `RunLog.waiting`에는 G2가 나오지 않는다. s2가 `CHECK_FAILED`면 `RunLog.blocked`에 이유("동일인 검사 미통과 n회", 보고서 경로)와 함께 올라간다. 아래는 이전 서술이다.

`graph.py`는 `Stage(id, deps: set[GateId], gate: GateId|None, parallel_group)` 목록을 가진다. S3의 `gate=G3`, S4·S5·S7의 `deps={G3}`, S6의 `deps={G4}`, S8은 `deps=set()`이지만 S7 완료가 필요하므로 `after={S7}`로 표현한다. S11의 `deps={G5, G8}`.

S9~S11은 다음 단계로 둔다(D-0044, §8.8~§8.11): `s9s` 데이터 샘플(`deps={G6}`, `gate=G7a`), `s9` 데이터셋(`deps={G7a}`, `gate=G7`), `s10t` 학습(`deps={G7}`, 관문 없음, 같은 단계 안에서 학습 환경별 `training-run-v2`를 만든다), `s10` 평가(`deps={G7}`, `after={s10t}`, `gate=G8`), `s11` 패키지(`deps={G4, G5, G5b, G6, G8}`, `gate=G9`), `sx` 내보내기(`deps={G9}`, 관문 없음). 실제 학습은 PoC에서 dry run까지이므로, 실제 설정의 `s10t`는 `training-run-v2(dryRun=true)`를 쓰고 사람 실행 지시를 기다리는 상태로 멈춘다. 가짜 학습 공급자에서는 끝까지 간다.

### 6.2 상태 파일과 전이

`state.json`: `{characterId|briefId, stages{<stage>: {status, currentRev, attempts, lastError, updatedAt}}, gates{<gate>: {status, rev, recordRef}}}`. 전이는 `state.py`의 함수 하나로만 하며 허용되지 않은 전이는 `StateTransitionError`다. 쓰기는 임시 파일 뒤 `os.replace`로 원자적으로 한다.

### 6.3 재개와 멱등성

`run`은 단계 상태가 `RUNNING`이면 작업 공간의 `progress.json`을 읽어 남은 하위 단계부터 이어 간다. `store.write()`는 같은 경로에 같은 바이트면 무시하고 다르면 `ImmutableWriteError`를 낸다.

### 6.4 검토 페이지

`gates.py`는 Jinja 없이 문자열 템플릿으로 정적 HTML을 만든다. 이미지·영상은 상대 경로로 넣고, 후보 레이블은 `secrets.SystemRandom`으로 섞어 `key.sealed.json`에 대응표를 둔다. 페이지의 버튼은 결정을 `gate-record-v1` JSON 텍스트로 만들어 복사하게 한다. 네트워크 요청은 없다.

### 6.5 워크숍 웹앱 API (D-0044 (6), PoC 계획서 §6)

`src/character_factory_poc/web/`(FastAPI)이다. 화면은 워크숍 시안(`c-glass.html` 작업실, `d-ops.html` 운영)을 `src/character_factory_poc/web/static/`에 두고 API로 데이터를 읽는다. 로그인은 없고, 공장 루트·포트·저장 위치는 설정값이다(배포 대비).

| 경로 | 동작 |
|---|---|
| `GET /api/health` | 서버·공장 루트 확인 |
| `GET /api/projects` | `runs/characters/*`·`runs/briefs/*` 목록과 단계·관문 상태 요약 |
| `GET /api/characters/{id}` | `state.json` 전체, 갈래별 진행 요약, 대기 관문 |
| `GET /api/characters/{id}/gates/{gate}` | 그 관문 검토 항목(파일 목록, 미리보기 URL, 기존 기록) |
| `GET /api/files/{id}/{path}` | 캐릭터 폴더 안 파일만. 경로 탈출은 거절한다 |
| `POST /api/characters/{id}/gates/{gate}/decision` | 본문은 `cfp gate import`의 답 JSON과 같다. 같은 코드 경로로 관문 기록을 남긴다 |
| `POST /api/jobs`, `GET /api/jobs/{jobId}` | `{characterId, action: run, until}`로 오케스트레이터를 백그라운드에서 돌린다. 캐릭터당 동시에 하나 |
| `GET /api/events` | SSE. `{type: job|state|gate, characterId, ...}` |

새 관문의 답 형식: G7a `{"decision": "SELECT"|"REQUEST_CHANGES", "cluster": "<clusterId>", "verdicts": {"<conversationId>": "ADOPT"|"FIX"|"REJECT"}, "notes": {...}}`, G7 `{"decision": "APPROVE"|"REQUEST_CHANGES", "verdicts": {...}}`(무작위 표본 20개), G8 `{"decision": "SELECT", "adopted": "LONG_BASE"|"<model_binding ref>", "humanPicks": [{"pairId", "pick"}]}`(학습 없이 진행 화면이면 `{"decision": "SELECT", "adopted": "LONG_BASE"}` 또는 `{"decision": "REJECT"}`), G9 `{"decision": "APPROVE"|"REJECT", "reasons": "..."}`.

구현 메모(2026-10-27, M8 1차): `/api/projects`는 `characters[]`(단계·관문·대기 관문·진행률·마지막 작업)와 `briefs[]`·`totals`를, `/api/characters/{id}`는 원본 `state` + `lanes`·`pendingGates`를, 관문 항목은 `files`·`previews`(URL)·`record`·`records`를 돌려준다. 작업 ID는 `job-<시각>-<hex>`, 상태는 `queued|running|succeeded|failed`이고 `[web] jobs_dir`(기본 `work/web-jobs`)에 남으며 재시작 때 끝나지 않은 작업은 실패로 정리한다. SSE 이벤트 이름은 `hello|job|state|gate`다. 오류: 없음 404, 형식 400, 이미 결정된 관문·동시 작업 409, 아직 구현되지 않은 관문 501, 캐릭터 폴더 밖 파일 400. 관문 결정과 작업은 캐릭터별 잠금으로 순서를 지킨다. 관문별 상세 화면은 아직 없고(K-0037), 대기 관문 칩은 검토 항목 JSON을 연다.

### 6.6 물결 실행 (D-0049, 명세 §7.1)

**상태 파일 잠금.** `StateFile.transition`·`set_gate`는 `state.json.lock`에 `fcntl.flock(LOCK_EX)`을 잡고 디스크의 `state.json`을 다시 읽어 그 위에 변경을 적용한 뒤 저장한다. 메모리의 `self.state`도 다시 읽은 값으로 바꾼다. 같은 스레드에서 잠금을 다시 잡지 않는다.

**관문 사건 기록.** `set_gate`는 관문 상태가 `AWAITING_HUMAN`이 되면 `{"at", "gate", "rev", "event": "opened"}`를, `APPROVED`·`REJECTED`가 되면 `"event": "decided"`를 `<캐릭터 폴더>/ledger/gate-events.jsonl`에 원장과 같은 방식(파일 잠금 덧붙이기)으로 남긴다.

**`Context` 지연 생성.** 공급자 객체를 처음 만드는 부분(`_text`·`_judge`·`_image`·`_video`·`_vision`·`_codex`)을 `threading.Lock` 하나로 감싼다. 예산(`Budget`)은 단계 실행 함수가 `ctx.budget()`으로 따로 만들기 때문에 공유하지 않는다.

**계산 함수.** `pipeline/scheduler.py`의 `ready_stages(state: StateFile, runners: Mapping[str, Callable], attempted: set[str]) -> list[str]`. `STAGES` 순서를 유지해 다음을 모두 만족하는 단계를 돌려준다. 실행 함수가 있고 `implemented`다. 상태가 `PENDING`·`RUNNING`·`CHECK_FAILED`·`REJECTED` 가운데 하나다. `require_deps`를 통과한다. `attempted`에 없다. 그래프에 없지만 실행 함수가 직접 확인하는 선행 단계는 `extra_needs`로 받는다. 외모 축 캐릭터의 s3는 s2 승인이 필요하다(`extra_needs_for(appearance_axis)`). 순차 훑기는 `STAGES` 순서라 이 조건이 저절로 지켜진다.

**물결 실행.** `run_waves(ctx: Context, cid: str, opt: RunOptions) -> RunLog`. 순서는 다음과 같다. (1) `run_until`과 같은 건너뜀 기록(외모 축 없음·`--ranking` 없음)을 남긴다. (2) `ready_stages`로 이번 물결을 고르고, 워크숍 실행이면 유료 단계를 덜어 `RunLog.held`에 넣는다(§6.7). (3) `ThreadPoolExecutor(max_workers=opt.max_parallel)`로 동시에 돈다. 단계마다 기존 `run_until`의 한 단계 처리(실행·예외별 기록·관문 대기 처리·자동 승인)를 그대로 쓰는 `_run_one(ctx, cid, sid, opt, runners) -> StageOutcome`를 부른다. (4) 물결이 끝나면 단계별 기록 줄을 `STAGES` 순서로 `RunLog.steps`에 붙여 기록이 실행 순서와 상관없이 같게 한다. (5) `--until`에 닿았거나 고를 단계가 없으면 멈춘다. 끝에 `run_until`과 같은 형식으로 기다리는 관문·시작하지 못한 단계를 보고한다.

`run_until`은 `opt.max_parallel <= 1`이면 지금의 순차 훑기를 그대로 돌고, 그보다 크면 `run_waves`를 부른다. 두 방식의 최종 상태는 같아야 한다(§11).

**`RunOptions`에 더하는 칸.** `max_parallel: int = 1`, `web: bool = False`(워크숍 실행), `confirmed: set[str]`(사람이 실행을 확인한 단계, 반복 상한을 한 번 넘기는 허락도 같은 칸으로 받는다). **`RunLog`에 더하는 칸.** `held: list[str]`(실행 확인 대기), `waves: list[list[str]]`(물결마다 동시에 시작한 단계), `timings: dict[str, dict[str, str]]`(단계별 `start`·`end`, UTC ISO).

**훅.** `_run_one`은 두 자리에서 다른 갈래의 함수를 부른다. 단계가 `REJECTED`에서 다시 돌기 직전에 `pipeline.rework.prepare_rework(ctx, cid, sid, opt) -> bool`(§6.9)을 부른다. `False`면 단계를 돌리지 않고 `RunLog.blocked`에 "<gate> 반복 상한" 사유로 올린다. 관문이 `AWAITING_HUMAN`이 된 뒤에는 `pipeline.review.review_on_open(ctx, cid, gate) -> Path | None`(§6.8)을 부른다. 이 함수는 예외를 밖으로 내지 않는다. A 갈래는 두 함수를 아무 일도 하지 않는 형태(각각 `True`·`None`를 돌려줌)로 먼저 두고, B·C 갈래가 내용을 채운다. 순차 훑기(`max_parallel = 1`)도 같은 두 자리에서 같은 함수를 부른다.

### 6.7 워크숍 자동 재개와 실행 확인 (D-0049, 명세 §7.1)

`JobManager.submit(character_id, action="run", until=None, *, confirm: list[str] | None = None, trigger: "manual" | "gate" = "manual")`. `Job`에 `trigger`·`confirm`·`held`를 더해 기록과 SSE `job` 이벤트에 싣는다. `_run_default`는 `RunOptions(until, max_parallel=[orchestrator] max_parallel, web=True, confirmed=set(confirm))`로 실행한다.

`JobManager.request_resume(character_id) -> dict | None`. `[orchestrator] auto_resume`가 꺼져 있으면 `None`. 그 캐릭터 작업이 돌고 있으면 `_rerun[character_id] = True`만 남기고 `None`. 아니면 `submit(character_id, until=resume_until, trigger="gate")`. 작업이 끝나 캐릭터 잠금을 놓은 뒤 표시가 있으면 지우고 같은 방식으로 한 번 더 넣는다. 작업 목록은 `(createdAt, 만든 순서)`로 정렬해 같은 초에 만든 작업도 순서가 맞다. 물결 실행의 작업 스레드는 `RunOptions.wrap_worker`로 감싸 작업 로그에 출력이 모인다. `POST .../gates/{gate}/decision`은 결정을 기록한 뒤 `request_resume`을 부르고, 응답에 `resumeJob`(넣은 작업 또는 `null`)을 싣는다.

**유료 단계.** `STAGE_PROVIDERS`(`pipeline/scheduler.py`)는 단계가 쓰는 공급자 종류다. s1 `{text, image}`, s2 `{image, vision}`, s3·s3r·s7·s9s·s9 `{text}`, s4a·s4b `{text, image}`, s4 `{image}`, s5·s6 `{video, image}`, s8·s10 `{text, judge}`, s10t `{tuning}`, s11·sx는 없음. `paid_stage(ctx, sid) -> bool`은 그 가운데 `adapter != "fake"`이고 공급자 표의 `paid = true`인 것이 있으면 참이다. 워크숍 실행(`opt.web`)에서 `paid_stage`이고 `sid not in opt.confirmed`면 단계를 돌리지 않고 `RunLog.held`에 넣는다. `GET /api/characters/{id}`는 마지막 작업의 `held`와, held 단계마다 그 단계가 쓰는 유료 공급자(`paid_providers`, "종류: 어댑터/모델")를 `held[]: {stage, providers}`로 싣는다. 정확한 호출 수·비용은 그 단계 명령의 dry run이 낸다. 화면의 "실행" 버튼은 `POST /api/jobs {characterId, action: "run", until: "sx", confirm: [stage]}`를 보낸다.

### 6.8 관문 사전 검토 (D-0049, 명세 §7.2)

`pipeline/review.py`: `NO_REVIEW_GATES = {"G7a", "G8"}`, `REVIEWERS: dict[str, ReviewSpec]`(관문별 모드·입력 조립 함수·프롬프트 파일 `prompts/review/<gate>.md`), `review_gate(ctx, cid, gate) -> Path | None`, `review_on_open(ctx, cid, gate) -> Path | None`, `load_review(char_dir: Path, gate: str, rev: str) -> GateReview | None`, `plan_review_calls(ctx, cid, gate) -> list[CallPlan]`.

- 입력 조립: 후보 목록과 파일은 `web/gate_items.py`의 `build_gate_items`가 화면에 내는 항목을 그대로 쓴다. 그래야 `candidateId`가 화면과 같다. 텍스트 관문은 항목 본문(JSON 칸)을, 비전 관문은 이미지 파일을, 영상 관문은 첫 프레임 이미지와 메타데이터를 넣는다. 사람 이름·순위 목록 이름은 넣지 않는다(FR-35).
- 호출: 텍스트는 `ctx.judge_model`(생성 계열과 같으면 지금 규칙대로 막음), 비전은 `ctx.vision_model`(`vision_family_warning`가 비어 있지 않으면 막음)로 관문 하나, 챕터가 있으면 챕터 하나당 한 번이다. G9는 `release` 검사 결과를 요약하는 결정적 검토다.
- 검증: 답에서 JSON을 뽑아(`extract_json_object`) `candidateId`가 보여 준 항목 안에 있는지, 고르기 관문이면 단위마다 `rank` 1이 하나인지 본다. 실패하면 사유를 붙여 한 번 더 부르고, 그래도 실패하면 기록을 쓰지 않는다.
- `review_on_open`: `[review] enabled`와 `gates`를 보고, 비전 관문이면 `[review] vision`도 본다. `ctx.execute`가 아니면 돌지 않는다. 예외는 잡아서 원장(`kind=REVIEW`, `ok=false`)에 남기고 `None`.
- 관문 기록: `write_gate_record`가 `load_review(char_dir, gate, rev)`로 검토를 찾으면 `reviewRef`를 채운다. `followedReview`는 고르기 관문에서 단위마다 `rank` 1인 `candidateId`가 모두 `selections`에 들어 있으면 참, 하나라도 빠지면 거짓, 검토가 없거나 승인 관문이면 비운다.
- 화면: `reads.gate_view`가 `review`(현재 관문 rev와 같은 것만)를 돌려준다. 관문 화면은 후보 카드에 "추천"·"걸리는 점" 표시와 근거 한두 줄을 붙이고, 검토가 없으면 "검토 없음"을 쓴다. G7a·G8 화면은 바꾸지 않는다. 구현 메모: G7 기록은 `s9_data/approve.py`가 직접 쓰므로 그 경로에서도 `review_fields`로 검토 참조를 채운다. `cfp review --execute`는 사람이 직접 부른 명령이라 `[review] enabled`·`gates`를 건너뛰지만 이미지 관문은 `vision = true`를 계속 요구한다. G4b 자세 후보는 그린 이미지가 없어 챕터 배경 사진과 자세 글을 함께 넣는다. `review_on_open`은 관문이 `AWAITING_HUMAN`일 때만 돈다.

### 6.9 수정 요청 재작업 (D-0049, 명세 §7.3)

`pipeline/rework.py`: `REWORK_GATES = {"G1", "G4a", "G4b", "G4", "G5", "G5b", "G6"}`, `prepare_rework(ctx, cid, sid, opt) -> bool`, `load_rework(ctx, cid, gate) -> ReworkBrief | None`, `rework_rounds(char_dir, gate) -> int`.

- `prepare_rework`: 단계의 관문이 `REWORK_GATES`에 있고 그 관문의 마지막 기록이 `REQUEST_CHANGES`일 때만 일한다(아니면 `True`). `round > max_rounds`이고 `sid not in opt.confirmed`면 `False`. 아니면 `rework-brief-v1`을 쓰고(이미 있으면 그대로) `True`.
- `load_rework`: 관문 상태의 `rev`(거절된 rev)와 `fromRev`가 같은 브리프를 돌려준다. 단계 실행 함수가 시작할 때 부른다.
- 단계별 부분 재생성: s4a·s4b는 `targets[].field`가 챕터 ID(`ch1`~`ch3`)이고 그 챕터만 다시 만들며, 다른 챕터의 후보 파일은 직전 rev에서 바이트 그대로 복사한다. s5는 소개 영상 후보 전체를 다시 만들되 메모를 영상 지시에 붙인다. s8은 프롬프트 쌍을 다시 만들되 메모를 Prompter 입력에 붙인다. 이미 메모를 읽는 G1(`cfp ref faces` 경로)·G4·G5b는 지금 동작을 유지하고 반복 상한만 같이 쓴다. 실행기는 G1이 `REQUEST_CHANGES`면 s1 실행 함수로 `run_faces`를 쓴다(`--ranking`이 없어도).
- 관문 페이지·답 검사: G4a·G4b는 `REQUEST_CHANGES`에 `requestedChanges[{field: chN, note}]`를 받는다(중복 없는 챕터, 빈 메모 거절). 워크숍 관문 화면은 수정 차수("수정 2/3")와 상한 도달을 보여 준다. 구현 메모: G1·G5·G6 화면은 메모를 `reasons`에 담으므로 `requestedChanges`가 비었으면 `reasons` 원문을 대상 하나로 담는다. G4a·G4b는 옛 형식(`reasons`만 있는 수정 요청)도 받고 그때는 세 챕터를 모두 다시 만든다. 워크숍 G4a·G4b 화면은 챕터별 메모 칸으로 `requestedChanges`를 보낸다. 단계 출력 계약이 세 챕터를 요구해 에이전트는 세 챕터를 다 내지만, 대상이 아닌 챕터의 후보·배경 사진은 직전 rev 파일을 그대로 옮긴다. s5 재작업은 첫 프레임도 새로 만든다. `capReached`는 `round >= max_rounds`(다음 수정 요청이 상한을 넘는 상태)이고, 막는 것은 `round > max_rounds`일 때다.

### 6.10 대기열과 사람 시간 보고서 (D-0049, 명세 §7.4)

`pipeline/queue.py`: `QueueItem(gate, stage, rev, openedAt, unblocks: int, unblockedStages: list[str])`, `downstream_stages(gate: str) -> list[str]`, `gate_queue(char_dir: Path, state: State) -> list[QueueItem]`.

- `downstream_stages`: `STAGES`의 `deps`(관문 → 단계)와 `needs`·`after`(단계 → 단계), 단계의 `gate`(단계 → 관문)를 따라 닿는 단계를 `STAGES` 순서로 돌려준다.
- `gate_queue`: `AWAITING_HUMAN` 관문마다 아직 `APPROVED`·`SKIPPED`가 아닌 뒤쪽 단계 수를 `unblocks`로 센다. `unblocks` 내림차순, 같으면 `openedAt`(원장 관문 사건, 없으면 단계 `updatedAt`) 오름차순, 그다음 `GATES` 순서로 정렬한다. `rev`·`openedAt`은 비어 있을 수 있다. 같은 rev가 여러 번 열렸으면 가장 이른 `opened`, 결정이 여러 번이면 가장 늦은 `decided`를 쓴다. 뒤쪽 단계 계산은 실행 함수가 직접 확인하는 선행(외모 축 s3 ← s2)도 따른다.
- 화면: `reads.character_detail`와 `list_projects`의 캐릭터 항목에 `queue`를 싣고, 작업실·운영 화면의 대기 관문 목록을 이 순서로 그린다. `held`(§6.7)를 "실행 확인 대기" 칩과 "실행" 버튼으로 그린다.
- `pipeline/hil_report.py`의 `build_hil_report(char_dir: Path) -> HilReport`와 `cfp report hil`. 대기 시간은 `decided.at - opened.at`(분)이다.

## 7. 에이전트 러너 (명세 §4)

구현(D-0014): 백엔드는 둘이다. `[agent] backend = "codex_exec"`이면 아래 codex 경로, 아니면 API 경로(한 번 호출·러너 재시도)다. codex 경로의 작업 공간은 `AGENTS.md`(역할 프롬프트 + `prompts/common-procedure.md` + 입력 목록 + 계약 이름), `inputs/`, `contract-example.json`, `check.sh`(현재 venv의 python으로 `character_factory_poc.checks.cli <stage> .` 실행)로 이루어진다. 실행은 `codex exec --json --skip-git-repo-check -m <model> -s workspace-write -C <workspace> -c model_reasoning_effort=... [-c mcp_servers={}]`이다. 이벤트에서 `command_execution` 명령·`agent_message`·`turn.completed` 사용량을 모으고, 명령 문자열의 절대 경로·`~`·`../`가 작업 공간 밖이면 `TaintedOutputError`다. 러너는 실행 뒤 `character_factory_poc.checks.registry.run_checks`로 다시 검사하고, 실패하면 사유를 프롬프트에 붙여 같은 작업 공간에서 재실행한다(최대 `max_check_retries`). 단계별 검사 묶음은 `checks/registry.py`가 작업 공간 inputs에서 재구성하므로 에이전트와 러너가 같은 검사를 쓴다.

```python
@dataclass(frozen=True)
class AgentSpec:
    role: str                 # prompts/<role>.md
    output_contract: str      # 계약 이름
    tools: frozenset[str]     # {"read_workspace", "write_workspace", "vision", "image", "video"}
    max_format_retries: int = 2
    max_check_retries: int = 3

def run_agent(spec, workspace, inputs, checks, provider) -> AgentResult
```

1. `workspace/`에 `inputs/`(입력 사본), `role.md`, `contract.json`(예시 포함)을 둔다.
2. 모델 호출 메시지는 `role.md` + 입력 목록 + 계약 + 이전 실패 사유다. 응답에서 코드 펜스를 벗기고 첫 JSON 객체를 파싱한다.
3. `schema.validate(contract, obj)` 실패 → 사유를 붙여 재호출. `max_format_retries` 초과 → `AgentFormatError`.
4. `checks` 각각을 돌린다. 실패 목록이 비면 통과. 아니면 사유를 붙여 재호출. `max_check_retries` 초과 → `CHECK_FAILED`로 반환하고 마지막 출력을 `workspace/last-failed.json`에 남긴다.
5. 모든 호출은 원장에 `stage`·`kind=AGENT`로 기록한다.

`codex_exec` 어댑터는 `codex exec --json -C <workspace> --sandbox read-only`로 실행하고 이벤트에서 파일 접근 경로를 모아 작업 공간 밖 경로가 있으면 `TaintedOutputError`를 낸다. 쓰기는 어댑터가 받은 최종 JSON을 러너가 대신 저장한다.

## 8. 단계별 알고리즘

### 8.1 S1 레퍼런스 (명세 §8)

구현: `stages/s1_reference/`, 진입점 `run.run_s1(ctx, cid, ranking)`. 단계 상태는 `s1`, rev는 `rf<k>`, 관문은 G1이다(D-0018).

**ranking.** `popularity-ranking-v2`를 검증해 `ranking.json`으로 고정한다. 이름은 공백 제거·casefold로 정규화해 목록 사이에서 같은 사람을 묶고 `people.json`을 쓴다. 백분위는 `(listSize - rank + 1) / listSize`(1위 = 1.0)이고, `listSize < min_list_size_for_percentile`이면 null(정규화 불가)이다.

**features.** Scout 에이전트(`prompts/scout.md`, 계약 `appearance-features-v1`)에 `people`(personId·이름·분류만), 어휘, 비교 범위를 준다. 검사(`check.py`, 에이전트의 `./check.sh`와 러너가 같은 함수를 쓴다): 모든 personId가 한 번씩 있다, 값이 어휘 안에 있다, 복수값은 3개 이하다, `recognized=true`면 단일값 4개 이상이 `unknown`이 아니고 복수값이 각각 1개 이상이다, 확신도 키가 필드 이름이다, `note`·`notes`에 이름이 없다.

**cluster.** `recognized=false`인 인물은 `excludedPeople`로 뺀다. 나머지를 필드·어휘 값별 차원의 벡터로 만들고 값에 그 필드의 확신도(없으면 1.0)를 넣는다. 거리는 코사인 거리(영벡터는 1.0)다. 각 인물을 한 군집으로 시작해 평균 연결 거리가 가장 작은 쌍을 `cluster_k`개가 될 때까지 합친다. 거리가 같으면 구성원 ID를 정렬한 튜플이 작은 쌍을 먼저 합쳐 결과를 결정적으로 만든다. 공통 특징은 단일값이면 구성원 전체의 과반이 가진 값(`unknown`은 어느 값에도 세지 않는다), 복수값이면 구성원 과반이 가진 값들이다. 구성원이 `min_members_per_cluster` 미만이거나 공통 특징 필드가 `min_common_fields` 미만인 군집은 `dropped`로 보낸다(D-0017).

**report.** 후보를 (목록 수 내림차순, 백분위 중앙값 내림차순(null은 뒤), 구성원 수 내림차순, 첫 구성원 ID) 순으로 정렬하고 `c1`부터 ID를 붙인다. `rationale`은 목록 수·중앙값·구성원 수를 문장으로 적는다. 목록 하나에서만 나온 후보와 정규화 불가 구성원은 `limitations`에 적는다. 이전 rev(`rf<k-1>`)의 보고서가 있으면 두 실행에 모두 군집된 인물로 Adjusted Rand Index를 계산한다(dropped 군집도 하나의 군집으로 센다).

**leak.** 순위 목록의 이름을 공백·문장부호 제거, casefold로 정규화하고, 검사할 텍스트도 같은 방식으로 정규화해 부분 문자열을 찾는다. 두 글자 미만 이름은 검사하지 않는다. 보고서·미리보기 프롬프트·`previews.json`이 대상이고, 미리보기 프롬프트는 이미지 호출 전에 검사한다.

**preview.** 후보마다(외모군마다 얼굴, D-0043) 공통 특징의 영어 구절과 비교 범위(성별·연령대·그림체·인물 인상)로 고정 템플릿 프롬프트를 만들고 `variation n/N` 문구만 바꿔 `previews_per_cluster`장을 `ImageGen`으로 만든다. 주어는 인물 인상과 성별을 합친 것이다(`korean` → "fictional Korean woman", `east-asian` → "fictional East Asian woman", `unspecified` → "fictional woman"). 네거티브 프롬프트는 "text, watermark, logo"다. "celebrity likeness"를 넣으면 인물 인상과 함께 쓰일 때 안전 시스템이 생성을 막았으므로 넣지 않는다(D-0020).

**page.** `gate-G1.html`은 외모군마다 얼굴, 공통 특징(한국어), 근거·한계, 구성원 이름과 순위(사람 검토용)를 보여 주고, 정렬 1위 외모군에 추천 표시를 붙인다. 얼굴 하나를 고르는 라디오와 고칠 점 메모 칸이 있고, 선택을 `SELECT` 또는 `REQUEST_CHANGES` 답 JSON으로 복사하게 한다(D-0042, D-0043). 네트워크 요청은 없다.

**approve.** `SELECT`는 얼굴 한 장(`referencePreviews`)과 그 외모군(`selections`, 비우면 얼굴에서 채움)을 받아야 하고, 얼굴이 없거나 두 장 이상이거나 다른 외모군의 얼굴이면 거절한다. `--auto-approve G1`은 정렬 1위 외모군의 첫 얼굴을 `SELECT`로 기록한다. `selected_cluster(ctx, cid)`가 승인된 외모군(이름 없음)을, `selected_references(ctx, cid)`가 고른 얼굴 한 장을 S2에 돌려준다. `s2`가 `APPROVED` 전이면 G1을 다시 받을 수 있다.

**faces(다시 만들기, D-0043).** `REQUEST_CHANGES` 기록의 `note`를 받아 새 `rf<k>`를 만든다. `ranking.json`·`people.json`·`features.json`·`report.json`는 직전 rf에서 바이트 그대로 복사하고(`settings.carriedFrom`), 미리보기 프롬프트 끝에 `Revision note: <메모>`를 붙여 얼굴만 다시 만든다. 메모도 이미지 호출 전에 이름 유출 검사를 한다.

구현 메모(2026-10-27, M8 1차, D-0042·D-0043·D-0046): G1 페이지는 외모군마다 얼굴 라디오(`name="face"`)·추천 표시·고칠 점 메모 칸을 보여 준다. `SELECT`는 `referencePreviews` 정확히 한 장이고 외모군은 그 얼굴에서 정한다(`selections` 생략 가능, 기록은 `[외모군, 얼굴]`). `REQUEST_CHANGES`는 `note`가 필수다. `cfp ref faces`는 새 `rf<k>`에 순위·인물·특징·보고서를 바이트 그대로 복사하고 `carried-from.json`(`fromRev`, 파일별 sha256, 메모)을 쓴다(보고서를 고칠 수 없으므로 `settings.carriedFrom` 대신). 순위 목록 입수는 `cfp ref collect` → `runs/rankings/<시각>-<출처>/ranking.json` + `collection-record.json` → `cfp ref run --ranking`이다. 목록 `gender`가 캐릭터 성별과 같을 때만 쓰고, 혼성 목록(배우)은 `characterGender = any`에서만 쓴다. 계약에 항목별 출처 칸이 없어 `listId`와 수집 기록으로 근거를 되짚는다. 수집 목록은 분류당 10명이라 기본 군집 설정(`cluster_k = 4`, `min_members_per_cluster = 3`)과 맞지 않는다(K-0035).

### 8.2 S2 기준 사진 (D-0042, D-0043)

구현: `stages/s2_hero/`, 진입점 `run.run_s2(ctx, cid)`. 단계 상태 `s2`, rev `ar<k>`, 사람 관문 없음. 지금 코드는 아직 옛 흐름(후보 4장 → G2)이다(K-0034).

**inputs.** G1 기록에서 외모군(`selected_cluster`)과 고른 얼굴 한 장(`selected_references`)을 읽고, 얼굴을 `references/<previewId>.png`로 복사해 `hero-inputs-v1`을 고정한다(`basePhoto` 포함). 순위 목록의 이름은 `s1-reference/rf<k>/ranking.json`에서 읽어 유출 검사에만 쓴다.

**picked.** `base_photo = "picked"`면 이미지·판정 호출 없이 G1 얼굴을 `referenceImage`로 삼아 `appearance-spec.json`(`identityCheck.status = SKIPPED`)과 manifest를 쓰고 `s2`를 `APPROVED`로 둔다.

**prompt.** `build_hero_prompt`는 "Reference portrait photograph of a fictional <인물 인상+성별> in their <연령대>, <그림체> style."로 시작하고, 사진형 촬영 조건(4분의 3 각도, 창가 방향광, 모공이 보이는 피부, 85mm f/2), 같은 얼굴·머리색·머리 모양을 유지하라는 문장, 손을 얼굴에서 떼고 턱을 괴지 않는다는 문장(D-0027), "An original person, not based on any real individual."을 붙인다. 외형(단일값) 태그는 빼고 스타일링·분위기만 넣는다. 외형 태그를 같이 주면 모델이 글을 따라 머리를 바꿨다(2026-10-21 실제 호출). `Variation n of N`은 쓰지 않는다. 피할 것은 "text, watermark, logo, blur, plastic skin, hand on face, chin resting on hand"다.

**generate.** 먼저 `ensure_judge`로 판정 공급자를 확인한다. 이미지 공급자가 실제인데 판정 공급자가 없거나 `[stages.image_qa] enabled = false`면 아무것도 쓰기 전에 `CheckFailed`이고, 메시지에 `base_photo = "picked"`를 안내한다. 프롬프트의 이름 유출을 검사한 뒤 `image_qa.generate_checked`로 한 장을 만든다. 기준표는 `identity-v1` = same_identity, hair_kept, hands_off_face, single_person_no_text다. 판정 요청 이미지는 `("candidate image", 시도 파일)`, `("identity reference (G1 face)", G1 얼굴)` 순서다. 수정은 `fix_mode` 설정과 상관없이 `regenerate`다(G1 얼굴을 참조로 원래 요청 끝에 "Fix: …"만 붙인다). 시도는 최대 `1 + max_fix_rounds`(기본 3)번이다.

**고정.** 통과하면 통과한 시도를 `candidates/h1.png`로 복사하고 `candidates.json`, `appearance-spec.json`(설명은 어휘의 한국어·영어 표기를 이어 붙인다. 금지 요소 기본값은 문자·워터마크·로고와 "실존 인물의 이름이나 사진을 생성 지시로 쓰지 않는다(D-0017)"), `manifest.sha256`을 쓰고 `s2`를 `APPROVED`로 둔다. 관문 기록은 만들지 않는다. 끝까지 통과하지 못하면 D-0037 (4)와 달리 가장 나은 시도를 넘기지 않는다. `s2`는 `CHECK_FAILED`이고 `lastError`에 FAIL 항목과 `qa/` 보고서 경로를 적는다. 외모 명세는 쓰지 않는다. 다시 실행(`cfp hero run`)은 새 `ar<k>`를 만든다. 이미지 실패·이름 유출도 `CHECK_FAILED`다.

**워크숍 화면 연결.** 시안(`d-ops.html`)은 S2를 결재가 아닌 자동 작업으로 보이고, 시도마다 실패·자동 재시도를 작업 기록에 남기며, 최종 실패는 "사람 확인 필요" 문제로 다시 실행·G1 얼굴 그대로 쓰기(`picked`)를 제시한다. 연결층은 `qa/` 보고서와 `state.json`의 `s2` 상태를 그대로 읽는다.

구현 메모(2026-10-27, M8 1차): `base_photo = "picked"`를 구현했다. G1 얼굴을 기준 이미지로 복사하고(이미지·판정 호출 0회) `appearance-spec-v1`에 `basePhoto: picked`, `identityCheck: {status: SKIPPED, attempts: 0}`을 쓰며 `s2`는 바로 `APPROVED`다. `hero-candidate`는 만들지 않는다. `generate`는 아무것도 쓰기 전에 K-0034와 `picked` 안내로 거절한다(D-0045 (5)). 문서상 기본값은 `generate`이므로 PoC 설정은 `picked`를 명시한다. `load_appearance_spec`은 `s2` 승인을 읽고, G2 기록만 있는 옛 상태는 읽기 전용으로 받아 준다. `s2` 승인 뒤 G1 얼굴을 바꾸는 것은 막고 S1을 새 rev로 다시 돌리게 한다.

### 8.3 S3 기획

**import.** v2 JSON을 `character-plan-v2`로 검증한다. evidence가 없는 편집 칸은 `{kind: USER}`로 채우고, 기획서의 성격·직업·나이·성별·배경으로 씨앗을 먼저 고정해 `seedRev`를 단다. 구형 v1 JSON은 `own.run_s3_own`으로 넘겨 신형 후보를 만든다(D-0080).

**브리프(D-0080).** 구형 Planner 초안은 지웠다. `seed.seed_fields_from_brief`가 브리프를 씨앗으로 옮기고 `variants.run_s3_from_brief`가 변형 경로를 부른다. 승인본 읽기(`load_approved_plan`)와 S3r·S4·S7의 v1 읽기는 과거 기록을 위해 남긴다. 시험의 과거 v1 기록은 `tests/support/legacy.py`가 깐다.

**씨앗(D-0033).** `stages/s3_plan/seed.py`의 `write_seed`가 `plan-seed-v1`을 `s3-plan/seeds/sd<k>.json`으로 고정한다. 성별이 비면 외모 명세 비교 범위의 성별(female·male)로 채운다. `load_latest_seed`가 가장 최근 씨앗을 읽는다.

**변형(D-0033, D-0034).** `variants.run_s3_variants(ctx, cid)`, rev `pr<k>`, 관문 G3. 씨앗(없으면 `NeedsInputError`)이 필요하다. 외모 축을 시작한 캐릭터는 `s2` 승인이 필요하고(없으면 `GateNotApprovedError`), S1을 시작하지 않은 페르소나 우선 캐릭터는 외모 없이 돈다(D-0080). Planner(`plan_variants`, 단계 표지 `s3-variants`)가 씨앗·외모 요약(D-0024의 사용 제한 문구 포함)·챕터 자리·프로필 카드 칸으로 `variants`(확정 3)안을 낸다. 코드가 ID·rev·씨앗 rev·변형 ID와 `chapterArc`의 자리·제목·관계 단계를 고정하므로 에이전트는 `arc` 문장만 쓴다. 검사(`check_v2.py`): 개수, 씨앗 직업 포함·나이·성별 일치, 모든 안이 같은 상황 집합을 쓰고 상황마다 첫 행동이 서로 다름, 성격 칸이 형용사만이 아님, 이름 유출. 결과는 `variants.json`(`plan-variants-v1`)과 `gate-G3.html`(안별 카드, 라디오, 고칠 칸 JSON).

**직접 쓴 안.** `own.run_s3_own(ctx, cid, user_text)`가 Normalizer(`plan_normalizer`, `s3-own`)로 사용자 글을 `u1` 하나로 정리한다. 글의 내용을 지키고 빠진 칸만 채우며, 칸의 근거를 `USER`·`AGENT`로 구분한다. 같은 씨앗 검사와 이름 유출 검사를 거쳐 새 rev에 `variants.json`(mode own)과 `user-text.md`를 쓴다.

**G3(새 흐름).** `approve.approve_g3_variants`: `SELECT`는 후보 하나와 선택적 `edits`(`EDITABLE_FIELDS`만)를 받아 합친 뒤 `character-plan-v2`로 다시 검증하고 `plan.json`·`selection.json`을 쓴다. `APPROVE`(자동 승인)는 첫 후보다. 알 수 없는 칸 수정은 거절한다. `pipeline/approve.py`는 rev에 `variants.json`이 있으면 이 함수로, 없으면 기존 승인으로 보낸다. `load_approved_plan`은 v1·v2를 모두 읽고, S4a 이후는 `load_approved_plan_v2`로 v2만 받는다.

### 8.3a S3r 참고 자료 선별 (D-0033, D-0035)

`stages/s3r_refs/`. **색인:** `index.build_index`가 Stanford 프리셋 카탈로그(항목 `STANFORD:<id>`, 용도 TRAITS·VOICE), chat-svc 페르소나 v6 JSON(항목 `AUTHORED:<revision>:traits`·`:voice`), 일반 JSONL(`{id, text, label?, uses?}`, 출처 SNS14·NIKL·OTHER, 기본 용도 DATA)을 `Embedder`로 벡터화해 `reference-index-v1`을 만든다. 지금 구현된 임베더는 오프라인 `hash-v1`(글자 n-gram 해시, L2 정규화)뿐이고 실제 임베딩 모델은 Q-0019다. 색인 파일은 원문을 담으므로 Git 밖에 둔다. **선별:** `select.run_s3r(ctx, cid)`, rev `rs<k>`, 관문 없음, 의존 G3. `[resources] reference_index`가 없으면 `SKIPPED`로 두고 끝난다. 기획서에서 용도별 질의(TRAITS: 핵심·대비 성격·선택·오해 지점, VOICE: 말투 요약·예시, DATA: 취향·배경)를 만들고 용도가 맞는 항목에서 `top_k`(제안 8)개씩 코사인 유사도로 찾는다. Curator(`curator`, `s3r`)가 후보(항목 ID·출처·라벨·용도·점수·발췌 400자)에서 `max_selected`(제안 8)개 이하를 고르고 이유를 쓴다. 검사: 그 용도의 검색 후보 안에서만, 중복 없음, 개수, 이유. `reference-set.json`에는 질의, 검색 ID와 점수, 고른 항목의 출처·버전·라벨·용도·이유만 남기고 원문은 남기지 않는다. 끝나면 단계는 `APPROVED`다(근거는 G6에서 함께 본다).

### 8.4 S4a 배경 → S4b 장면 사실·자세 → S4 완성 이미지 (명세 §3·§9, D-0033·D-0034)

**S4a 배경 후보.** `stages/s4a_backgrounds/`, 진입점 `run.run_s4a(ctx, cid)`, rev `bg<k>`, 관문 G4a, 그래프 의존 G3와 `s2` 승인. `character-plan-v2`가 아니면 이유와 함께 `CheckFailed`다. Location Scout(`scene_scout`, 단계 표지 `s4a`)가 기획 요약(이름·직업·배경·취향·챕터 흐름)과 비교 범위로 챕터당 `candidates_per_chapter`(확정 3)개를 낸다. 검사: 개수·ID, 챕터 안 장소 중복, `plateBrief`에 사람 단어 금지(`no people`처럼 부정은 허용), 이름 유출. `plates = true`면 후보마다 인물 없는 사진을 `request_size(9:16)`로 요청하고 `crop_to_ratio`로 자른다(`plates/<후보>.png`). 비율이 25% 넘게 벗어나면 `CheckFailed`. G4a 페이지는 챕터마다 배경 사진·칸·라디오·직접 정의 칸을 보이고 `{decision, picks, custom}`을 복사하게 한다. G4a `SELECT`는 챕터마다 picks·custom 가운데 정확히 하나여야 하고 `selection.json`을 쓴다. `APPROVE`(자동 승인)는 챕터마다 b1이다.

**S4b 장면 사실·자세.** `stages/s4b_poses/`, 진입점 `run.run_s4b(ctx, cid)`, rev `ps<k>`, 관문 G4b, 의존 G4a. (1) Scene Writer(`scene_writer`, `s4b-scene`)가 고른 후보 전체와 직접 정의 문장(USER), 챕터 흐름으로 챕터 사실을 쓴다. 검사: 고른 챕터는 후보의 장소를 그대로 두고 `source = CANDIDATE`, 직접 정의 챕터는 `USER`, 2·3챕터의 관계 정본이 비지 않음(앞 챕터를 잇는다), 경계 1개 이상, 배경 사진 묘사에 사람 없음, 이름 유출. 고른 배경 사진은 bg rev에서 복사하고 직접 정의 배경은 새로 만든다. `scene-plan.json`. (2) Pose Director(`pose_director`, `s4b-pose`)가 장면 사실·챕터 관계 단계·몸짓에 필요한 성격 몇 줄로 챕터당 `candidates_per_chapter`(확정 3)개를 낸다. 검사: 개수·ID, `animatable = true`, 손 칸에 얼굴 접촉어(턱·볼·얼굴에·얼굴을·입가·chin·cheek·face·mouth) 금지(D-0027), 의상. G4b 페이지는 배경 사진·챕터 사실(검토용)·자세 카드·직접 정의 칸·세부 수정 칸을 보인다. G4b `SELECT`는 챕터마다 picks·custom 가운데 하나, `tweaks`는 고른 챕터의 자세 칸만 받는다. `selection.json`과 해석된 `pose-plan.json`을 쓴다. `APPROVE`는 챕터마다 p1이다.

**S4 완성 이미지.** `stages/s4_frames/`, 진입점 `run.run_s4(ctx, cid)`, rev `fr<k>`, 관문 G4, 의존 G4b와 `s2` 승인. 기준 이미지를 `reference/`로 복사하고 얼굴 크롭(D-0027, 실패하면 전체 이미지와 `cropNote`)을 만든다. 챕터마다 한 장(확정, D-0034): 참조 두 장(얼굴 크롭 또는 전체, 배경 사진), 프롬프트는 비교 범위의 인물 주어, "참조 1은 얼굴에만", "참조 2는 장소·빛·배치를 그대로", 장면 사실 요약, 자세 칸 또는 직접 정의 문장, 의상, 표정, 손 문장(D-0027)과 자세 비복사 문장, 세로 9:16 구도, "An original person, not based on any real individual." 피할 것에 `chin resting on hand`. `request_size(9:16)` → `crop_to_ratio` → `ch<n>/f1.png`. 프롬프트마다 이름 유출을 먼저 검사한다. **부분 재생성:** 직전 `fr` rev의 G4 기록이 `REQUEST_CHANGES`이고 `requestedChanges.field`가 ch1~ch3이며 장면 rev가 같으면, 그 챕터만 프롬프트 끝에 `Revision note: <메모>`를 붙여 다시 만들고 나머지는 파일과 기록을 바이트 그대로 가져온다(`settings.carriedFrom`). 아니면 전부 다시 만든다. G4 페이지는 세 장과 챕터별 승인·수정 메모 칸을 보이고, 모두 승인이면 `{decision: APPROVE}`, 아니면 `{decision: REQUEST_CHANGES, requestedChanges[{field: ch<n>, note}]}`를 복사하게 한다. `APPROVE`면 `approved-frames.json`(챕터마다 f1)을 쓴다. 호환을 위해 `SELECT`(챕터마다 하나)도 받는다.

### 8.4a 이미지 자동 검사 루프 (명세 §9, D-0036·D-0037)

`stages/image_qa.py`의 `generate_checked`가 이미지 하나를 처리한다. **기준표:** `identity-v1` = same_identity, hair_kept, hands_off_face, single_person_no_text(S2, D-0043). `plate-v1` = no_people, no_text, matches_brief, usable_background. `composite-v1` = same_identity, same_place, pose_match, hands_ok, outfit_match, single_person_no_text. **판정 요청:** `VisionRequest(images=[("candidate image", 시도 파일), 참조...])`. 완성 이미지의 참조는 `identity reference (face|full)`, `background plate` 순서다. 프롬프트는 `<rubric>`(항목 ID와 영어 기준)과 `<context>`(배경 사진: 장소·시간대·분위기·plateBrief, 완성 이미지: 장면 요약·자세 칸 또는 직접 정의 문장·의상·표정)를 담고, 시스템 프롬프트는 `prompts/image_judge.md`다. **수정:** FAIL이 있으면 `fixHint`(없으면 FAIL 이유를 이은 문장)를 다음 시도에 쓴다. `fix_mode = "edit"`면 직전 시도 파일을 참조 이미지 마지막에 붙이고 프롬프트 앞에 "Edit the last attached image. Fix: … Keep everything else the same."를 둔다. `"regenerate"`면 원래 요청 끝에 "Fix: …"만 붙인다. **끝:** 통과한 첫 시도를 쓰고, 없으면 FAIL 수가 가장 적은 시도(같으면 나중 것)를 쓰고 `status = FAIL`이다. 단계 상태는 바꾸지 않는다. 시도 파일은 `attempts/`, 보고서는 `qa/`에 남고 최종 파일은 기존 경로(`plates/<id>.png`, `ch<n>/f1.png`)에 쓴다. **준비 검사(`ensure_judge`):** 이미지 공급자가 실제인데 비전 공급자가 `fake`이고 주입된 판정 모델이 없으면, 또는 이미지 생성과 판정 모델 계열이 같은데 `allow_same_family`가 없으면 아무것도 쓰기 전에 `CheckFailed`다. **호출 계획:** 이미지 N장이면 이미지 호출은 최대 `N × (1 + max_fix_rounds)`회, 비전 호출은 판정 형식 재질의까지 넣어 그 두 배다(배경 사진 9장이면 이미지 27회, 판정 54회). 예산 확인은 이 최대치로 한다. **부분 재생성:** S4에서 가져온 챕터는 자동 검사 요약과 보고서를 그대로 가져온다. **페이지:** G4a·G4b·G4는 이미지마다 "자동 검사 통과 (n회째)" 배지, 또는 빨간 "자동 검사 미통과 — 사람 확인 필요"와 항목 이유, 판단 보류 항목, 보고서 링크를 보인다. **원장:** 판정 호출은 `kind = VISION`.

**S2 예외(D-0043).** S2는 수정 방식이 항상 `regenerate`이고, 끝까지 FAIL이면 호출한 쪽(`run_s2`)이 단계를 `CHECK_FAILED`로 바꾼다.

**보류.** 얼굴 임베딩 유사도와 S1 얼굴 미리보기 검사는 나중에 붙인다(Q-0011).

### 8.5 S5·S6 영상 (S5 구현, S6은 골격)

**S5 구현.** `stages/s5_intro/`, 진입점 `run.run_s5(ctx, cid)`. 단계 `s5`, rev `vi<k>`, 관문 G5, 그래프 의존은 `s2` 승인(D-0028, D-0042). (1) 실행 전 `plan_calls`가 예상 비용을 계산해 예산 상한을 넘으면 거절한다. (2) 첫 프레임(D-0031, `stages/s5_intro/first_frame.py`): 외모 명세의 기준 이미지(기준 사진)를 `hero.png`로 복사하고, `first_frame = "vertical"`(기본)이면 `hero.png`를 참조로 붙여 이미지 모델에 세로 첫 프레임 1장을 요청한다(크기 힌트 `1024x1536`, 고정 프롬프트: 같은 얼굴·머리·옷·배경·빛, 허리 위 미디엄 샷, 눈높이 위 1/3, 손은 내려 얼굴에서 뗌; 피할 것 문자·워터마크·로고·얼굴에 손·턱 괴기). 원본은 `first-frame-raw.png`로 두고, 가운데 기준으로 목표 비율의 가장 큰 상자를 잘라 `first-frame.png`를 쓴다. 생성 결과 비율이 목표에서 25%를 넘게 벗어나면(예: 정사각형) 자르지 않고 `CHECK_FAILED`로 멈춘다. `"hero"`면 대표 이미지를 그대로 쓴다. 얼굴 크롭은 쓰지 않는다(첫 프레임이 곧 첫 장면이므로). 재개할 때는 `inputs.json`이 있으면 첫 프레임을 다시 만들지 않는다. (3) 움직임 프롬프트는 고정 템플릿이다: 첫 프레임에서 시작하는 고개 돌림·미소·머리카락·눈 깜빡임, 고정 카메라 또는 아주 느린 푸시인, 같은 사람·옷·배경 유지, 손은 얼굴에서 떨어짐, 문자·로고·다른 사람 없음. (4) 후보마다 `submit` 직후 `jobs/v<n>.json`(SUBMITTED, 작업 ID)을 먼저 쓰고 `collect`로 받는다. MP4 시그니처(4~8바이트 `ftyp`)를 확인하고 `videos/v<n>.mp4`, `assets/v<n>.json`을 쓴다. ffprobe가 있으면 길이·해상도를 잰다. (5) 시간 초과(`VideoTimeoutError`)면 작업을 SUBMITTED로 두고 단계 `CHECK_FAILED`. 다음 실행은 같은 rev에서 받은 영상은 건너뛰고, 재개할 수 있는 공급자(`xai_video`)는 같은 작업 ID로 다시 수집하며, 재개할 수 없는 공급자(`grok_web`)는 다시 제출한다. 그 밖의 실패는 FAILED와 사유를 남긴다. (6) `videos.json`, `gate-G5.html`(대표 이미지와 첫 프레임을 나란히 보이고 `<video>` 재생), manifest. G5 SELECT면 `approved-intro.json`. 자동 영상 검사(`video-qa`)는 보류한다.

**S6 골격(L1, D-0038·D-0040·D-0041).** `stages/s6_actions/`, 진입점 `run.run_s6(ctx, cid)`, rev `va<k>`, 관문 G5b, 그래프 의존 G4. (1) 카탈로그는 `app_clips.py`의 앱 표준 37편 사본이다(api-svc 캐릭터 9 · 2단계 · e51 세트의 `clip_key`·제목·설명·사용 조건·움직임 지시문). `s6_config`가 `preset`(`l2` = idle_good, idle_bad, glad_good, amused_good, shy_good, sorry_good / `standard` = 37편)이나 `actions` 목록, 길이(대기 15초·감정 10초·특별 6초), 후보 수를 검사하고 틀리면 호출·파일 쓰기 전에 `CHECK_FAILED`. `plan_calls`로 예산을 먼저 확인한다. (2) `load_approved_frames`로 G4 승인 이미지 세 장을 `first-frames/ch<N>-good.png`로 복사해 미소 출발 첫 프레임으로 고정한다. 무표정 출발(`_bad`) 동작이 있는 챕터는 그 사진을 참조로 붙여 이미지 모델에 "같은 사진에서 표정만 차분한 무표정으로"를 요청하고(원본 `-bad-raw.png`), 목표 비율로 잘라 `ch<N>-bad.png`를 쓴다. 앱도 미소·무표정 참조 사진 두 장을 쓴다. (3) 프롬프트는 앱 움직임 지시문 그대로 + 챕터 관계 단계 메모(ch1 조심스럽고 작게, ch2 설렘이 비치게, ch3 가깝고 편하게) + 같은 사람·옷·배경 유지, 문자·로고·다른 사람 없음. 앱 지시문은 이미 시작 표정으로 돌아와 끝나라는 문장을 담고 있다. (4) 동작·후보마다 S5와 같은 순서로 제출 → `jobs/<actionId>-v<n>.json` → 수집 → MP4 시그니처 → `videos/`·`assets/` → 실측. 무표정 출발 영상은 무표정 첫 프레임에서 시작한다. 재개 규칙도 S5와 같다. (5) **동작별 부분 재생성:** 직전 `va` rev의 G5b 기록이 `REQUEST_CHANGES`이고 G4 프레임 rev와 동작 목록·설정·길이가 같으면, 요청한 동작만 프롬프트 끝에 `Reviewer note: <메모>`를 붙여 다시 만들고 나머지 영상·자산과 첫 프레임(무표정 사진 포함)은 그대로 복사한다(`reusedFrom`). 아니면 전부 다시 만든다. (6) `clips.json`, `gate-G5b.html`(챕터별 미소·무표정 첫 프레임, 동작별 제목·`clip_key`·출발 표정·길이·사용 조건과 `<video>`, 선택·제외·수정 메모 칸, 답 JSON 복사), manifest. G5b SELECT면 `approved-actions.json`(앱 단계·`clip_key` 포함). (7) 특별 행동(챕터마다 장면 소품을 쓰는 애교·터치 3~5편)은 다음 단계에서 에이전트가 G4b 장면 사실·소품을 읽어 제안하게 한다. 이번 골격은 계약 칸만 있다. 영상 자동 검사는 넣지 않는다.

**S6 영상 자동 검사(R1, 보류).** `jobs`는 입력 이미지·프롬프트·사양으로 VideoGen에 제출하고 `providerJobId`를 기록한다. `collect`는 상태를 폴링해 파일을 받고 `video-asset-v1`을 쓴다. `qa`는 `ffmpeg`로 시작·중간·끝과 2초(제안) 간격 프레임을 뽑아 `vision_judge`에 보내고, 손 항목과 루프 이음새(첫·끝 프레임 유사도) 판정을 추가한다. 실패는 사유를 붙여 재제출하며 횟수를 센다.

### 8.6 S7 특질 시트

Profiler는 기획서, 기준 문서 발췌(5항목 설명, 카드 7요소 설명), 사용자가 지정한 참조 유형 카드를 받는다. `check`는 템플릿의 필수 칸, 각 칸의 최소 길이, "형용사 나열" 패턴(명사·형용사만 있고 동사·조건이 없는 칸), `switchConditions` 1개 이상, `references`의 버전 기록을 확인한다. 대응표(Q-0005)가 없으면 14유형과 프리셋을 함께 참조해도 서로 대응한다고 쓰지 않는다.

### 8.7 S8 프롬프트

모티브는 모델 덱 사용 여부와 관계없이 providers.text를 한 번 호출한다(로컬 비교의 편집 모델을 사용할 수 있다)(명세 §10.2, D-0163). assembler-input.json에 입력을, assembly.json에 frame·검증한 ids(1~3개)·응답 모델을 기록한다. G0 비교 세트·표시된 개인정보 메시지를 예시로 쓰지 않는다. 긴 본문과 호환용 짧은 사본은 같다. 스튜디오는 V3 본문을 그대로 사용하고 공개 내보내기에서는 원문 예시 칸을 제거한다.

선택 설정 `[stages.s8] scene_traits=true`(D-0170, 명세 §10.2)는 G0 생성용 원문에서 연속한 상대 발화와 본인 답을 한 쌍으로 복원한다. 같은 사람이 연달아 보낸 메시지는 묶고, 개인정보 표시·제3자·시간 공백을 건너뛰지 않는다. 원문 파일이 여러 개면 파일 단위, 하나면 대화 단위로 발견·대조 묶음을 나눈다. 각 묶음 최대 160쌍이며 대화별로 고르게 뽑는다.
발견 모델은 단서·관심 대상·대응·적용 범위를 쓰고 원문 쌍과 양쪽 문장 번호를 고른다. 서로 다른 두 대화에서 관찰된 후보는 다른 계열 모델에 넘겨 별도 자료에서 지지와 반례를 찾는다. 양쪽에 서로 다른 주제(기타 제외)가 있고 독립 대조에서 지지 대화 수가 반례 대화 수보다 많을 때만 V3에 넘긴다. 무엇이 반복됐고 어떤 근거로 제외됐는지는 내부 response-traits.json에 남긴다. 결과는 개인 고유성 판정이나 관측 빈도 추정이 아니다. 기본 설정은 꺼짐이다. 이전 네 말차례 실험은 D-0169 검증 기록을 참고한다.

`trait_method="contrast"`(D-0171)는 같은 상황의 두 반응과 상대 말에서 관찰 가능한 구분 단서를 발견한다. 다른 파일 또는 대화 묶음 전체의 상대 발화에서 갈래별 발견 예와 비슷한 장면 및 고정 표본을 섞어 최대 128쌍을 고른다. 첫 예측에는 실제 답이 없고, 별도 판정 모델에는 예측 라벨과 단서가 없다. 각 갈래 절반 초과 일치, 양쪽 지지, 둘 이상의 검토 대화 및 최소 한 갈래의 주제 이동이 있어야 한다. 고른 장면에만 해당하며 사람 식별 점수가 아니다. 최대 모델 호출은 조립 별도 3회이고, 기각 기록은 revision 안에만 남는다. 기존 scene_traits=true의 trait_method 기본값은 focus다.

선택 설정 `[stages.s8] example_turns = N`(D-0173, 명세 §10.2, 기본 0)은 조립 뒤 같은 revision에 example-turns.json을 남긴다. 모델을 부르지 않는다. 승인된 생성용 원문에서 같은 사람의 연속 메시지를 한 말차례로 묶고, 개인정보 표시·제3자 발화·링크·사진 표기·30분 넘는 공백을 건너뛰지 않고 이어진 "상대 말차례 → 본인 말차례"만 후보로 삼는다(상대 250자, 본인 450자 이하, 같은 답 중복 제거). 원문이 전부 카톡이 아니면 본인 답 길이의 하위 75% 안에서만 뽑는다. 출처(textId)가 하나면 무작위로, 여럿이면 출처마다 돌아가며 N개를 뽑는다. 시드는 캐릭터 ID와 원문 revision의 해시다. 파일에는 뽑은 문답(msgId·user·reply), 길이 제한, 그리고 system(조립 지시문의 첫 문단 + 연결 문장 + 사실표)을 적는다. 대화 테스트와 G6 표본 대화(common/demo_chat.py의 Scene.opening)는 최신 프롬프트 revision에 이 파일이 있고 turns가 비어 있지 않으면 system을 시스템 프롬프트로 쓰고 문답을 이전 턴으로 넣는다. 없으면 기존처럼 long.md를 쓴다. long.md, G6 본문, S11 내보내기는 바꾸지 않는다.


2026-10-29 보완(명세 §10.2): `stages/s8_prompts/source.py`가 승인 v1/v2 기획을 개인 식별용 레퍼런스·외모 축 없이 투영한다. `source-plan.json`에 입력 파일 SHA-256과 허용 필드를 고정한다. S8 모델 입력에 이 투영을 추가하고, 조립 시 ACTOR_IDENTITY·PERSONA / FACTS·PERSONA / VOICE·CHAPTERS는 정본으로 대체한다. v1에 없는 필드는 만들지 않고 말투는 기존 특질 시트로 보완한다. 모델 생성 전 정본+시스템+출력 규칙만으로도 short 상한을 넘으면 거절한다. 동결 쌍의 재개를 새 정본 사전 검사보다 먼저 판단한다. 생성할 네 섹션마다 최소24자 예산을 확보하지 못하면 호출 전에 거절한다. v1 말투는 dialogueHabits 다섯 항목을 모두 보존한다. 생성 뒤 전체 상한과 long/short 정렬 검사도 유지한다. 다른 선택·전환 섹션은 모델이 간결하게 작성하며 각 규칙을 적용하지 않을 조건과 자유 대화의 여지를 명시한다. 신규 tr/pv로만 실행한다.

`resources/prompt-sections-v1.json`의 섹션 목록으로 긴·짧은 프롬프트를 조립한다. 긴 프롬프트의 시스템 규칙 섹션은 `systemRulesRef` 파일을 그대로 넣는다. `align`은 두 프롬프트의 섹션 헤더 집합이 같은지, 짧은 프롬프트가 `short_prompt_max_chars` 이내인지, 금지 표현이 없는지 확인한다. `probe`는 `voiceProbes`마다 두 프롬프트로 응답을 받고 판정 모델이 캐릭터 일치를 비교한다. 결과는 G6 페이지에 나란히 표시되며 자동 승인에 쓰지 않는다.

### 8.8 S9 데이터셋 (명세 §10.3, D-0044, D-0045)

학습 가이드 §7·§13의 절차를 따른다. 그래프에서는 두 단계다: `s9s`(인계안·샘플, 관문 G7a, 의존 G6)와 `s9`(대량 작성·검사·분할, 관문 G7, 의존 G7a).

1. `plan`: G6 승인 `prompt-pair-v1`의 짧은 프롬프트와 특질 시트로 `data-plan-v1`을 고정한다. 클러스터 목표 수는 `round(target × share)`이고 합이 목표와 다르면 `base`에서 맞춘다.
2. `samples`: 클러스터마다 인계안을 작성 모델로 만들고(특질 시트의 선택 기준 5항목·상황별 변화 → 행동 기준표), 같은 인계안으로 샘플 12개를 쓴다. 각 대화의 `skeletonId`는 장면 뼈대 단위로 붙인다. G7a 페이지는 클러스터별 인계안과 샘플 전문을 보여 주고 판정·고칠 점을 받는다. `REQUEST_CHANGES`면 고칠 점을 인계안에 붙여 그 클러스터만 다시 만든다.
3. `build`: G7a에서 채택된 샘플은 그대로 넣고, 나머지는 같은 인계안 + 채택 샘플을 예시로 작성한다. 재료: `SNS_REWRITE`(`gemini-sft-poc` 후보 대화를 읽기 전용으로 열어 흐름 뼈대만 쓰고 양쪽 대사를 새로 쓴다, D-0135), `SYNTH`(합성 장면), `NIKL`(접근 경로가 정해질 때까지 비활성). 원본 SFT가 없는 캐릭터의 `base`는 `SNS_REWRITE`와 `SYNTH`로 채운다(가이드에서 검증되지 않은 적용, 계획서 §9).
4. 기계 검사(차단): 형식(역할 교대·system 존재·빈 답 없음), SNS 재작성의 원본 10글자 겹침·흐름 뼈대 3~8줄·메시지 수 ±2(D-0135), 프리필 없음, 원본 화자 사실 미포함, 금지 표현, 같은 말끝·같은 사과 문장 반복(데이터셋 전체 n-gram, 가이드 §8), 최대 길이(학습 템플릿 토큰 수, 기본 4,096). 경고: 길이 비율, 감정 표지 분포. charforge의 표준 검사·렌더러를 이 프로젝트 코드로 옮겨 쓴다(다른 저장소 코드를 import하지 않는다).
5. 분할: `skeletonId` 묶음째 나눈다. 검증은 `base`에서 `baseConversations`, 보강 클러스터마다 `augmentedShare`. 평가 세트는 학습·검증과 따로 만든다(§8.9).
6. G7: 검사 보고서, 클러스터별 수·답변 수·토큰 수, 무작위 표본 20개를 보여 준다. 승인하면 `dataset-rev-v2`를 고정한다.

작성 호출은 실행기 예산(동시 호출 상한은 설정값, 기본 4)과 원장을 쓰고, 재시도는 같은 입력의 재전송이며 첫 성공 결과를 보존한다.

### 8.9 S10 학습·평가 (명세 §10.4, D-0044, D-0045)

학습(`s10t`, 관문 없음, 의존 G7)과 평가(`s10`, 관문 G8, 선행 `s10t`)로 나눈다.

학습 어댑터는 `TrainingProvider` 포트(`plan`, `submit`, `status`, `collect`)를 따른다.

- `gemma_qlora`: 임대 GPU(Vast). 기본 설정과 실행 순서는 D-0077에 따라 §21을 따른다(머스크 N3b 프로토콜, 0.5 epoch 체크포인트, 생성 결과로 체크포인트 선택, 실행마다 GPU 임대·삭제). 2026-10-27의 학습 가이드 §11 설정(Gemma 2/3 응답 표시, linear, 3 epoch)은 폐기했다.
- `vertex_gemini`: Vertex 튜닝. 기반 모델은 설정값이고 착수 때 지원 목록으로 정한다. `plan`은 과금 토큰 수(데이터셋 토큰 × 에폭)와 단가로 비용을 낸다. 체크포인트 ID·step을 공급자 값 그대로 기록하고 중간 epoch를 추정하지 않는다.
- `fake`: 오프라인 전체 흐름용. 즉시 `SUCCEEDED`와 가짜 `model_binding`을 돌려준다.

비용 추정이 `budgetUsd`를 넘으면 `submit`을 거절한다. PoC는 `plan`(dry run)까지만 실제 설정으로 확인한다(D-0044 (9)).

평가: `prereg`가 조건(LONG_BASE, SHORT_GEMMA_SFT, SHORT_GEMINI_SFT)·세트(OE 고정 이력 질문, SE 서운함, APOLOGY 무례·사과 대본, LONG200 200턴 × 사용자 페르소나 4명)·판정·기준을 고정하고 해시를 낸다. `run`은 조건마다 응답을 모은다. 연속 대화는 모델 답을 다음 턴에 그대로 넣고 턴마다 다른 시드를 쓴다. 지표: `repeat_rate_101_200`(101~200턴 말풍선 가운데 앞서 나온 것과 같은 말풍선 비율), `memory_recall_200`(초반에 심은 정보를 200턴 시점에 묻는 확인 질문 정답률, 판정 모델 + 정답 키), `apology_recovery`(진지한 사과 대본에서 회복한 비율). `judge`는 같은 입력의 두 조건 응답을 정순·역순으로 판정해 합의만 센다. G8 페이지는 지표·기준 결과·LLM 짝 판정과 사람 블라인드 20쌍 화면을 보여 주고, 사람 판정으로 일치율을 낸다. 기준 미달이어도 보고서는 나오고 채택은 사람이 G8에서 정한다.

학습 없이 진행(K-0038, D-0048): 평가 진입 때 학습 결과가 없고 `[stages.s10] untrained`이 `ask`(기본)이면, 평가 대신 `s10-eval/ev<k>/prompt-only.json`(`eval-prompt-only-v1`: 사유, 데이터셋 rev, 학습 계획 목록과 추정 비용, 긴 프롬프트 참조)과 `gate-G8.html`을 쓰고 G8을 연다. 답은 `{"decision": "SELECT", "adopted": "LONG_BASE"}`(긴 프롬프트로 진행) 또는 `{"decision": "REJECT"}`(학습을 기다린다)다. SELECT면 G8이 승인되고 S11 패키지는 `sft.evalReport = null`, `sft.adoptedBinding = "LONG_BASE"`로 만들어진다. REJECT면 `s10`이 반려되고, 학습 결과가 생길 때까지 오케스트레이터는 같은 질문을 다시 열지 않고 "학습 결과 대기"로 멈춘다. 학습 결과가 생기면 새 ev revision으로 정상 평가를 한다. `untrained = "wait"`이면 묻지 않고 기다린다. 학습 제출은 `cfp run --submit-training`을 줄 때만 하고, 기본 `cfp run`은 학습 계획(dry run)만 쓴다.

### 8.10 S11 릴리즈 패키지 (D-0011, D-0044)

의존: G4, G5, G5b, G6, G8. 승인된 revision의 파일을 패키지 폴더로 복사하고(`profile`은 G3 기획서, `chapters`는 S4b 챕터 사실과 G4 완성 이미지, `videos`는 G5·G5b 승인 영상, `persona`는 G6, `sft`는 G7·G8) `character-package-v1`을 쓴다. 쓰기 전에 모든 파일의 sha256을 다시 재고, 원본 기록의 해시와 다르면 실패한다. G9 페이지는 패키지 요약(프로필 카드 미리보기, 챕터 3개, 영상 수와 가짜 여부, 대화 경로 두 개, 관문 기록)을 보여 준다.

### 8.11 우리 앱 내보내기 `doki-app` (D-0044 (1))

G9 승인 패키지를 우리 앱 두 시스템의 공식 적재 입력으로 바꾼다. 두 저장소는 읽기만 하고, 적재는 그 저장소의 명령을 그 저장소 환경에서 부른다.

| 대상 | 적재 입력 | 공식 적재 명령 | 담는 것 |
|---|---|---|---|
| api-svc | 시드 묶음 `dokilabs-seed/1`(`data/seed/content.json`과 같은 형식, 테이블별 행) | `uv run alembic upgrade head` → `uv run python -m scripts.seed load` | `character`(이름·성별·나이·소개·직업·취미 등), `character_profile_card`(ko 줄의 새 칸·`tags`·`tmi_items`), `character_stage`(챕터 = 단계, `stage_no` 1~3), 미디어(상대 키, CDN 절대 URL 없음), `character_clip`(`clip_key`·제목·설명·사용 조건·표정·`pick_role`·`action_category`), 소개 영상 |
| chat-svc | 콘텐츠 트리 `data/`의 캐릭터 묶음(`personas/<slug>-r1.json`, `relationship_profiles/`, `quests/`, `chapter_definitions/`, `chapters/`, `pointers/content-pointers-v2.json` 갱신) | `uv run alembic upgrade head` → `uv run python -m scripts.db_ops.content_release publish --data-dir <트리>` → `verify` | persona는 `character-persona-v6`(여덟 섹션)으로 렌더한다. 긴 프롬프트·특질 시트 → v6 섹션 대응표가 변환기의 일부다 |

변환기는 매핑 표(`mapping`)와 버린 칸(`unmapped`)을 `export-result-v1`에 남긴다. 대상의 alembic head가 변환기가 아는 값과 다르면 적재 전에 멈춘다(현재: chat-svc `0028_authoring_project_locale`, api-svc는 구현 때 기록).

적재 확인(`--verify`): 관리자 접속 정보(환경변수 이름만 설정)로 일회용 PostgreSQL 데이터베이스를 두 개 만들고, 각 저장소의 head까지 올린 뒤 위 명령으로 넣고, 캐릭터 ID·단계 수·클립 수·persona revision을 조회해 확인하고 데이터베이스를 지운다. chat-svc 트리는 저장소의 `data/`를 임시 폴더로 복사한 위에 캐릭터 묶음을 더해 publish한다. dev/stage DB에는 연결하지 않는다.

## 9. 공급자 어댑터 (명세 §11)

| 어댑터 | 동작 |
|---|---|
| `openai_compat`(비전) | `OpenAICompatVisionModel`: user 메시지에 텍스트 조각과 `[라벨]` 다음 `image_url`(data URI)을 순서대로 넣고 `response_format = json_object`, `temperature = 0`으로 판정 JSON을 받는다. 429·5xx는 지수 대기 3회. 중계가 이미지 입력을 넘기는지는 실제 호출 전에 확인한다(Q-0020). |
| `openai_compat` | `httpx`로 `<base_url>/chat/completions`(텍스트·비전)과 `/images/generations`·`/images/edits`(이미지)를 부른다. 429·5xx는 지수 대기 3회. 비용은 설정의 단가표로 추정한다. |
| `codex_exec` | §7 참조. |
| `xai_video` | `POST {base}/videos/generations`에 `{model, prompt, image: {url: data URI}, duration, resolution, generate_audio[, aspect_ratio]}`를 보내 `request_id`를 받는다. `GET {base}/videos/{id}`를 `poll_interval_s`마다 조회해 status가 done이면 `video.url`을 키 없이 바로 내려받고, failed·expired·error면 사유와 함께 실패, `timeout_s`를 넘으면 `VideoTimeoutError(job_id)`. 429·5xx는 지수 대기 3회. 키는 `api_key_env`(기본 `XAI_API_KEY`)로만 읽고 없으면 호출 전에 실패. 비용은 단가표(1.5: 480p $0.08·720p $0.14·1080p $0.25/초, 1.5-lite: $0.02·$0.03·$0.14/초, 2026-10-21) × 실제 초 + 입력 이미지 $0.01. |
| `grok_web` | 기본 꺼짐(`accept_terms_risk = true` 필요, D-0029). `playwright`(`--extra web`)의 `connect_over_cdp(cdp_url)`로 사용자가 띄운 전용 프로필 Chrome에 붙어 새 탭을 앞으로 가져와 Imagine을 연다. 화면 흐름은 2026-10-21 로그인 화면에 맞췄다(D-0032): 입력 폼(`form:has(button[type=submit])`) 안에서 비디오 모드 버튼 → 해상도 라디오(`480p`·`720p`) → 길이 라디오(`6s`·`10s`·`15s`) → 소리 버튼(`aria-pressed`를 요청과 맞춤) → 파일 입력에 첫 프레임 업로드(이미지 제거 버튼이 보일 때까지 대기, 업로드 뒤 종횡비 버튼이 사라지고 영상은 이미지 비율을 따름) → 편집기(`[contenteditable]`)에 프롬프트(들어갔는지 확인) → 제출. 제출 뒤 주소가 `/imagine/post/<id>`로 바뀌면 그 id가 든 `<video>`의 주소(assets.grok.com의 `generated_video.mp4`)를 로그인 세션 요청으로 받는다(다운로드 버튼은 다운로드 이벤트가 오지 않아 쓰지 않는다). 옵션 클릭이나 제출 뒤 주소에 `#subscribe`가 붙으면(결제 창) 등급 제한·사용량 소진으로 바로 실패한다. 90초 안에 결과 페이지로 넘어가지 않으면 제출 안 됨으로 실패한다. 웹에 없는 길이·해상도는 S5가 첫 프레임을 만들기 전에 `check_settings`로 거절한다. 어느 단계든 실패하면 `~/.cfp/grok-web-work/<job>/error-<단계>.png` 스크린샷을 남기고 `VideoGenerationError`. 탭만 닫고 사용자의 Chrome은 닫지 않는다. 재개 불가(`resumable = False`), 비용 0, 작업 ID는 `web-<hex>:<post id>`. 복구층(Stagehand `act()`)은 자리만 둔다. |
| `grok_oauth` | `VideoModel`. 요청·상태 처리는 `xai_video`와 같고 인증만 OAuth 접근 토큰(Bearer)이다. 토큰은 `token_file`(기본 opencodex 인증 파일의 활성 xAI 계정)이나 `token_env`에서 읽고, 값을 출력·기록하지 않는다. 만료면 다시 로그인하라는 오류를 낸다(새로 고침 없음). 명시해야 켜진다. 실제 호출 확인 전이다(D-0044 (3)). 토큰 해석 순서: `token_env` → `token_file`의 `xai.accounts[id == xai.activeAccountId].credential.access`, `credential.expires`는 epoch 밀리초로 본다(로컬 파일 기준 가정). 요청·상태·비용은 `XaiVideoModel`을 상속해 같다. 공급자 응답에 토큰이 섞여 와도 오류 메시지에서 지운다. |
| 순위 수집기(`src/character_factory_poc/collectors/`) | 출처별 어댑터 + 가짜. 이용 조건 확인 기록이 없는 출처는 거절하고, 호출 계획(dry run)을 먼저 낸다. 요청 간격·User-Agent·재시도는 설정값. 출처 조사는 `docs/research/2026-10-27-ranking-sources.md`. |
| `gemma_qlora` | `TrainingProvider`: 임대 GPU QLoRA(§8.9). |
| `vertex_gemini` | `TrainingProvider`: Vertex 튜닝(§8.9). `gemini-sft-poc`의 구현을 참고하되 코드는 복사하지 않는다. 옛 이름 `vertex_tuning`을 대체한다. |
| `fake_image` | `ImageGen` 가짜. 프롬프트 해시로 색을 정한 64×64 단색 PNG를 돌려준다. |
| `codex_image` | `ImageGen` 실제(D-0019). 임시 폴더에서 `codex exec --json -s read-only -c mcp_servers={} --disable apps --disable browser_use --disable computer_use -m <model>`에 "내장 이미지 도구로 정확히 한 장, 셸·파일 접근 금지" 지시와 프롬프트·피할 것·선호 크기를 넘긴다. 첫 이벤트 `thread.started`의 `thread_id`로 `$CODEX_HOME/generated_images/<thread_id>/*.png` 가운데 가장 최근 파일을 읽어 PNG 서명을 확인하고 돌려준다. 원본은 지우지 않는다. 종료 코드가 0이 아니거나 PNG가 없으면 `ImageGenerationError`. 원장에는 `kind=IMAGE`, 구독 사용 토큰(`turn.completed.usage`), 비용 0을 남긴다. 크기는 지시일 뿐이며 관측된 출력은 1254×1254다. 장당 약 30~40초가 걸린다. `reference_images`가 있으면 파일마다 `-i <절대경로>`를 붙이고, `-i`가 여러 값을 받으므로 프롬프트는 `--` 뒤에 둔다. 참조 파일이 없으면 호출 전에 `ImageGenerationError`. 참조 이미지로 같은 얼굴이 유지되는 것을 확인했다(2026-10-21). |
| `fake` | 모든 포트. `(stage, ref)` 키로 준비된 응답을 돌려주고 받은 요청을 기록한다. 이미지는 단색 PNG, 영상은 ffmpeg로 만든 1초 더미 파일. |

## 10. 오류 처리

| 상황 | 처리 |
|---|---|
| 같은 경로에 다른 내용을 쓰려 한다. | `ImmutableWriteError`. 새 revision으로 다시 실행한다. |
| 브리프 필수 칸이 빠졌다. | 빠진 칸 목록을 출력하고 아무것도 쓰지 않는다. |
| 의존 관문이 승인되지 않았다. | `GateNotApprovedError`. 어떤 관문인지 출력한다. |
| 에이전트 응답이 연속 형식 실패다. | `AgentFormatError`. 작업 공간에 마지막 응답을 남긴다. |
| 자동 검사 재시도 초과 | 단계 `CHECK_FAILED`. 실패 사유 목록을 `status`에 표시한다. |
| `codex_exec`가 작업 공간 밖을 읽었다. | 출력을 버리고 원장에 `TAINTED`로 남긴다. |
| 순위 목록에 출처·기간·인물 인상이 없거나 순위·이름이 겹친다. | 검증 실패. 아무것도 쓰지 않는다. |
| 순위 목록이 v1 형식이다. | 검증 실패. `scope.appearanceOrigin`을 넣고 v2로 바꾸라는 안내를 낸다(D-0021). |
| 이전 rev의 보고서가 v1이다. | 실행은 계속하고 일치도 비교만 건너뛴다(`agreementWithPrevious=null`, D-0021). |
| 이미지 공급자가 이미지를 돌려주지 않는다(안전 시스템 차단 등). | `ImageGenerationError`. 단계 `CHECK_FAILED`로 기록하고 멈춘다. |
| 기준을 넘는 외모군이 하나도 없다. | 단계 `CHECK_FAILED`. 목록을 늘리거나 `cluster_k`를 줄여 새 rev로 다시 돈다. |
| 군집 근거 필드가 비었다. | 보고서 생성 실패. G1에 올리지 않는다. |
| 이름이 보고서·미리보기 프롬프트에 있다. | 프롬프트면 이미지 호출 전에 중단, 산출물이면 단계 `CHECK_FAILED`(FR-35). |
| 예산 상한에 닿는다. | 실행 전이면 거절, 실행 중이면 남은 작업 중단. |
| 영상 공급자 작업이 시간 안에 끝나지 않는다. | 작업 ID를 SUBMITTED로 남기고 단계 `CHECK_FAILED`. 다음 `cfp video intro --execute`가 같은 rev에서 같은 작업을 다시 수집한다(재제출 없음). |
| 영상 예상 비용이 상한을 넘는다. | 제출 전에 `BudgetExceeded`. |
| 영상 공급자가 실패를 돌려준다(정책 차단 등). | 작업을 FAILED와 사유로 남기고 단계 `CHECK_FAILED`. |
| `grok_web`에서 화면 요소를 못 찾는다. | 단계 이름이 든 오류와 스크린샷. 선택자를 고친다. |
| 사전 등록 해시가 다르다. | 분석 거절. |
| 생성·판정 모델 계열이 같다. | 시작 시 경고. `--allow-same-family`가 없으면 판정 단계를 거절한다. |

## 11. 테스트 (NFR-08)

| 층 | 범위 |
|---|---|
| 단위 | 정규화·해시, 한 번만 쓰기, ID 형식, 모든 계약의 왕복과 알 수 없는 필드 거절, 상태 전이, 예산 계산, 순위 목록 검증, 백분위 정규화, 군집 결정성과 구성원 수 기준, 이름 유출 검사, 근거 완전성 검사, 외모→성격 추론 금지 검사, 섹션 일치 검사, 재작성 규칙 검사, 분할 규칙, 짝 판정 합의 |
| 에이전트 러너 | 가짜 모델로 형식 실패 재시도, 검사 실패 재시도, 재시도 초과, 작업 공간 밖 접근 거부 |
| 동작 영상 골격(D-0038, D-0040) | `tests/test_actions.py`(G4 의존, 미소 첫 프레임 = 승인 이미지, 무표정 첫 프레임 생성·비율, `l2` 18편·`standard` 111편 계획, 길이, 앱 지시문·관계 단계 메모, G5b 선택·제외·잘못된 답, 승인 기록의 앱 칸, 동작별 부분 재생성과 첫 프레임 재사용, 재개, 설정 검사, dry run, 오케스트레이터 G5b 대기) |
| 이미지 자동 검사(D-0036) | `tests/test_image_qa.py`(루프 단위·S4a·S4b·S4 통합·준비 검사·비전 어댑터 요청·호출 최대치) |
| 오프라인 기획·장면 흐름(D-0033) | `tests/test_plan_variants.py`(씨앗·변형·직접 쓴 안·G3 선택과 수정·검사 재시도·이름 유출), `tests/test_refs.py`(색인·검색·선별·원문 미복사·건너뛰기), `tests/test_scene_flow.py`(배경 사진 9:16, G4a 직접 정의, 장면 사실, 자세 검사 재시도, G4b 수정, 완성 이미지 참조 두 장, 챕터별 부분 재생성), `tests/test_orchestrator_flow.py`(씨앗 대기 중 S5 갈래 진행 → 씨앗 뒤 G4까지). |
| 오프라인 전체 흐름 | `tests/test_reference.py`: 합성 순위 목록 → S1 → G1 import(현재 구현 범위). `tests/test_offline_pipeline.py`(목표): 합성 브리프 → S1(합성 순위 목록) → G1 import(얼굴 한 장) → S2(자동 동일인 검사) → S3 → G3 → S4·S5·S7 병렬 → G4·G5·G6 → S6 → S8 → S9 → G7 → S10 → G8 → S11 → G9. 네트워크는 소켓 차단 fixture로 막는다. |
| 통합(선택) | `pytest -m live`: 실제 중계로 S1 태깅 1건, S3 초안 1건. 환경변수가 있을 때만 실행하고 원장에 남긴다. |
| 에이전틱 실행(D-0049) | `tests/test_state_concurrency.py`(두 스레드 전이 손실 없음, 관문 사건 기록), `tests/test_scheduler.py`(차례별 `ready_stages`, 유료 단계 판정), `tests/test_run_waves.py`(장벽으로 동시 실행 확인, 한 갈래 검사 실패 중 다른 갈래 진행, 순차·물결 최종 상태 같음, 기록 순서 결정성), `tests/test_web_auto_resume.py`(결정 POST 하나로 다음 물결, 실행 중 결정은 한 번 더, 유료 단계 held와 호출 0회, 확인 뒤 실행, 꺼짐), `tests/test_review.py`(가짜 판정 순위 기록·화면, G7a·G8 거절, 형식 오류 뒤 검토 없음, 기록만으로 상태 불변, `followedReview`, 옛 rev 숨김, 같은 계열 거절, 비전 꺼짐이면 이미지 관문 건너뜀), `tests/test_rework.py`(G4a 챕터 부분 재생성과 해시 보존, 메모 원문 전달, 상한과 허락, G6 재작업 뒤 s9s 대기, REJECT는 브리프 없음, G1 자동 얼굴 재생성), `tests/test_gate_queue.py`·`tests/test_report_hil.py`(G3가 G5보다 앞, 보고서 관문 수와 G7a·G8 빈 일치율), 전체 흐름(워크숍 API로 결정만 보내 두 브리프가 sx까지, 수정 요청 2회 포함, SFT·학습 없이 두 경로) |

반드시 고정할 위험: (1) 승인되지 않은 관문의 산출물을 다음 단계가 읽지 못한다. (2) 판정 프롬프트에 후보 식별 정보가 없다. (3) 같은 특징·설정이면 군집이 같다. (4) 성격 칸의 근거에 외모 명세가 들어가면 실패한다. (5) 섹션 집합이 다르면 프롬프트 쌍이 고정되지 않는다. (6) 평가 분할 예시가 학습 생성 입력에 들어가면 실패한다. (7) 비밀값이 원장·보고서·표준 출력에 없다. (8) 순위 목록의 이름이 S1 보고서·미리보기 프롬프트·S2 입력에 없다(FR-35). (9) G1은 얼굴 정확히 한 장만 받는다. (10) S2 판정이 상한까지 FAIL이면 외모 명세 없이 `CHECK_FAILED`이고, 판정 공급자가 없으면 `generate`는 아무것도 쓰기 전에 거절되며, `picked`는 이미지 호출 0회로 고정된다(D-0042, D-0043).

`scripts/check.sh`는 `uv sync --locked`, `ruff check`, `ruff format --check`, `pytest -q`를 차례로 돈다.

## 12. 구현 순서

| 단계 | 내용 | 끝나는 조건 | 릴리스 |
|---|---|---|---|
| M0 | 골격: `pyproject`, `common/`, 포트와 가짜 어댑터, 원장·예산, 상태 파일, `graph.py`, `check.sh` | 검사 스크립트 통과. `cfp status`가 빈 상태를 표시한다. | R0 |
| M4 (선행, D-0013) | `cfp plan import`, S7 특질 시트·검사, S8 프롬프트 조립·정렬·표본, G6 페이지, 오프라인 흐름 테스트 | 오프라인 통과. 실제 모델로 `persona_version` 1개 발급(사용자 지시 뒤). | R0 |
| M1 | S1(D-0017): 순위 목록 고정·인물 묶기, Scout 특징 태깅과 검사, 정규화, 군집(구성원 수 기준), 보고서, 이름 유출 검사, ImageGen 포트(가짜·`codex_image`)로 미리보기, G1 페이지·선택, `cfp ref run`·`cfp run --ranking` | 오프라인 골격: 합성 순위 목록으로 G1 선택까지 통과. `codex_image` 실제 호출 확인(D-0019). 다음: 사용자 지시 뒤 실제 순위 목록으로 J2 실험 보고서. | R0 |
| M2 | S2(D-0022, D-0023): G1 참조 사진 선택, 참조 이미지 입력 후보 생성, G2 페이지·선택, 외모 명세, `cfp hero run`·`cfp run --until G2`. S3: 기획 초안이 외모 명세를 참조(남음). 짝 비교(FR-11)는 보류 | S2 오프라인 통과와 실제 구독 호출로 G2 → `appearance_rev` 확인(2026-10-21). 남은 것: 실제 순위 목록으로 S1→S2 한 번, S3 연결 | R0 |
| M2b | 외모 한 번 고르기(D-0042, D-0043): S1 외모군당 얼굴 1장, G1 얼굴 한 장 선택·고칠 점 메모, `cfp ref faces`, S2 기준 사진 + `identity-v1` 동일인 검사(재생성 최대 3번 시도), `base_photo = "picked"`, G2 제거와 `needs` 의존, `load_appearance_spec`의 `s2` 기준, 옛 G2 칸 읽기 호환 | 오프라인 통과(가짜 판정으로 통과·재시도·최종 실패·판정 없음 거절·picked 네 경로). 남은 것: 판정 경로 확인(Q-0020) 뒤 실제 S1 얼굴 → S2 `generate` 1회 | R0 |
| M3 | S3 외모 연결(D-0024), S4 프레임 생성과 G4 사람 승인(D-0025, D-0026), `cfp frames run`. 일관성 판정·챕터별 재생성은 보류 | 오프라인 통과. 실제 구독으로 3챕터 프레임 생성과 G4 승인 확인(2026-10-21). 남은 것: 실제 Planner로 S3, 판정 모델 참고 자료 | R0 |
| M3b | 기획·장면 흐름(D-0033~D-0035): 씨앗 → 변형 → G3, S3r 참고 자료(hash-v1 색인), S4a 배경 → G4a → S4b 장면 사실·자세 → G4b → S4 완성 이미지 → G4(챕터별 부분 재생성), 갈래별 진행 오케스트레이터, `cfp plan seed/variants/own`·`refs index/select`·`scene backgrounds/poses` | 오프라인 통과(2026-10-22, 182 passed). 남은 것: 실제 Planner·Scout·Writer·Pose 모델과 구독 이미지로 데모 캐릭터 한 번, 실제 임베딩(Q-0019) | R0 |
| M3c | 이미지 자동 검사 루프(D-0036, D-0037): 비전 포트·가짜·OpenAI 호환 어댑터, 기준표, 편집 수정 반복, 배지, 원장 VISION | 오프라인 통과(2026-10-22, 221 passed). 남은 것: 실제 판정 경로 확인(Q-0020), 사람 판단과의 일치율 | R0 |
| M5 | S5·S6·S9·S10·S11 뼈대를 가짜 어댑터로 연결, 전체 오프라인 흐름 테스트, 원장 보고서 | PRD §14 수용 조건 1·4 충족. | R0 |
| M5 | S5 소개 영상(D-0028~D-0032): 9:16 세로 첫 프레임, `xai_video`·`grok_web` 어댑터, 제출·재개·실측, G5 사람 선택, `cfp video intro`·`web-setup` | 오프라인 통과. 2026-10-21 실제: 세로 첫 프레임 생성 확인, grok.com 화면 맞춤과 웹 영상 1편 생성·받기 확인, S5 전체 웹 실행은 무료 등급 한도(결제 창)로 막힘. 남은 것: 웹 한도 또는 유료 등급(Q-0018) 뒤 S5 전체 실행, 실제 API 1회(사용자가 보류) | R0 |
| M6 | S6 동작 영상(D-0038, D-0040, D-0041): G4 승인 이미지 → 미소·무표정 첫 프레임 → 앱 통화 영상 표준 세트(`l2` 6편·`standard` 37편) → G5b 선택·제외·부분 재생성, `cfp video actions`. 다음: 특별 행동 제안 에이전트, 영상 자동 검사 | 골격: 오프라인 통과(2026-10-22). 남은 것: 영상 공급자 사용량 확보(Q-0018) 뒤 `l2` 18편 실제 실행과 G5b 승인 | R0 골격·R1 |
| M7 | SNS 재작성·NIKL·합성·분할, 학습 제출·수집, 사전 등록·블라인드 평가, 릴리즈 매니페스트, G7~G9 | 사전 등록 기준 판정 보고서와 `release_rev` 1개. | R1 |
| M8 (PoC, D-0044·D-0045) | 3일 PoC: A 외모 흐름(M2b의 `picked`까지), B 순위 수집기, C S9 데이터셋, D S10 학습(dry run)·평가, E 패키지·우리 앱 변환기, F Grok OAuth, G 워크숍 웹앱, H 그래프에 `s9s`·`s9`·`s10t`·`s10`·`s11`·내보내기 연결과 `tests/test_offline_pipeline.py` | 여성·남성 합성 브리프 두 개가 가짜 공급자로 S1 → G9 → 패키지 → 일회용 DB 적재까지 네트워크 없이 통과하고, 워크숍 화면에서 관문만 눌러 같은 흐름을 끝까지 간다. 실제 호출은 순위 수집·이미지·LLM 1회씩 | PoC |
| M9 (D-0049) | 에이전틱 실행: A 상태 잠금·관문 사건·`ready_stages`·`run_waves`·자동 재개·유료 단계 확인, B 사전 검토(`gate-review-v1`·검토 실행기·화면), C 수정 요청 재작업(`rework-brief-v1`·G4a·G4b·G5·G6 부분 재생성·반복 상한), D 대기열·`hil-report-v1`·화면, E 통합 | 워크숍에서 관문 결정만으로 여성·남성 합성 브리프가 가짜 공급자로 sx 적재 확인까지 가고, 고르기 관문에 추천이 붙고, 수정 요청이 요청한 부분만 다시 만들고, 유료 단계는 확인 전 호출 0회다 | PoC 뒤 |

구현 순서는 M0 → M4(선행) → M1 → M2 → M3 → M5 → M6 → M7이다(D-0013). M2b는 워크숍 화면 연결 전에 한다. 각 노드의 현재 성숙도(L0~L4)와 올리는 규칙은 [현재 상태](../status/current-state.md)와 [인계 규칙](../status/README.md#노드-성숙도-규칙)에 있다. 마일스톤의 "끝나는 조건"은 대부분 L1(오프라인)이고, L2 이상은 그 규칙을 따른다. M4의 실제 실행은 `cfp plan import`로 들여온 기획서의 G3 기록이 있으면 된다.

## 13. 착수 때 확인할 사항

| 확인할 것 | 방법 | 단계 |
|---|---|---|
| opencodex 중계의 비전 입력 형식과 모델 이름 | 중계 설정과 1회 호출 | M2 |
| OpenAI Images의 참조 이미지(edits) 입력 지원과 크기 제한 | 공식 문서와 1회 호출 | M2 |
| 화제성 순위 출처의 발표 형식과 자동 수집 허용 여부(Q-0013) | 출처 공지·이용 조건 | M1 |
| ChatGPT 구독 이미지 생성의 사용량 한도(장당 입력 약 11.8만 토큰 관측)와 S1 한 번(최대 12장)이 한도 안에 드는지 | 첫 실제 S1 실행의 원장 | M1 |
| `codex_image`가 참조 이미지 입력(`codex exec -i`)으로 같은 인물을 유지하는지 | 확인함(2026-10-21, 검증 기록) | M2 |
| xAI 영상 API: 이미지 필드 이름(`image.url`), done·failed 외 상태 이름, 결과 URL 유효 기간, 요청 속도 제한 | 첫 실제 호출(사용자 지시 뒤) | M5 |
| grok.com Imagine 화면의 업로드·프롬프트·영상 모드·생성·결과·다운로드 선택자 | 2026-10-21 한국어 UI로 확인(D-0032). 영어 UI의 aria-label은 추정이다 | M5 |
| 현행 운영 프롬프트의 섹션 목록과 시스템 규칙 원문 위치 | 사용자 지정 | M4 |
| `gemini-sft-poc` SNS 후보 파일의 경로·형식(`confirmed/<dialogueID>.json`, `candidates-r2/`) | 그 프로젝트 인계 §3 | M7 |
| NIKL 말뭉치 접근 경로와 이용 조건 | 사용자 확인 | M7 |
| Vertex tuning의 지원 기반 모델(3.1 Flash-Lite 통과 사례) | `gemini-sft-poc` 인계 | M7 |
| 얼굴 임베딩 라이브러리를 쓸지(선택) | 설치 가능성과 라이선스 | M3 |
| S2 `identity-v1` 판정이 G1 얼굴과 같은 사람인지를 사람 판단과 얼마나 맞게 보는지 | 실제 기준 사진 몇 장(같은 사람·다른 사람 섞어)을 판정하고 사람 판단과 비교 | M2b |


## 14. 기본 품질 공정 구현(2026-10-29, 명세 §16)

형성 설정은 `[stages.s7] formation_profile = "ko-text-prompt-long-v1"`로 명시하며 이전 설정은 legacy로 읽는다. S7 하위 단계는 새 revision 아래 design/workspace·dialogues/workspace에 원문과 입력을 각각 보존하고, 단계 완료 파일이 있으면 다시 호출하지 않는다. 내용 검사는 재생성 대신 CHECK_FAILED로 남긴다. S8 컴파일은 섹션 순서·본문 필드·예시 선택 ID를 고정하며 long8,000자를 넘으면 조용히 자르지 않는다.

`contracts/formation.py`에 형성·프로필 계약을, `contracts/persona.py`에 prompt-pair-v2와 버전 로더를 둔다. S7의 trait-sheet.json은 v1 호환 투영으로 유지한다. bundle은 정확한 plan/trait/blueprint/dialogues/프로필/시스템 규칙/컴파일 버전을 해시로 묶는다. G6는 bundle이 참조한 S7 revision을 승인하며 현재 최신 revision으로 대신하지 않는다.

컴파일 매핑은 정본 IDENTITY·LIFE·VOICE_EXAMPLES·CHAPTERS 직접 투영, blueprint의 decisionRules→행동, voiceProfile→목소리, ordinaryModes→일상 흐름, factPolicy→사실 경계, 고정4슬롯→CHARACTER_EXAMPLES다. 예시는 실제 messages에 넣지 않는다. 메시지 계약은 고정 system+실제 누적 이력+현재 user→첫 assistant 하나다. 이력 요약·재추출을 하지 않는다.

품질 CLI는 `cfp persona qualify plan <cohort>`(기본 dry run), `cfp persona qualify run <cohort> --execute`, `cfp persona qualify report <run> [--human-reviews <file>]`로 분리한다. cohort는 사전 등록 슬롯·프로필·시나리오·분기·출처 해시를 포함한 불변 manifest다. 실제 대화 원문은 runs/에만 저장한다. 외부 대화 모델·tokenizer 바인딩이 없으면 실행을 미확인 상태로 막으며 추정 토큰을 실측으로 기록하지 않는다.

판정은 모든 예정 응답·실패를 원장에서 재구성한다. 독립 사람 검토의 scene/turn 결함·행동·말투, 이중 평가32장면과 불일치 조정·인용 유효성을 확인한다. 기준과 분모를 만족하지 않으면 합격하지 않는다. 자세한 실행 예산과 개발/보류 규약은 [계획](../product/2026-10-29-persona-quality-floor-plan.md)을 따른다. 실제 구현 인터페이스와 검증 결과는 이 절에 갱신한다.

§14 구현 인터페이스: `build_formation`과 `build_formation_dialogues`는 S7의 동결 revision을 사용한다. `compile_persona(..., source_hashes, trait_revision, persona_version, rules_text, rules_ref)`는 순수 컴파일이며 `verify_bundle`이 승인·소비 전에 파일 해시를 검증한다. 품질 실행은 `run_qualification(ctx, cohort, run_dir, dialogue_model, token_counter, formation_runner)`이며 정확한 counter가 없으면 실제 대화 전에 거절한다. baselineSource/baselineSourceSha256으로 동결 legacy 코드를 별도 프로세스에서 읽고 short 필수 소비를 우회하지 않는다. S11의 Persona.shortPrompt는 long 전용일 때 null이며 빈 성공 파일로 위장하지 않는다.

실제 개발 관찰에서 Gemini의 max_tokens는 추론 토큰도 포함해 500 설정의24응답 중8개가 잘렸다. 소비 프로필의 total maxOutputTokens 상한을2,400으로 올릴 수 있게 하며, 본문 길이와 추론 예산을 같은 값으로 간주하지 않는다. 변경한 설정은 별도 관찰 조건으로 기록하고 정식 실행 전에 토큰/비용 상한을 다시 계산한다.

## 15. 선택·말투 분리 구현(명세 §17)

구현 순서와 계약은 [개선 계획 §6](../product/2026-10-29-persona-choice-voice-plan.md)을 따른다. 기존 `CharacterPlanV2` 투영을 유지하고 `seed-requirements-v1`, `choice-design-v1`, 생성/저장/선택 v2와 안정 choiceRuleId를 연결한다. v1 SourceRef/DecisionRule은 바꾸지 않는다.

말투 자료의 실제 파일 해시·승인 원문·styleView 계보를 검증해 VoiceBinding을 고정한다. S7 revision 하위에 design/beats/render/preservation을 저장하며 원문·형식 재시도·의미 실패를 남긴다. v2의 말투 섹션에는 S3 생성 초안이 승인 팩 기준을 덮어쓰지 못한다.

필수 커버리지는 일상·감정/관계 변화·핵심 선택·조건 변경과 승인 choiceRuleIds다. 충족하는 4예시 조합을 ID 순으로 고르고 불가능하면 COVERAGE_GAP이다. 선택/보존 FAIL·UNRESOLVED는 승인·소비 불가다.

공유 RunBudget은 호출 전 입력/총 출력 토큰·비용을 예약하고 영속 원장에서 복원한다. 개발용 두 장면 프로토콜은 기존 정식 7장면 계약과 버전을 나누고 QUALIFIED를 내지 않는다. 모든 회귀는 합성 자료와 가짜 모델을 사용한다.

v1.8 변경: §15에 선택·말투 분리의 계약·실행·검증 근거를 추가했다.

구현 기록: `persona_quality/producers.py`는 `development-producer-v1`의 실제 파일 해시·선택 ID를 검사하고 A의 bundle 및 B/C/D의 고정 v1 컴파일을 재현한다. `DevelopmentCohortV2.comparison="selection"`에서는 같은 원천 자산의 CURRENT/COVERED만 허용하고 v2 조립 함수에서 선정 방식만 바꾼다. `s3_diagnostics.py`는 template의 씨앗·행동 예시 자리표시자와 실제 입력·첫 시도·출력/실패를 대조하고 블라인드 후보·사람 분류 집계를 내보낸다.

VoicePack의 주입·검증 예시는 원본 대화 ID와 실제 파일/필드/인용을 모두 요구한다. 분리 감사의 파일·해시·필드·대화 ID도 그 원본과 같아야 한다. 부정형 말투 목표에는 유효한 requiredTags/forbiddenTags를 요구한다. G6 대기 중에는 현재 설정의 말투 정책과 승인 자료로 바인딩을 재계산한다. RunBudget은 별도 lock 파일과 원자적 교체로 저장하며 손상된 기존 원장을 새 예산으로 초기화하지 않는다. 정식 v2 재개 계획은 완료 요청을 다시 예산에 더하지 않으며 결과 미확인 형성 시도는 재추출하지 않는다.

지원하지 않는 경로는 실제 nested Codex, 공유 예산 밖 구형 subprocess 형성, 의미 상태 분기다. 중립 후속 질문과 API 경로를 사용하며 지원 범위 밖 입력은 선제 거절한다. wheel에는 prompts·resources의 JSON/Markdown·정적 웹 자산을 모두 포함한다.

## 16. 추가 특질 추천 구현(명세 §18)

### 16.1 자산과 저장

- `contracts/creator_traits.py::CreatorTrait`는 선택한 저작 행동과 출처를 담는다. `contracts/planning.py`의 seed/plan selectedTraits는 기본 빈 목록, 최대5개다(D-0067 구현 제안값).
- `resources/creator-traits-v1.json`은 기존 06-presets.json의 144개 expression_focus.behavior를 literal로 투영한다. 원 카탈로그 SHA256·presetId·field path가 있으며 개인 점수/과거/원 대화는 복사하지 않는다. 패키지에 포함되어 외부 원본 경로 없이 동작한다.
- `stages/s3_plan/trait_recommendations.py`는 load_catalog, catalog_view, recommend_traits, resolve_traits, verify_selected_traits를 제공한다. 추천은 어휘 검색이며 의미 적합성 PASS가 아니다. 한 번 최대5개를 보여주고 선택/제외 ID를 뺀다. 직접 검색과 관련 단서가 적은 경우의 탐색을 지원한다.
- `seed.write_seed(..., trait_ids=None, expected_seed_rev=...)`는 단계 전이와 같은 state 잠금 안에서 최신 상태를 확인하고 실행/검토/승인 중이면 CLI와 웹 모두 거절한다. 원문 성격과 신원을 보존하고 선택 snapshot을 검증한 뒤 `.seed.lock` 배타 잠금 안에서 단조 revision과 예상 revision을 확인한다. CLI와 웹이 같은 저장 경로를 사용한다.

### 16.2 진입점

`cfp plan suggest --personality ... [--trait ID] [--search ...]`는 호출 없이 JSON 후보를 반환한다. `cfp plan seed ... --trait ID`를 반복해 고른 항목을 저장한다. 웹 `/trait-authoring.html?character=<id>`는 기존 캐릭터 선택·기본 설정·추천/검색·선택 목록·저장을 제공한다. 기존 워크숍 스타일을 재사용한다.

| API | 계약 |
|---|---|
| GET /api/traits/catalog | 카탈로그 hash, 수량, 행동 snapshot 목록 |
| POST /api/traits/recommend | personality, selectedIds, dismissedIds, search, limit → items, method=lexical-v1, matchStatus |
| GET /api/characters/{id}/seed | seed 또는 null, editable, reason |
| POST /api/characters/{id}/seed | fields, selectedIds, expectedSeedRev, catalogSha256 → 새 seed, nextUrl |

특질을 선택하지 않았으면 카탈로그 조회 실패/로딩과 무관하게 저장할 수 있고 hash=null을 보낸다. 서버도 빈 선택에 카탈로그 읽기를 요구하지 않는다. 클라이언트는 행동/출처 본문을 저장 요청으로 제출하지 않는다. 서버는 ID를 해석하고 변조·중복·알 수 없는 ID를 거절한다. state가 손상되거나 S3가 RUNNING/AWAITING_HUMAN/APPROVED거나 작업 중이면 409다. seed/catalog stale은 409, 입력 오류는 400/422다. 캐릭터별 임시 입력과 선택을 보존하고 늦게 도착한 응답이 다른 캐릭터나 최신 검색을 덮지 않게 한다.

### 16.3 하류 전달과 검증

`variants._fix_plan`이 선택 목록을 각 후보에 결합한다. `choice_flow`는 selectedTraits 고정 요구를 추가하고 `check_choice_design`은 목록·요구 누락과 연결된 행동 규칙이 없는 경우를 거절한다. creator 요구의 검토 인용은 실제 행동 설계에서만 허용하고 공장이 복사한 selectedTraits metadata만으로 구현을 인정하지 않는다. `formation.canonical_plan`과 `source.project_plan`이 선택을 전달한다. v1/v2 컴파일러와 구형 long/short assemble은 `with_creator_traits`로 실제 선택 행동을 disposition에 보존한다. 의미 검토는 선택의 구현을 읽어야 하며 metadata 복사를 실현으로 오해하지 않도록 역할 지침에 명시한다.

회귀 검사는 `test_trait_recommendations.py`, `test_trait_authoring.py`, `test_creator_trait_flow.py`에 있다. 합성 기획/대화와 fake 공급자로 전파를 확인하며 실제 대화 품질 검증과 구분한다. 다른 저장소 변경은 없다.


## 17. 서비스 기반 actor compiler 구현(명세 §19)

- contracts/actor_persona.py에 RuntimePersona 여덟 섹션과 단일 RuntimeContext(relationship/scene/speechLevel)를 둔다. stages/s8_prompts/actor_persona.py는 project_actor_persona/compose_actor_runtime/verify_actor_runtime를 제공한다. coreTraits와 선택 behavior는 disposition, wanted/fear는 해당 칸, attention/interpretationPriority는 해석, choice priority는 선택 경향, 개인별 표현 강도/리듬/직설성/감정 변화는 voice에 연결한다. 출처는 bundle asset으로만 기록한다.
- actor-profile-v1은 내부 원천에서 결정적으로 투영한 문장 목록이며 새 모델 호출을 요구하지 않는다. exact 중복만 제거하며 의미/심리 타당성 점수라고 주장하지 않는다. 현행 여덟 섹션을 유지하되 개별 문장이 인물 주어의 저작 문장이어야 한다.
- S8 새 조립은 actor-tendencies-compiler-v3와 examplesUsage=review-only를 기록한다. 기존 compose_choice_voice_text/coverage-policy-v1은 바꾸지 않는다. 내부 검토용 selectedDialogueIds4개는 runtime 예시 주입을 뜻하지 않는다. 새 bundle은 실제 본문과 actor profile을 원천으로 재현해 비교한다.
- runtime rules는 새 resource로 두고 현재 관계·장면은 단일 객체만 받는다. 전체 챕터/예시/규칙표/제작 메타정보는 본문 검증에서 거절한다. 8000자 초과를 조용히 자르지 않는다.
- tests/test_prompt_identity_preservation.py 및 기존 choice_voice_flow/creator_trait/development 회귀, 전체 scripts/check.sh, 독립 검토와 실제 Gemini 대조를 수행한다. 과거 실험과 다른 저장소는 수정하지 않는다.

v1.10 변경은 사용자가 정정한 runtime 요구를 따른다. 처음 제안한 runtime 예시 선정 강화는 구현 범위에서 제외한다.

## 18. 텍스트 제작 덱 연결(명세 §20)

`resources/text-model-deck-v2.json`은 사용자 원본의 snapshot이다. `common/text_deck.py`는 task→profile override→route model ID 순으로 해석한다. `FactoryConfig.text_pipeline/task_provider/text_binding`, `Context.task_model/role_model`이 기존 공급자 포트와 추적 원장을 사용한다. 같은 텍스트 단계는 Codex subprocess를 우회하고 `max_retries=0`으로 HTTP 재시도를 예산 밖에 숨기지 않는다.

`cfp models show/select --profile ... --route ...`는 네트워크 없이 해석·전환한다. 선택은 `work/text-pipeline-selection.json`에 원자적으로 저장한다. 설정은 `factory.toml`의 `[text_pipeline.routes.opencodex]`/`[text_pipeline.routes.test]`와 `models` 매핑이다. 주소에 인증정보/query를 넣지 못하며 인증 값은 환경변수로만 읽는다.

표준 S3의 `model_deck.py`는 원문 요구 추출, 인용을 가진 설정 충돌 검토, 대상 필드만 한 번 수정, voice 두 필드만 확정하는 과정을 더한다. typed step fingerprint와 S7 recipe에는 덱 배정을 포함한다. 표준 S8은 `compose_approved_sheet`로 승인 원문을 서비스 섹션에 투영하고, 기존 v1 short 칸은 동일한 무압축 본문으로 보존한다. 새 압축/품질 합격을 주장하지 않는다. 선택의 예외는 산문으로 보존하고 기존 system_rules_path도 존중한다. G6 수정 후 동일 본문 재조립은 NeedsInputError로 멈추며 원천 수정 후 재개한다. S7 원천 생성 배정과 S8 현재 선택은 구분하고 최종 점검 상태는 NOT_RUN으로 남긴다.

S9의 `deck.py`는 revision snapshot, 배치 입력/출력·검사/수정·실패 기록, 배치별 호출 계획 상한을 관리한다. `ledger.calls.jsonl`의 textBinding과 각 요청 기록으로 실제 출처를 추적한다. 의미 오류 재추첨·자동 경로 대체는 없다. 상세 사용법은 [실행 안내](../guides/text-model-deck.md)를 따른다.

v1.11 변경(2026-10-30): 텍스트 모델 덱·프로필과 별도 테스트 호출 경로를 연결했다(D-0072).

D-0080 구현(2026-11-04): `pipeline/orchestrator.py`의 s3 실행 함수는 씨앗이 없으면 `--seed` 또는 `seed.seed_fields_from_brief(brief)`로 씨앗을 먼저 고정한 뒤(다른 단계가 돌기 전), 외모 축이면 s2 승인을 확인하고 `run_s3_variants`를 부른다. `variants._preflight`는 S1·G1이 PENDING인 캐릭터에서 외모 명세를 요구하지 않고 appearance=None, 이름 검사 목록을 빈 목록으로 둔다. `prompts/plan_variants.md`는 appearance=null과 seed.notes의 브리프 원문(피해야 할 것·말투 확인 문장)을 요구로 다룬다. `s8_prompts/actor_persona.compose_approved_sheet`는 lifeAndTastes·wantsAndFears·voiceSummary·boundaries가 비면 ValueError이며, 이름 뒤 주제 조사는 받침에 따라 은/는을 고른다. 테스트는 `tests/test_brief_seed.py`, `tests/test_plan_variants.py`의 페르소나 우선 시험, `tests/support/flow.py`의 `variants_for_seed`·`v2_plan`이다.

D-0082 구현(2026-11-04): `common/call_context.py`의 `CALL_OBSERVATION_RULE`을 `actor_persona`의 두 조립 경로 boundaries 끝에 넣고, `appearance_reading_problems`를 `check_plan_v2`(coreTraits·contrastTrait·choices·misreadings·voiceSummary·voiceExamples)와 `check_trait_sheet`(choice·stance·dialogueHabits·judgmentPriorities·situational)에서 부른다. 저작 지시문 6개 끝에 영상통화 맥락 절을 붙였다. `s7_traits/check._mentions`는 원문 포함 또는 2자 이상 어절의 70% 포함이면 기획 핵심 성격을 언급한 것으로 본다.

D-0083(2026-11-04): `pipeline/agent.AGENT_MAX_OUTPUT_TOKENS`(32,000, 추론·생각 토큰 포함)를 `run_agent`, S9 덱, S7 formation 호출이 함께 쓴다.

D-0084(2026-11-04): `errors.ProviderTransportError`(kind: disconnect·timeout·rate_limit·server_error·malformed_stream). `openai_compat`은 `stream=True`이고 공식 호스트일 때 `_send_stream`으로 SSE를 `collect_stream`에 모아 비스트리밍 응답 모양으로 바꾸고, Gemini는 `extra_body.google.thinking_config`(thinking_level=추론 강도, include_thoughts)를 보낸 뒤 `strip_thoughts`로 생각 블록을 걷어낸다. `TrackedTextModel(transport_retries=N)`은 `ProviderTransportError`일 때만 `<ref>~transport<k>`로 새 예약을 잡아 다시 부른다. `Context.task_model`이 `[text_pipeline] transport_retries`(기본 1)를 넘기고, `text_deck.resolve`는 api 경로 provider extra에만 `stream`을 둔다. `model_deck._review`의 인용 확인은 원래 문자열 값(`_strings`)에서 찾는다.

D-0085(2026-11-05): `actor_persona.compose_approved_sheet`의 CHOICES는 `_choice_lines`가 만든다. 첫 줄은 "특별한 단서가 없을 때 → {primaryResponse}.", 다음은 switchConditions 원문, 판단 우선순위는 "{dilemma} → {choice}. 다만 {switch}."이며 `_bare`가 끝 마침표를 떼어 '..'을 막는다. `load_actor_rules`의 기본값은 `resources/actor-system-rules-v2.md`(ref `builtin:actor-system-rules-v2`)다. `s7_traits.check.check_speech_level(voiceSummary)`는 voiceSummary에서 해요체·반말을 읽어 dialogueHabits 다섯 칸과 choice.expressionIntensity에 다른 말높임의 어미·예시가 있으면 문제를 돌려준다. `sheet.run_s7`과 `checks.registry`의 s7 검사에 들어 있다.

D-0086(2026-11-05): 덱 S3의 `model_deck.finish(ctx, cid, folder, seed, draft, budget, checks)`는 `deck_plan_voice` 하나만 부른다(`AgentSpec(..., max_check_retries=1)`, 검사: 변형 검사 + axisNote 보존 + voice 두 칸 밖 변경 금지 + `mixed_speech_levels`). 설정 검토·수정·재검토(`deck-review`·`deck-repair`·`deck-recheck`)는 없다. 첫 단락의 "인용을 가진 설정 충돌 검토, 대상 필드만 한 번 수정"은 이 결정으로 대체한다.

## 19. 글래스 시안 연결 구현(명세 §21)

WebSettings.studio_dir/studio_path로 시안 경로를 설정한다. create_app은 web.text_pipeline.install_text_pipeline_routes를 설치하고 루트 정적 파일보다 먼저 /studio를 mount한다. _StudioStaticFiles는 기존 HTML/shared/assets/previews/recordings만 제공하며 plans·작업자 로그와 임의 파일을 노출하지 않는다.

GET /api/text-pipeline, POST /api/text-pipeline/selection, GET /api/text-pipeline/characters, GET /api/text-pipeline/characters/{id}를 제공한다. 선택 실패는 현재 값을 보존하고 활성 작업은409다. 캐릭터 경로와 revision·symlink를 검사하고 원장 읽기는 바이트/행/개수 상한을 둔다. 최근50개 텍스트 호출과 알려진 문서의 제한된 본문을 반환하며 textTruncated를 표시한다. 실제 sourceGeneration과 selectedConfiguration은 구분한다.

별도 시안의 shared/text-pipeline.js/.css는 mount가 반환한 컨트롤러의 open/close로 동작한다. 프로필/경로·역할 모델·실제 기록을 렌더링하며 로딩/오류/오프라인/빈 상태·포커스 트랩과 복귀를 처리한다. 기본 테스트 덱 스냅샷을 시연 작업대에 적용하고 프롬프트 조립은 호출0회로 표시한다. 실제 실행/관문 처리는 기존 /c-glass.html?character=...로 이동한다.

v1.12 변경(2026-10-30): 기존 글래스 시안과 텍스트 공정 API를 연결했다(D-0074).

워크숍 CLI의 --jobs-dir은 create_app의 jobs_dir override로만 적용한다. 모델 설정 파일을 복제하지 않고 실제 factory.toml의 후속 변경을 읽는다. 별도 검토 서버가 기존 작업 큐를 복구/수정하지 않게 하는 선택적 실행 옵션이다.

## 20. 실제 공장 화면 연결 구현(명세 §22)

web.runtime.install_runtime_routes를 create_app에 설치한다. GET /api/runtime/graph는 pipeline.graph.STAGES의 deps/needs/after/gate를 정렬한 배열로 반환한다. POST /api/runtime/characters {slug,brief}는 검증 뒤 새 캐릭터와 creator-input/brief-r1.md를 만들며 모델을 호출하지 않는다. JobManager 기본 러너는 저장된 브리프를 RunOptions.brief_text로 전달한다. 빈 값·큰 본문·중복 ID·경로 탈출과 손상 상태는 거절한다.

시안 d-ops.html은 shared/runtime.js/.css를 불러오고 기본 FactoryRuntime.mount를 사용한다. shared/ops.js는 ?mode=demo에만 초기화한다. 실제 렌더러는 기존 DOM 슬롯·글래스 토큰에 실제 목록·진행·그래프·관문·산출물을 보여 주며 시연 localStorage를 읽지 않는다. EventSource /api/events의 hello/state/gate/job를 snapshot 재조회 신호로 사용하고 재접속/주기 복구를 지원한다. 요청 경합은 선택 캐릭터별 최신 응답만 반영한다.

시작/재개는 POST /api/jobs를 사용하고, held 단계만 별도 confirm으로 요청한다. 실제 관문은 drawer 안 /gate.html?character=...&gate=... iframe에서 고르고 승인/수정한다. SSE로 부모 화면도 재조회한다. 실제 텍스트 자료와 호출은 기존 /api/text-pipeline/characters/{id}에서 읽는다. 취소·일시정지 API가 없으므로 실제 모드에서 그 버튼과 시연 제어를 숨긴다. 워크숍 factory.toml은 [orchestrator] auto_resume=true/max_parallel=3/resume_until=sx로 연결한다. 실행 API를 부르기 전에는 생성이 없다.

v1.13 변경(2026-10-30): 기본 실제 모드·브리프 보존·실행/관문/이벤트 연결을 추가한다.

관문 iframe의 currentAnswer는 검토한 view.rev를 expectedRev로 함께 보낸다. 결정 API는 캐릭터 잠금 안에서 현재 상태를 다시 읽고 revision 불일치·이미 결정된 관문을409로 거절한다. 기존 CLI/API 호출은 expectedRev를 생략할 수 있다.

최종 보완: runtime 그래프는 기존 reads.LANES도 반환해17단계를8갈래 작업대로 배치한다. 생성은 숨긴 staging과 파일 잠금·rename으로 완성 후 게시하며, 작업 큐는 state-v1과 subjectId를 함께 검증한다. 오래된 job-only 주소는 개별 작업 API로 캐릭터를 복원하고 모든 작업 ID는 jobId를 정규화한다. 관문 iframe은 embedded=1에서 내부 탐색을 숨기고 Escape/포커스 복귀를 부모와 연결한다.

## 21. QLoRA 실제 연결 구현(명세 §23, D-0077·D-0078)

**학습 공급자.** `providers/training/gemma_qlora.py`의 `GemmaSettings` 기본값은 머스크 N3b 프로토콜이다(revision 8e256fc6d63003fc0ca8c91b976e6dcc38433385, gemma-4-thinking, r16/α32, LR 5e-5 constant_with_warmup, warmup 5%, adamw_8bit, weight decay 0.001, 배치 1×4, 4,096토큰, 2 epoch, 체크포인트 0.5/1/1.5/2, 고정 버전 unsloth 2026.10.3·torch 2.10.0+cu128·transformers 5.5.0·trl 0.23.1·peft 0.18.1·datasets 4.3.0·bitsandbytes 0.50.2). 비용 추정은 스텝당 8.7초(N3b 236스텝 2,060초 실측), 준비 900초, 선별 생성당 12초+420초, 시간당 $0.90이다. `ssh_host`가 없으면 임대 모드다. 제출은 데이터 조각 전송·해시 확인 → 원격 스크립트 세 개 확인 → `screen/requests.jsonl` → `job.sh`(학습 → 성공 시 선별 → `job-exit.json`)를 `nohup timeout`으로 실행한다. 상태는 `complete.json`과 `screen-complete.json`·`job-exit.json`으로만 판정한다. 회수는 체크포인트·선별 파일 해시를 확인한 뒤 원격 폴더를 지우고 GPU를 삭제한다. `abort`는 로그를 남기고 GPU를 지운다.

**원격 스크립트.** `remote/train_qlora.py`는 FastModel·get_chat_template·언어 층 LoRA·`train_on_responses_only("<|turn>user\n", "<|turn>model\n")`·SFTConfig(max_length, packing 없음, bf16)를 쓰고, 지도 토큰 0인 대화·최대 길이 초과·collator 라벨 변경·버전 불일치를 학습 전에 거절한다. step 목표로 0.5 epoch마다 어댑터를 저장하고 검증 loss를 기록한다. `remote/screen_qlora.py`는 기반 모델을 한 번 올리고 base·체크포인트 어댑터를 차례로 붙여 첫 출력만 남긴다. `remote/serve_qlora.py`는 127.0.0.1의 `/v1/generate`·`/health` 서버다.

**GPU 임대.** `providers/training/vast.py`의 `VastLease`는 vastai CLI(--raw)로 잔액 확인 → 조건 제안 중 최저가 → 고유 라벨 생성 → 애매하면 라벨로 찾기(재생성 금지) → running·22/tcp에서 로컬 공개 키 attach(한 번) → SSH 확인 → 삭제·목록 부재 확인 순서를 `lease.json`에 기록한다. 템플릿 해시는 머스크 학습과 같은 c412724d111f171ee3c8554066ba564d다.

**선별과 선택.** `providers/training/screening.py`가 검증 분할에서 단발 24·6턴 장면 2개를 뽑는다. `stages/s10_train/select.py`의 `select_checkpoint`가 결함 지표(빈 답·잘림·4-gram 루프·직전 답 반복·조기 중단·길이 중앙값)로 적격 구간을 정하고, `prompts/checkpoint_pair_judge.md`로 정순·역순 짝 판정해 `checkpoint-selection-v1`을 쓴다. `stages/s10_train/collect.py`가 선택을 binding에 반영한다. `stages/s10_train/drive.py`의 `drive_s10t`가 상태 확인 → 회수·선택을 끝날 때까지 몰고, 예외·중단이면 모든 미완료 실행을 abort한다. `run_s10t`는 제출된 revision이 있으면 새 계획 없이 이어 간다. 명령은 `cfp train drive|cleanup`이다.

**평가.** `providers/training/inference.py`의 `GpuInferenceSession`이 어댑터 업로드·서버 기동·ready 대기·SSH 포트 전달·정리를, `GemmaAdapterChat`이 평가 대화 포트를 맡는다(기본 최대 32,768토큰, 미검증). `[stages.s10] gpu_seconds_per_turn`·`gpu_budget_usd`로 비용을 확인한다. 사전 등록은 미설정 공급자의 SFT 조건을 빼고, judge·metrics·report는 등록된 조건만 다룬다.

**패키지.** `stages/s11_release/package.py`의 `collect_serving`이 `sft/serving.json`(`sft-serving-v1`)을 쓴다. 어댑터 해시는 회수 때의 원격 완료 기록과 대조하고, 선택 기록의 체크포인트와 채택 binding이 다르면 막는다.

**창작 인물 정책.** `common/qlora_policy.py`가 `resources/qlora-authored-policy-v1.json`(정본은 `docs/guides/qlora-authored/policy-v1.json`)을 읽는다. S9 적용과 S10 보고서 연동은 같은 정책을 쓴다(세부는 이 절 끝의 S9·S10 보완을 따른다).

**독립 검토 반영(2026-11-02).** 원격 세 스크립트는 버전 검사 직후 Unsloth를 다른 학습 패키지보다 먼저 불러온다. 학습 전에는 모든 행의 로컬 토큰화 일치, BOS 한 번, 길이, 지도 토큰, 모든 샘플의 collator 라벨 보존을 확인한다(`data-check.json`, `collator-label-parity-confirmed.json`). 행에 `supervisedAssistantIndexes`가 있으면 그 assistant 턴만 지도한다(원본 masking.select_labels). 없으면 모든 assistant 턴을 지도하며, 이 점이 N3b(선택 턴 지도)와 다르다. 마감에 닿으면 `checkpoints/budget-partial`을 남긴다. 선별은 자동 재시작을 거절하고 어댑터 텐서 일치와 wire 해시를 기록한다. 종료 이유는 EOS로 판정한다.

GPU 비용 안전: 임대 전에 분리 프로세스 `cfp train guard`(`stages/s10_train/guard.py`)를 띄우고 준비 기록이 없으면 빌리지 않는다. guard는 `guard.json`에 한 번 정한 마감(학습 벽시계 상한 + 준비 대기 상한 + 회수 여유 2시간)과 잔액 하한을 넘으면 인스턴스를 지운다. drive는 제출을 abort 구간 안에서 하고 SIGTERM·SIGHUP을 중단으로 바꾼다. 재실행은 지워지지 않은 lease가 있으면 같은 revision을 이어 간다. 회수는 크기 비례 시간 제한과 재시도를 쓰고, 끝내 실패하면 GPU를 남긴 채 `collectError`를 기록해 멈춘다(다음은 `cfp train collect`→`cleanup`). `cleanup`은 모든 tr과 `s10-eval/*/inference`의 lease를 훑고 ID 없는 기록은 라벨로 지운다.

선택과 binding: 회수 직후 run을 binding 없이 `selection.decision = PENDING`으로 먼저 쓰고, 선택이 DEVELOPMENT_RECOMMENDED·INCONCLUSIVE일 때만 고른 체크포인트를 binding으로 남긴다. KEEP_INCUMBENT·BLOCKED_*는 binding이 없어 평가 진입점이 학습 없이 진행할지 묻는다. 선택이 실패하면 다시 돌릴 때 원격 재접속 없이 선택만 다시 한다. 패키지는 선택 결정이 KEEP_INCUMBENT·BLOCKED_*이거나 선택 체크포인트가 binding과 다르면 serving을 막는다. 사전 등록은 학습 revision을 숫자 순으로 읽는다.

v1.14 변경(2026-11-02): §21을 더하고 §8.9의 Gemma 기본값을 D-0077로 바꿨다.

## 22. 공식 API 직접 연결 구현(명세 §24, D-0079)

### 22.1 파일 소유

갈래 작업자는 같은 작업 폴더에서 동시에 일하므로 아래 표에 적힌 파일만 고친다. 표에 없는 파일이 깨지면 고치지 않고 통합(E)에 알린다. 편집은 apply_patch로 해당 부분만 바꾸고 파일 전체를 다시 쓰지 않는다. commit·push·실제 네트워크 호출은 하지 않는다.

| 갈래 | 고치는 파일 | 새 테스트 |
|---|---|---|
| A 호출 경로 | 새 `common/api_routes.py`, `common/text_deck.py`, `web/text_pipeline.py` | `tests/test_api_route.py` |
| B 요청 형식 | `providers/openai_compat.py`, `providers/base.py`, `common/errors.py` | `tests/test_openai_dialect.py` |
| C 단가표 | 새 `common/pricing.py`, 새 `resources/price-table-v1.json`, `common/config.py` | `tests/test_pricing.py` |
| D 기록·예산·보고 | `providers/tracked.py`, `common/ledger.py`, `common/budget.py`, `pipeline/context.py`, `cli.py`, 새 `common/cost_report.py` | `tests/test_cost_recording.py`, `tests/test_cost_report.py` |
| E 통합 | `factory.example.toml`, `.env.example`, `docs/`, 갈래 사이에서 생긴 기존 테스트 수정 | 없음 |

경로는 `src/character_factory_poc/` 아래 기준이다. 기존 테스트가 자기 갈래의 변경 때문에 깨지면 그 갈래가 고친다.

### 22.2 갈래 사이 계약

**A → D.** `api_routes.FAMILY_DEFAULTS`는 `{"openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"}, "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "api_key_env": "GEMINI_API_KEY"}}`다. `family_of(model: str) -> str | None`는 `gpt-` → `"openai"`, `gemini-`·`google-antigravity/gemini-` → `"gemini"`, 그 밖은 `None`이다. `official_model_id(model: str) -> str`는 `google-antigravity/` 접두사를 뺀다. `billing_for(cfg: ProviderConfig, route: str | None = None) -> dict`는 `{"route": str, "family": str | None, "class": "api_billed" | "relay_equivalent" | "unverified" | "none"}`를 돌려준다. `class`는 어댑터가 `fake`면 `none`, 주소 호스트가 `api.openai.com`이나 `generativelanguage.googleapis.com`이면 `api_billed`, `127.0.0.1`·`localhost`면 `relay_equivalent`, 그 밖은 `unverified`다. `route` 인자가 없으면 `direct`(덱 밖 공급자) 또는 `fake`를 넣는다.

`text_deck.resolve`는 `route == "api"`를 받아 모델 계열의 기본값에 `[text_pipeline.routes.api.families.<family>]`의 `base_url`·`api_key_env`·`timeout_s`를 덮고, 모델 ID는 `[text_pipeline.routes.api.models]` 매핑 → `official_model_id` 순으로 정한다. 계열을 정할 수 없으면 `ValueError`다. opencodex·test 경로의 반환값은 바꾸지 않는다. 형성 fingerprint가 해석 결과를 쓰기 때문이다. `api` 경로의 반환값에는 `family`를 더한다. 키 값 확인은 하지 않는다(호출 전 확인은 기존 `Context.task_model`이 한다).

**B → D.** `ChatResponse`와 `VisionResult`에 맨 끝 필드 `usage: dict | None = None`을 더한다. 값은 `usage-v1`(`inputTokens`, `cachedInputTokens`, `cacheWriteTokens`, `outputTokens`, `reasoningTokens`, `finishReason`, `usageSource`)이며 모르는 값은 `None`이다. 기존 `input_tokens`·`output_tokens`도 같은 값으로 채운다(`output_tokens`는 보정한 청구 출력). `errors.ProviderRequestError(FactoryError, RuntimeError)`는 `status: int`, `provider_message: str`(앞 500자, 키 값 가림)를 가진다. 형식 선택은 `openai_compat.request_dialect(base_url) -> "openai" | "gemini" | "generic"`, 사용량 정리는 `openai_compat.normalize_usage(data: dict) -> dict`다.

**C → D.** `pricing.PriceEntry`(frozen dataclass)는 `model`, `family`, `effective_from: date`, `effective_to: date | None`, `input_per_million: float | None`, `cached_input_per_million: float | None`, `cache_write_per_million: float | None`, `output_per_million: float | None`, `source: str`, `checked_at: str`, `basis: "table" | "config_override"`를 가진다. 함수는 `canonical_model(model) -> str`(`google-antigravity/`·`openai/` 접두사 제거), `lookup(model, at: datetime, overrides: dict | None = None) -> PriceEntry | None`, `estimate(usage: dict | None, entry: PriceEntry | None) -> dict`(`{"usd": float | None, "upperBound": bool, "reason": str | None}`), `price_ref(entry) -> dict | None`(`table`, `model`, `effectiveFrom`, `effectiveTo`, `source`, `basis`), `max_rates(models, at, overrides=None) -> tuple[float, float] | None`다. `FactoryConfig.pricing`은 `[pricing.models."<id>"]`의 `input_per_million`·`cached_input_per_million`·`output_per_million`을 담는 dict이며 기본값은 빈 dict다. 덮어쓰기는 기간과 무관하게 우선한다.

**D.** `Ledger.record_call`에 키워드 인자 `cached_input_tokens`, `cache_write_tokens`, `reasoning_tokens`, `finish_reason`, `usage_source`, `price`, `billing`, `error_status`를 더하고, 값이 `None`이 아닐 때만 행에 쓴다. `TrackedTextModel`·`TrackedVisionModel`은 `billing`과 가격 덮어쓰기를 받아 성공 호출의 비용을 계산한다. `billing.class`가 `none`이면 단가를 찾지 않고 `estCostUsd`를 `None`으로 둔다. `usage`가 없으면 `input_tokens`·`output_tokens`로 `usage-v1`을 만든다. 가격 조회 모델은 요청 모델(`inner.model`)이다. 실패 호출은 `ProviderRequestError`의 상태 코드를 `error_status`로 남긴다. `RunBudget.settle`은 보정한 출력 토큰을 쓴다. `Context.formation_budget`은 설정 단가가 없고 합성 예산이 아니면 현재 덱 해석 모델들의 `max_rates`를 쓰고, 미확인이면 지금처럼 `ValueError`로 거절하되 미확인 모델 이름을 알린다. `cost_report.build(rows, *, recompute=False, overrides=None, at=None) -> dict`는 `cost-report-v1`을 만든다. `cfp ledger report <id>`는 기존 출력에 `cost`를 더하고, `cfp ledger cost <id 또는 calls.jsonl 경로> [--recompute] [--out 파일]`은 보고서를 출력·저장한다. 재계산은 원래 원장을 고치지 않는다. `cfp models select --route`의 선택지에 `api`를 더한다.

### 22.3 통합 순서와 검사

1. A·B·C·D가 동시에 시작한다. D는 A·B·C의 계약을 `tests/` 안의 가짜 구현이나 monkeypatch로 대신하고, 실제 모듈이 생기면 그것을 import한다.
2. 각 갈래는 자기 테스트와 `uv run ruff check`·`uv run ruff format --check`를 통과시키고, 바꾼 파일 목록과 계약에서 벗어난 점을 보고한다.
3. E는 C → B → A → D 순서로 결과를 검토하고, 전체 테스트를 돌린 뒤 설정 예시·안내 문서·상태 문서를 갱신한다. 독립 검토를 한 번 받는다.
4. 실제 호출 확인은 사용자가 키를 넣고 실행을 지시한 뒤 `--execute`로 한다.

v1.15 변경(2026-11-04): 공식 API 직접 연결의 파일 소유·갈래 계약·통합 순서를 추가했다(D-0079).

## 23. 진행 화면 구현(명세 §25, D-0101)

- `pipeline.state`: `STAGE_EVENTS = "stage-events.jsonl"`, `stage_events_path(char_dir)`. `StateFile.transition`은 잠금 안에서 전이를 저장한 뒤 `{at, stage, from, to, rev, attempt, error}`를 `ledger/stage-events.jsonl`에 덧붙인다. OSError는 무시한다.
- `web.reads.stage_timeline(char_dir)`: RUNNING이 회차를 열고 AWAITING_HUMAN·APPROVED·CHECK_FAILED·REJECTED·SKIPPED가 닫는다. 닫힌 뒤 오는 APPROVED·REJECTED는 사람 결정(`decision`, `decidedAt`)이다. 열린 회차에 RUNNING이 다시 오면 앞 회차를 RESTARTED로 닫는다. 단계마다 최근 10회차를 남기고 파일은 끝 20,000줄만 읽는다. 깨진 줄은 건너뛴다.
- `web.reads.gate_timeline(char_dir)`: `opened` 사건이 `openedAt`을 새로 쓰고 `decided`가 `decidedAt`·`decision`을 쓴다. `cost_summary(char_dir)`: `Ledger.report()`의 `estCostUsd` 합, `totalCalls`, `unpricedCalls`. 호출 기록이 없으면 0, 읽지 못하면 None.
- `character_summary`: stages 행에 `startedAt`·`endedAt`·`decidedAt`, gates 행(`pendingGates` 포함)에 `openedAt`·`decidedAt`. `character_detail`: `history{stage: attempts[]}`와 `cost`. `state_signature`의 단계 값은 `[status, attempts, currentRev]`. `_lane_status` 순서는 gate, failed, running.
- `web.runtime`: `GET /api/runtime/graph`의 `stages[].paid`(`scheduler.paid_providers`)와 `orchestrator{autoResume, resumeUntil, maxParallel}`. `web.app`: studio 허용 목록에 `factory.html`.
- `studio/factory.html`, `shared/flow.js`, `shared/flow.css`. `flow.js`는 `runtime.js`의 순수 함수(`buildGraph`, `pendingGatesFor`, `extractHeld`, `runRequest`, `confirmHeldRequest`, `createCharacterRequest`, `gateUrl`)를 재사용한다. 팀 칸은 LANES id를 그리드 영역에 대응한다(appearance ap, scene sc, video vd, plan pl, persona ps, data dt, training tr, release pk). 같은 줄에서 칸을 건너뛰는 선은 사이 칸 위로 돌린다. 검토는 상세 영역의 `/gate.html?...&embedded=1` iframe이다. 갱신은 `/api/events` 신호를 받아 다시 읽고, 연결이 끊기면 30초마다 다시 읽는다. 시각 표시는 30초마다 다시 그린다.
- 시험: `tests/test_web_history.py`(8개), `studio/tests/flow.test.cjs`(6개).

v1.16 변경(2026-11-07): 단계 이력 기록, 읽기 모델 확장, 진행 화면 구현을 추가했다(D-0101).

## 24. 브랜드·토큰·테마 구현(명세 §26, D-0102)

- 토큰: `studio/shared/foundry-tokens.css`와 `src/character_factory_poc/web/static/shared/foundry-tokens.css`(같은 내용). 변수 접두사 `--fd-`. 기본 색 `--fd-slate-1..12`, `--fd-violet-*`, `--fd-blue-*`, Primer 상태 `--fd-attention-*`·`--fd-success-*`·`--fd-danger-*`·`--fd-done-*`. 의미 토큰 `--fd-bg-*`·`--fd-fg-*`·`--fd-line*`·`--fd-primary-*`·`--fd-accent-*`·`--fd-run-*`, 간격 `--fd-space-*`(4pt), 모서리 `--fd-r-*`(4/6/8/12), 그림자 `--fd-shadow-*`(떠 있는 층). 테마 선택자는 `:root,[data-fd-theme="light"]`, `[data-fd-theme="dark"]`, 속성이 없을 때 `@media (prefers-color-scheme: dark)`.
- 진행 화면: `studio/factory.html`은 파비콘, 첫 그림 전 테마 읽기(localStorage `fd-theme`), `.fd-shell`(`.fd-side`, `.fd-head`, `.fd-canvas`, `.fd-inspector`)과 `.fd-sheet`·`.fd-scrim`을 둔다. `studio/shared/flow.css`는 토큰만 쓴다. 1439px 이하에서 사이드바를 아이콘 줄로, 1099px 이하에서 사이드바를 숨기고 `.fd-pick` 고르기 목록을 보이며 인스펙터를 캔버스 아래로 내린다. 캔버스 컨테이너 질의(760px 이하)로 그래프를 한 줄로 쌓는다.
- `studio/shared/flow.js`: 순수 함수는 그대로 두고 `MARK`(로고 SVG)와 아이콘(sun·moon·monitor·inbox·plus·close)을 더했다. `mount`가 사이드바(브랜드, 새 캐릭터, 받은 일 수, 캐릭터 목록과 상태 점·할 일 수, 테마 버튼 `data-act="theme"`·`aria-pressed`, 이전 화면·모델 설정 링크), 머리줄(경로, 상태 알약, 지표, 연결 상태), 캔버스, 인스펙터(속성 목록, 미리보기, 회차 이력), 검토 시트를 그린다. 시트는 `gateUrl(...)`에 `&embedded=1&skin=foundry&theme=<지금 테마>`를 붙인 iframe이고 Escape·바깥 누르기로 닫으며 연 버튼으로 초점을 돌린다. 문서 제목은 "… · Foundry"다. 캐릭터 이름이 id와 같으면 제목 옆 id를 숨긴다.
- 관문 화면: `src/character_factory_poc/web/static/gate.html`이 토큰과 `shared/gate-foundry.css`를 읽는다. 머리 스크립트는 주소에 `skin=foundry`가 있을 때만 `body.fd`와 `data-fd-theme`을 붙인다. `gate-foundry.css`의 모든 규칙은 `body.fd` 아래에 있어 따로 연 관문 화면에는 영향이 없다. 글래스 변수를 토큰으로 다시 묶고, 안쪽 구획의 인라인 반투명 배경을 덮으며, 결정 옆 칸은 680px 폭까지 오른쪽 260px을 유지한다.
- 시험: `studio/tests/flow.test.cjs`에 토큰 두 사본 일치와 관문 덮어쓰기 범위(`body.fd`) 확인 1개를 더해 7개.

v1.17 변경(2026-11-07): Foundry 토큰·테마·3단 화면·관문 화면 테마 연결 구현을 추가했다(D-0102).

## 25. 개요·받은 일·그래프 보기·실패 기록 구현(명세 §27, D-0103)

- 서버: `pipeline/orchestrator._step`이 `AgentFormatError`와 문자열 코드의 `SystemExit`을 검사 실패로 다룬다(`_mark_failed`: RUNNING이면 CHECK_FAILED로 전이, 오류 2,000자까지). 그 밖의 `Exception`은 `_mark_failed` 뒤 다시 던진다. `web/jobs.py`는 `(Exception, SystemExit)`를 작업 실패로 기록한다. `web/app.py`의 `/api/projects`가 캐릭터마다 `held`(`_held`)를 싣는다. 시험 `tests/test_stage_failure_state.py`(형식·검사 실패 2개), `tests/test_web_queue.py`(목록 held).
- 경로: `#all`(전체), `#all/mine`(받은 일), `#all/run|fail|done`, `#c/<id>`(캐릭터). `flow.js`의 `summaryOf(c)`가 `viewsFor`·`buildTasks`로 멈춤·검토·유료 확인 수, 완료 수, 팀 8칸 상태, 순위(rank 0~6), 가장 오래된 대기 시각을 만든다. 사이드바(전체 캐릭터·받은 일·캐릭터 목록), 머리줄, 개요(`overviewHTML`, `rowHTML`, `<table>`, 760px 이하는 카드)가 이 값을 쓴다. 개요의 검토하기는 `state.pendingReview`와 `state.batch`(관문 id)를 두고 캐릭터 경로로 간다. `refresh`가 상세를 읽은 뒤 시트를 연다. `nextInBatch`가 같은 관문을 기다리는 다음 캐릭터(오래 기다린 순)를 고르고, 시트 머리와 결정 알림에 "다음 건"을 둔다.
- 그래프 보기: `factory.html`의 `.fl-view[data-view]`(svg + grid)와 `.fl-zoom[data-zoombar]`. `zoom = {z, x, y, h}`, 단계 `[0.75, 1, 1.25, 1.5, 2]`. 확대 중에는 보기 높이를 고정(`h`)하고 `.fl-grid`에 `translate·scale`을 준다. `drawEdges`는 보기 영역 기준 화면 좌표로 그린다. 포인터 끌기(5px 넘으면 이동, 뒤따르는 클릭 삼킴), 휠(Ctrl/⌘ 확대, 확대 중 이동), 보기 영역 키(+ − 0, 화살표). 크게 보기는 `.fd-shell.focus`, Esc로 끈다. 760px 이하 컨테이너에서는 확대를 끈다.
- 할 일: 실패 항목은 `failReason`의 요약, `N회차 실패`, 2회차 이상이면 `copy-error`(클립보드에 캐릭터·단계·회차·오류·회차별 오류). 앞 단계가 끝났고 작업이 없으며 `lastJob.blocked`에 없는 목표 범위 단계는 `ready` 항목(이어서 실행). 다시 실행은 `runRequest(id, currentUntil() || resumeUntil)`. `currentUntil`은 실행 확인·단계 하나짜리 작업을 뺀다. 결정 알림은 할 일 아래에 둔다.
- 유료 확인: `state.confirming`이 있으면 할 일 줄에 `confirmHTML`(공급자, "견적 없음", 지금까지 추정 비용)과 `confirm-go`·`confirm-cancel`. 비용 값이 없으면 머리줄은 "—".
- 시트: 열면 `.fd-shell`에 `inert`. 관문 화면(`shared/gate.js`)이 결정 저장 뒤 `postMessage({type:'foundry:gate-decided', characterId, gate, decision, status})`, Escape에 `{type:'foundry:close'}`를 보낸다(같은 출처만 받음). 받은 상태가 AWAITING_HUMAN이 아니면 시트를 닫고 알림을 남긴다(G7a 묶음별 결정은 유지). 같은 관문의 상태 비교 알림은 60초 동안 겹치지 않게 뺀다. 반려는 `window.confirm`으로 한 번 더 묻는다. `render`는 다시 그리기 전후로 초점 요소(id·data-act·data-gate·data-stage 등)와 입력 커서를 되살린다.
- 토큰: `--fd-fg-subtle`을 밝은 화면 slate-10·11 반반, 어두운 화면 6:4 혼합으로 바꿔 보조 글자 대비를 AA로 올렸다(두 사본 같음).
- 시험: `studio/tests/flow.test.cjs` 8개(실패 문구·회차·복사·이어서 실행·서버 차단 제외·회복 알림 추가).

v1.18 변경(2026-11-07): 개요·받은 일·다음 건, 그래프 확대·크게 보기, 실패 기록·이어서 실행, 유료 두 단계 확인, 시트 결정 알림·초점 구현을 추가했다(D-0103).

## 26. 관문 화면 문장·블라인드 비교 구현(명세 §28, D-0104)

- `web/static/shared/gate.js`: `DECISION_KO`·`VERDICT_KO`·`PICK_KO`·`ARM_KO`·`METRIC_KO`·`STAGE_KO`·`GENDER_KO`로 코드를 한국어로 보인다(보내는 값은 그대로). 모든 안내·배너·오류 문장을 해요체로 바꿨다. 메타 줄은 이름·판·상태만, 결정 기록 배너는 결정·검토자(user 제외)·시각만 보인다. 사전 검토가 없을 때 안내는 AWAITING_HUMAN에서만 보인다. G1 생성 지시와 G7a 상황 설정은 `details.card-tech`, G6은 표본 응답 → `details.gate-more` 안의 프롬프트 원문 순서다.
- G8: `renderEval`이 쌍 카드(`article.pair`, 머리줄에 번호·상태·선택 버튼과 단축키, 앞 대화 `details.pair-history`, 마지막 사용자 말)와 고정 막대(`.blind-bar`: 수·막대·`data-next-pair`·단축키 안내)를 그린다. `applyPick`이 고른 값을 반영하고 `sessionStorage`(`fd-blind:<캐릭터>:<관문>:<판>`)에 남긴 뒤 다음 안 고른 쌍으로 초점·스크롤을 옮긴다(움직임 줄이기 설정을 따름). 다 고르면 채택 칸으로 간다. `onEvalKey`는 입력 칸 밖에서 1·A/2·B/3/N/P를 받는다. `updateBlind`가 수·막대·지표 열기와 결정 버튼 잠금, 결정 칸 안내 문장을 맞춘다. `restorePicks`는 같은 판의 쌍만 되살린다.
- `gate.html`: 결정 칸은 버튼 → 상태 줄 → '메모 남기기(선택)'(이유·검토한 사람·걸린 시간) → '기술 정보'(보낼 답 미리 보기) 순서다. 검토한 사람은 `localStorage`의 `fd-reviewer`를 채운다. 파일 목록·기록 원문은 '기술 정보 · …'로 이름을 바꿨다. 스타일은 `gate.css`(공통)와 `gate-foundry.css`(시트)에 더했다.
- `web/gate_items.py`: 얼굴 고르기 `helper` 문장을 바꾸고 `_plain_rationale`이 `listCount`·`memberCount`·`popularity`로 근거 문장을 만든다(값이 없으면 보고서 문장 그대로).
- 시험: `tests/test_gate_copy.py`(관문 화면 문자열에 '-다'체·개발자 말이 없는지, 기술 정보가 결정 버튼 뒤에 있는지, 근거 문장).

v1.19 변경(2026-11-08): 관문 화면 해요체·개발자 말 접기, G8 블라인드 비교 진행 막대·단축키·잠금·보존을 추가했다(D-0104).

## 27. 얼굴 고르기 갤러리 구현(명세 §29, D-0105)

- `stages/s1_reference/preview.py`: `face_counts(n_clusters, total, low, high)`, `VARIATION_HINTS`(n번째 얼굴 각도·표정 문장), `generate_previews(per_cluster: int | list[int])`. 미리보기 `settings.variation`에 n이 남는다.
- `stages/s1_reference/run.py`: `DEFAULTS`에 `faces_total = 10`, `min_previews_per_cluster = 2`, `previews_per_cluster = 3`(외모군당 최대). `preview_counts(cfg, n)`이 배분한다(`faces_total = 0`이면 고정 장수). `plan_calls`는 최대 외모군 수 기준 합을 예산에 올린다. `faces.py`(다시 만들기)도 같은 배분을 쓴다. `ReportSettings.previewsPerCluster`는 외모군당 최대 장수다.
- `web/gate_items.py`: 얼굴마다 `variation`, 추천은 추천 외모군의 첫 얼굴만. 도움말 문장 갱신.
- `web/static/shared/gate.js`: `renderFaces`가 칩·그리드·비교·트레이 자리를 만들고 `paintFaces`가 상태(`state.face`, `faceLikes`(최대 3), `faceCompare`, `faceFilter`)로 그린다. `paintFaceSide`가 `gate.html`의 `[data-side-extra]`에 고른 얼굴·태그·각도·근거를 보이고 주 버튼 이름을 '얼굴 N로 확정'으로 바꾼다. 키: 1~0(보이는 순서), S(추리기), Esc(비교 닫기). 결정 기록이 있으면 `referencePreviews` 또는 `selections`의 얼굴을 고른 상태로 잠가 보인다. `buildFaces`는 `state.face`로 답을 만든다.
- 스타일: `gate.css`(공통), `gate-foundry.css`(시트).
- 시험: `tests/test_reference.py`(배분 규칙, 외모군 3개 × 3장, 각도 문장, 예산 14회), `test_face_once.py`·`test_codex_image.py`·`test_hero.py` 기대값 갱신.

v1.20 변경(2026-11-08): 얼굴 장수 배분과 G1 갤러리 구현을 추가했다(D-0105).

## 28. 기획안 가로 비교표 구현(명세 §30, D-0106)

- `web/static/shared/gate.js`: `planRows(plans)`가 줄(묶음, 이름, 값 함수)을 만들고 값의 JSON 문자열로 `diff`를 정한다. `renderPlans`가 머리·막대·표 자리·접는 고치기 칸을 만들고 `paintPlans`가 `state.planPick`·`state.planOnlyDiff`로 표를 그린다(열 수 × 150px + 112px보다 좁으면 가로로 넘긴다). `paintPlanSide`가 결정 칸 요약과 주 버튼('안 N로 확정')을 맞춘다. 숫자 키 1~N은 `onPlanKey`. 결정 기록이 있으면 `selections`의 안을 고른 상태로 잠근다. `renderPlanFields`는 `FIELD_KO` 칸 이름을 쓰고 같은 안이면 다시 만들지 않는다(고치던 내용 보존). `buildPlans`는 `state.planPick`을 쓴다. 얼굴·기획안 버튼 문구는 `ro()`로 '로/으로'를 맞춘다.
- `web/gate_items.py`: G3 도움말 문장 해요체.
- 스타일: `gate.css`(공통), `gate-foundry.css`(시트, 고치기 칸 이름 열 110px).

## 29. 챕터별 배경 줄 구현(명세 §31, D-0107)

- `web/static/shared/gate.js`: 상태 `bgPicks`(챕터 → 후보 id 또는 `custom`)·`bgCustom`·`bgOpen`·`bgCurrent`. `bgRestore`가 결정 기록(`picks`·`custom`) 또는 `selection.json`에서 고른 값을 한 번 읽는다(기록 원문은 `selections`에 `custom:chN`만 남기므로 글은 선택 파일에서 읽는다). `renderBackgrounds`가 머리·고정 막대·줄 자리·접는 '다시 만들 때 고칠 점'을 만들고 `paintBackgrounds`가 줄을 그린다(줄 머리 `bgLabel`은 `ch1` → '1장'). 후보 칸은 `data-bg-pick="chN|후보 id"` 버튼이고 사진 비율은 `aspectRatio`(기본 9/16)다. `paintBgMeta`는 글을 적는 동안에도 줄 상태·막대·결정 칸 요약·주 버튼 잠금을 맞춘다(입력 칸은 다시 그리지 않는다). 고르면 `pickBackground`가 고르지 않은 다음 챕터로 옮기고, 직접 적기를 고르면 그 입력 칸으로 초점을 옮긴다. 숫자 키·N/P는 `onBackgroundKey`. 좁은 화면에서 줄이 넘치면 고른 후보 자리로 가로 위치를 옮긴다. `buildBackgrounds`는 `state`에서 `picks`·`custom`을 만들고, 다시 만들기 메모가 비면 접은 칸을 열고 첫 칸에 초점을 둔다. `customCard`·`collectPicks`는 G4b가 계속 쓴다.
- 스타일: `gate.css`(공통, 820px 이하 없음·640px에서 흐름 줄바꿈·520px에서 칸 42%), `gate-foundry.css`(시트).

v1.22 변경(2026-11-08): 챕터별 배경 줄 구현을 추가했다(D-0107).

## 30. 나머지 관문 화면 구현(명세 §32, D-0108~D-0114)

- 공통(`web/static/shared/gate.js`): 관문마다 상태를 `state`에 두고(`posePicks`·`frameVerdict`·`introPick`·`actionPick`·`sampleVerdict`·`pkgManual` 등) `render()` 끝에서 `paintPoses`·`paintFrames`·`paintIntro`·`paintActions`·`paintSamples`·`paintPackage`를 부른다. 결정 칸 요약·버튼 잠금은 각 `…Meta` 함수가 맡고 저장이 끝나면 다시 부른다. 결정 기록은 처음 한 번 `…Restore`로 읽는다. 크게 보기 창(`.frame-zoom`)은 G4·G5b가 같이 쓰고, Escape는 캡처 단계에서 받아 시트 닫기보다 먼저 닫는다(시트 닫기 처리는 `defaultPrevented`면 무시). 재생하지 못한 영상은 `watchClips`가 이유와 파일 링크로 바꾼다. 지난 판 수정 요청은 `lastAsk()`가 결정 기록에서 읽는다.
- G4b: `renderPoses`·`paintPoses`·`paintPoseMeta`·`pickPose`·`onPoseKey`·`buildPoses`. 표는 `plan-table`을 다시 쓰고 최소 폭을 둬 좁은 화면에서 옆으로 넘긴다. 세부 고치기는 칸을 벗어날 때 표에 반영하고 초점을 되돌린다. 쓰지 않게 된 `customCard`·`collectPicks`·`poseCard`·`tweakFields`·`chapterChangeSection`은 지웠다.
- G4: `renderFrames`·`paintFrames`·`paintFrameMeta`·`paintFrameZoom`·`setFrameVerdict`·`buildFrames`. 승인은 모두 괜찮을 때, 수정 요청은 고칠 챕터 메모가 다 있을 때 풀린다.
- G5: `renderIntro`·`paintIntro`·`introPlay`·`onIntroKey`·`buildIntro`. G5b: `actionGrid`·`paintActions`·`actionCell`·`paintActionBox`·`pickAction`·`onActionKey`·`buildActions`. 기록 보기는 `selections`(`actionId:candidateId`)로 쓰기를, 나머지를 뺌으로 되살린다.
- G7a·G7: `sampleClusters`(G7은 표본 한 묶음)·`paintSamples`·`paintSampleMeta`·`paintDatasetMeta`·`setSampleVerdict`·`onSampleKey`·`buildSamples`·`buildDataset`. 묶음을 보내면 `send` 뒤 아직 안 보낸 묶음 탭으로 옮긴다(진행 화면 시트는 `AWAITING_HUMAN`이면 닫지 않는다).
- G9: `pkgChecks`(자동 점검 7개)·`renderPackage`·`paintPackage`·`buildPackage`. 점검 항목을 누르면 해당 `details`를 열고 옮긴다.
- 서버(`web/gate_items.py`): `_sent_verdicts`가 `s9-data/<판>/qa/G7a-<묶음>.json`·`G7-<판>.json`의 판정·메모를 `sentVerdicts`·`sentNotes`로 준다.
- 스타일: `gate.css`(공통·좁은 화면), `gate-foundry.css`(시트).
- 시험: `tests/test_gate_copy.py`에 관문 종류마다 적힌 render·build 함수가 실제로 있는지 보는 시험을 더했다.

v1.23 변경(2026-11-08): 나머지 관문 화면 구현을 추가했다(D-0108~D-0114).

## 31. 동작 영상 판단 이월 구현(명세 §33, D-0115)

- 계약(`contracts/video.py`): `action-choices-draft-v1`(`characterId`·`actionRev`·`picks`·`excluded`·`recordRef`·`createdAt`, 쓰기와 빼기는 겹치지 않음).
- `stages/s6_actions/approve.py`: `REQUEST_CHANGES`에서 `_draft_choices`가 `picks`·`excluded`를 검사한다(이 판의 동작·후보만, 겹침·중복 없음, 일부만 있어도 됨). 관문 기록을 쓴 뒤 값이 있으면 `choices_path(char_dir, rev)` = `choices/G5b-<판>.json`에 한 번만 쓴다. 판 폴더와 그 manifest는 바꾸지 않는다. 틀린 값이면 관문 상태를 바꾸지 않고 파일도 만들지 않는다.
- `web/gate_items.py`: `actions()`가 `_carried_choices`로 `carried = {fromRev, picks, excluded, regenerated}`를 준다. 새 판 `inputs.json`의 `previousRev`·`regenerate`를 쓰고, 쓰기는 같은 후보가 `reusedFrom = previousRev`일 때만 넘긴다.
- `gate.js`: `buildActions`의 수정 요청에 `picks`·`excluded`를 담는다. `actionRestore`는 결정 기록이 없을 때 `carried`로 `state.actionPick`을 채우고 `state.actionCarried`에 수를 남긴다. 진행 막대에 'N칸 이어받음', 결정 칸에 남은 칸 안내, '남은 칸 열기'(`data-action-next`)를 둔다. 다 정하면 '남은 칸 열기'·'남은 칸 모두 첫 후보로'를 숨긴다.
- 시험(`tests/test_actions.py`): 이월 저장·판 폴더 불변·다시 만든 칸 제외, 틀린 값 5가지로 관문이 그대로인지.

v1.24 변경(2026-11-08): 동작 영상 판단 이월 구현을 추가했다(D-0115).

## 32. 사용성 정리 구현(명세 §34, D-0129)

- 서버: `GET /api/characters/{id}/stages/{stage}/plan`(S5·S6만). `Context(execute=False)`로 각 단계 `plan_calls`를 불러 `plans[{description, calls, estUsd}]`·`estUsd`(하나라도 모르면 null)·`adapter`·`model`·`unitPrices`·`reason`을 준다. 판 폴더를 만들지 않는다. `_StudioStaticFiles`에 `help.html`을 더했다. `gate_items.data_dataset`은 `plan.json`의 묶음 이름을 `clusterLabels`로 준다.
- `studio/shared/flow.js`: `displayName`·`revLabel`·`providerKo`·`gateSub`. 유료 확인은 `loadPlan`·`planText`·`confirmHTML`·`confirmAllHTML`('함께 보기', `confirm-all-go`는 `runRequest(id, 목표, [단계들])`). 결정 알림은 '방금 한 일'(`.fl-recent`)에 두고 '다음 검토'는 그릴 때·누를 때 `nextReviewAfter`로 다시 고른다(같은 캐릭터 → 다른 캐릭터의 가장 오래된 검토). 실패 할 일에 `help` 동작('막혔을 때 안내'), 설정에 `target-first`. 숫자 단위, 시트 제목 중복 제거, 범례는 svg 선(`.e.stop` 점선 9-3-2-3).
- `web/static/shared/gate.js`: `revLabel`·`GATE_KO`·`focusField`·`guardQuickApprove`(G3·G4a·G4b·G5b), `rejectQuestion`, `delayedSend`·`flushSend`·`cancelSend`·`releaseButtons`(5초), `postAnswer`, `onCommonKey`(⌘/Ctrl+Enter·?·Esc)·`toggleKeys`·`KEYS_BY_KIND`, `navStep`(J·K·N·P·→·←)과 `NAV_KEYS` 안내, `markScroll`(MutationObserver·resize·scroll로 `.scroll-hint`), G3 `renderPlanFields`·`collectEdits`의 `data-edit-kind`(text·number·lines·json), G7 `sampleSeen`, G9 `PKG_AFTER`, G8 `METRIC_HELP`, G5b `bulkActions`·`data-action-col`·`data-action-undo`. '내 차례예요'·'검토 모델 의견 없음' 배너는 머리줄 칩으로 옮겼다. 관문 이름 `name`은 진행 화면과 같은 규칙.
- `gate.html`: 결정 칸 아래 단축키·사용 안내 줄, 기술 정보 문구 '이 버전의 파일'. CSS: 접는 칸 ▸ 표시, 단축키 표, 스크롤 안내, 대기 중 상태 줄.
- 시험: `tests/test_web_gates.py`에 예상 비용 API(계획만, 가짜 공급자 0원, 잘못된 단계 404), `studio/tests/flow.test.cjs` 기대값('새 버전 만드는 중', '실행 N번 실패', '막혔을 때 안내', '운영 담당에게').

v1.25 변경(2026-11-08): 사용성 정리 구현을 추가했다(D-0129).

## 33. 모델 만들기 보기 구현(명세 §35, D-0130)

- 읽기: `web/model_path.py`의 `model_path(char_dir, state)` = `{material, dataset, training, eval}`. 데이터셋은 G7이 가리키는 `s9-data/ds<k>`의 `plan.json`·`index.jsonl`(클러스터·재료·분할 수)·`check-report.json`(경고·막는 문제)·`qa/G7a-<cluster>.json`(샘플 판정)·관문 기록. 학습은 최신 `s10-train/tr<k>`의 공급자 폴더마다 `training-run.json`·`lease.json`·`guard.json`·`checkpoint-selection.json`로 진행 줄 7칸(`ok·run·fail·warn·skip·idle`)과 상태(`locked·pending·plan·run·hold·done·stopped·fail·skip`)를 낸다. hold = 결과 받기 대기(`collectPending`) 또는 끝난 실행의 GPU 기록이 살아 있음. 쓴 돈 = lease 생성~삭제(또는 지금) 시간 × `dphTotal`. API `GET /api/characters/{id}/model-path`, 캐릭터 상세 `modelPath`.
- 쓰기: 작업 `action=train`(`confirm`에 `s10t`가 없으면 400, 학습 상태가 `plan·stopped·fail·hold·done·skip`일 때만). 최신 계획의 공급자가 모두 `PLANNED`면 `drive_s10t`, 아니면 `run_s10t`(이어 몰기 또는 새 계획). 끝나면(`stoppedAt=s10t`) `request_resume`. `action=skip-training`은 `skip-training.json`을 쓰고 기본 실행기로 이어서 돈다. `POST …/training/stop`은 도는 `train` 작업이 있을 때만 `stop-request.json`을 쓰고, `drive_s10t`가 확인마다(실제 시계로 오래 쉬면 2초마다) 보고 `DriveStopped`(BaseException)로 abort → `ensure_failed`. `POST …/training/release`는 작업이 없고 hold일 때 `cleanup_s10t` 뒤 실행 기록을 `CANCELLED`로 바꾼다.
- 오케스트레이터: 웹 실행(`opt.web`)은 학습 결과가 없고 최신 학습 계획에 `skip-training.json`이 없으면 s10을 `NeedsInputError`로 기다리게 한다(학습 없이 진행 G8을 바로 열지 않는다). `gpu_eval_held`: s10이 실제 Gemma 어댑터 폴더(`needs_gpu_eval`)로 평가하면 유료 실행 확인 대기로 둔다. 상세 `held`의 공급자는 `gpu: vast`, 예상 비용 API는 상한만 알린다.
- 공급자: `gemma_qlora` `status`는 원격 `state.json`(step)·`checkpoint-plan.json`(maxSteps)를 `appliedConfig.progress{phase, step, maxSteps}`로 남기고, 학습 뒤 선별 중이면 `phase=screen`. 가짜 학습 공급자는 `run_polls`(상태 확인 N번 동안 RUNNING, 스텝 증가)·`collect_failures`(결과 받기 N번 실패, 그동안 binding 없음)·`abort`를 받는다.
- 화면: `studio/shared/flow.js` `trainingStageView`(s10t·s10 상태를 학습 기록으로)·`trainingTasks`(hold는 맨 위 실패, plan·stopped·fail은 확인)·`modelMode`·`viewTabsHTML`·`mSteps·nowBarHTML·stepperHTML·srcHTML·dataHTML·trainHTML·evalHTML·modelPanelHTML`. 확인은 `state.mconfirm`(start·skip·stop·release) 칸으로 받는다. 학습이 돌면 3초마다 상세를 다시 읽는다. CSS `.md-*`.
- 시험: `tests/test_web_training.py` 7개(계획 상태·웹 실행이 평가를 기다림, 비용 확인 없는 시작 거절과 완료, 학습 없이 진행 → G8, 중단, 결과 받기 실패 → 다시 받기, 결과 버리고 반납, GPU 평가 확인 조건), `studio/tests/flow.test.cjs` 학습 상태·할 일.

- S9 재료 구간(D-0131): `samples.read_sns_sources(path, limit, window)` → `(sources, stats)`. 후보마다 앞뒤를 다듬고(사용자 시작·캐릭터 끝) 검사해 이유별로 버리고, window턴을 넘으면 `_windows`로 자른다(끝 자투리 4턴 미만은 버림). 구간은 `{sourceId: <세션>~w<k>, sessionId, turns}`이고 세션마다 첫 구간부터 돌아가며 놓은 뒤 limit으로 자른다. `skeleton_id`는 sessionId를 쓴다. `run_build`는 `sources(+used)`를 `check-report.json`에, `source_warning` 한 줄을 분할 경고에 더한다. 화면 읽기 모델은 `dataset.sources`·`dataset.notes`(클러스터 이름으로 시작하지 않는 경고)를 준다. 설정 `[stages.s9] sns_window`.
- S9 재료 출처(D-0134): 후보 줄의 `source`에 NIKL이 있으면 말뭉치, 나머지는 SNS다. 구간마다 `source`·`channel`(파일 값, 없으면 말뭉치 `call`·SNS `text`)을 붙인다. 출처마다 세션을 돌아가며 놓은 두 줄을 `_mix`가 합친다: 자리 n마다 `floor(n·corpus_share + 0.5)`개까지 말뭉치를 먼저 넣고 나머지는 SNS로 채운다. 말뭉치만 있으면 비율 1, SNS가 바닥나면 멈춘다(남은 말뭉치는 `over_share`). `batch_inputs`는 `sources`에 `origin`·`channel`을 싣는다. 통화 장면의 글자 표기 차단(`voice_channel_spoken`)은 D-0136으로 없앴다. 채널은 장면 설명과 말 리듬에만 쓴다. D-0137: 차단 검사 `no_emoji`는 모든 캐릭터 말에서 그림 이모지(U+1F000~U+1FAFF, U+FE0F)만 막는다. S8 공통 규칙은 `builtin:actor-system-rules-v4`(3행: 그림 이모지 금지, 자모 웃음·글자 표정 허용). `run_build`는 `sources.usedBySource`를 남긴다. 설정 `[stages.s9] corpus_share`(기본 0.2).
- S9 흐름 뼈대 재작성(D-0135): 작성 출력 `flowBeats`(SNS 재작성 3~8줄, 합성은 빈 배열)를 `Conversation.provenance.flowBeats`에 남긴다. `checks.overlaps(texts, sources, n=10)`는 `normalize`(공백·문장 부호·ㅋㅎㅠㅜ 제거) 뒤 원본 n-gram과 겹치면 True다. 차단 검사 `source_overlap`(메시지·뼈대·system+장면), `flow_beats`, `source_flow_turns`(|메시지 수 − 원본 턴 수| ≤ 2). `batch_problems`는 장면 겹침도 본다. 덱 수리는 `flowBeats`가 비면 원래 값을 잇는다. `run_build`는 `sources.rewrite=SKELETON`, `overlap{limit, checked, max}`(`longest_overlap`), `example{beats, origin, messages, sourceTurns}`를 남긴다. 화면 읽기 모델 `material.rewrite`는 보고의 값(없으면 옛 `TURN_ONLY`).
- S9 한소민 구성(D-0138): `training_prompt.build(pair)`는 `[PERSONA / …]` 칸(FACTS·LIFE_AND_TASTES·DISPOSITION·WANTS_AND_FEARS·READING_AND_TENSION·CHOICES·VOICE·KNOWS_AND_LIMITS, CHOICES는 예외·빈도 문장 제거) + `[TRAINING_RULES]`로 핵심을 만들고, `system(relationship, channel)`이 `[RELATIONSHIP]`·`[CHANNEL]`을 붙인다. `ensure(rev_dir, pair)`가 `training-prompt.json`을 남긴다. `Slot`에 `relationship`·`channel`, `make_slots`는 `assign_relationships(shares, start, n)`(자리마다 가장 모자란 관계)로 배정한다. `samples.write_batch`는 먼저 `seeds.attach`로 SNS 자리에 시드를 붙인다(`seeds/<sourceId>.json`, 원본 해시 확인, 없는 것만 한 번에 요청, 덱이면 `deck.request(task=scenarios, role=data_seed)`). `batch_inputs`는 시드가 있으면 원문 대신 `seed`·`sourceTurns`·`lengths`와 `assignments`·`turnMaxChars`를 싣는다. 검사: `turn_length`·`close_formal_opener`·`repeated_lines`(차단), `style_warnings`(경고). 덱 작성은 기계 검사 실패 때 문제를 메모로 최대 `max_retries`번 다시 쓴다. 설정 `[stages.s9] relationship_shares·synth_channel`, `[stages.s9.checks] turn_max_chars`.
- 학습용 프롬프트 연결(D-0139): `training_prompt.load/find/eval_system/relationship_for_stage`. `prereg.discover_bindings`는 `datasetRev`도 읽고, `_arms(..., rev_dir, relationship)`는 학습 모델 조건마다 `sft_prompt()`가 쓴 `s10-eval/<ev>/prompts/sft-system-<ds>-<rel>.md`를 promptRef로 쓴다(없으면 short.md). `eval_relationship(plan, relationship)`. S11 `collect_sft`는 `sft/training-prompt.json`과 `Sft.trainingPrompt`, `collect_serving`은 `SftServing.systemPrompt·systemAssembly`을 채운다. 화면 읽기 모델 `dataset.trainingPrompt`, `eval.sftPrompt`.

v1.26 변경(2026-11-08): 모델 만들기 보기 구현과 S9 재료 구간 자르기를 추가했다(D-0130, D-0131).

v1.27 변경(2026-11-08): S9 실제 대화 재료의 출처 섞기와 통화 장면 채널 규칙을 추가했다(D-0134).

v1.28 변경(2026-11-08): S9 SNS 재작성을 흐름 뼈대 + 양쪽 다시 쓰기로 바꾸고 원본 10글자 겹침 검사를 추가했다(D-0135).

v1.29 변경(2026-11-08): 한소민 구성(학습용 짧은 프롬프트·관계·채널 배정·흐름 시드·작가 지침·검사기)을 S9에 추가했다(D-0138).

v1.30 변경(2026-11-08): 학습용 짧은 프롬프트를 S10 평가 학습 모델 조건과 S11 서빙 기록에 연결했다(D-0139).

## 원문 근거 표준 구현 (2026-11-11, 명세 원문 근거 표준 절, D-0174)

- `evidence_source.py`: 순수 분리·표본 선정·근거 검사. 작성용 후보는 제한된 corpus 표본, 비교 원문은 제외한다.
- `evidence_pipeline.py`: 승인 원천과 G0/G3/S7 해시 결속, 사실표·장면 고정, 추출 1회, 후보별 구조 검사, `evidence-packet.json` 및 `evidence-review.json` 저장, 기존 `evidence_compiler.compile_prompt` 호출. 실패 시 `CHECK_FAILED`, 성공 시 기존 G6 `AWAITING_HUMAN`. 후보의 의미적 타당성은 모델 점수로 대체하지 않는다.
- `run_deck_s8`가 모티브 기본 경로에서 호출한다. V3 비교 실행은 명시적 설정만 허용한다. 예시 주입 설정은 표준 경로에서 허용하지 않는다.
- G6 `evidenceReviewed: true` 요구, 원천·후보 해시와 컴파일 결과 재검증, 승인기록에 근거 자료 해시 포함. 자동 진행은 G6를 건너뛰지 않는다. 수정 요청은 기존 rework 경로로 새 불변 revision 생성.
- 검증: 합성 원문으로 S0→G3→S7→S8→G6→시연 본문 연결, 비교 원문 유출·예시·낡은 승인·자동 승인 우회·누락근거·수정 재시도 회귀 검사. 실제 인물 품질 평가는 별도이며 이 구현 검증으로 대신하지 않는다.

## 전체 원문 공정 구현 (명세 전체 원문 공정, D-0176)

evidence_full_source.prepare_full_source는 안전 검사와 시간 경계로 나눈 모든 말차례를 chunk로 만들고 input/included/excluded coverage를 검증한다. 기본 24,000 JSON자 상한은 호출별 크기일 뿐 총량 표본 제한이 아니다. 최대 다섯 앞 말차례를 가능한 만큼 중첩하며 원문을 자르지 않는다. evidence_full_pipeline은 N개 discover, consolidate 1개, N개 audit 호출을 수행하고 단계별 JSON과 request hash를 저장한다. audit에는 모든 후보 결과가 있어야 하고 현재 chunk의 SUBJECT ID만 허용한다. 겹친 문맥의 상충 분류는 지지에서 제외한다. 후보 필드 다섯 개를 고정 문구로 조립하며 rule 요약은 v2 본문에 쓰지 않는다. evidence-review-v2가 coverage/auditCoverage/analysisArtifacts를 묶고 G6/시연에서 해시를 검증한다. 전체 읽기 누락, 미지원 근거, 반례, 예산 초과는 통과시키지 않는다. evidence_workers 기본2, 범위1~4; evidence_chunk_chars 기본24000, 범위6000~60000. 실험의 상한은 작업별 예산 원장으로 별도 지정한다.


## 2026-11-11 evidence-v3 구현(명세 v1.33)

evidence_atomic.py에서 unit의 SHA-256 순서로 약 1/4를 confirmation에 배정한다(최소 1, 총 최소 3 unit). 원자 형식은 section/function/dimension/trigger/behavior/exclusion/evidence다. audit 항목은 recordId/applicable/behavior/triggerReason/behaviorReason다. support는 조건 yes와 전체 행동 support에 한하며 context가 없거나 continuation의 next/followup이 없으면 unclear다. 중복 구간의 counter/unclear는 support를 제거한다. 구현 기본값은 발견 지지 2개 독립 unit+확인 지지 1개, 양쪽 counter 0이다. 이는 보수적 기계 필터이며 통계적 검증 기준은 아니다. 전수 대조란 모든 구간을 입력으로 읽힌다는 뜻이고 저장 인용은 후보당 구간별 지지 최대3/반례3/불명·범위밖2다. 관측 빈도 추정에는 쓰지 않는다. 한 번만 개발용 근거로 refine하고 모든 개발 구간을 reaudit한다. 확인 자료로 재수정하지 않는다. v1/v2는 명시 설정으로 재현 가능하며 evidence-v3는 선택 경로다. 전체 보류 결과로 기본은 evidence-v2를 유지한다.

형식 재시도는 revision 전체 공유 상한 10회이며 파일 잠금으로 병렬 예약한다. 남은 기본 호출+남은 형식 재시도를 실행 전 예산에 확인한다. 성공 캐시는 별도 receipt 해시로 변경을 탐지한다. v3의 receipt 누락은 자동 재사용을 차단하며 v1/v2의 이전 캐시는 과거 호환 경로로 유지한다. 구체 자음 표기를 예시로 포함한 원자는 최종 조립에서 보류한다.


## 2026-11-11 evidence-v4 구현(명세 v1.34)

evidence_tendencies.py는 section/function/dimension/trigger/realization/linguisticLevel/exclusion/observability/evidence를 추출한다. linguisticLevel은 morphology/syntax/discourse/lexical_register/turn_management다. 적용 조건이 prior_context가 아닌 후보는 보류한다. targets는 원문의 실제 응답 ID·이전 USER 목록·이전 SUBJECT를 고정한다. 판독은 responseTurnId/conditionTurnId와 각 원문 인용, applicability, functionMatch, formMatch를 반환한다. 서로 다른 기능·형식의 부분 지지는 공동 지지로 세지 않는다. 개발 공동 지지 2 unit·확인 1 unit은 구현상 반복 필터이며 품질 합격선이 아니다. variation 또는 unclear가 있으면 mixed로 남기며 조건부 선택지와 변이 한계를 조립한다. 지지 인용 수는 확률로 계산하지 않는다.

발견27/확인25처럼 원래 청크 안에서 unit이 분할될 수 있으므로 단계별 청크 수는 전체32와 다를 수 있다. 계산은 2×developmentChunks+confirmationChunks+1과 공유 형식 재시도10회다. v4도 캐시 receipt와 전체 분석 해시를 검증한다. compiler가 바뀌면 이전 CHECK_FAILED revision을 재사용하지 않고 새 revision을 만든다. G6는 AWAITING_HUMAN이며 자동 승인하지 않는다. 시연 비교는 검사된 실제 생성 본문을 사용하고 불변 facts·8섹션·무예시·조건 보존을 확인한다.

실행 보완: v4의 validate_transport는 후보별 정상 items와 오류 invalidItems를 분리한다. 오류의 원본과 이유를 그대로 보존하고 invalidCount를 근거 상태에 반영한다. 오류 인용을 고쳐 지지로 승격하지 않으며, 캐시를 읽을 때도 동일한 정규화가 멱등적으로 적용된다.

## 2026-11-11 evidence-v5 구현(명세 v1.35)

evidence_usage.py는 v4 실행기의 profile 훅으로 호출·카드 조립·집계·검토 메타데이터만 교체한다. 후보는 usageAxis 필드를 추가하고 audit item은 conditionBasis(explicit_user_act/visible_turn_sequence/response_derived/unknown)를 추가한다. 인용/말차례 오류는 invalidItems에 격리하며 조건 근거 미판정/응답 역산은 집계에서 unclear가 된다. evidence-usage-coverage.json과 review.usageCoverage는 각 축의 candidates/retained/status를 담는다. analysisArtifacts에 포함하여 변조를 검출한다. schemaVersion=evidence-review-v5, compiler=evidence-pipeline-v5이며 facts/role/scene와 무예시 계약은 pv6와 동일하다. CLI·시연·패키지·서비스 내보내기는 v5를 인식하고 이전 명시 버전을 유지한다.


## 2026-11-11 pv6 현행 표준 확정(D-0180)

version_for/selected·CLI 계획·motif_plan_calls·factory.example.toml의 기본값을 evidence-v4로 통일한다. 명시적 evidence-v5와 해당 산출물 읽기는 유지한다. 로컬 익준 미리보기는 순수 pv6 compose를 사용하고 임시 슬랭 지시를 제거한다. 기준 프롬프트 SHA-256과 실제 미리보기 본문 일치를 검증한다.


## 2026-11-11 프론트 생성 경로와 대화 보존(D-0181)

명세 v1.37에 따라 SourcePack/초안의 chapterTemplate 확장, S3/S8/챕터 매핑과 UI 선택을 연결한다. common.demo_chat의 provider는 명시적 demo_chat 설정을 우선하고 미설정 시 설정된 text 공급자를 사용한다. 로컬 Vertex와 서비스 인증 제한은 유지한다. chat_history API는 안전한 세션 ID·메시지 검증·동시 수정 충돌 검사를 적용한다. 브라우저 임시 기록을 우선 보존하여 이관하고 저장 오류를 표시한다. 실제 상태에서 진행률을 계산한다.


D-0181 상세: `GET /api/characters/{cid}/chat/sessions`, `GET/PUT .../{sid}`는 UUID 세션을 `chat-history/{sid}.json`에 원자 저장한다. POSIX 디렉터리 잠금·O_NOFOLLOW·revision 충돌(409)을 사용한다. 저장 한도는 2MiB/2,000메시지/메시지1Mi자이며, 새 모델 입력은 16,000자로 제한한다. 과거의 긴 메시지는 보관과 복원 대상으로 유지한다. UI는 임시 기록을 이관하고 새 대화/이전 대화 선택/저장 실패 재시도를 제공하며 충돌본을 새 세션으로 보존한다. 저장 API는 모델 호출과 분리한다. 모델 설정은 explicit demo_chat→configured text→legacy DEFAULT 순서이며 서버 모드의 Vertex 제한은 그대로다. FRIEND_CHAT/INTERVIEW 자동 표본은 장면별 3개×4턴을 사용하며 평가 질문은 최종 페르소나에 주입하지 않는다. 기존 FAN_CALL/FAMILY_CALL 표본 규칙은 유지한다.
