# 에이전틱 캐릭터 공장 상세 설계 (LLD)

- 문서 버전: v1.3
- 작성일: 2026-10-14
- 상태: 초안, 사용자 검토 전
- 근거: [PRD v1.3](../product/prd.md), [시스템 명세 v1.3](spec.md). 이 문서는 명세를 코드로 옮기는 세부만 정하고 다른 결정을 담지 않는다. 절마다 근거가 되는 명세 절을 `(명세 §n)`으로 적는다.
- 변경 이력: v0.1 최초 작성 / v0.2(2026-10-20) S1을 화제성 순위 → 외모 특징 프록시로 바꾸고 §2~§5·§8.1·§9~§13을 고쳤다(D-0017, D-0018) / v0.3(2026-10-20) 인물 인상 칸과 계약 v2(§5.2·§5.5·§8.1·§10, D-0020, D-0021) / v0.4(2026-10-21) G1 참조 사진·S2 구현(§2~§5·§5.7·§5.8·§8.1·§8.2·§9·§10·§12·§13, D-0022, D-0023) / v0.5(2026-10-21) S3 외모 연결, S4·G4 구현(§2~§5·§5.10·§8.3·§8.4·§12, D-0024~D-0026) / v0.6(2026-10-21) S5·G5와 xai_video·grok_web 어댑터(§2~§5·§5.11·§8.5·§9·§10·§12·§13, D-0028~D-0030) / v0.7(2026-10-21) 9:16 세로 첫 프레임과 `intro-inputs-v2`(§3·§4·§5.11·§8.5, D-0031), 실제 grok.com 화면에 맞춘 `grok_web`(§9, D-0032) / v0.8(2026-10-22) 씨앗 → 변형 기획, S3r 참고 자료, S4a·S4b·S4 배경 → 자세 → 완성 이미지, 갈래별 진행 오케스트레이터(§2~§6·§8.3·§8.3a·§8.4·§11·§12, D-0033~D-0035) / v0.9(2026-10-22) 이미지 자동 검사·수정 루프(§2·§3·§5.10b·§8.4a·§9·§11·§12, D-0036, D-0037) / v1.0(2026-10-22) S6 동작 영상 골격과 G5b(§2~§5·§5.11a·§6.1·§8.5a·§11·§12, D-0038, D-0039) / v1.1(2026-10-22) 앱 통화 영상 카탈로그, 무표정 첫 프레임, 계약 v2(§2~§4·§5.11a·§8.5·§11·§12, D-0040, D-0041) / v1.2(2026-10-27) 얼굴은 G1에서 한 장만 고르고 S2를 자동 기준 사진·동일인 검사로 바꿔 G2를 없앴다. 아직 코드에는 반영하지 않았다(§2~§4·§5.7·§5.8·§5.9·§5.17·§6.1·§8.1~§8.5·§11~§13, D-0042, D-0043) / v1.3(2026-10-27) 3일 PoC 계약: §4 명령(S1 수집·S9~S11·내보내기·웹앱), §5.14·§5.15·§5.17을 새 계약(`data-plan-v1` 등, `training-run-v2` 등, `character-package-v1`·`export-result-v1`)으로 바꾸고, §6.5 워크숍 API, §8.8~§8.11(S9 샘플·대량 두 단계와 G7a, S10 학습·평가 분리, 패키지, 우리 앱 내보내기), §9 어댑터(`grok_oauth`, 순위 수집기, `gemma_qlora`, `vertex_gemini`), §12 M8을 더했다(D-0044, D-0045)

## 1. 범위와 기준

R0(PRD §7)에 필요한 전부와, R1 단계의 계약·명령·알고리즘 골격을 정한다. R1 어댑터의 세부 인자는 착수 때 확인한다(§13). 언어·도구는 Python 3.12, `uv`, `ruff`, `pytest`, 명령 이름 `acf`다(D-0008).

## 2. 패키지 구조 (명세 §2)

```
agentic-character-factory/
  pyproject.toml
  scripts/check.sh
  src/acf/
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
[providers.text]       adapter = "openai_compat"; base_url = "http://127.0.0.1:10100/v1"; model = "gpt-6.1-sol"; api_key_env = "ACF_TEXT_API_KEY"
[providers.judge]      adapter = "openai_compat"; model = "anthropic/claude-opus-5-5"; api_key_env = "ACF_TEXT_API_KEY"
[providers.vision]     adapter = "openai_compat"; base_url = "http://127.0.0.1:10100/v1"; model = "google-antigravity/gemini-3.1-pro"; api_key_env = "ACF_TEXT_API_KEY"   # 이미지 생성(gpt)과 다른 계열(D-0010). 중계의 이미지 입력은 Q-0020
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
```

모델 이름·수치는 전부 제안이다. 키는 `api_key_env`에 적힌 환경변수 이름으로만 읽는다. 생성(`text`)과 판정(`judge`)의 모델 계열이 같으면 시작 시 경고한다(D-0010).

## 4. 명령 (명세 §2·§7)

모든 명령은 기본이 dry run이다. 외부 호출이 있는 명령은 `--execute`가 없으면 호출 계획(호출 수·예상 비용·입력 revision)만 출력한다.

