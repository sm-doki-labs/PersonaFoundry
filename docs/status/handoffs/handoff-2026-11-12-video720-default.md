# 720p 시작·끝 프레임 기본 모델과 실제 호출 검증

## 요청과 범위

사용자: “영상 쪽도 테스트…720p에 프레임 시작/끝 선택 가능한 모델을 디폴트”. 영상 기본값과 작은 실호출만 진행했다. 이전에 중단한 페르소나·검토 화면 수정은 재개하지 않았다. PR #14는 main에 이미 머지됐으며 이번 변경은 로컬 미커밋이다. 8776 서버는 재시작하지 않았다.

## 변경

- D-0189: xAI API·공장 OAuth·Grok 체인의 모델 미지정 기본값을 `grok-imagine-video-1.5`로 통일했다. 설정 예시·사전 확인 계획·S5/S6 비용 기본값도 맞췄다. 해상도는 720p다. 명시된 기존 모델 설정과 팀 서버 fake 설정은 유지한다.
- `last_frame`이 있으면 Lite·1080p를 제출 전에 거절한다. 포트는 서로 다른 첫·끝 사진도 받는다. S6 기본은 첫 사진과 같은 끝 사진이다. 임의 끝 사진을 고르는 새 프론트 화면은 만들지 않았다.
- 비용 계획·작업 저장·결과 추정에서 끝 프레임 입력 이미지 비용을 포함한다. 재개 계획은 저장된 `pinLastFrame` 값을 따른다. 끝 고정 여부가 바뀐 영상은 부분 재생성·등급 변경에서 재사용하지 않는다.
- PRD v1.27 → spec v1.39 → LLD v1.44에 범위와 구현을 연결했다.

## 검증

오프라인 합성 자료 검사:

```sh
.venv/bin/pytest -q tests/test_video_frame_defaults.py tests/test_video.py tests/test_actions.py tests/test_grok_oauth.py tests/test_grok_chain.py tests/test_twin_precheck.py
# 128 passed, 기존 warnings 2
.venv/bin/pytest -q tests/test_video_tiers.py tests/test_video_evidence_handoff.py tests/test_shared_run_budget.py
# 33 passed, 기존 warnings 3
```

변경 Python 파일 ruff 및 `git diff --check` 통과. 기본 모델·비용 변경 검사가 먼저 실패하는 것을 확인한 뒤 수정했고, 끝 고정 변경 시 재사용 회귀 검사도 실패→통과를 확인했다.

유료 검증은 합성 공 이미지로 2초×2편, 예상 $0.60·상한 $1을 사전 고지했다. `work/video720-frame-test/run.py --execute`는 공장 `make_video_model`을 사용하며, 작업별 POST 시도 여부를 먼저 기록해 중복 제출을 막고 작업 ID가 있으면 조회만 재개한다. 실제로 두 편 모두 `grok_oauth`에서 완료됐다.

| 항목 | 같은 시작·끝 루프 | 서로 다른 시작·끝 |
|---|---:|---:|
| 실제 모델 | grok-imagine-video-1.5 | grok-imagine-video-1.5 |
| 디코딩 크기 | 720×1280 | 720×1280 |
| 프레임 | 24fps, 49장 | 24fps, 49장 |
| 디코딩 길이 | 2.042초 | 2.042초 |
| 제출 뒤 수집 시간 | 31.0초 | 31.9초 |
| 원본 대비 첫/끝 평균 픽셀 차이(255 기준) | 3.22 / 3.66 | 2.48 / 3.60 |
| 공개 단가 기준 추정 | $0.30 | $0.30 |

시작·중간·끝 연락판을 직접 보았다. 루프는 공이 위로 튄 뒤 원위치로 돌아왔고, 전환은 왼쪽에서 오른쪽 지정 위치로 이동했다. 픽셀 차이는 배경 영향을 받는 참고치이며 얼굴·동작 품질 점수가 아니다. 청구 내역 확인은 하지 않았다. 실인물 품질과 프론트 전체 공정은 이번 검증 범위 밖이다.

자료는 Git 제외 경로 `work/video720-frame-test/`에 있으며, 사용자 출력 복사본은 `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/video720-frame-test/`에 있다. `loop.mp4`, `transition.mp4`, 각 JSON·연락판·실행 스크립트·로그를 포함한다. 기존 보존 기준 파일 2,101개는 해시 비교 결과 변경·누락 0개다(`data-preservation.json`).

## 다음 할 일

실제 인물 영상 품질이 필요하면 별도 승인된 입력과 비용 범위로 얼굴·표정·자세·전환 이음새를 평가한다. 이번 결과는 기술 경로 확인이며 기존 인물 품질 승인을 대체하지 않는다. 미커밋 변경 가운데 중단한 공정 수정과 다른 세션 변경이 섞여 있으므로 이후 커밋 요청 시 영상 변경 범위를 따로 선별한다.

공식 근거: [시작·끝 프레임·720p 지원](https://docs.x.ai/developers/model-capabilities/video/reference-to-video), [단가](https://docs.x.ai/developers/pricing), 2026-11-12 조회.
