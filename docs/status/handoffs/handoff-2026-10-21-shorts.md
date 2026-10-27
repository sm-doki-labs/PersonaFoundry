# 인계: 2026-10-21(쇼츠) S5 9:16 세로 첫 프레임과 Grok 웹 어댑터 실제 화면 맞춤

이전 인계: [handoff-2026-10-21-video.md](handoff-2026-10-21-video.md)(같은 날 앞 세션).

## 1. 지금 상태 한눈에

- 소개 영상은 쇼츠용 9:16이다(D-0031, 비율은 사용자 확정). S5가 G2 대표 이미지를 참조로 세로 첫 프레임을 구독 이미지 생성으로 만들고 정확한 9:16으로 잘라 영상에 넣는다. Q-0017 해결.
- `grok_web`을 실제 grok.com 화면에 맞췄다(D-0032). 웹 영상 1편을 실제로 만들어 받았다(480p·6초, 같은 얼굴 유지).
- 이 Grok 계정은 무료 등급이라 480p·6초만 되고, 1편 뒤로는 제출하면 결제 창이 뜬다. 그래서 데모 캐릭터의 S5 전체 웹 실행은 G5까지 가지 못했다(Q-0018).
- xAI 공식 API는 사용자 지시("api는 스킵")로 부르지 않았다. 테스트 89 passed.

## 2. 이번 세션에서 한 일

- 코드: `stages/s5_intro/first_frame.py`(세로 프롬프트, 크기 힌트, 가운데 자르기, 비율 25% 넘게 벗어나면 실패), `run.py`(첫 프레임 생성·고정, `first_frame = vertical|hero`, `aspect_ratio = "9:16"` 기본, 웹 설정 사전 확인, 끊겨 RUNNING으로 남은 실행도 같은 rev에서 재개), `contracts/video.py`(`intro-inputs-v2`, `firstFrameSource`), `page.py`(대표 이미지와 첫 프레임 나란히), `providers/grok_web.py`(실제 화면 흐름, 결제 창 감지, 영상 주소 받기, `check_settings`), `providers/tracked.py`(`check_settings` 전달), `providers/fake_image.py`(요청 크기 비율을 지킨 가짜 이미지).
- 테스트: `tests/test_video.py` 20개(세로 첫 프레임, 정사각형 거절, 대표 이미지 모드, 자르기 계산, 웹 설정 거절·결제 창, 끊긴 실행 재개, 실제 흐름 순서).
- 문서: [PRD](../../product/prd.md)·[명세](../../architecture/spec.md)·[LLD](../../architecture/lld.md) v0.7, [결정 기록](../decisions.md) D-0031·D-0032, [미결 질문](../open-questions.md) Q-0017 해결·Q-0018 추가, [factory.example.toml](../../../factory.example.toml) `[stages.s5]`·grok_web 주석.
- 실제 실행: 구독 이미지 세로 시험 1장, Grok 웹 수동 흐름 1편, 데모 사본 S5 `--execute` 2회(첫 프레임 생성 통과, 웹 제출은 결제 창). 결과는 [검증 기록](../verification.md).
- 실행하지 않았다: xAI 공식 API 호출, Grok 결제·구독.

## 3. 결정

D-0031(비율 확정·방법 제안), D-0032(제안).

## 4. 확인한 사실과 정정

- Codex 내장 이미지 생성은 세로 크기를 요청하면 941×1672처럼 세로로 만든다. Q-0017에 적었던 "Codex 이미지 경로는 크기를 강제하지 못한다"는 정사각형 기본값만 본 판단이었다.
- grok.com 웹은 이미지를 올리면 종횡비 버튼이 사라지고 영상이 이미지 비율을 따른다. 길이는 6/10/15초, 해상도는 480p/720p만 있다. 웹에는 8초(D-0030 기본값)가 없다.
- 결과 페이지의 다운로드 버튼은 Playwright 다운로드 이벤트를 내지 않았다. 영상은 `assets.grok.com/.../generated_video.mp4` 주소를 로그인 세션으로 받으면 된다.
- 웹 결과는 400×736으로 정확한 9:16(0.5625)이 아니라 0.543이다. 편집 단계에서 맞출 일이 남는다.
- 첫 자동 실행이 결과 대기에서 멈춘 원인은 탭 위치가 아니라 결제 창(사용량 소진)이었다. 그때는 주소의 `#subscribe`를 보지 않아 90초·10분을 기다렸다. 지금은 바로 실패한다.

## 5. 미결

Q-0002, Q-0004, Q-0013, Q-0018.

## 6. 다음 할 일

1. Q-0018 결정: Grok 사용량을 어떻게 확보할지(유료 등급, 한도 회복 대기, 공식 API). 확보되면 `/tmp/acf-s5-dry-185811`에서 `uv run --extra web acf --root /tmp/acf-s5-dry-185811 video intro cf-20261021-s2real --execute`를 다시 돌린다. vi1의 세로 첫 프레임을 그대로 쓰고 영상 2편만 만들어 G5 페이지로 간다.
2. G5 페이지에서 사람이 한 편을 고르고 `acf gate import ... G5`로 승인한다.
3. 480p 웹 결과가 쇼츠 품질로 충분한지 사람이 본다. 부족하면 720p(유료 등급) 또는 공식 API 1080p를 비교한다.
4. S6 챕터 동작 영상 설계(G4 승인 프레임 입력).

## 7. 떠 있는 것

- 전용 프로필 Chrome(`~/.acf/grok-chrome`, 원격 디버깅 포트 9222)이 grok.com에 로그인된 채 떠 있다. 닫아도 로그인은 프로필에 남는다.
- 데모 사본 `/tmp/acf-s5-dry-185811/`: `factory.toml`이 grok_web 설정이고, S5 vi1은 첫 프레임까지 고정된 채 CHECK_FAILED다.
- 웹 작업 폴더 `~/.acf/grok-web-work/`(오류 스크린샷). 시험 산출물 `/tmp/acf-s5-vertical-20261021/`.
- 실행 중인 프로세스 없음.