| 명령 | 동작 |
|---|---|
| `acf brief new <slug> --from brief.md` | 브리프 Markdown을 `brief-v1`로 변환·검증·고정한다. 미정 항목은 `assumptions`에 기록한다. |
| `acf run <character_id> [--new-slug <slug>] --until <stage|gate> [--brief brief.md] [--seed seed.json] [--probes probes.txt] [--auto-approve G3] [--execute]` | 그래프를 따라 관문까지 연속 실행한다. 외모 축 캐릭터는 s1 → s2 → s3(씨앗·변형) → s5 → s3r → s4a → s4b → s4 → s7 → s8 순서이고, 한 갈래가 관문·씨앗을 기다리면 다른 갈래를 계속 돈다(D-0035). 이미 끝난 단계는 건너뛰고, 관문 대기나 CHECK_FAILED에서 멈춘다. `--auto-approve`는 실험 전용이며 기록에 남는다(D-0015). |
| `acf plan draft <slug> --brief brief.md [--execute]` | Planner 에이전트가 브리프와 프리셋 카탈로그(`[resources] stanford_presets_json`)로 기획서를 쓰고 G3 대기로 둔다. |
| `acf check <stage> <workspace>` | 작업 공간의 output.json을 계약·단계 검사로 확인한다. 에이전트가 `./check.sh`로 호출한다. |
| `acf status <id>` | 단계·관문 상태, 최신 revision, 대기 중인 관문을 표로 낸다. |
| `acf gate export <id> G<n>` | 검토 페이지 HTML을 만든다. |
| `acf gate import <id> G<n> --answer answer.json` | 결정을 기록하고 상태를 전이한다. 사람 시간을 함께 받는다. |
| `acf ref run <character_id> --ranking ranking.json [--new-slug <slug>] [--execute]` | S1 전체를 돈다: 순위 목록 고정 → 인물 묶기 → Scout 특징 태깅 → 정규화 → 군집 → 보고서 → 이름 유출 검사 → 미리보기 → G1 페이지. 결과는 G1 대기다. `acf run ... --ranking ranking.json`도 s1부터 돈다. `--ranking`이 없으면 `acf run`은 s1을 건너뛴다(페르소나 우선 경로, D-0013). |
| `acf gate import <id> G1 --answer answer.json` | G1 결정. `{"decision": "SELECT", "selections": ["c2"], "referencePreviews": ["c2-1"], "reviewer": ..., "minutes": ..., "reasons": ...}`. `referencePreviews`는 정확히 한 장이고 `selections`의 외모군 미리보기여야 한다(외모군은 고른 얼굴에서 정한다, D-0042). `selections`를 비우면 얼굴의 외모군으로 채운다. `--auto-approve G1`은 정렬 1위 외모군의 첫 얼굴을 고른다. `REQUEST_CHANGES`는 `note`(고칠 점)를 받고, 다음 `acf ref faces`가 얼굴만 다시 만든다. `REJECT`이면 다음 `ref run`이 새 `rf<k>`를 만든다. `s2`가 아직 `APPROVED`가 아니면(대기·`CHECK_FAILED`) G1을 다시 받아 다른 얼굴로 바꿀 수 있다. |
| `acf ref faces <character_id> [--execute]` | 얼굴 다시 만들기(D-0043). 직전 G1이 `REQUEST_CHANGES`일 때만 돈다. 같은 rf의 순위·인물·특징·보고서를 바이트 그대로 가져와 새 `rf<k>`를 만들고, 얼굴 미리보기만 메모를 붙여 다시 만든다. Scout를 부르지 않는다. 결과는 G1 대기다. |
| `acf hero run <character_id> [--execute]` | S2 기준 사진(D-0042, D-0043). G1 승인이 필요하다. G1 얼굴을 rev 폴더로 복사한다. `generate`면 기준 사진을 만들고 동일인 검사를 돌려 통과하면 외모 명세를 고정하고 `s2`를 `APPROVED`로 둔다. 끝까지 통과하지 못하면 `CHECK_FAILED`다. `picked`면 이미지 호출 없이 G1 얼굴로 바로 고정한다. 기본은 호출 계획(`generate`: 이미지 최대 3회, 판정 최대 6회)만 낸다. `acf run ... --until s2`도 s2를 돈다(외모 축을 탄 캐릭터만). |
| `acf gate import <id> G2 ...` | 없앴다(D-0042). "G2는 결번이다. 외모는 G1에서 고르고 S2는 자동으로 고정된다"는 오류를 낸다. `--auto-approve G2`도 받지 않는다. |
| `acf plan seed <character_id> [--file seed.json] [--personality ..] [--job ..] [--age N] [--gender female|male|other] [--background ..]` | 기획 씨앗을 `sd<k>`로 고정한다(D-0033). 대표 성격은 필수, 나머지는 비우면 에이전트가 채운다. |
| `acf plan variants <character_id> [--execute]` | S3 변형. 외모 명세(`s2` 승인)와 씨앗이 필요하다. 변형 3안과 G3 페이지를 만든다. |
| `acf plan own <character_id> --file mine.md [--execute]` | 직접 쓴 상세안을 Normalizer가 `u1` 하나로 정리하고 G3 대기로 둔다. |
| `acf gate import <id> G3 --answer answer.json` | 새 흐름 G3 결정. `{"decision": "SELECT", "selections": ["v2"], "edits": {"tagline": "..."}, ...}`. `APPROVE`는 첫 안. |
| `acf refs index --out index.json [--stanford catalog.json] [--personas <dir>] [--jsonl path:SNS14 ...]` | 참고 자료 색인을 `hash-v1`로 만든다(Git 밖 경로에 쓴다). |
| `acf refs select <character_id> [--execute]` | S3r. G3 승인이 필요하다. 색인이 없으면 건너뛴다. |
| `acf scene backgrounds <character_id> [--execute]` | S4a. 배경 후보와 배경 사진, G4a 페이지. |
| `acf gate import <id> G4a --answer answer.json` | `{"decision": "SELECT", "picks": {"ch1": "ch1-b2", "ch2": "ch2-b1"}, "custom": {"ch3": "한강 공원 벤치, 해질녘"}, ...}`. `APPROVE`는 챕터마다 b1. |
| `acf scene poses <character_id> [--execute]` | S4b. 장면 사실 작성(직접 정의 배경의 배경 사진 포함)과 자세 후보, G4b 페이지. |
| `acf gate import <id> G4b --answer answer.json` | `{"decision": "SELECT", "picks": {"ch1": "ch1-p2", "ch2": "ch2-p1"}, "custom": {"ch3": "..."}, "tweaks": {"ch1": {"hands": "..."}}, ...}`. `APPROVE`는 챕터마다 p1. |
| `acf frames run <character_id> [--execute]` | S4. 외모 명세(`s2` 승인)와 G4b 승인이 필요하다. 챕터마다 완성 이미지 1장(9:16). 직전 G4가 챕터별 수정 요청이면 그 챕터만 다시 만든다. |
| `acf gate import <id> G4 --answer answer.json` | `{"decision": "APPROVE"}` 또는 `{"decision": "REQUEST_CHANGES", "requestedChanges": [{"field": "ch2", "note": "..."}]}`. 승인하면 `approved-frames.json`을 쓴다. |
| `acf video intro <character_id> [--execute]` | S5. 외모 명세(`s2` 승인)가 필요하다. 기본은 후보 수·모델·해상도·길이와 예상 비용(USD)만 보여 준다. dry run에는 세로 첫 프레임 이미지 1장도 함께 나온다. 실행하면 세로 첫 프레임을 만들어 고정하고 후보를 제출·수집해 G5 대기로 둔다. 직전 실행이 원격 대기·실패로 멈췄으면 같은 rev에서 이어 간다. |
| `acf gate import <id> G5 --answer answer.json` | G5 결정. `{"decision": "SELECT", "selections": ["v2"], ...}`. SELECT면 `approved-intro.json`을 쓴다. |
| `acf video web-setup [--port 9222] [--profile ~/.acf/grok-chrome]` | `grok_web` 준비 안내: 전용 프로필 Chrome 실행 명령, 한 번 로그인, 설정 항목, `uv sync --extra web`. |
| `acf video actions <character_id> [--execute]` | S6. G4 승인이 필요하다. 기본은 무표정 첫 프레임 이미지 수와 동작 영상 편수(3챕터 × 동작 수 × 후보 수, 수정 요청 뒤에는 다시 만들 동작만)·모델·해상도·길이별 예상 비용만 보여 준다. 실행하면 G4 승인 이미지를 미소 첫 프레임으로 복사하고, 무표정 출발 영상이 있으면 챕터마다 무표정 첫 프레임을 만든 뒤 동작마다 제출·수집해 G5b 대기로 둔다. 직전 실행이 원격 대기·실패로 멈췄으면 같은 rev에서 이어 간다. |
| `acf gate import <id> G5b --answer answer.json` | G5b 결정. `{"decision": "SELECT", "picks": {"ch1-idle_good": "v1", ...}, "excluded": ["ch2-shy_good"]}` 또는 `{"decision": "REQUEST_CHANGES", "requestedChanges": [{"field": "ch1-glad_good", "note": "..."}]}`. `APPROVE`(자동 승인)는 모든 동작의 v1을 고른다. SELECT면 `approved-actions.json`을 쓴다. |
| `acf plan import <slug> --from plan.json [--brief brief.json]` | 사용자가 직접 쓴 기획서를 `character-plan-v1`로 검증·고정하고 `character_id`·`plan_rev`를 발급한다. G3를 `reviewer=user, decision=APPROVE, note=manual-plan`으로 기록한다(D-0013). 성격 칸 evidence는 `BRIEF` 또는 `USER`만 허용한다. |
| `acf persona traits [--references refs.json] [--reference-doc card.json ...]` | S7. 참조 ID 목록과 카드 본문을 에이전트 입력에 넣는다. |
| `acf persona prompts --probes probes.txt` | S8. 프롬프트 쌍·말투 확인 표본·G6 페이지. 직전 실행이 표본 단계에서 끊겼으면 같은 rev에서 이어 간다. |
| `acf persona probe --probes probes.txt` | 고정된 프롬프트 쌍은 두고 표본만 다시 돌린다. 결과는 `prompt-probe-r<k>.json`으로 누적되고 G6 페이지는 다시 만든다. |
| `acf ref collect --source <source_id> [--categories female,male] [--execute]` | S1 실제 순위 수집(D-0044 (4)). 기본은 호출 계획(어떤 URL을 몇 번)만 낸다. 실행하면 `popularity-ranking-v2`를 쓰고 출처·수집 시각·이용 조건 확인 기록을 남긴다. 이용 조건이 자동 수집을 허용하지 않는 출처는 거절한다. |
| `acf data plan|samples|build <character_id> [--execute]` | S9(§8.8). `plan`은 G6 승인 프롬프트 쌍으로 `data-plan-v1`을 고정한다. `samples`는 클러스터별 인계안(`data-handoff-v1`)과 샘플(`data-sample-v1`)을 만들고 G7a 대기로 둔다. `build`는 G7a 승인 뒤 나머지를 작성·검사·분할해 `dataset-rev-v2`를 만들고 G7 대기로 둔다. 기본은 호출 계획만, `--execute`로 작성 모델을 부른다. |
| `acf train plan|submit|collect <character_id> --provider gemma_qlora|vertex_gemini` | S10 학습(§8.9). `plan`은 `training-run-v2`(`dryRun=true`: 요청 설정·전송 파일·비용 추정)을 쓴다. PoC는 여기까지다(D-0044 (9)). `submit`·`collect`는 `--execute`와 사용자 지시가 있어야 하고, 비용 추정이 상한을 넘으면 제출하지 않는다. |
| `acf eval prereg|run|judge|report <character_id>` | S10 평가(§8.9). 사전 등록 → 조건별 응답 수집(`eval-run-v1`) → LLM 짝 판정 → 보고서(`eval-report-v2`) → G8 대기. |
| `acf release build <character_id>` | S11(§8.10). 승인된 revision으로 `character-package-v1` 패키지를 만들고 G9 대기로 둔다. |
| `acf export doki-app <character_id> [--verify]` | 우리 앱 변환(§8.11). G9 승인 패키지를 api-svc 시드 묶음과 chat-svc 콘텐츠 트리로 바꾸고 `export-result-v1`을 쓴다. `--verify`는 일회용 PostgreSQL 두 개에 적재해 확인한다. |
| `python -m acf.web --root <공장 루트> [--port 8765]` | 워크숍 웹앱(§6.5). |
| `acf ledger report <id>` | 원장으로 비용·시간 보고서를 만든다. |
| `acf verify <id>` | 모든 revision 폴더의 manifest.sha256을 확인한다. |

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

