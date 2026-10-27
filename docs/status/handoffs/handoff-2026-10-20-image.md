# 인계: 2026-10-20(이미지) S1 미리보기를 ChatGPT 구독 이미지 생성으로 연결

이전 인계: [handoff-2026-10-20.md](handoff-2026-10-20.md)(같은 날 앞 세션).

## 1. 지금 상태 한눈에

- S1 미리보기 이미지를 ChatGPT 구독으로 만든다(D-0019). 어댑터 `codex_image`는 `codex exec`의 내장 image_gen으로 한 장씩 만들고 `~/.codex/generated_images/<thread_id>/`의 PNG를 읽어 온다. API 키·과금은 쓰지 않는다.
- `factory.toml`(gitignored)과 `factory.example.toml`의 `[providers.image]`를 `codex_image`로 바꿨다. 테스트는 가짜 실행기로 돈다(38 passed).
- 실제 구독 호출을 2회 했다(테스트 도형 1장, 합성 데모의 외모군 c1 미리보기 1장). 실제 순위 목록으로 S1 전체를 돌리지는 않았다.
- 첫 실제 미리보기가 서양인 인상으로 나왔다. 비교 범위에 인종·지역 칸이 없어서다(Q-0015).

## 2. 이번 세션에서 한 일

- 확인: Codex CLI 0.160.1, `image_generation` 기능 켜짐, 인증 `auth_mode=chatgpt`(API 키 없음). 과거 데스크톱 세션 기록에서 이미지 항목(`image_gen.generation`, `savedPath`) 형식을 확인했다. `codex exec --json` 이벤트에는 이미지 항목이 따로 나오지 않지만 파일은 `generated_images/<thread_id>/`에 저장된다.
- 코드: `providers/codex_image.py`(새 파일), `providers/base.py`의 `ImageResult`에 토큰·원본 경로 칸, `TrackedImageModel`이 구독 토큰을 원장에 기록, `providers/factory.py`에 `codex_image`, `common/errors.py`에 `ImageGenerationError`, `stages/s1_reference/run.py`의 호출 계획에 이미지 경로 표시.
- 테스트: `tests/test_codex_image.py` 4개(정상, 이미지 없음·실행 실패, 설정으로 생성, S1 전체를 `codex_image`(가짜 실행기)로 9장).
- 문서: [결정 기록](../decisions.md) D-0019, [미결 질문](../open-questions.md) Q-0014 해결·Q-0015 추가, [PRD](../../product/prd.md) §11, [명세](../../architecture/spec.md) §11, [LLD](../../architecture/lld.md) §2·§3·§9·§12·§13, README.

## 3. 결정

D-0019(확정).

## 4. 확인한 사실과 정정

- 앞 인계의 "실제 이미지 어댑터는 없다"는 이번 세션으로 바뀌었다.
- 이미지 한 장에 구독 사용량 기준 입력 토큰이 약 11.8만 개였다(만든 이미지가 모델 입력으로 다시 들어가는 것으로 보인다). apps·browser_use·computer_use·MCP를 꺼도 이 부분은 줄지 않는다. 같은 설정의 짧은 텍스트 응답은 약 1.9만 토큰이었다.
- 장당 27~36초가 걸렸다. S1 한 번(최대 12장)은 순차 실행으로 약 6~8분이다.
- 출력 크기는 1254×1254였다. 크기 지시는 강제되지 않는다.

## 5. 미결

Q-0002, Q-0004, Q-0013, Q-0015.

## 6. 다음 할 일

1. Q-0015를 정한다. 넣기로 하면 `popularity-ranking-v1` scope에 칸(예: 인물 인상·지역)을 추가하고 `preview.build_prompt`에 반영한다. 계약이 바뀌므로 schemaVersion을 올릴지 함께 정한다.
2. 사용자가 실제 순위 목록과 비교 범위(Q-0002)를 채우면 `acf ref run x --new-slug <slug> --ranking <file>`로 계획을 보고, 지시 뒤 `--execute`로 S1을 돌린다. 원장으로 구독 사용량을 확인한다(LLD §13).
3. G1 선택 뒤 S2(M2)를 시작한다. `codex exec -i`로 참조 이미지를 넣어 같은 인물을 유지하는지 확인한다.

## 7. 떠 있는 것

없음. 임시 파일: `/tmp/acf-imgprobe-20261020/`(실제 호출 시험 이벤트·이미지 사본). 원본 이미지는 `~/.codex/generated_images/01a158ab-…/`, `~/.codex/generated_images/01a158ae-…/`에 있다.
