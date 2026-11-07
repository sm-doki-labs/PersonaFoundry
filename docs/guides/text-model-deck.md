# 텍스트 자료 제작 모델 덱

2026-10-30 사용자 요청(D-0072)으로 [원본 모델 덱 snapshot](../research/2026-10-30-text-model-deck-source.md)을 S3·S7·S8·S9에 연결했다. 미디어 생성과 실제 서비스 응답 모델은 별도 설정이다. 개발 기본 경로는 `opencodex`, 모델 프로필은 `basic_test`다. 경로와 프로필은 독립적으로 선택한다.

## 현재 배정

| 역할 | basic_test | demo / pre_demo_completion_check | 추론 강도 |
|---|---|---|---|
| 기본 프로필·배경·제약 | gpt-6.1-sol | 동일하다. | high |
| 성격 초안 | google-antigravity/gemini-3.8-flash | 동일하다. | high |
| 명시적 설정 충돌 검토 | gpt-6.1-sol | 동일하다. | high |
| 성격 확정·최종 말투·대표 대사 | google-antigravity/gemini-3.8-flash | google-antigravity/gemini-4-argon | high |
| SFT 상황·사실 맥락 | gpt-6.1-sol | 동일하다. | medium |
| SFT 답변·이전 assistant 발화 | google-antigravity/gemini-3.8-flash | google-antigravity/gemini-4-argon | high |
| 전수 검사 | gpt-6.1-terra | 동일하다. | high |
| 검토 이견 재검토 | gpt-6.1-sol | 동일하다. | high |
| 확인된 오류 수정 | google-antigravity/gemini-3.8-flash | google-antigravity/gemini-4-argon | high |

현재 유효 배정은 저장소 루트에서 다음 명령으로 확인한다. 모델 호출은 없다.

```sh
uv run --locked cfp models show
```

## 프로필 및 호출 경로 전환

```sh
uv run --locked cfp models select --profile basic_test
uv run --locked cfp models select --profile demo
uv run --locked cfp models select --profile pre_demo_completion_check
uv run --locked cfp models select --route opencodex
```

선택값은 Git에서 제외되는 `work/text-pipeline-selection.json`에 저장하며 다음 명령과 새 작업 문맥부터 적용한다. 실행 중인 작업을 소급해서 바꾸지 않는다. 이번 코드 변경 전에 이미 켜져 있던 워크숍 서버는 새 코드를 적용하려면 재시작해야 한다. 저장된 선택이 `factory.toml`의 초기 profile/route보다 우선한다. 원래 설정을 쓰려면 선택 파일을 제거한다.

별도 API/테스트 서버는 사용자가 전환을 요청할 때 다음 설정에 실제 주소·인증 환경변수 이름을 채운다. 인증 값은 파일이나 명령 인자에 쓰지 않고 해당 환경변수로 공급한다. 서버에서 opencodex 모델 ID를 그대로 받으면 models 매핑은 생략한다.

```toml
[text_pipeline.routes.test]
adapter = "openai_compat"
base_url = "https://your-test-server.example/v1"
api_key_env = "CFP_TEST_API_KEY"
timeout_s = 240

[text_pipeline.routes.test.models]
"gpt-6.1-sol" = "server-sol-id"
"gpt-6.1-terra" = "server-terra-id"
"google-antigravity/gemini-3.8-flash" = "server-flash-id"
"google-antigravity/gemini-4-argon" = "server-argon-id"
```

```sh
uv run --locked cfp models select --route test --profile basic_test
```

미설정 test 경로 선택은 저장 전에 거절한다. 모델·경로를 실패 시 자동 대체하지 않으며 HTTP의 숨은 재시도도 끈다. 실제 요청은 기존 `--execute`와 사용자 실행 지시가 있어야 한다. OpenAI API 크레딧 소비 여부와 실제 청구액은 이 설정만으로 확인되지 않는다.

## 공정 연결과 기록