코드는 `src/acf/contracts/dataset.py`다. `dataset-rev-v1`·`data-qa-v1`을 대체한다(실제 산출물 없이 바뀜).

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

코드는 `src/acf/contracts/training.py`다. `training-run-v1`·`eval-prereg-v1`·`eval-report-v1`을 대체한다.

| 계약 | 내용 |
|---|---|
| `training-run-v2` | `{characterId, datasetRev, datasetDigest, provider: gemma_qlora|vertex_gemini|fake, baseModel, baseModelRevision, requestedConfig, appliedConfig, dryRun, estimate{usd, gpuHours, billableTokens, basis}, budgetUsd, status: PLANNED|SUBMITTED|RUNNING|SUCCEEDED|FAILED|CANCELLED, jobId, transfers[{path, bytes, sha256, remoteSha256}], checkpoints[{checkpointId, epoch, step, ref}], modelBinding{provider, ref, checkpointId}}`. `dryRun=true`이면 `jobId`가 없다 |
| `eval-prereg-v2` | `{characterId, personaVersion, arms[{armId: LONG_BASE|SHORT_GEMMA_SFT|SHORT_GEMINI_SFT, promptRef, model}], sets[{setId: OE|SE|APOLOGY|LONG200, ref, seeds, perTurnSeed, personas}], judge{model, family, orderSwap}, humanPairs, criteria[{id, metric, comparator, threshold, appliesTo}], frozenAt}`. 기본 기준(D-0045 (3)): `repeat_rate_101_200 <= 0.05`, `memory_recall_200 >= 0.9`, `apology_recovery >= 4/6`, `appliesTo = SFT_ANY` |
| `eval-run-v1` | 한 조건·한 세트의 응답: `{preregSha256, armId, setId, model, items[{itemId, personaId, turns[{user, reply, seed}]}]}` |
| `eval-report-v2` | `{preregSha256, runRefs, metrics[{armId, metric, value, detail}], criteriaResults[{id, armId, value, passed}], llmPairs[{pairId, armA, armB, forward, reverse, consensus}], humanPicks[{pairId, pick}], llmHumanAgreement, recommendation}` |

저장 위치: `runs/characters/<id>/s10-train/tr<k>/<provider>/training-run.json`(어댑터·체크포인트는 Git 밖), `runs/characters/<id>/s10-eval/ev<k>/{prereg.json, runs/<arm>-<set>.json, pairs.json, report.json}`.

### 5.16 `gate-record-v1`

