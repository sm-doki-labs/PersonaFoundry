# 인계: 2026-10-21(영상) S5 소개 영상 — 공식 API 어댑터와 Grok 웹 어댑터

이전 인계: [handoff-2026-10-21-pose.md](handoff-2026-10-21-pose.md)(같은 날 앞 세션).

## 1. 지금 상태 한눈에

- S5 소개 영상을 R0에 넣고 구현했다(D-0028). G2 대표 이미지 전체를 첫 프레임으로 후보 영상을 만들고, G5에서 사람이 한 편을 고른다.
- 영상 어댑터는 `xai_video`(xAI 공식 API, 유료)와 `grok_web`(Playwright가 전용 Chrome 프로필에 CDP로 붙어 grok.com을 조작, 기본 꺼짐) 두 개다(D-0029). 테스트와 기본값은 `fake`다.
- 기본값은 제안이다: 후보 2편 × 8초 × 720p, 소리 없음, `grok-imagine-video-1.5-lite`, 실행당 약 $0.50(D-0030).
- 유료 호출은 하지 않았다. 실제 `factory.toml`에는 `[providers.video]`가 없어 `fake`로 동작한다.
- 테스트 83 passed.

## 2. 이번 세션에서 한 일

- 문서: [PRD](../../product/prd.md)·[명세](../../architecture/spec.md)·[LLD](../../architecture/lld.md) v0.6(S5 R0 편입, 영상 포트, 두 어댑터, 계약, G5, 재개 규칙, 비용 계산). [결정 기록](../decisions.md) D-0028~D-0030, [미결 질문](../open-questions.md) Q-0017.
- 공급자: `providers/base.py`(`VideoRequest`·`VideoResult`·`VideoModel`, submit/collect, `resumable`), `fake_video.py`, `xai_video.py`(POST `/v1/videos/generations` → GET `/v1/videos/{id}` 폴링, 429·5xx 3회 재시도, 결과 URL은 인증 헤더 없이 내려받음, 단가표), `grok_web.py`(주입 가능한 드라이버, `PlaywrightCdpDriver`, 단계별 오류 스크린샷, `resumable=False`), `factory.py` `make_video_model`(grok_web은 `accept_terms_risk = true` 없으면 거절), 원장 `kind=VIDEO`(초·비용).
- 계약: `contracts/video.py` — `intro-inputs-v1`, `video-job-v1`, `video-asset-v1`, `intro-video-approved-v1`. videoId는 `vd-<cid>-intro-vi<k>-<n>`.
- 단계: `stages/s5_intro/`(고정 동작 프롬프트, ffprobe 선택 검사, submit 직후 job 파일 기록, CHECK_FAILED 뒤 같은 rev에서 재개, 비용 상한 사전 확인, G5 페이지 `<video>`, `approve_g5`·`load_approved_intro`). 그래프에서 s5는 G2에 의존하고 오케스트레이터가 외모 축 캐릭터에서 돌린다.
- CLI: `acf video intro <id> [--execute]`(dry run은 예상 USD 표시), `acf video web-setup`(전용 프로필 Chrome 실행 명령과 설정 안내).
- 의존성: 선택 extra `web = ["playwright>=1.45,<2"]`, `uv.lock` 갱신. 기본 설치에는 Playwright가 들어가지 않는다.
- 설정 예시: [factory.example.toml](../../../factory.example.toml)에 `[providers.video]`(xai_video, 주석으로 grok_web·선택자)와 `[stages.s5]`.
- 테스트: `tests/test_video.py`(가짜 영상으로 S5 → G5 SELECT, xAI 요청 본문·폴링·실패·시간 초과·재시도·인증 헤더 미전달을 가짜 HTTP로, grok_web 가짜 드라이버 흐름·오류 스크린샷·약관 플래그 거절, 비용 상한 거절, job 재사용 재개).
- 실제 xAI 호출, 실제 grok.com 조작은 실행하지 않았다.

## 3. 결정

D-0028(확정), D-0029(확정), D-0030(제안).

## 4. 확인한 사실과 정정

- xAI 이미지→영상은 입력 이미지 비율을 따른다. 공식 문서끼리 `aspect_ratio` 설명이 달라 Q-0017로 남겼다.
- 결과 URL은 임시 URL이라 바로 내려받아야 한다. 어댑터는 다운로드에 API 키를 붙이지 않는다.
- xAI 이용 정책은 봇·스크립트로 서비스에 접근하는 것을 금지한다. grok_web은 이 위험을 사용자가 감수한다는 결정(D-0029) 아래에서만 켜진다.
- grok_web 선택자는 로그인하지 않은 상태에서 추정한 기본값이다. 실제 화면과 맞는지 확인하지 않았다.
- Chrome이 디버깅 포트로 떠 있지 않을 때 Playwright CDP 연결이 거부되고 어댑터가 준비 절차를 안내하는 오류를 내는 것을 직접 확인했다.

## 5. 미결

Q-0002, Q-0004, Q-0013, Q-0017.

## 6. 다음 할 일

1. 사용자 승인을 받아 xAI 실제 1회: `XAI_API_KEY`를 셸에 두고 `factory.toml`에 예시의 `[providers.video]`·`[stages.s5]`를 넣은 뒤 데모 캐릭터 사본에서 `acf --root <사본> video intro cf-20261021-s2real --execute`(예상 $0.50). 얼굴 유지, 8초 길이, 첫 프레임 일치를 G5 페이지에서 본다.
2. grok_web 보정: `acf video web-setup` 안내대로 전용 프로필로 로그인한 뒤, 실제 화면에서 업로드·프롬프트·영상 모드·생성·다운로드 선택자를 확인해 `[providers.video.selectors]`에 적는다.
3. Q-0017(정사각형 vs 9:16) 결정. 9:16이면 S2 또는 S5 입력 단계에서 세로 첫 프레임을 만드는 방법을 정한다.
4. S6 챕터 동작 영상 설계(G4 승인 프레임 입력).

## 7. 떠 있는 것

- 비용 미리보기 확인용 데모 사본 `/tmp/acf-s5-dry-185811/`(예시 설정을 `factory.toml`로 넣음). 지워도 된다.
- 실행 중인 프로세스·외부 작업 없음.

