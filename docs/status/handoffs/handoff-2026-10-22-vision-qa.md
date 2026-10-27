# 인계: 2026-10-22(이미지 검사) 배경 사진·완성 이미지 비전 평가자 루프

이전 인계: [handoff-2026-10-22-planning-flow.md](handoff-2026-10-22-planning-flow.md)(같은 날 앞 세션).

## 1. 지금 상태 한눈에

- S4a·S4b 배경 사진과 S4 챕터 완성 이미지에 비전 평가자–최적화자 루프를 붙였다(D-0036). 만들기 → 비전 판정(기준표 항목마다 PASS·FAIL·UNSURE) → FAIL이면 수정 지시로 직전 이미지를 편집 → 다시 판정을 최대 2회 수정까지 반복한다(D-0037 제안).
- 끝까지 통과하지 못해도 단계는 멈추지 않는다. FAIL이 가장 적은 시도를 쓰고, 관문 페이지에 빨간 "자동 검사 미통과 — 사람 확인 필요" 경고와 이유를 보인다.
- 가짜 공급자로 오프라인 검증만 했다. 실제 비전 모델은 부르지 않았다. 테스트 221 passed.
- 실제 판정 경로(로컬 중계가 이미지 입력을 넘기는지)는 미확인이다(Q-0020).

## 2. 이번 세션에서 한 일

- 주 에이전트: 비전 포트(`VisionRequest`·`VisionResult`·`VisionModel`), `providers/fake_vision.py`, `OpenAICompatVisionModel`(data URI 이미지, 429·5xx 재시도), `make_vision_model`, `TrackedVisionModel`(원장 kind=VISION), `Context.vision_model`·`use_vision`·`vision_family_warning`, 계약 `contracts/qa.py`(`vision-verdict-v1`, `image-qa-v1`, `QaSummary`)와 기존 계약의 선택 칸 `qa`, 루프 `stages/image_qa.py`(기준표 `plate-v1`·`composite-v1`, 판정 프롬프트, 편집·재생성 방식, 준비 검사 `ensure_judge`, 최대 호출 수), `prompts/image_judge.md`. 문서·설정 예시·호출 최대치 보정(판정 형식 재질의 포함)과 관문 페이지 간격 수정.
- 하위 에이전트(gpt-6.1-sol): S4a·S4b·S4 실행·페이지 통합(시도 파일 `attempts/`, 보고서 `qa/`, 부분 재생성 때 검사 기록 이월, 통과·경고 배지), 호출 계획, `tests/test_image_qa.py`, `tests/test_scene_flow.py` 기대값.
- 문서: [PRD](../../product/prd.md) v0.9(FR-16 수정, FR-42 추가), [명세](../../architecture/spec.md) v0.9(§3·§5·§9·§11), [LLD](../../architecture/lld.md) v0.9(§2·§3·§5.10b·§8.4a·§9), [결정 기록](../decisions.md) D-0036·D-0037, [미결 질문](../open-questions.md) Q-0020, [factory.example.toml](../../../factory.example.toml) `[providers.vision]`·`[stages.image_qa]`.
- 수동 확인: 가짜 판정으로 G4a 페이지를 만들어 headless Chrome으로 캡처했다(`/tmp/acf-vqa-demo-20261022/g4a.png`).
- 실행하지 않았다: 실제 비전 판정 호출, 실제 이미지 생성.

## 3. 결정

D-0036(확정), D-0037(제안).

## 4. 확인한 사실과 정정

- 비전 판정 연결은 이번에 처음 생겼다. 명세에 있던 `VisionModel` 포트는 코드에 없었다.
- 호출 최대치는 판정 형식이 틀릴 때 한 번 더 묻는 호출까지 넣는다. 배경 사진 9장이면 이미지 최대 27회, 판정 최대 54회다. 하위 에이전트가 처음 넣은 값(판정 27회)은 실제 최대보다 작아 고쳤다.
- 판정 모델 기본값은 Gemini 계열(`google-antigravity/gemini-3.1-pro`)이다. 이미지 생성(`codex_image`)은 gpt 계열이라 D-0010을 지킨다.
- 얼굴 임베딩(Q-0011의 둘째 층)과 G2 대표 이미지·S1 미리보기 검사는 아직 없다.

## 5. 미결

Q-0002, Q-0004, Q-0011, Q-0013, Q-0018, Q-0019, Q-0020.

## 6. 다음 할 일

1. Q-0020 확인: 로컬 중계에 이미지 한 장을 붙인 chat/completions를 보내 Gemini가 이미지를 읽는지 본다(사용자 승인 뒤). 안 되면 판정 경로를 정한다.
2. 실제 판정과 사람 판단 비교: 지난 실험 이미지(배경 속 인물, 턱 괴기 사례)를 판정에 넣어 기준표 항목의 일치율을 검증 기록에 남긴다.
3. 기획 → 장면 → 완성 이미지 실제 흐름 1회(앞 인계의 다음 할 일 1)에 이 검사를 함께 켠다.

## 7. 떠 있는 것

- 하위 에이전트는 종료했다. 실행 중인 프로세스 없음.
- 데모 폴더 `/tmp/acf-vqa-demo-20261022/`(가짜 데이터). 지워도 된다.