`{schemaVersion, characterId|briefId, gate, shownArtifacts[{ref, sha256}], decision, selections[], reasons, requestedChanges[{field, note}], reviewer, minutes, decidedAt}`

### 5.17 `character-package-v1` / `export-result-v1` (D-0011, D-0044)

코드는 `src/acf/contracts/release.py`다. `release-manifest-v1`을 대체한다.

패키지(형식 중립): `{characterId, packageRev(pk<k>), locale: ko, builtAt, profile{name, gender, age, job, tagline, description, hobby, likes, dislikes, mbti, tags[≤4], tmiItems[{text, revealStage}]}, appearance{appearanceRev, heroImage, spec}, chapters[{chapterNo, chapterId, title, relationshipStage, intro, goal, facts, frame, background}], videos[{videoId, kind: INTRO|ACTION, chapterNo, clipKey, title, description, useWhen, expression, durationS, file, provider, synthetic}], persona{personaVersion, traitSheet, longPrompt, shortPrompt}, sft{datasetRev, datasetDigest, trainingRuns, evalReport, adoptedBinding}, gates[{gate, rev, decision, recordRef}], files[{path, sha256, bytes}]}`. 경로는 모두 패키지 루트 기준 상대 경로이고 `files`에 있어야 한다. G2는 결번이다(D-0042). 옛 캐릭터의 G2 기록이 있으면 `gates`에 함께 담는다.

패키지 폴더: `runs/characters/<id>/s11-release/pk<k>/` 아래 `package.json`, `appearance/`, `chapters/ch<n>/`, `videos/`, `persona/`, `sft/`, `gates/`.

내보내기 기록: `{characterId, package{ref, sha256}, target: doki-app, targetVersions{api-svc: <alembic head>@<commit>, chat-svc: ...}, outputs[{system: api-svc|chat-svc, kind: seed-bundle|content-tree, path, sha256}], mapping[{source, target, note}], unmapped[], verification{status: NOT_RUN|PASSED|FAILED, disposableDb, steps[{name, ok, detail}]}}`.

### 5.18 원장

`calls.jsonl` 한 줄: `{callId, at, stage, kind, provider, model, inputTokens, outputTokens, images, seconds, ms, ok, estCostUsd, ref}`. `human-time.jsonl` 한 줄: `{at, gate, minutes, ref}`.

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

`src/acf/web/`(FastAPI)이다. 화면은 워크숍 시안(`c-glass.html` 작업실, `d-ops.html` 운영)을 `src/acf/web/static/`에 두고 API로 데이터를 읽는다. 로그인은 없고, 공장 루트·포트·저장 위치는 설정값이다(배포 대비).

| 경로 | 동작 |
|---|---|
| `GET /api/health` | 서버·공장 루트 확인 |
| `GET /api/projects` | `runs/characters/*`·`runs/briefs/*` 목록과 단계·관문 상태 요약 |
| `GET /api/characters/{id}` | `state.json` 전체, 갈래별 진행 요약, 대기 관문 |
| `GET /api/characters/{id}/gates/{gate}` | 그 관문 검토 항목(파일 목록, 미리보기 URL, 기존 기록) |
| `GET /api/files/{id}/{path}` | 캐릭터 폴더 안 파일만. 경로 탈출은 거절한다 |
| `POST /api/characters/{id}/gates/{gate}/decision` | 본문은 `acf gate import`의 답 JSON과 같다. 같은 코드 경로로 관문 기록을 남긴다 |
| `POST /api/jobs`, `GET /api/jobs/{jobId}` | `{characterId, action: run, until}`로 오케스트레이터를 백그라운드에서 돌린다. 캐릭터당 동시에 하나 |
| `GET /api/events` | SSE. `{type: job|state|gate, characterId, ...}` |

새 관문의 답 형식: G7a `{"decision": "SELECT"|"REQUEST_CHANGES", "cluster": "<clusterId>", "verdicts": {"<conversationId>": "ADOPT"|"FIX"|"REJECT"}, "notes": {...}}`, G7 `{"decision": "APPROVE"|"REQUEST_CHANGES", "verdicts": {...}}`(무작위 표본 20개), G8 `{"decision": "SELECT", "adopted": "LONG_BASE"|"<model_binding ref>", "humanPicks": [{"pairId", "pick"}]}`, G9 `{"decision": "APPROVE"|"REJECT", "reasons": "..."}`.

구현 메모(2026-10-27, M8 1차): `/api/projects`는 `characters[]`(단계·관문·대기 관문·진행률·마지막 작업)와 `briefs[]`·`totals`를, `/api/characters/{id}`는 원본 `state` + `lanes`·`pendingGates`를, 관문 항목은 `files`·`previews`(URL)·`record`·`records`를 돌려준다. 작업 ID는 `job-<시각>-<hex>`, 상태는 `queued|running|succeeded|failed`이고 `[web] jobs_dir`(기본 `work/web-jobs`)에 남으며 재시작 때 끝나지 않은 작업은 실패로 정리한다. SSE 이벤트 이름은 `hello|job|state|gate`다. 오류: 없음 404, 형식 400, 이미 결정된 관문·동시 작업 409, 아직 구현되지 않은 관문 501, 캐릭터 폴더 밖 파일 400. 관문 결정과 작업은 캐릭터별 잠금으로 순서를 지킨다. 관문별 상세 화면은 아직 없고(K-0037), 대기 관문 칩은 검토 항목 JSON을 연다.

## 7. 에이전트 러너 (명세 §4)

구현(D-0014): 백엔드는 둘이다. `[agent] backend = "codex_exec"`이면 아래 codex 경로, 아니면 API 경로(한 번 호출·러너 재시도)다. codex 경로의 작업 공간은 `AGENTS.md`(역할 프롬프트 + `prompts/common-procedure.md` + 입력 목록 + 계약 이름), `inputs/`, `contract-example.json`, `check.sh`(현재 venv의 python으로 `acf.checks.cli <stage> .` 실행)로 이루어진다. 실행은 `codex exec --json --skip-git-repo-check -m <model> -s workspace-write -C <workspace> -c model_reasoning_effort=... [-c mcp_servers={}]`이다. 이벤트에서 `command_execution` 명령·`agent_message`·`turn.completed` 사용량을 모으고, 명령 문자열의 절대 경로·`~`·`../`가 작업 공간 밖이면 `TaintedOutputError`다. 러너는 실행 뒤 `acf.checks.registry.run_checks`로 다시 검사하고, 실패하면 사유를 프롬프트에 붙여 같은 작업 공간에서 재실행한다(최대 `max_check_retries`). 단계별 검사 묶음은 `checks/registry.py`가 작업 공간 inputs에서 재구성하므로 에이전트와 러너가 같은 검사를 쓴다.

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