표준 S3 변형 경로는 Sol의 원문 요구 추출 → Flash 초안 → Sol의 설정 충돌 검토 → Gemini의 최종 말투를 순서대로 실행한다. 검토에서 확인한 오류가 있으면 해당 필드만 Gemini가 한 번 수정하고 Sol이 재검사한다. 최종 말투 단계는 voiceSummary·voiceExamples 외 필드와 axisNote·후보 순서를 바꿀 수 없다. 직접 작성/기존 브리프 기획 경로는 Gemini 저작 모델 배정을 적용하며, 변형 경로의 모든 추가 검토 단계를 자동 수행하는 것으로 간주하지 않는다.

기존 선택·말투 분리 프로필의 역할에도 같은 덱을 적용한다. `seed_requirements`는 Sol, `choice_variants`는 Flash, `choice_review`는 Sol, 성격 확정·대사 렌더링은 Gemini, 내용 뼈대는 Sol medium, 보존 검토는 Sol이다. 해당 텍스트 단계는 `[agent] backend = "codex_exec"`보다 API 경로가 우선한다. 형성 fingerprint와 recipe는 유효 모델·프로필·경로를 포함하므로 설정이 달라진 결과를 같은 형성 단계로 재사용하지 않는다.

표준 S8은 승인 기획·특질 문장을 현재 서비스의 여덟 persona 섹션으로 결정적으로 조립한다. runtime에 예시 대화·전체 챕터·제작자 메타데이터를 넣지 않는다. 구형 `prompt-pair-v1` 소비자와 호환하기 위해 short 칸에도 압축하지 않은 같은 본문을 저장하며 shortAdopted는 false다. 짧은 프롬프트 최적화·정식 품질 검증을 수행한 것이 아니다. 본문이 설정된 long_prompt_max_chars(기본 8,000자)를 넘으면 내용을 자르지 않고 거절한다. 행동 선택의 예외 조건은 내부 필드명 없이 원문 문장으로 함께 보존한다. system_rules_path 설정도 존중하며 actor_system_rules_path가 있으면 그것이 우선한다. G6 수정 요청 뒤 같은 본문을 다시 조립하려 하면 S3/S7 원천 또는 시스템 규칙을 먼저 수정하도록 멈춘다. 기존 formation 프로필은 각 프로필의 컴파일러/계약을 유지한다.

S9는 모델 덱 snapshot을 revision에 고정하고 작성·Terra 전수 검사·Sol 이견 검토·필요한 Gemini 수정 한 번·재검사를 수행한다. GPT는 assistant 대사를 다시 쓰지 않는다. 통과/탈락 판정 및 원문 인용과 첫 출력·실패를 보존한다. 사람은 기존 G7a/G7에서 확인한다. 사람 표본 비율의 교정은 미완이며 자동 검수 결과를 사람 승인으로 바꾸지 않는다.

호출 원장의 `textBinding`은 task/profile/route/요청 모델/추론 강도/공급자 설정 및 덱 해시를 남긴다. 응답이 보고한 실제 모델도 기존 model 필드에 기록한다. 표준 S7은 원천 생성 배정·응답 모델·시트 해시를 저장하고 S8은 sourceGeneration과 selectedConfiguration을 분리한다. 과거 생성 기록이 없으면 legacy_or_unknown으로 표시하며 현재 모델로 소급 표시하지 않는다. S8의 completionCheck는 NOT_RUN이다. 인증 값은 기록하지 않는다. 형식 재시도는 같은 역할·같은 모델에서만 수행하며 의미 오류의 새 결과 재추첨으로 쓰지 않는다.

## 검증 한계

이 셋업은 네트워크 없는 테스트로 연결과 오류 처리를 검증한다. 실제 opencodex를 통한 새 덱 실행, 별도 테스트 서버 실행, Argon SFT 품질, Terra 판정 정확도는 아직 검증하지 않았다. `pre_demo_completion_check` 선택만으로 최종 점검 완료를 기록하지 않으며, Flash 실행 결과로 Argon 최종 점검을 대신하지 않는다.


## 글래스 시연 화면과 연결

2026-10-30부터 실제 시안 폴더를 `[web] studio_dir`로 연결할 수 있다. 2026-11-07에 시안 폴더를 저장소 안 `studio/`로 옮겼다. 같은 FastAPI 서버에서 `/studio/d-ops.html?panel=text#job/seoha-new/floor`를 열면 **텍스트 공정** 패널이 열린다.

