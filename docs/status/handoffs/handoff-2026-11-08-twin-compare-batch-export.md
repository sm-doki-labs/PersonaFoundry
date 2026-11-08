# 인계: 2026-11-08 트윈 비교 보고·여러 캐릭터 병렬·앱 내보내기

이전 인계: [handoff-2026-11-08-twin-persona-model.md](handoff-2026-11-08-twin-persona-model.md)

## 1. 지금 상태 한눈에

- 실존 인물 갈래 계획 §12 순서 1~10을 구현했다. 남은 것은 순서 11(공급자 사전 확인과 유료 리허설)과 12(발표 점검)다. 둘 다 사용자 자료·승인이 필요하다.
- 트윈 세 방식(TRAIN·BIND_EXISTING·PROMPT_ONLY) 모두 합성 출처 → G0 → … → G8(비교 보고 포함) → G9 → 내보내기 → 일회용 PostgreSQL 적재 확인까지 통과했다.
- 전체 테스트 1372개 통과, 건너뜀 0(`CFP_PG_ADMIN_URL`을 켜고 `scripts/verify_db.sh up`으로 띄운 일회용 DB). Ruff 깨끗. 실제 공급자 호출·학습·커밋·push는 하지 않았다. 일회용 DB는 내렸다.

## 2. 이번 세션에서 한 일

- 서브에이전트 Beauvoir(gpt-6-astra): 순서 8. `stages/s10_eval/compare.py`(비교 보고·호출 계획·`append_twin_comparison`), `blind.py`(가족 블라인드 화면·`import_blind_answers`), `twin.py`·`approve.py` 연결, `contracts/twin_comparison.py`, `prompts/twin_actual.md`, `tests/test_twin_comparison.py`.
- 서브에이전트 Aquinas: 순서 9. `pipeline/batch.py`, `contracts/batch.py`, `cli.py`(`cfp batch run --spec [--execute]`), `pipeline/context.py`·`providers/tracked.py`·`openai_compat.py`·`xai_video.py`·`providers/training/__init__.py`(공급자 상한·429 대기 장부), `web/reads.py`·`runtime.py`·`jobs.py`(캐릭터별 그래프), `tests/test_batch_run.py`, `tests/test_web_twin_graph.py`.
- 서브에이전트 Pascal: 순서 10. `contracts/source.py`(`voiceId`)·`release.py`, `stages/s11_release/package.py`·`twin.py`, `stages/export/export.py`·`settings.py`·`doki_app/api_svc.py`·`chat_svc.py`, `tests/test_twin_export.py`.
- 메인:
  - `pipeline/orchestrator.py`: 트윈 TRAIN의 s10이 기존 평가 보고서 뒤 `append_twin_comparison`을 부르게 연결(긴 프롬프트 질문 경로·보고서가 없는 경우는 그대로 돌려준다). 임시 스크립트로 호출 순서(사전 등록 → 평가 → 보고 → 비교)를 확인했다.
  - 적재 확인 버그 수정: 트윈은 콘텐츠 판 이름에 패키지 판(`pk1`)을 붙이는데 `stages/export/verify.py`는 옛 이름(`<slug>-r1`)을 찾아 실제 DB 적재가 "persona revision 조회 0건"으로 실패했다. 가짜 SQL 테스트로는 드러나지 않았다. `doki_app/naming.revision_prefix`로 규칙을 모으고 chat-svc·api-svc 변환기와 적재 확인이 같이 쓰게 했다.
  - `tests/test_twin_export.py`에 세 방식 실제 적재 테스트(`CFP_PG_ADMIN_URL`이 있을 때만) 추가.
  - 결정 D-0133, 계획 문서 변경 이력.

## 3. 결정

- D-0133 순서 8·9·10 구현 방식(제안)

## 4. 확인한 사실과 정정

- 손흥민 역 TRAIN 경로의 비교 보고는 합성 모델로만 확인했다. 학습된 모델이 서빙되지 않으면 그 조건은 "서빙 없음"으로 표시된다.
- 실제 가족의 구별률, 실제 모델·GPU 서빙 품질, 실제 앱 통화는 측정하지 않았다.
- 배치 실행은 합성 손흥민 역(TRAIN)과 부모님 역(PROMPT_ONLY)을 동시에 s0까지 돌려 각각 G0에서 멈추는 것까지 확인했다. 두 캐릭터를 끝까지 한 명령으로 돌린 실제 실행은 순서 11이다.

## 5. 미결

- 새 질문 없음.

## 6. 다음 할 일

1. 화면(다른 세션 범위와 겹침): Studio가 캐릭터를 바꿀 때 `/api/runtime/graph?character_id=`로 그래프를 다시 받아 s0·s9h·G0·G1s 노드를 그린다. G8의 고정 문구 "긴 프롬프트로 진행"을 서버가 주는 `items.adoptLabel`로 바꾼다. G0·G1s 전용 검토 화면.
2. 다른 저장소 제안(이번에는 고치지 않음): api-svc가 챕터 틀·시작 버튼 문구·"AI 생성 · 본인과 무관한 기술 시연" 표시를 내려주고 앱이 탐색·통화 화면에 보여 준다. chat-svc가 발행 검증과 통화 시 모델 선택 모두 번들의 `modelConfigRevision`(`models/*.json`)을 따르게 한다. 지금 chat-svc는 배포 단위로 모델을 고른다.
3. S4 장면 프롬프트(`stages/s4_frames/prompt.py`)가 트윈에도 "a fictional …"(가상 인물)이라고 적는다. 트윈에서 고칠지 순서 11 사전 확인 때 함께 본다.
4. 순서 11: 실존 얼굴 이미지·영상 공급자 사전 확인 1건씩 → 손흥민 학습 → 손흥민·부모님 병렬 유료 리허설(`cfp batch run --execute`). 사용자 자료(출처 묶음·사진·부모님 동의)와 비용 승인이 필요하다.
5. 순서 12: D-0126 발표 점검 네 항목.

## 7. 떠 있는 것

- 서브에이전트 3명은 모두 끝났고 닫았다.
- 일회용 DB 컨테이너(`cfp-verify-pg-1`)는 내렸다. musk-demo 컨테이너는 건드리지 않았다.
- 코드 변경은 커밋하지 않았다. 다른 세션의 변경과 같은 작업 트리에 있다.