구현 메모(2026-10-27, M8 1차, D-0042·D-0043·D-0046): G1 페이지는 외모군마다 얼굴 라디오(`name="face"`)·추천 표시·고칠 점 메모 칸을 보여 준다. `SELECT`는 `referencePreviews` 정확히 한 장이고 외모군은 그 얼굴에서 정한다(`selections` 생략 가능, 기록은 `[외모군, 얼굴]`). `REQUEST_CHANGES`는 `note`가 필수다. `acf ref faces`는 새 `rf<k>`에 순위·인물·특징·보고서를 바이트 그대로 복사하고 `carried-from.json`(`fromRev`, 파일별 sha256, 메모)을 쓴다(보고서를 고칠 수 없으므로 `settings.carriedFrom` 대신). 순위 목록 입수는 `acf ref collect` → `runs/rankings/<시각>-<출처>/ranking.json` + `collection-record.json` → `acf ref run --ranking`이다. 목록 `gender`가 캐릭터 성별과 같을 때만 쓰고, 혼성 목록(배우)은 `characterGender = any`에서만 쓴다. 계약에 항목별 출처 칸이 없어 `listId`와 수집 기록으로 근거를 되짚는다. 수집 목록은 분류당 10명이라 기본 군집 설정(`cluster_k = 4`, `min_members_per_cluster = 3`)과 맞지 않는다(K-0035).

### 8.2 S2 기준 사진 (D-0042, D-0043)

구현: `stages/s2_hero/`, 진입점 `run.run_s2(ctx, cid)`. 단계 상태 `s2`, rev `ar<k>`, 사람 관문 없음. 지금 코드는 아직 옛 흐름(후보 4장 → G2)이다(K-0034).

**inputs.** G1 기록에서 외모군(`selected_cluster`)과 고른 얼굴 한 장(`selected_references`)을 읽고, 얼굴을 `references/<previewId>.png`로 복사해 `hero-inputs-v1`을 고정한다(`basePhoto` 포함). 순위 목록의 이름은 `s1-reference/rf<k>/ranking.json`에서 읽어 유출 검사에만 쓴다.

**picked.** `base_photo = "picked"`면 이미지·판정 호출 없이 G1 얼굴을 `referenceImage`로 삼아 `appearance-spec.json`(`identityCheck.status = SKIPPED`)과 manifest를 쓰고 `s2`를 `APPROVED`로 둔다.

**prompt.** `build_hero_prompt`는 "Reference portrait photograph of a fictional <인물 인상+성별> in their <연령대>, <그림체> style."로 시작하고, 사진형 촬영 조건(4분의 3 각도, 창가 방향광, 모공이 보이는 피부, 85mm f/2), 같은 얼굴·머리색·머리 모양을 유지하라는 문장, 손을 얼굴에서 떼고 턱을 괴지 않는다는 문장(D-0027), "An original person, not based on any real individual."을 붙인다. 외형(단일값) 태그는 빼고 스타일링·분위기만 넣는다. 외형 태그를 같이 주면 모델이 글을 따라 머리를 바꿨다(2026-10-21 실제 호출). `Variation n of N`은 쓰지 않는다. 피할 것은 "text, watermark, logo, blur, plastic skin, hand on face, chin resting on hand"다.

**generate.** 먼저 `ensure_judge`로 판정 공급자를 확인한다. 이미지 공급자가 실제인데 판정 공급자가 없거나 `[stages.image_qa] enabled = false`면 아무것도 쓰기 전에 `CheckFailed`이고, 메시지에 `base_photo = "picked"`를 안내한다. 프롬프트의 이름 유출을 검사한 뒤 `image_qa.generate_checked`로 한 장을 만든다. 기준표는 `identity-v1` = same_identity, hair_kept, hands_off_face, single_person_no_text다. 판정 요청 이미지는 `("candidate image", 시도 파일)`, `("identity reference (G1 face)", G1 얼굴)` 순서다. 수정은 `fix_mode` 설정과 상관없이 `regenerate`다(G1 얼굴을 참조로 원래 요청 끝에 "Fix: …"만 붙인다). 시도는 최대 `1 + max_fix_rounds`(기본 3)번이다.

**고정.** 통과하면 통과한 시도를 `candidates/h1.png`로 복사하고 `candidates.json`, `appearance-spec.json`(설명은 어휘의 한국어·영어 표기를 이어 붙인다. 금지 요소 기본값은 문자·워터마크·로고와 "실존 인물의 이름이나 사진을 생성 지시로 쓰지 않는다(D-0017)"), `manifest.sha256`을 쓰고 `s2`를 `APPROVED`로 둔다. 관문 기록은 만들지 않는다. 끝까지 통과하지 못하면 D-0037 (4)와 달리 가장 나은 시도를 넘기지 않는다. `s2`는 `CHECK_FAILED`이고 `lastError`에 FAIL 항목과 `qa/` 보고서 경로를 적는다. 외모 명세는 쓰지 않는다. 다시 실행(`acf hero run`)은 새 `ar<k>`를 만든다. 이미지 실패·이름 유출도 `CHECK_FAILED`다.

**워크숍 화면 연결.** 시안(`d-ops.html`)은 S2를 결재가 아닌 자동 작업으로 보이고, 시도마다 실패·자동 재시도를 작업 기록에 남기며, 최종 실패는 "사람 확인 필요" 문제로 다시 실행·G1 얼굴 그대로 쓰기(`picked`)를 제시한다. 연결층은 `qa/` 보고서와 `state.json`의 `s2` 상태를 그대로 읽는다.

구현 메모(2026-10-27, M8 1차): `base_photo = "picked"`를 구현했다. G1 얼굴을 기준 이미지로 복사하고(이미지·판정 호출 0회) `appearance-spec-v1`에 `basePhoto: picked`, `identityCheck: {status: SKIPPED, attempts: 0}`을 쓰며 `s2`는 바로 `APPROVED`다. `hero-candidate`는 만들지 않는다. `generate`는 아무것도 쓰기 전에 K-0034와 `picked` 안내로 거절한다(D-0045 (5)). 문서상 기본값은 `generate`이므로 PoC 설정은 `picked`를 명시한다. `load_appearance_spec`은 `s2` 승인을 읽고, G2 기록만 있는 옛 상태는 읽기 전용으로 받아 준다. `s2` 승인 뒤 G1 얼굴을 바꾸는 것은 막고 S1을 새 rev로 다시 돌리게 한다.

### 8.3 S3 기획

**import.** 사용자가 쓴 JSON(또는 템플릿 Markdown)을 `character-plan-v1`로 검증한다. evidence가 없는 칸은 `{kind: USER}`로 채운다. 브리프 없이 들여올 수 있으며 그 경우 `briefId`는 null이다.