패널은 현재 프로필/호출 경로를 바꾸고 실제 캐릭터의 단계·관문·최근 텍스트 호출·산출물 출처를 읽는다. 실행 중인 작업이 있거나 경로가 미설정이면 선택을 거절한다. 과거 자료의 생성 모델/프로필은 현재 선택과 구분하며 잘린 미리보기는 일부 표시임을 알린다. 생성·학습·관문 승인은 새 패널에서 자동으로 하지 않고 기존 워크숍에서 수행한다.

```toml
[web]
studio_dir = "studio"
```

새 API는 `GET /api/text-pipeline`, `POST /api/text-pipeline/selection`, `GET /api/text-pipeline/characters`, `GET /api/text-pipeline/characters/{id}`다. 설정 응답에는 인증 값·환경변수 이름·개발 서버 주소를 넣지 않는다. 시안은 HTML/shared/assets/previews/recordings만 서빙하며 계획·작업자 로그는 서빙하지 않는다.

현재 검토 서버는 127.0.0.1:8776이며 실제 factory.toml을 직접 읽고 `--jobs-dir work/studio-web-jobs-20261030`으로 작업 큐만 분리한다. 실제 데이터 루트는 character-factory-poc다. 현재 runs/characters가 없어 목록0건이며, 다른 실험 루트와 옛 저장소의 기록을 자동 합치지 않았다. 기존 공장 현장의 시간·비용·진행은 각본으로 유지하고, 텍스트 작업대의 모델 배정만 기본 테스트 덱 스냅샷으로 맞췄다.

[연결 계획표](../../studio/plans/2026-10-30-text-pipeline-connection.md)와 `studio/design.md` §16에 구체적인 분담·화면·검증 기록을 남겼다.

## 실제 공장 화면 연결(2026-10-30 후속)

설정·조회 패널에 한정했던 이전 연결은 D-0076으로 확장한다. 기본 공장 화면의 요청·시작·실제 관문·상태 갱신은 [실제 실행 안내](agentic-studio.md)를 따른다. 옛 각본은 ?mode=demo에만 남긴다.


## 공식 API 경로와 비용 기록(2026-11-04, D-0079)

`api` 경로는 덱의 GPT 단계를 OpenAI 공식 API로, Gemini 단계를 Gemini API의 OpenAI 호환 주소로 보낸다. 프로필 선택(basic_test·demo·pre_demo_completion_check)은 그대로 쓰며, 경로와 프로필은 지금처럼 따로 고른다.

| 계열 | 주소 | 키 환경변수 | 모델 ID |
|---|---|---|---|
| GPT | `https://api.openai.com/v1` | `OPENAI_API_KEY` | 덱 ID 그대로(`gpt-6.1-sol`, `gpt-6.1-terra`) |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `GEMINI_API_KEY` | `google-antigravity/`를 뺀 ID(`gemini-3.8-flash`, `gemini-4-argon`) |

### 준비와 전환

1. 저장소 루트 `.env`에 `OPENAI_API_KEY`와 `GEMINI_API_KEY`를 넣는다. 공장은 설정을 읽을 때 `.env`를 읽고, 셸에 같은 이름이 있으면 셸 값을 쓴다. 견본은 `.env.example`이다.
2. `uv run --locked cfp models select --route api`로 전환하고 `uv run --locked cfp models show`로 배정을 확인한다. 키가 비어 있어도 전환과 확인은 되며, 실제 호출 직전에 거절된다.
3. 되돌릴 때는 `--route opencodex`를 고른다. 실행 중인 작업에는 소급 적용하지 않는다.

주소·환경변수 이름·모델 ID를 바꿔야 하면 `factory.toml`의 `[text_pipeline.routes.api.families.<openai|gemini>]`와 `[text_pipeline.routes.api.models]`에 적는다. 계열을 정할 수 없는 모델은 해석 단계에서 거절한다.

### 요청 형식

OpenAI로 보내는 요청은 출력 상한을 `max_completion_tokens`로 보내고, 추론 강도가 켜져 있으면 `temperature`를 뺀다. Gemini와 중계로 보내는 요청은 지금 형식을 유지한다. 429를 뺀 4xx 응답은 재시도하지 않고 상태 코드와 공급자 문구를 남긴 채 멈춘다. 출력 상한에는 추론·생각 토큰도 들어가므로, 잘린 응답(`finishReason = length`)이 생기면 그 단계의 상한을 검토한다.

