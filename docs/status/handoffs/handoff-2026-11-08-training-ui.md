# 인계: 모델 만들기 보기(D-0130)

이전 인계: [handoff-2026-11-08-ux-fixes.md](handoff-2026-11-08-ux-fixes.md)

## 지금 상태

- 진행 화면에 '공정 | 모델 만들기' 탭과 학습 경로 단계 화면을 붙였다. 서버에 학습 시작·중단·진행 읽기·결과 버리고 반납·학습 없이 진행을 더했다.
- 작업 폴더는 `character-factory-poc-wt/foundry-screens`(브랜치 `codex/foundry-screens`)이고 커밋하지 않았다.

## 한 일

1. 서버: `web/model_path.py`(읽기 모델), `web/app.py`(`model-path`, `training/stop`, `training/release`, 상세 `modelPath`, s10 GPU 확인 표기), `web/jobs.py`(`train`·`skip-training` 작업).
2. 학습 단계: `s10_train/io.py`(중단·학습 없이 진행 기록), `drive.py`(중단 요청 확인, 2초 간격 대기), `gemma_qlora.py`(원격 스텝 진행), 가짜 학습 공급자(`run_polls`·`collect_failures`·`abort`).
3. 오케스트레이터: 웹 실행은 학습 선택 전 평가를 기다림, 실제 어댑터 평가 GPU는 유료 확인.
4. 화면: `studio/shared/flow.js`·`flow.css` 모델 만들기 보기, 학습 상태를 그래프·할 일·인스펙터에 반영. 사용 안내 문구.
5. 시험·문서: `tests/test_web_training.py`, `studio/tests/flow.test.cjs`, D-0130, 명세 v1.25 §35, LLD v1.26 §33, PRD v1.18 FR-78, K-0100~K-0102, 검증 기록, 공장 화면 안내.

## 확인

- 서버 1251 passed·1 skipped, 화면 노드 44 passed.
- 가짜 공급자로 밝은·어두운 화면에서 시작·진행·중단, 결과 받기 실패·다시 받기·평가, 학습 없이 진행을 화면만으로 끝까지 봤다(`work/training-ui-20261108/shots/`).

## 남은 것

- 실제 GPU 학습을 화면으로 돌려 보지 않았다(K-0100). 서버를 다시 켜면 도는 학습 작업은 중단으로 끝난다.
- 재료·데이터셋 새 버전과 대화 데이터 창고 연결은 아직 없다(K-0101). 원래 작업 폴더(main)에 적은 K-0098·K-0099(말뭉치 위치·재작성 방식)와 번호가 이어진다.
- 평가 GPU 예상 비용은 상한만 보인다(K-0102).
- 재료 연결 점검: S9는 4~12턴 후보만 받아 실제 긴 세션을 경고 없이 버린다(K-0103). 12턴으로 잘라 넣는 실험은 `work/training-ui-20261108/real_sources.py --window 12`, `prep_real.py`.
- D-0131로 긴 세션 자르기·같은 세션 묶기·버린 수 경고를 넣었다. 실제 재료 실행은 `serve.py --sns-file /tmp/tui-real-raw.jsonl --target 120 --relax-repeat`(원문 파일은 `real_sources.py`로 만든다).