**draft.** 외모 명세가 고정돼 있으면(`s2` 승인) Planner 입력에 `appearance.json`(`appearanceRev`, 한국어 외모 설명, 비교 범위, 사용 제한 문구)을 넣는다. 이미지·순위 목록 이름은 넣지 않는다. Planner는 `appearanceRev`를 그대로 쓰고 챕터마다 `lighting`·`composition`을 채운다(D-0024). Planner는 브리프 각 문장에 번호를 붙인 사본을 받고, 칸마다 근거 번호를 적는다. `check`는 (a) 필수 칸, (b) 각 evidence의 `quote`가 원문 부분문자열인지, (c) 성격 칸의 evidence에 `APPEARANCE`가 없는지(D-0005)를 확인한다.

**씨앗(D-0033).** `stages/s3_plan/seed.py`의 `write_seed`가 `plan-seed-v1`을 `s3-plan/seeds/sd<k>.json`으로 고정한다. 성별이 비면 외모 명세 비교 범위의 성별(female·male)로 채운다. `load_latest_seed`가 가장 최근 씨앗을 읽는다.

**변형(D-0033, D-0034).** `variants.run_s3_variants(ctx, cid)`, rev `pr<k>`, 관문 G3. 외모 명세(`s2` 승인, 없으면 `GateNotApprovedError`)와 씨앗(없으면 `NeedsInputError`)이 필요하다. Planner(`plan_variants`, 단계 표지 `s3-variants`)가 씨앗·외모 요약(D-0024의 사용 제한 문구 포함)·챕터 자리·프로필 카드 칸으로 `variants`(확정 3)안을 낸다. 코드가 ID·rev·씨앗 rev·변형 ID와 `chapterArc`의 자리·제목·관계 단계를 고정하므로 에이전트는 `arc` 문장만 쓴다. 검사(`check_v2.py`): 개수, 씨앗 직업 포함·나이·성별 일치, 모든 안이 같은 상황 집합을 쓰고 상황마다 첫 행동이 서로 다름, 성격 칸이 형용사만이 아님, 이름 유출. 결과는 `variants.json`(`plan-variants-v1`)과 `gate-G3.html`(안별 카드, 라디오, 고칠 칸 JSON).

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

`resources/prompt-sections-v1.json`의 섹션 목록으로 긴·짧은 프롬프트를 조립한다. 긴 프롬프트의 시스템 규칙 섹션은 `systemRulesRef` 파일을 그대로 넣는다. `align`은 두 프롬프트의 섹션 헤더 집합이 같은지, 짧은 프롬프트가 `short_prompt_max_chars` 이내인지, 금지 표현이 없는지 확인한다. `probe`는 `voiceProbes`마다 두 프롬프트로 응답을 받고 판정 모델이 캐릭터 일치를 비교한다. 결과는 G6 페이지에 나란히 표시되며 자동 승인에 쓰지 않는다.

### 8.8 S9 데이터셋 (명세 §10.3, D-0044, D-0045)

학습 가이드 §7·§13의 절차를 따른다. 그래프에서는 두 단계다: `s9s`(인계안·샘플, 관문 G7a, 의존 G6)와 `s9`(대량 작성·검사·분할, 관문 G7, 의존 G7a).

1. `plan`: G6 승인 `prompt-pair-v1`의 짧은 프롬프트와 특질 시트로 `data-plan-v1`을 고정한다. 클러스터 목표 수는 `round(target × share)`이고 합이 목표와 다르면 `base`에서 맞춘다.
2. `samples`: 클러스터마다 인계안을 작성 모델로 만들고(특질 시트의 선택 기준 5항목·상황별 변화 → 행동 기준표), 같은 인계안으로 샘플 12개를 쓴다. 각 대화의 `skeletonId`는 장면 뼈대 단위로 붙인다. G7a 페이지는 클러스터별 인계안과 샘플 전문을 보여 주고 판정·고칠 점을 받는다. `REQUEST_CHANGES`면 고칠 점을 인계안에 붙여 그 클러스터만 다시 만든다.
3. `build`: G7a에서 채택된 샘플은 그대로 넣고, 나머지는 같은 인계안 + 채택 샘플을 예시로 작성한다. 재료: `SNS_REWRITE`(`gemini-sft-poc` 후보 대화를 읽기 전용으로 열어 캐릭터 턴만 다시 쓴다, D-0007), `SYNTH`(합성 장면), `NIKL`(접근 경로가 정해질 때까지 비활성). 원본 SFT가 없는 캐릭터의 `base`는 `SNS_REWRITE`와 `SYNTH`로 채운다(가이드에서 검증되지 않은 적용, 계획서 §9).
4. 기계 검사(차단): 형식(역할 교대·system 존재·빈 답 없음), 사용자 턴 원문 일치(SNS 재작성), 프리필 없음, 원본 화자 사실 미포함, 금지 표현, 같은 말끝·같은 사과 문장 반복(데이터셋 전체 n-gram, 가이드 §8), 최대 길이(학습 템플릿 토큰 수, 기본 4,096). 경고: 길이 비율, 감정 표지 분포. charforge의 표준 검사·렌더러를 이 프로젝트 코드로 옮겨 쓴다(다른 저장소 코드를 import하지 않는다).
5. 분할: `skeletonId` 묶음째 나눈다. 검증은 `base`에서 `baseConversations`, 보강 클러스터마다 `augmentedShare`. 평가 세트는 학습·검증과 따로 만든다(§8.9).
6. G7: 검사 보고서, 클러스터별 수·답변 수·토큰 수, 무작위 표본 20개를 보여 준다. 승인하면 `dataset-rev-v2`를 고정한다.

작성 호출은 실행기 예산(동시 호출 상한은 설정값, 기본 4)과 원장을 쓰고, 재시도는 같은 입력의 재전송이며 첫 성공 결과를 보존한다.

### 8.9 S10 학습·평가 (명세 §10.4, D-0044, D-0045)

학습(`s10t`, 관문 없음, 의존 G7)과 평가(`s10`, 관문 G8, 선행 `s10t`)로 나눈다.

학습 어댑터는 `TrainingProvider` 포트(`plan`, `submit`, `status`, `collect`)를 따른다.

- `gemma_qlora`: 임대 GPU(Vast). 기본 설정은 학습 가이드 §11(unsloth/gemma-4-31B-it-unsloth-bnb-4bit, QLoRA r16/α32, dropout 0, LR 5e-5 linear, warmup 5%, 배치 1×4, 최대 4,096토큰, seed 3407, 1·2·3에폭 저장, assistant 답변만 손실). `plan`은 전송 파일 목록·바이트·sha256, 예상 GPU 시간(스텝 수 × 스텝당 초, 기본값은 소민 r3 실측 6초), 시간 단가로 비용을 낸다. `submit`은 이어 올리기 가능한 조각 전송 → 원격 해시 확인 → 학습 시작, `collect`는 완료 기록 확인 → 어댑터 회수·해시 확인 → 서버 삭제 순서다. 원격 상태는 계획 파일이 아니라 원격 로그와 완료 파일로 판단한다.
- `vertex_gemini`: Vertex 튜닝. 기반 모델은 설정값이고 착수 때 지원 목록으로 정한다. `plan`은 과금 토큰 수(데이터셋 토큰 × 에폭)와 단가로 비용을 낸다. 체크포인트 ID·step을 공급자 값 그대로 기록하고 중간 epoch를 추정하지 않는다.
- `fake`: 오프라인 전체 흐름용. 즉시 `SUCCEEDED`와 가짜 `model_binding`을 돌려준다.