### 비용 기록

호출마다 `resources/price-table-v1.json`의 단가로 비용을 계산해 원장(`ledger/calls.jsonl`)에 남긴다. 원장의 `textBinding`에는 환경변수 이름을 남기지 않는다. 행에는 `estCostUsd`, 적용한 단가(`price`), 과금 구분(`billing.class`), 입력·캐시된 입력·출력·추론 토큰, 잘림 여부가 들어간다. 과금 구분은 공식 API 청구(`api_billed`), 중계 환산(`relay_equivalent`), 미확인(`unverified`), 가짜(`none`)다. 단가나 사용량을 모르면 비용은 `null`이며 0으로 적지 않는다.

Gemini 응답의 출력 토큰 수가 생각 토큰을 빼고 보고될 수 있어, 총 토큰이 더 크면 `총 토큰 − 입력 토큰`을 출력으로 쓰고 `usageSource = total_minus_prompt`로 표시한다(Q-0023). 단가는 기간 한정 행사가가 있어 호출 날짜로 고른다. Gemini 4 Argon은 2026-12-01부터, Gemini 3.8 Flash는 2027-01-01부터 단가가 오른다. 확인하지 못한 단가(Q-0024)는 비워 두며, 형성 실행 예산은 쓸 모델 가운데 단가 미확인이 있으면 호출 전에 거절한다. 표에 없는 단가는 `[pricing.models."<모델 ID>"]`로 덮어쓸 수 있다.

보고서는 원장만 읽는다.

```sh
uv run --locked cfp ledger report <캐릭터>
uv run --locked cfp ledger cost <캐릭터 또는 calls.jsonl 경로> [--recompute] [--out work/cost.json]
```

`--recompute`는 과거 기록(중계 실행 포함)에 실행 시각의 단가를 적용한 "API 환산" 값을 내며 원래 원장을 고치지 않는다. `--out`은 원장 폴더 밖(예: `work/`)에만 쓸 수 있다. 과금 구분이 없는 이전 행은 가짜 공급자면 `none`, 덱 경로가 남아 있으면 그 경로로 추정하고, 나머지는 `unknown`으로 둔다. 중계 기록의 출력 토큰에는 추론 토큰이 빠졌을 수 있어 환산값은 하한에 가깝다. 단가표 밖 모델(예: Claude Sonnet)은 미확인으로 센다. 원장 합계는 추정이다. 실제 청구액은 각 회사의 사용량 화면과 대조해 [검증 기록](../status/verification.md)에 남긴다.


### 스트리밍과 전송 재시도(D-0084)

`[text_pipeline.routes.api] stream = true`이면 공식 API 호출을 스트리밍으로 받는다. OpenAI는 마지막 조각의 사용량을, Gemini는 조각마다 오는 사용량의 마지막 값을 쓴다. Gemini는 생각 요약을 함께 받아 긴 생각 중에도 조각이 오며(첫 조각 약 30초), 생각 요약(`<thought>` 블록)은 본문에서 걷어내고 저장하지 않는다. 이를 위해 Gemini 요청은 `reasoning_effort` 대신 같은 강도의 `thinking_config.thinking_level`을 보낸다.

`[text_pipeline] transport_retries`(기본 1)는 연결 끊김·시간 초과·429·5xx·깨진 스트림일 때만 같은 모델·경로로 다시 보내는 횟수다. 시도마다 예산 예약과 원장 행이 따로 남고, 끊긴 시도는 청구됐을 수 있어 예약을 풀지 않는다(`usageSource = transport_failed:<종류>`). 4xx 거절은 다시 보내지 않는다.

### 범위 밖

이미지 생성, S1·S4a의 `codex exec` 실행은 구독으로 돌아 이 비용에 들어가지 않는다. 영상과 GPU 학습은 각자의 단가 계산을 쓴다. 덱 밖 `[providers.text]`·`[providers.judge]`도 주소와 환경변수 이름을 직접 적으면 공식 API로 보낼 수 있고 같은 요청 형식·비용 기록이 적용된다.