비용 추정이 `budgetUsd`를 넘으면 `submit`을 거절한다. PoC는 `plan`(dry run)까지만 실제 설정으로 확인한다(D-0044 (9)).

평가: `prereg`가 조건(LONG_BASE, SHORT_GEMMA_SFT, SHORT_GEMINI_SFT)·세트(OE 고정 이력 질문, SE 서운함, APOLOGY 무례·사과 대본, LONG200 200턴 × 사용자 페르소나 4명)·판정·기준을 고정하고 해시를 낸다. `run`은 조건마다 응답을 모은다. 연속 대화는 모델 답을 다음 턴에 그대로 넣고 턴마다 다른 시드를 쓴다. 지표: `repeat_rate_101_200`(101~200턴 말풍선 가운데 앞서 나온 것과 같은 말풍선 비율), `memory_recall_200`(초반에 심은 정보를 200턴 시점에 묻는 확인 질문 정답률, 판정 모델 + 정답 키), `apology_recovery`(진지한 사과 대본에서 회복한 비율). `judge`는 같은 입력의 두 조건 응답을 정순·역순으로 판정해 합의만 센다. G8 페이지는 지표·기준 결과·LLM 짝 판정과 사람 블라인드 20쌍 화면을 보여 주고, 사람 판정으로 일치율을 낸다. 기준 미달이어도 보고서는 나오고 채택은 사람이 G8에서 정한다.

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
| `grok_web` | 기본 꺼짐(`accept_terms_risk = true` 필요, D-0029). `playwright`(`--extra web`)의 `connect_over_cdp(cdp_url)`로 사용자가 띄운 전용 프로필 Chrome에 붙어 새 탭을 앞으로 가져와 Imagine을 연다. 화면 흐름은 2026-10-21 로그인 화면에 맞췄다(D-0032): 입력 폼(`form:has(button[type=submit])`) 안에서 비디오 모드 버튼 → 해상도 라디오(`480p`·`720p`) → 길이 라디오(`6s`·`10s`·`15s`) → 소리 버튼(`aria-pressed`를 요청과 맞춤) → 파일 입력에 첫 프레임 업로드(이미지 제거 버튼이 보일 때까지 대기, 업로드 뒤 종횡비 버튼이 사라지고 영상은 이미지 비율을 따름) → 편집기(`[contenteditable]`)에 프롬프트(들어갔는지 확인) → 제출. 제출 뒤 주소가 `/imagine/post/<id>`로 바뀌면 그 id가 든 `<video>`의 주소(assets.grok.com의 `generated_video.mp4`)를 로그인 세션 요청으로 받는다(다운로드 버튼은 다운로드 이벤트가 오지 않아 쓰지 않는다). 옵션 클릭이나 제출 뒤 주소에 `#subscribe`가 붙으면(결제 창) 등급 제한·사용량 소진으로 바로 실패한다. 90초 안에 결과 페이지로 넘어가지 않으면 제출 안 됨으로 실패한다. 웹에 없는 길이·해상도는 S5가 첫 프레임을 만들기 전에 `check_settings`로 거절한다. 어느 단계든 실패하면 `~/.acf/grok-web-work/<job>/error-<단계>.png` 스크린샷을 남기고 `VideoGenerationError`. 탭만 닫고 사용자의 Chrome은 닫지 않는다. 재개 불가(`resumable = False`), 비용 0, 작업 ID는 `web-<hex>:<post id>`. 복구층(Stagehand `act()`)은 자리만 둔다. |
| `grok_oauth` | `VideoModel`. 요청·상태 처리는 `xai_video`와 같고 인증만 OAuth 접근 토큰(Bearer)이다. 토큰은 `token_file`(기본 opencodex 인증 파일의 활성 xAI 계정)이나 `token_env`에서 읽고, 값을 출력·기록하지 않는다. 만료면 다시 로그인하라는 오류를 낸다(새로 고침 없음). 명시해야 켜진다. 실제 호출 확인 전이다(D-0044 (3)). 토큰 해석 순서: `token_env` → `token_file`의 `xai.accounts[id == xai.activeAccountId].credential.access`, `credential.expires`는 epoch 밀리초로 본다(로컬 파일 기준 가정). 요청·상태·비용은 `XaiVideoModel`을 상속해 같다. 공급자 응답에 토큰이 섞여 와도 오류 메시지에서 지운다. |
| 순위 수집기(`src/acf/collectors/`) | 출처별 어댑터 + 가짜. 이용 조건 확인 기록이 없는 출처는 거절하고, 호출 계획(dry run)을 먼저 낸다. 요청 간격·User-Agent·재시도는 설정값. 출처 조사는 `docs/research/2026-10-27-ranking-sources.md`. |
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
| 영상 공급자 작업이 시간 안에 끝나지 않는다. | 작업 ID를 SUBMITTED로 남기고 단계 `CHECK_FAILED`. 다음 `acf video intro --execute`가 같은 rev에서 같은 작업을 다시 수집한다(재제출 없음). |
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

반드시 고정할 위험: (1) 승인되지 않은 관문의 산출물을 다음 단계가 읽지 못한다. (2) 판정 프롬프트에 후보 식별 정보가 없다. (3) 같은 특징·설정이면 군집이 같다. (4) 성격 칸의 근거에 외모 명세가 들어가면 실패한다. (5) 섹션 집합이 다르면 프롬프트 쌍이 고정되지 않는다. (6) 평가 분할 예시가 학습 생성 입력에 들어가면 실패한다. (7) 비밀값이 원장·보고서·표준 출력에 없다. (8) 순위 목록의 이름이 S1 보고서·미리보기 프롬프트·S2 입력에 없다(FR-35). (9) G1은 얼굴 정확히 한 장만 받는다. (10) S2 판정이 상한까지 FAIL이면 외모 명세 없이 `CHECK_FAILED`이고, 판정 공급자가 없으면 `generate`는 아무것도 쓰기 전에 거절되며, `picked`는 이미지 호출 0회로 고정된다(D-0042, D-0043).

`scripts/check.sh`는 `uv sync --locked`, `ruff check`, `ruff format --check`, `pytest -q`를 차례로 돈다.

## 12. 구현 순서

| 단계 | 내용 | 끝나는 조건 | 릴리스 |
|---|---|---|---|
| M0 | 골격: `pyproject`, `common/`, 포트와 가짜 어댑터, 원장·예산, 상태 파일, `graph.py`, `check.sh` | 검사 스크립트 통과. `acf status`가 빈 상태를 표시한다. | R0 |
| M4 (선행, D-0013) | `acf plan import`, S7 특질 시트·검사, S8 프롬프트 조립·정렬·표본, G6 페이지, 오프라인 흐름 테스트 | 오프라인 통과. 실제 모델로 `persona_version` 1개 발급(사용자 지시 뒤). | R0 |
| M1 | S1(D-0017): 순위 목록 고정·인물 묶기, Scout 특징 태깅과 검사, 정규화, 군집(구성원 수 기준), 보고서, 이름 유출 검사, ImageGen 포트(가짜·`codex_image`)로 미리보기, G1 페이지·선택, `acf ref run`·`acf run --ranking` | 오프라인 골격: 합성 순위 목록으로 G1 선택까지 통과. `codex_image` 실제 호출 확인(D-0019). 다음: 사용자 지시 뒤 실제 순위 목록으로 J2 실험 보고서. | R0 |
| M2 | S2(D-0022, D-0023): G1 참조 사진 선택, 참조 이미지 입력 후보 생성, G2 페이지·선택, 외모 명세, `acf hero run`·`acf run --until G2`. S3: 기획 초안이 외모 명세를 참조(남음). 짝 비교(FR-11)는 보류 | S2 오프라인 통과와 실제 구독 호출로 G2 → `appearance_rev` 확인(2026-10-21). 남은 것: 실제 순위 목록으로 S1→S2 한 번, S3 연결 | R0 |
| M2b | 외모 한 번 고르기(D-0042, D-0043): S1 외모군당 얼굴 1장, G1 얼굴 한 장 선택·고칠 점 메모, `acf ref faces`, S2 기준 사진 + `identity-v1` 동일인 검사(재생성 최대 3번 시도), `base_photo = "picked"`, G2 제거와 `needs` 의존, `load_appearance_spec`의 `s2` 기준, 옛 G2 칸 읽기 호환 | 오프라인 통과(가짜 판정으로 통과·재시도·최종 실패·판정 없음 거절·picked 네 경로). 남은 것: 판정 경로 확인(Q-0020) 뒤 실제 S1 얼굴 → S2 `generate` 1회 | R0 |
| M3 | S3 외모 연결(D-0024), S4 프레임 생성과 G4 사람 승인(D-0025, D-0026), `acf frames run`. 일관성 판정·챕터별 재생성은 보류 | 오프라인 통과. 실제 구독으로 3챕터 프레임 생성과 G4 승인 확인(2026-10-21). 남은 것: 실제 Planner로 S3, 판정 모델 참고 자료 | R0 |
| M3b | 기획·장면 흐름(D-0033~D-0035): 씨앗 → 변형 → G3, S3r 참고 자료(hash-v1 색인), S4a 배경 → G4a → S4b 장면 사실·자세 → G4b → S4 완성 이미지 → G4(챕터별 부분 재생성), 갈래별 진행 오케스트레이터, `acf plan seed/variants/own`·`refs index/select`·`scene backgrounds/poses` | 오프라인 통과(2026-10-22, 182 passed). 남은 것: 실제 Planner·Scout·Writer·Pose 모델과 구독 이미지로 데모 캐릭터 한 번, 실제 임베딩(Q-0019) | R0 |
| M3c | 이미지 자동 검사 루프(D-0036, D-0037): 비전 포트·가짜·OpenAI 호환 어댑터, 기준표, 편집 수정 반복, 배지, 원장 VISION | 오프라인 통과(2026-10-22, 221 passed). 남은 것: 실제 판정 경로 확인(Q-0020), 사람 판단과의 일치율 | R0 |
| M5 | S5·S6·S9·S10·S11 뼈대를 가짜 어댑터로 연결, 전체 오프라인 흐름 테스트, 원장 보고서 | PRD §14 수용 조건 1·4 충족. | R0 |
| M5 | S5 소개 영상(D-0028~D-0032): 9:16 세로 첫 프레임, `xai_video`·`grok_web` 어댑터, 제출·재개·실측, G5 사람 선택, `acf video intro`·`web-setup` | 오프라인 통과. 2026-10-21 실제: 세로 첫 프레임 생성 확인, grok.com 화면 맞춤과 웹 영상 1편 생성·받기 확인, S5 전체 웹 실행은 무료 등급 한도(결제 창)로 막힘. 남은 것: 웹 한도 또는 유료 등급(Q-0018) 뒤 S5 전체 실행, 실제 API 1회(사용자가 보류) | R0 |
| M6 | S6 동작 영상(D-0038, D-0040, D-0041): G4 승인 이미지 → 미소·무표정 첫 프레임 → 앱 통화 영상 표준 세트(`l2` 6편·`standard` 37편) → G5b 선택·제외·부분 재생성, `acf video actions`. 다음: 특별 행동 제안 에이전트, 영상 자동 검사 | 골격: 오프라인 통과(2026-10-22). 남은 것: 영상 공급자 사용량 확보(Q-0018) 뒤 `l2` 18편 실제 실행과 G5b 승인 | R0 골격·R1 |
| M7 | SNS 재작성·NIKL·합성·분할, 학습 제출·수집, 사전 등록·블라인드 평가, 릴리즈 매니페스트, G7~G9 | 사전 등록 기준 판정 보고서와 `release_rev` 1개. | R1 |
| M8 (PoC, D-0044·D-0045) | 3일 PoC: A 외모 흐름(M2b의 `picked`까지), B 순위 수집기, C S9 데이터셋, D S10 학습(dry run)·평가, E 패키지·우리 앱 변환기, F Grok OAuth, G 워크숍 웹앱, H 그래프에 `s9s`·`s9`·`s10t`·`s10`·`s11`·내보내기 연결과 `tests/test_offline_pipeline.py` | 여성·남성 합성 브리프 두 개가 가짜 공급자로 S1 → G9 → 패키지 → 일회용 DB 적재까지 네트워크 없이 통과하고, 워크숍 화면에서 관문만 눌러 같은 흐름을 끝까지 간다. 실제 호출은 순위 수집·이미지·LLM 1회씩 | PoC |

구현 순서는 M0 → M4(선행) → M1 → M2 → M3 → M5 → M6 → M7이다(D-0013). M2b는 워크숍 화면 연결 전에 한다. 각 노드의 현재 성숙도(L0~L4)와 올리는 규칙은 [현재 상태](../status/current-state.md)와 [인계 규칙](../status/README.md#노드-성숙도-규칙)에 있다. 마일스톤의 "끝나는 조건"은 대부분 L1(오프라인)이고, L2 이상은 그 규칙을 따른다. M4의 실제 실행은 `acf plan import`로 들여온 기획서의 G3 기록이 있으면 된다.

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

