# 검증 기록

규칙은 [인계 규칙](README.md)을 따른다. 오프라인 검증과 실제 외부 공급자를 부른 검증을 구분한다.

| 날짜 | 종류 | 실행한 것 | 입력 | 결과 | 결과 경로 |
|---|---|---|---|---|---|
| 2026-10-14 | 문서(오프라인) | 저장소 안 모든 `*.md`의 링크 대상 파일 존재 여부와 절 참조 표기(§)를 스크립트로 확인 | 문서 16개 | 통과. 유일한 미존재 링크는 `templates/handoff-template.md`의 자리표시자 `handoff-YYYY-MM-DD.md`로 의도된 것 | 없음 |
| 2026-10-14 | 코드(오프라인) | `scripts/check.sh` = `uv sync --locked`, `ruff check`, `ruff format --check`, `pytest -q` | src 2,700여 줄, tests 17개(가짜 모델, 소켓 차단) | 통과: lint 0건, 17 passed. 페르소나 전체 흐름(plan import → S7 → S8 → G6 승인 → pv1), 검사 실패 재시도, 재시도 초과 CHECK_FAILED, 섹션 불일치 거절, D-0005 근거 검사, 판정 입력 익명화 확인 | 없음(테스트는 tmp_path) |
| 2026-10-14 | 실제 공급자(로컬 opencodex 중계) | `acf plan import dohee` → `persona traits --execute` → `persona prompts --execute`(pv1 정렬 실패, pv2 중단 후 재개) → `persona probe --execute` | 기획서 pr1(P29 기반), 생성 Opus 5.5, 판정 gpt-6.1-sol | S7 2회 시도 통과, S8 pv2 통과, 표본 2차 판정 LONG 4:1. 호출 37회(실패 1). G6 대기 중 | `runs/characters/cf-20261014-dohee/`, [보고서](../reports/2026-10-14-dohee-p29-persona-run.md) |
| 2026-10-14 | 코드(오프라인) | `scripts/check.sh` | 테스트 22개(가짜 codex 백엔드, 오케스트레이터, 검사 CLI, 오염 탐지 추가) | 통과 | 없음 |
| 2026-10-14 | 실제 공급자 | `acf run x --new-slug agentic-p29 --until G6 --auto-approve G3 --brief ... --probes ... --execute` | 브리프 1장, codex_exec(Opus 5.5) × 3단계, 표본 Opus, 판정 Sol | S3→G3(자동)→S7(자가 수정 1회)→S8→G6 대기. 18회 호출, 오염 0. 약 3분 10초 | `runs/characters/cf-20261014-agentic-p29/`, [보고서](../reports/2026-10-14-agentic-p29-run.md) |
| 2026-10-20 | 코드(오프라인) | `scripts/check.sh` = `uv sync --locked`, `ruff check`, `ruff format --check`, `pytest -q` | 테스트 34개(기존 22 + S1 12: 합성 순위 목록 2개·인물 14명, 가짜 Scout·가짜 ImageGen, 소켓 차단) | 통과: lint 0건, 34 passed. S1 → G1 SELECT, 3명 미만 외모군 제외, 미인식 인물 제외, 이름 유출 0건(보고서·미리보기·S2 입력), 프롬프트에 이름이 있으면 이미지 호출 전 중단, 재실행 ARI 1.0, 예산 초과 시 쓰기 전 거절, dry run에 이름 미출력 | 없음(테스트는 tmp_path) |
| 2026-10-20 | 수동 확인(오프라인) | 테스트와 같은 합성 입력으로 `run_s1`을 돌려 `gate-G1.html`을 headless Chrome으로 캡처 | 합성 순위 목록, 가짜 모델 | 후보 3개(공통 특징·근거·한계·미리보기 3장), 제외 2건, 주의점 3개, 결정 양식 표시 확인 | `/tmp/acf-s1-demo-20261020/g1.png`(저장소 밖) |
| 2026-10-20 | 문서(오프라인) | 저장소 안 모든 `*.md`의 상대 링크 대상 존재 여부를 스크립트로 확인 | 링크 88개 | 통과. 미존재는 `templates/handoff-template.md`의 자리표시자 하나(의도됨) | 없음 |
| 2026-10-20 | 실제 공급자(ChatGPT 구독, Codex CLI 0.160.1) | `codex exec --json -s read-only -m gpt-6.1-sol`로 내장 이미지 생성 1장(테스트 도형, 플러그인 켠 상태) | 프롬프트 "plain flat blue circle" | 통과. 26.7초, 1254×1254 PNG가 `generated_images/<thread_id>/`에 저장됨. JSON 이벤트에는 이미지 항목 없음 | `/tmp/acf-imgprobe-20261020/events.jsonl` |
| 2026-10-20 | 실제 공급자(ChatGPT 구독) | `CodexImageModel().generate(...)`(apps·browser_use·computer_use·MCP 끔) | 합성 데모 외모군 c1 미리보기 프롬프트 1개(이름 없음) | 통과. 36.3초, 1254×1254 PNG, 입력 117,721·출력 323 토큰. 인물이 서양인 인상(Q-0015) | `/tmp/acf-imgprobe-20261020/c1-1-codex.png` |
| 2026-10-20 | 코드(오프라인) | `scripts/check.sh` | 테스트 38개(+ `codex_image` 4개, 가짜 실행기) | 통과: lint 0건, 38 passed | 없음 |
| 2026-10-20 | 실제 공급자(ChatGPT 구독) | `CodexImageModel().generate(...)`, 외모군 c1 프롬프트에 "fictional Korean woman" + 피할 것 "text, watermark, logo, celebrity likeness" | 같은 프롬프트 2회 | 실패 2회: "Image generation was blocked by the safety system". 어댑터가 `ImageGenerationError`로 보고 | 없음 |
| 2026-10-20 | 실제 공급자(ChatGPT 구독) | 같은 프롬프트, 피할 것 "text, watermark, logo"(celebrity likeness만 제거) | 1회 | 통과. 35.8초, 입력 40,367 토큰, 1254×1254 PNG, 한국인 인상 확인 | `/tmp/acf-imgprobe-20261020/c1-1-korean.png` |
| 2026-10-20 | 코드(오프라인) | `scripts/check.sh` | 테스트 43개(+ 인물 인상·v2·차단 처리 5개) | 통과: lint 0건, 43 passed | 없음 |
| 2026-10-21 | 실제 공급자(ChatGPT 구독) | `codex exec -i <참조.png> -- <프롬프트>`로 내장 이미지 생성 1회 | 참조: 2026-10-20 배우 화보 시험 이미지, 새 장면(카페·니트) | 통과. 32초, 입력 50,235 토큰. 얼굴·머리가 유지된 새 장면 | `/tmp/acf-imgprobe-20261020/ref-test.png` |
| 2026-10-21 | 실제 공급자(ChatGPT 구독) | `run_s2` 1차(합성 S1, 재생 미리보기, G1 c2 + 참조 c2-1, 후보 2장) | 외형 태그 포함 프롬프트 | 생성 통과(장당 약 36초, 입력 5.1만·17.4만 토큰). 그러나 머리가 태그(긴 흑발 생머리)대로 바뀌어 참조 사진과 다름 | `/tmp/acf-s2-demo-20261021/runs/characters/cf-20261021-s2real/s2-hero/ar1/` |
| 2026-10-21 | 실제 공급자(ChatGPT 구독) | G2 REQUEST_CHANGES → `run_s2` 2차(참조 있으면 외형 태그 제외) → G2 SELECT h1 | 같은 입력 | 통과. 후보 2장 모두 참조 사진과 같은 얼굴·머리. `appearance-spec.json`(ar2) 고정 | 같은 캐릭터의 `s2-hero/ar2/`, `/tmp/acf-s2-demo-20261021/ar2-compare.png` |
| 2026-10-21 | 코드(오프라인) | `scripts/check.sh` | 테스트 55개(+ S2·G1 참조 사진 11개, codex 참조 첨부 1개) | 통과: lint 0건, 55 passed | 없음 |
| 2026-10-21 | 실제 공급자(ChatGPT 구독) | 데모 캐릭터(G2 ar2 승인)에 가짜 Planner로 S3 pr1(appearanceRev=ar2) → G3 → `run_s4` fr1(챕터당 1장) | 기획 장면: 비 오는 책방 창가 / 야시장 골목 / 새벽 버스 정류장 | 통과. 3장 모두 기준 얼굴·장면·조명 일치. 장당 32~38초, 입력 5.1만~12.5만 토큰. ch1이 기준 사진의 턱 괴는 자세를 복사 | `/tmp/acf-s2-demo-20261021/runs/characters/cf-20261021-s2real/s4-frames/fr1/`, `/tmp/acf-s2-demo-20261021/fr1-compare.png` |
| 2026-10-21 | 실제 공급자(ChatGPT 구독) | G4 REQUEST_CHANGES → 자세 문장 추가 후 `run_s4` fr2 → G4 SELECT(ch1-f1, ch2-f1, ch3-f1) | 같은 입력 | 생성·승인 통과, `approved-frames.json` 고정. 자세 문제는 남음(3장 중 2장이 턱 괴기, Q-0016) | 같은 캐릭터의 `s4-frames/fr2/`, `/tmp/acf-s2-demo-20261021/fr2-compare.png` |
| 2026-10-21 | 코드(오프라인) | `scripts/check.sh` | 테스트 66개(+ S3 외모 연결·S4·G4 11개) | 통과: lint 0건, 66 passed | 없음 |
| 2026-10-21 | 실제 공급자(ChatGPT 구독) | 자세 비교 실험: fr2 프롬프트 그대로 참조만 바꿔 3챕터씩 생성 | (a) 얼굴 크롭(OpenCV Haar, 1.4배) (b) 대표 이미지로 만든 손 없는 정면 헤드샷 | 턱 괴기: 전체 이미지(fr1·fr2) 6장 중 3장, (a) 3장 중 1장(ch1), (b) 3장 중 1장(ch1). ch1은 참조와 무관하게 남음 | `/tmp/acf-s2-demo-20261021/facecrop-vs-full.png`, `pose-compare-3way.png` |
| 2026-10-21 | 실제 공급자(ChatGPT 구독) | ch1에 손 문장 + 피할 것 추가, 얼굴 크롭 참조로 2회 | 같은 ch1 프롬프트 | 턱 괴기 2장 중 0장, 손이 테이블 위 | `/tmp/acf-s2-demo-20261021/guard-ch1-compare.png` |
| 2026-10-21 | 실제 공급자(ChatGPT 구독) | 공정 적용 뒤 `run_s4` fr3(챕터당 2장, 자동 얼굴 크롭) | 데모 캐릭터 G2 ar2·G3 pr1 | 통과. 얼굴 상자 자동 검출, 6장 모두 같은 얼굴·장면, 턱 괴기 0장. 장당 32~54초. G4 대기 | `/tmp/acf-s2-demo-20261021/runs/characters/cf-20261021-s2real/s4-frames/fr3/`, `fr3-vs-fr2.png` |
| 2026-10-21 | 코드(오프라인) | `scripts/check.sh`(OpenCV 4.14 포함 `uv.lock`) | 테스트 69개(+ 얼굴 크롭·S4 참조 선택 3개, 기존 테스트 기대값 보강) | 통과: lint 0건, 69 passed | 없음 |
| 2026-10-21 | 코드(오프라인) | `scripts/check.sh`(선택 extra `web`의 Playwright 포함 `uv.lock`) | 테스트 83개(+ S5·G5·영상 어댑터 14개: 가짜 영상 S5 → G5, 재개·실패·비용 상한, 가짜 HTTP xAI 요청·폴링·재시도·다운로드 인증 헤더 미전달, 가짜 드라이버 grok_web 흐름·오류 스크린샷, 약관 플래그 거절) | 통과: lint 0건, 83 passed. 유료 호출 없음 | 없음 |
| 2026-10-21 | 수동 확인(오프라인) | Chrome 디버깅 포트가 없는 상태에서 `PlaywrightCdpDriver`로 연결 | `http://127.0.0.1:9222` | 연결 거부를 `VideoGenerationError`로 바꾸고 `acf video web-setup` 안내를 붙이는 것 확인 | 없음 |
| 2026-10-21 | 수동 확인(오프라인) | 데모 캐릭터 사본에 `factory.example.toml`을 넣고 `acf video intro` dry run(`XAI_API_KEY` 없음) | G2 ar2 승인 캐릭터 | 후보 2편, 720p 8초, 예상 0.50 USD 표시. 파일·호출 없음 | `/tmp/acf-s5-dry-185811/`(저장소 밖) |
| 2026-10-21 | 실제 공급자(ChatGPT 구독) | `CodexImageModel().generate(...)`로 세로 첫 프레임 시험 1회(대표 이미지 참조, 크기 힌트 1024x1536, 9:16 프롬프트) | 데모 캐릭터 G2 h1 | 통과. 33초, 입력 12.7만 토큰, 941×1672(9:16과 0.1% 차이). 같은 얼굴·머리·옷·빛, 턱 괴는 손 없음 | `/tmp/acf-s5-vertical-20261021/compare.jpg` |
| 2026-10-21 | 실제 공급자(Grok 웹, 무료 등급) | 전용 프로필 Chrome(CDP)에서 비디오 모드 화면 확인, 옵션별 클릭, 9:16 첫 프레임 업로드 → 움직임 프롬프트 → 제출 → 결과 영상 받기 | 위 세로 첫 프레임(940×1672로 자름), 480p·6초·소리 끔 | 720p·10s·15s는 누르면 결제 창. 480p·6s 1편 약 20초 생성, 400×736·6.04초·24fps·소리 없음, 처음부터 끝까지 같은 얼굴. 다운로드 버튼은 다운로드 이벤트 없음, 영상 주소 직접 받기는 200 video/mp4 1.33MB | `/tmp/acf-s5-vertical-20261021/grok-web-480p-6s.mp4`, `strip.jpg` |
| 2026-10-21 | 실제 공급자(구독 이미지 + Grok 웹) | 데모 사본에서 `acf video intro --execute`(grok_web, 후보 2편, 480p·6초) | 데모 캐릭터 G2 ar2 | 세로 첫 프레임 생성 통과(43초, 입력 5.2만 토큰, 941×1672 → 940×1672). 웹 제출은 결제 창으로 막힘(사용량 소진). 1차는 결과 대기에서 멈춰 중단, 결제 창 감지 추가 뒤 2차는 8초 만에 "영상 생성 한도를 다 썼다" 오류와 스크린샷. G5까지는 가지 못함 | `/tmp/acf-s5-dry-185811/runs/characters/cf-20261021-s2real/s5-intro/vi1/`, `/tmp/acf-s5-vertical-20261021/vi1-compare.jpg` |
| 2026-10-21 | 코드(오프라인) | `scripts/check.sh` | 테스트 89개(+ 세로 첫 프레임 생성·자르기·정사각형 거절·대표 이미지 모드, 웹 설정 사전 거절, 결제 창 실패, 끊긴 실행 재개, 실제 화면 흐름의 가짜 드라이버) | 통과: lint 0건, 89 passed. xAI API 호출 없음 | 없음 |
| 2026-10-22 | 조사(읽기 전용) | api-svc 캐릭터·프로필 카드·단계·미디어 모델, chat-svc 페르소나 v6·챕터 정의·챕터 사실·관계 프로필·퀘스트를 읽어 앱의 캐릭터·챕터 칸 정리 | 이서연 퀘스트 v48(페르소나 r14, 챕터 v43·v42·v42·v24) | 캐릭터 칸(프로필·페르소나·미디어)과 챕터 사실 칸 확인. 영상통화 배경은 세 챕터 장소 재사용 | 없음 |
| 2026-10-22 | 코드(오프라인) | 하위 에이전트별 검사: 기획 `tests/test_plan_variants.py`, 참고 자료 `tests/test_refs.py`, 장면 `tests/test_scene_flow.py`·`test_frames.py`·`test_video.py` | 가짜 텍스트·이미지 모델, 소켓 차단 | 각각 53·19·67 passed(에이전트 보고, 통합 뒤 전체 실행에 포함) | 없음 |
| 2026-10-22 | 코드(오프라인) | `scripts/check.sh` | 테스트 182개(+ 기획 변형·참고 자료·배경·자세·완성 이미지·갈래별 오케스트레이터) | 통과: lint 0건, 182 passed. 씨앗 없이 돌리면 S3가 입력을 기다리고 S5가 G5까지 가며, 씨앗 뒤 G4 승인까지 이어짐. 실제 모델 호출 없음 | 없음 |
| 2026-10-22 | 수동 확인(오프라인) | 빈 루트에 `factory.example.toml`을 넣고 `acf plan variants`·`scene backgrounds`·`scene poses`·`frames run`·`refs select` dry run | 없는 캐릭터 | 의존 안내와 호출 계획(변형 최대 6회, 배경 에이전트 1 + 배경 사진 9, 장면·자세 2 + 직접 정의 배경 최대 3, 완성 이미지 3)만 출력, 파일 생성 없음 | 없음 |
| 2026-10-22 | 코드(오프라인) | `scripts/check.sh` | 테스트 221개(+ 이미지 검사 루프 단위: 첫 시도 통과, 편집 수정 뒤 통과, 재생성 방식, 상한 초과 시 FAIL 최소 시도 선택, 판정 형식 재질의·항목 불일치 거절, 검사 끔 / S4a·S4b·S4 통합: 배경 사진 2회째 통과, 계속 실패해도 단계는 G4a 대기, 완성 이미지 판정 참조 순서, 부분 재생성 때 검사 기록 이월, 배지 / 준비 검사: 실제 이미지 + 가짜 판정 거절, 같은 계열 거절 / OpenAI 호환 비전 요청 본문·재시도 / 호출 최대치) | 통과: lint 0건, 221 passed. 실제 모델 호출 없음 | 없음 |
| 2026-10-22 | 수동 확인(오프라인) | 가짜 판정(ch1-b1 계속 실패, ch2-b1 한 번 실패 뒤 통과, ch3-b2 판단 보류)으로 S4a를 돌려 G4a 페이지를 headless Chrome으로 캡처 | 데모 캐릭터(가짜 공급자) | 실패 후보에 빨간 "자동 검사 미통과 — 사람 확인 필요"와 이유, 나머지에 통과 배지와 보고서 링크 표시 확인. 배지·링크 간격을 고쳤다 | `/tmp/acf-vqa-demo-20261022/g4a.png`(저장소 밖) |
| 2026-10-22 | 문서(오프라인) | 인계 문서 11개를 `docs/status/handoffs/`로 옮긴 뒤 저장소 안 모든 `*.md`의 상대 링크 대상 존재 여부를 스크립트로 확인 | 문서 전체 | 통과. 미존재는 인계 양식의 자리표시자 `handoff-YYYY-MM-DD.md` 하나(의도됨) | 없음 |
| 2026-10-22 | 실제 공급자(Opus 5.5 codex_exec 에이전트 + ChatGPT 구독 이미지) | 데모 캐릭터를 `runs/`로 옮긴 뒤 `acf plan seed`(시험 씨앗) → `acf plan variants --execute` 1차 | 씨앗 sd1, G2 ar2 | 실패: 에이전트가 보조 스크립트를 `/tmp/gen_pr1.py`에 써서 오염 검사가 출력을 버렸다(pr1, 원장 AGENT_TAINTED). 같은 검사가 말투 표기 "'~요'"의 물결표를 홈 경로로 잘못 잡았다(오탐) | `runs/characters/cf-20261021-s2real/s3-plan/pr1/workspace/codex-events.jsonl` |
| 2026-10-22 | 코드(오프라인) | 오염 검사 정규식 수정(홈 경로만 잡음), 공통 작업 규칙에 `scratch/` 사용 추가, `tests/test_agentic.py` 오탐·`/tmp` 사례 추가 | — | 통과. 1차 실행 기록을 다시 검사하면 `/tmp/gen_pr1.py`만 남음 | 없음 |
| 2026-10-22 | 실제 공급자(같은 구성), L2 확인 | `plan variants --execute`(2차) → G3 자동 승인(v1) → `scene backgrounds --execute` → G4a 자동 승인(b1) → `scene poses --execute` → G4b 자동 승인(p1) → `frames run --execute`. 이미지 자동 검사 끔(`[stages.image_qa] enabled = false`) | 시험 씨앗 sd1, G2 ar2. 자동 승인은 `reviewer=auto:l2-run`(사람 검토 아님) | 통과, G4 사람 검토 대기. 약 12분(04:25~04:37). 변형 3안 87초(입력 13.4만·출력 7.5천 토큰, 같은 4개 상황·서로 다른 첫 행동, 에이전트가 `scratch/` 사용). 배경 에이전트 53초 + 배경 사진 9장 302초(940×1672, 사람 없음, 입력 64.5만 토큰). 장면 사실 28초·자세 54초(챕터 사실이 ch1 첫 만남 → ch2 산책 약속 → ch3 마지막 컷으로 이어짐, 손은 모두 소품 위). 완성 이미지 3장 202초(940×1672, 기준 얼굴 유지, 턱 괴기 없음). 관찰: 세 챕터 모두 b3가 해질녘 한강으로 겹침 | `runs/characters/cf-20261021-s2real/{s3-plan/pr2, s4a-backgrounds/bg1, s4b-poses/ps1, s4-frames/fr1}`, `/tmp/acf-l2/plates.jpg`, `/tmp/acf-l2/frames.jpg` |
| 2026-10-22 | 코드(오프라인) | S6 동작 영상 골격: `scripts/check.sh`(ruff + pytest), `tests/test_actions.py` 46개(G4 의존, 첫 프레임 = 승인 이미지 바이트, 3챕터 × 3동작 제출, 반복 재생 문장, G5b 선택·제외·잘못된 답, 동작별 부분 재생성과 재사용 영상 해시 동일, 시간 초과·중단 재개, 설정·예산 검사, dry run, 오케스트레이터 G5b 대기·자동 승인) | 가짜 이미지·영상 공급자 | 통과, 전체 267 passed. 실제 영상 호출 없음 | `tests/test_actions.py` |
| 2026-10-22 | 수동 확인(오프라인) | 테스트가 만든 G5b 검토 페이지를 headless Chrome으로 캡처 | 가짜 공급자 | 챕터별 첫 프레임, 동작별 영상 재생기, 선택·제외·수정 메모 칸 표시 확인 | `/tmp/acf-s6-demo/g5b.png`(저장소 밖) |
| 2026-10-22 | 코드(오프라인) | S6 동작 목록을 앱 통화 영상 표준 세트로 교체(D-0040, D-0041): `scripts/check.sh`, `tests/test_actions.py` 57개(`l2` 18편 + 무표정 사진 3장, 무표정 출발 영상의 첫 프레임, 길이 15·10초, 앱 지시문·관계 단계 메모, `standard` 111편 계획, 목록 직접 지정, 승인 기록의 앱 칸, 부분 재생성 때 무표정 사진 재사용, 설정 검사) | 가짜 이미지·영상 공급자. 카탈로그는 api-svc `data/call_clips.json` 사본 | 통과, 전체 278 passed. 실제 호출 없음 | `tests/test_actions.py`, `src/acf/stages/s6_actions/app_clips.py` |
| 2026-10-22 | 수동 확인(오프라인) | 새 G5b 페이지를 headless Chrome으로 캡처 | 가짜 공급자 | 챕터별 미소·무표정 첫 프레임 나란히, 동작마다 앱 이름·제목·출발 표정·길이·사용 조건·프롬프트 표시 확인 | `/tmp/acf-s6-demo2/g5b.png`(저장소 밖) |
| 2026-10-27 | 수동 확인(오프라인) | 데모 캐릭터 G1 미리보기의 공급자·모델과 파일 해시 확인(`previews.json` 읽기, `shasum -a 256`) | `cf-20261021-s2real` `rf1`, 미리보기 9장 | 9장 모두 같은 해시 `3a07fa186ed2…`, 공급자·모델 `replay`. 실제 얼굴 미리보기가 아니다(K-0033) | `runs/characters/cf-20261021-s2real/s1-reference/rf1/previews.json` |
| 2026-10-27 | 코드(오프라인) | 새 프로젝트 `character-factory-poc`(Git)에서 PoC 계약(`f8bc6e4`)과 A·B·F·G 갈래를 합친 뒤 `scripts/check.sh` | 가짜 공급자, `httpx.MockTransport`, FastAPI TestClient, 합성 runs | 통과: lint 0건, 347 passed(기존 278 + 계약 15 + A 순증 8 + F 11 + B 22 + G 11 + 수집 CLI 2). 경고 1건(Starlette TestClient의 httpx 폐기 예정 안내). 실제 공급자 호출 없음 | 없음 |
| 2026-10-27 | 수동 확인(오프라인) | G 갈래: 합성 데모 루트(가짜 공급자)에 `python -m acf.web`을 띄우고 브라우저로 d-ops·c-glass·index를 열어 목록·단계·대기 관문·작업 실행 확인 | `/tmp` 합성 루트 | 실제 API 값 표시와 백그라운드 작업 완료 갱신 확인(하위 에이전트 보고, 통합 담당은 다시 열어 보지 않음) | 저장소 밖 |
| 2026-10-27 | 코드 + 실제 DB(일회용 Docker) | C·D1·D2·E·G2 갈래를 합친 뒤 이름 바꾸기(모듈 `acf` → `character_factory_poc`, 명령 `acf` → `cfp`, 배포 이름 `character-factory-poc`, 환경변수 `ACF_` → `CFP_`), `scripts/verify_db.sh up` 뒤 `CFP_PG_ADMIN_URL`을 설정하고 `scripts/check.sh` | 가짜 공급자, 합성 캐릭터 1명(실제 적재 테스트), 일회용 컨테이너 `cfp-verify-pg-1` | 합치기 직후 443 passed + 1 skipped(적재 테스트, 환경변수 없음). 이름 바꾼 뒤 444 passed, 건너뜀 0. 실제 적재 테스트가 chat-svc(정의 15개 publish·verify, 캐릭터 1·챕터 3)와 api-svc(seed load, 캐릭터 1·단계 3·클립 18·미디어 8)에 넣고 일회용 DB를 지웠다. 남은 `cfp_verify_*`·`acf_verify_*` DB 없음 | 없음 |
| 2026-10-27 | 코드 + 실제 DB(일회용 Docker) | H 갈래 연결 뒤 `CFP_PG_ADMIN_URL` 설정, `scripts/check.sh`. 핵심은 `tests/test_offline_pipeline.py`: 여성·남성 합성 브리프를 `run_until(until="sx")`로 돌리고 모든 관문 결정을 워크숍 웹 API로 보낸다 | 가짜 공급자(이미지·영상·LLM·학습), 합성 순위 목록(성별만 바꿈), 일회용 컨테이너 `cfp-verify-pg-1` | 462 passed, 건너뜀 0. 두 캐릭터 모두 8회 실행으로 sx까지, G1·G3·G4a·G4b·G4·G5·G5b·G6·G7a·G7·G8·G9 전부 웹 결정으로 승인, G7a~G9 화면은 실제 산출물을 보여 줌. 패키지에 영상 19편(소개 1·동작 18, 모두 가짜 표시). 적재 확인 PASSED: chat-svc 캐릭터 1·챕터 3·persona r1·릴리스 1, api-svc 캐릭터 1·단계 3·클립 18·미디어 8, 일회용 DB 2개 삭제. 남은 `cfp_verify_*` DB 0 | 없음 |
| 2026-10-28 | 코드 + 실제 DB(일회용 Docker) | D-0048 구현 뒤 `CFP_PG_ADMIN_URL` 설정, `scripts/check.sh` | 가짜 공급자, 전체 흐름 테스트 4개(SFT 경로 여성·남성, 학습 없이 진행, 학습을 기다린다) | 464 passed. 학습 없이 진행: 학습은 계획만(dry run), G8 "학습 없이 진행"에서 긴 프롬프트 선택 → 패키지(`evalReport` 없음, 채택 LONG_BASE) → 적재 확인 PASSED(chat-svc 캐릭터 1·챕터 3, api-svc 캐릭터 1·단계 3·클립 18·미디어 8). 학습을 기다린다: s10 반려, 다시 돌려도 새 질문을 열지 않음 | 없음 |
| 2026-10-28 | 브라우저(오프라인) | `scripts/build_late_gates_demo.py`로 G7a·G7·G8(평가)·G8(학습 없이)·G9에서 멈춘 데모 캐릭터 다섯을 만들고 `cfp web`을 띄워 ChatGPT 앱 내 브라우저로 화면을 눌러 결정 | `work/late-gates-demo-1`·`-2`(저장소 밖 Git 제외 폴더), 가짜 공급자 | G7a 클러스터 5개 판정 → 승인, G7 승인, G8 블라인드 20쌍 → 승인, G8 학습 없이 진행 → 긴 프롬프트 선택과 학습을 기다린다 둘 다, G9 승인. 이어 `cfp run --verify-export`로 두 캐릭터 패키지·적재 PASSED. 찾아 고친 것: G7a 두 번째 전송이 막히던 버그(전송 후 busy가 풀리지 않음), 성공 메시지가 바로 지워짐, G8 지표 표가 블라인드 전에 조건 이름을 보여 줌(20쌍을 다 고르면 열리게), 학습 없이 진행 화면 제목, G9 SFT 칸 표기, 좁은 폭 상단 메뉴 줄바꿈·상태 표시 겹침, 결정 끝난 관문의 "결정 가능" 표기 | 화면 캡처는 대화에만 |
| 2026-10-28 | 코드 + 실제 DB(일회용 Docker) | D-0049 A~D 갈래를 합친 뒤 `CFP_PG_ADMIN_URL` 설정, `scripts/check.sh`. 핵심은 `tests/test_agentic_flow.py`(워크숍 API로 작업 시작 1회 + 관문 결정만, G4a·G4 수정 요청 1회씩, 가짜 검토자), `tests/test_run_waves.py`(순차·물결 최종 상태 같음) | 가짜 공급자, 합성 브리프 여성·남성, 일회용 컨테이너 `cfp-verify-pg-1` | 515 passed. 두 브리프 모두 sx 적재 확인 PASSED, 모든 관문 APPROVED, 사람이 시작한 작업 1회. 동시 실행 s3‖s5·s4a‖s7·s4b‖s9s·s4‖s9·s6‖s10t | 없음(tmp) |
| 2026-10-28 | 브라우저(오프라인) | `scripts/agentic_demo.py work/agentic-demo-1`로 가짜 공급자 워크숍을 띄워 ChatGPT 앱 내 브라우저로 결정 | 여성 합성 브리프, 소개 영상 공급자만 유료 표시 | G1 결정 → s2·s3 자동 실행·G3 대기·s5 실행 확인 대기, G3 추천·근거 표시, G4a ch2 수정 요청 → bg2·수정 1/3·브리프 targets 원문·ch1·ch3 배경 해시 같음, "실행" → s5 → G5 대기. 화면 문제 2개(G4a·G4b 챕터 메모, G1 뒤쪽 단계 수) 고침 | `work/agentic-demo-1` |
| 2026-10-29 | 실제 텍스트 중계 | `scripts/persona_quality_20261028.py bootstrap/s3/s7/s8`와 `scripts/persona_dialogue_20261028.py dialogue/judge`: 단계마다 dry run 저장 후 execute. G3 agent 선택, judge의 잘린 호감 장면만 low 추론으로 재시도 | 합성 S1·fake 이미지·S2 picked, 씨앗 26세 여성 책방 직원, pr1/v3→tr1→pv1, 고정 G6 system | 실제 172호출(생성4·대화134·판정34), G6 대기. 긴·짧은 각각 16장면67응답, 대화 재추출0·134/134 finish_reason stop·670개 결함 분류. 직접 읽은 판단은 HTML에 있다. 실제 청구액 미확인, 가정 단가 민감도 $1.89–18.93 | `runs/experiments/20261028-persona-quality/`, `docs/reports/2026-10-28-persona-quality.html` |
| 2026-10-29 | 원문·해시·계약 | 고정 system+누적 실제 이력+현재 user를 요청 JSON과 134턴 전부 대조하고 요청·응답 SHA-256 재계산, `cfp --root runs/experiments/20261028-persona-quality verify cf-20261029-persona-quality` | 같은 동결 출력, 응답 재생성 없음 | 134 대화 계약·해시 일치, 중복 ref0, 모든 revision manifest 일치. 판정 32장면·134턴·670분류, 원문 미일치 인용3개 표시 | `dialogue-verification.json`, `judgment-verification.json`, `manifest-verify.log`(실험 루트) |
| 2026-10-29 | 오프라인 | `scripts/check.sh`, 실험 스크립트 3개 `ruff check`·`ruff format --check`·`py_compile` | src·tests 변경 없음, 실제 대화 fixture 추가 없음 | 514 passed, 1 skipped, 1 warning. DB 적재 환경 변수가 없어 이번에는 DB 검사를 건너뛰었다. 스크립트 lint·format·compile 통과 | `runs/experiments/20261028-persona-quality/offline-check.log` |
| 2026-10-29 | 브라우저·HTML | 로컬 보고서 서버 + 앱 내 브라우저에서 첫 화면·실제 대화 이동 확인, DOM의 turn 개수와 근거 anchor 점검 | 생성 보고서 약2MB, 원문 접기 포함 | 134턴 표시, 깨진 anchor0, 1280px 화면 가로 넘침0. 실제 대화·판정·API 원문을 함께 볼 수 있다. 모바일 화면은 별도로 검증하지 않았다 | `docs/reports/2026-10-28-persona-quality.html` |
| 2026-10-29 | 실제 자료 재집계 | 한소민r3 train·index·tokenized와 실제 학습 train의 SHA 대조 | somin-final-sft-2026-10-22-r3·somin-r3-training-2026-10-22-r1 | 644대화·3,977답변·109,157학습 토큰·중앙값33자·15턴 이상37개, 두train SHA 일치. 다른 저장소 수정 없음 | `runs/experiments/20261029-somin-transfer/somin-evidence.json` |
| 2026-10-29 | 오프라인 회귀 | 정본3검사 실패 후 수정, 리뷰 경계3검사 실패 후 수정, scripts/check.sh | 합성 v1/v2, source 보존·초과 예산·재개·구형 말투 | 최종520 passed, 1 skipped, 1 warning. DB 적재 미실행. 경계19검사도 통과 | `runs/experiments/20261029-somin-transfer/*tests*.log`, `offline-check-reviewed.log` |
| 2026-10-29 | 실제 텍스트 | 단계별 dry run→scripts/persona_somin_transfer_20261029.py execute, tr2·pv2 | 같은pr1/v3·Gemini3.8Flash, 새누적67·고정이력40 | 실제127호출(생성3·대화107·판정17). 대화 재추출0·107 stop. 판정335분류·인용 불일치1표시, 갈등 첫 원문 구조괄호1개 복구. G6대기 | `runs/experiments/20261029-somin-transfer/`, `docs/reports/2026-10-29-somin-transfer.html` |
| 2026-10-29 | 해시·대조 계약 | 127요청·응답SHA, 실제누적67·고정이력40의 messages와 모델설정 비교, cfp verify | 같은동결출력 | 254원문해시·107계약 일치, 이전796파일 해시 유지, 모든revision manifest 일치. 실제 청구액 미확인·가정 민감도$0.48–4.80 | 실험루트 `verification.json`·`manifest-verify.log` |
| 2026-10-29 | 보고서 브라우저 확인 | localhost:8878 분석·전후 HTML 첫 화면과 DOM 근거 anchor 확인 | 67새누적·40고정이력 원문 포함 | 표시67+40응답·깨진근거링크0·1280px 가로넘침0. 모바일 별도 검증 없음 | `docs/reports/2026-10-29-somin-transfer.html` |
| 2026-10-29 | 문서·독립 검토 | 새 계획/검토/인계의 상대 링크 검사, 호출·토큰 산식 Python 단언, `git diff --check` | 기본 품질 공정 계획, Raman/Turing 1차11건·재검토2건 | 링크·산식 검사 통과, 공백 오류 없음. 코드 테스트·실제 대화 실험·학습은 미실행이며 품질 합격이 아니다 | [계획](../product/2026-10-29-persona-quality-floor-plan.md) · [검토](../reports/2026-10-29-persona-quality-floor-plan-review.md) |
| 2026-10-29 | 코드·독립 검토 | `bash scripts/check.sh`, 새 합성 회귀 검사, Zeno·Bohr·Parfit 독립 검토 반영 | 새 계약·S7a/b·S8 bundle·G6/S9/S11·품질 CLI | lint/format 통과, 654 passed·1 skipped, DB 미실행. 초기 독립 지적12건 반영 후 회귀 검사 통과. 실제 품질 합격이 아니다 | [구현 보고서](../reports/2026-10-29-persona-quality-floor-implementation.md), `work/persona-quality-floor/` |
| 2026-10-29 | 실제 공급자·개발 관찰 | 단계 dry run→4캐릭터 형성·복구, 500/2400예산 각24응답 | GPT 생성28요청(HTTP400 4포함), Gemini 대화48요청. fake 외모, 실제 영상/이미지/판정/학습 없음 | 첫 형성0/4 실패 보존, 새 tr2 설계/예시 각1회로4/4 완성, G6 대기. 500은8 length/16 stop, 2400은24 stop. 공식 요금 미확인, 정식 품질 NOT_RUN | `runs/experiments/20261029-quality-floor-development/summary.json`, [전체 원문](http://127.0.0.1:8879/report.html) |
| 2026-10-29 | 원문 감사·오프라인 검사 반례 | `uv run python work/persona-choice-analysis/audit.py`, 원본 복사본에 같은 행동3재서술 후 `check_variants` 호출 | 실제4씨앗·12후보·G3 선택·S7/S8·새24응답, 합성 검사 입력 | 전원 v1, 지각 행동3번호군 확인, 관련13/13규칙 전달, 같은 행동3재서술도 검사0문제. 이는 코드 의미 검사 한계이며 생성 원인의 통제 실험은 아니다. 새 모델 호출·제품 코드 수정·전체 테스트 실행 없음 | `runs/experiments/20261029-quality-floor-development/choice-cause-analysis/trace.json`, [분석](../reports/2026-10-29-persona-choice-cause-analysis.md) |
| 2026-10-29 | 계획·독립 검토·문서(오프라인) | 특질·선택·실제 말투 개선 계획 작성, 서브에이전트 2명 최초 검토·수정본 재확인, 8문서 로컬 링크 검사와 git diff --check | 새 계획·검토·인계와 관련 상태 문서 | 113개 로컬 링크 누락 0개, 구현 작업 7개, 검토 지적 12건 반영, 최신 인계 10행, 결정 ID 중복 0개, diff 공백 오류 0개. 제품 코드·실제 모델 대조·학습·커밋은 실행하지 않았고 전체 테스트를 반복하지 않았다. | work/persona-choice-voice-plan/document-check.json, [개선 계획](../product/2026-10-29-persona-choice-voice-plan.md), [검토 보고서](../reports/2026-10-29-persona-choice-voice-plan-review.md) |
| 2026-10-29 | 선택·말투 v2 오프라인 구현·독립 검토 | RED/GREEN 경계 검사→`bash scripts/check.sh`, `node --check`, Planck 1차5건·후속3건 수정/한정 재확인 | 합성 요구/기획/대화·승인 fixture, fake 공급자, 새/기존 프로필 | 최종 lint·format 통과, 729 passed·1 skipped(DB 환경 없음)·기존 warning1건, 79.04초. 실제 v2 모델·대화·학습은 미실행, 품질 NOT_RUN | [구현](../reports/2026-10-29-persona-choice-voice-implementation.md) · [검토](../reports/2026-10-29-persona-choice-voice-code-review.md), `work/persona-choice-voice-implementation/final-check.log` |
| 2026-10-29 | 최종 wheel·런타임 자산 | `uv build --wheel --out-dir work/persona-choice-voice-implementation/dist-final` 후 추출본을 cwd=/tmp에서 import/기본 규칙·새 프로필 읽기 | 실제 빌드 파일, 프로젝트 가상환경 의존성, PYTHONPATH는 추출본만 | prompts36·런타임 파일90 누락0, 새 생산자/진단 모듈·프로필·기본 규칙 실행 통과. package-data 키와 resources Markdown 누락 수정. 깨끗한 신규 의존성 설치 전체를 시험한 것은 아니다 | `work/persona-choice-voice-implementation/wheel-check.json`, `final-build.log`, `dist-final/` |
| 2026-10-29 | 문서·원본 보존 | 변경 문서의 코드 블록 제외 상대 링크 검사, 결정 ID/최신 인계 검사, 기준선 파일/사본 SHA 점검, `git diff --check` | 기준선 411파일, 변경 문서14개 | 실제 로컬 링크142개 누락0, 결정 ID 중복0, 최신 인계10행, 원래 파일 삭제0·기준선 사본 변경0, diff 공백 오류0 | `work/persona-choice-voice-implementation/document-check.json`, `changed-files.json`, `change.diff` |
| 2026-10-29 | 자료 감사·실제 모델 관찰 | persona_choice_voice_live_20261029.py 단계 dry run→execute, 기존자료4팩 감사, 독립검토/원문 읽기 | GPT6.1Sol 생성·Sonnet5 검토·Flash3.8 소비, 동일4씨앗·fake 외모, 학습/영상/이미지 없음 | HTTP183요청(소비132·단계40·추가판정8·연결3), 원래108/192+최종조립24응답, 소비잘림0. 최초형성0/4·앞선실패1보존. 기본 품질 개선 미확인·정식 NOT_RUN | [실제 보고서](../reports/2026-10-29-persona-choice-voice-live-validation.md), runs/experiments/20261029-choice-voice-live-r1/summary.json |
| 2026-10-29 | 실제 원문·예산·회귀 | 183요청/응답 SHA·132누적 messages/첫응답·source split 대조, bash scripts/check.sh, Boole 재개/usage2지적 수정·7회귀/5경로 재확인 | 입력1,360,995·추론 포함출력212,403, 300요청/250만토큰/환산75달러 상한, tokenizer미연결 | 183 HTTP원문·132이력·고유ref 일치, 이전695파일 보존. 실제소비입력최대4834·출력최대126·132 stop. 환산52.70826달러/청구미확인. 742 passed·1 skipped·기존 warning1, lint/format 통과 | runs/experiments/20261029-choice-voice-live-r1/live-verification.json, work/persona-choice-voice-live/final-check.log |


## 2026-10-29 추가 특질 추천

- `./scripts/check.sh`: baseline742 passed/1 skipped에서 최종773 passed/1 skipped,기존 Starlette 경고1. 최종79.88초. `work/trait-recommendations-20261029/final-check.log`.
- 새 기능31개 targeted, 원문144/144 일치, 실제 브라우저 정상 및 카탈로그 GET503에서 빈 선택 저장, 외부 원본 없이 추출 wheel 추천을 확인했다. [구현 보고서](../reports/2026-10-29-trait-recommendation-implementation.md).
- 독립 검토 R1~R4는 재현 RED→GREEN 뒤 범위 한정 재확인 PASS다. 근거는 작업 폴더의 review.md / review-followup.md / review-final.md 및 r3-ui-smoke.cjs에 남겼다.
- 실제 캐릭터 생성/대화 모델 호출은0이며 이번 기능을 페르소나 품질 합격으로 승격하지 않는다. 기존 실험은 보존했다.


## 2026-10-29 윤서진 생성·Gemini 실제 대화

- 실행: `.venv/bin/python -m scripts.trait_persona_gemini_20261029 prepare`, 이어 `probe / plan / select --variant v3 / form / collect / assess`에 `--execute`, `export / summary`는 로컬 처리다. 기본 프로필sd1·추가 행동2개→S3 pr1/v3→S7 tr1→S8 pv1, G6 대기다. S1/S2는 합성이며 학습·이미지·영상은 실행하지 않았다.
- 실제 모델: GPT5회·Gemini43회(연결1+대화42)·Sonnet9회(공정3+독립평가6)=HTTP57요청/응답이다. 소비42첫응답은 stop·전체누적이력, 공정 의미보존 판정#1 length→형식 재시도#2 stop를 보존했다. 설계·렌더/소비를 다시 뽑지 않았다.
- 감사: 57요청/응답 SHA쌍·42이력/최종system SHA·실제 모델명·추가 특질2개 전달·제품snapshot263개 불변·예산58예약 모두정산을 대조했다. 1예약은 no-HTTP 추론 회계 보정이다. 입력345758·별도 Gemini추론 포함출력77659=보수적423417토큰, 가정환산 USD16.23424/청구미확인이다.
- 결과: 소유권/변경 수용 양호, 감정/관계의 상담체와 입력한 무뚝뚝함·장난기 손실이 남는다. 대조군·두 번째 인물·사람 투표가 없어 개선/기본 품질 보장은 미입증이다. 형성 의미검사68턴PASS·Sonnet선택 good5/mixed1/자연스러움 good6을 품질 합격으로 승격하지 않는다.
- 근거: [실제 보고서](../reports/2026-10-29-trait-persona-gemini-live.md), `runs/experiments/20261029-trait-persona-gemini-r1/{summary,final-audit,final-observations}.json`, `dialogues.txt`, `final-system-prompt.txt`. 작업로그는 `work/trait-persona-gemini-20261029/`다.
- 로컬 마무리: 실험 스크립트 `ruff check --ignore E501`·`ruff format --check`·`py_compile` 통과, 변경8문서의 로컬 링크135개 누락0·결정ID 중복0·최신인계10행을 확인했다. `git diff --check` 공백 오류0이다. 제품코드는 수정하지 않아 전체773개 검사는 반복하지 않았다. 문서검사 기록은 `work/trait-persona-gemini-20261029/document-check.json`이다.


## 2026-10-29 윤서진 프롬프트 오프라인 감사

- 실제 sd1/pr1/tr1/pv1과 공급자에 보낸 최종 프롬프트를 대조했다. `compose_choice_voice_text`에 같은 승인 입력을 넣어6683자/SHA256 `09cd75d0…`를 정확히 재현했다. 실행당시 제품263파일 해시가 현재와 일치한다. 추가 모델 호출0·제품 수정0·기존 실험 원문 수정0이다.
- coreTraits와 bp.voiceProfile이 최종에 포함되지 않는 코드 경로를 확인했다. 무뚝뚝함·자존심 직접 지시 누락을 원문과 함께 확인했으며 문자열 불포함만을 모든 성향의 의미 누락으로 일반화하지 않았다.
- 4개 예시 커버리지 조건의 유효47조합 중6조합에 d06 장난 예시를 포함할 수 있었다. 현재 ID순 선택은 d01/d07/d08/d12다. 생성34개 캐릭터 발화→선정13개, 중간 작성기에 제공한 말투20조각의 최종 직접 포함0개를 확인했다. 말투 직접 포함 수를 재현 품질 점수로 쓰지 않는다.
- [분석 보고서](../reports/2026-10-29-trait-persona-prompt-audit.md), `runs/experiments/20261029-trait-persona-gemini-r1/prompt-audit/trace.json`, `work/trait-persona-prompt-audit-20261029/offline-verification.json`에 근거를 보존했다. 실제 품질 인과 대조는 NOT_RUN이며 전체 제품 테스트를 반복하지 않았다.


## 2026-10-29 영상 파이프라인 감사

- `uv run pytest -q tests/test_reference.py tests/test_hero.py tests/test_frames.py tests/test_image_qa.py tests/test_video.py tests/test_actions.py`:142 passed in31.45s.
- `uv run pytest -q tests/test_scene_flow.py tests/test_codex_image.py`:48 passed in3.59s.
- 입력은 기존 합성 테스트이며 외부 생성 호출0이다. [결과 보고서](../reports/2026-10-29-video-pipeline-audit.md)를 따른다. 기존 서비스의 실제 완성 이미지3장은 직접 열어 확인했으나 영상·정량 동일인 검증은 하지 않았다.


## 2026-10-29 현행 서비스 기반 actor runtime 구현·실제 비교

- 사용자 정정: 특질은 정규화된 성격 문장, runtime은 서비스v6의8섹션, 예시/전체챕터/내부조건표/제작자표기 제외다(D-0070). 로컬 활성 pointer→한소민quest-v48/persona-r11과 frame-v40/actor 조립을 읽었다. 운영DB 발행/서비스배포는 확인하지 않았다.
- TDD/검토: actor RED6건, styleEvidence KeyError RED1건, 저작lexicon RED1건, 독립검토 R1~R3의4개 재현 RED→GREEN이다. 마지막 targeted37 passed, `bash scripts/check.sh` 최종785 passed/1 skipped/기존 Starlette warning1·lint/format 통과(84.52초). `work/trait-persona-prompt-fix-20261029/{actor-red,style-red,lexicon-red,review-red,review-green,final-check}.log`. 사후 독립 재검토를 받은 것은 아니다.
- 패키지: 최종wheel에 actor계약/compiler/rules가 들어 있고 추출본을 별도 cwd에서 불러 resource를 읽었다. build-final.log/wheel-check.json/dist-final이 근거다.
- 실제: `.venv/bin/python -m scripts.persona_service_runtime_live_20261029 prepare`, probe/form/collect/assess --execute, export를 실행했다. pr1고정→tr2/pv2 G6대기. 실제HTTP107요청=Gemini97(연결1+대화96)+GPT3+Sonnet7, 보존판정첫 length1→형식재시도1, 소비96 stop/재추첨0이다. source S1/S2는 합성이며 이미지/영상/학습/commit/push는 없다.
- 대조: A기존6683자/B동일원천 새2874자/C새형성3045자, 각32응답이다. 고정이력36+독립누적60, 새누적최대6턴, 사람투표0이다. 선택/자연스러움의 부분 개선은 관측했으나 강도·과한 사과/추정은 남는다. 자동major2건은 경향을 필수절차로 본 오판으로 배제했다. NOT_RUN / NOT_QUALIFIED다.
- 감사: 107요청/응답 해시·모델명·107예산예약 정산·96전체이력/프롬프트 검증, 이전실험516파일/실행중제품329파일 불변을 확인했다. 입력409570·별도Gemini추론 포함출력87768=보수적497338토큰, 가정환산USD18.72356/청구미확인, 마지막응답23.52분이다.
- 근거: [구현·실제 보고서](../reports/2026-10-29-service-persona-runtime.md), `runs/experiments/20261029-service-persona-runtime-r1/{summary,consumer-audit,final-observations}.json`, final-system-prompt.txt, dialogues.txt. 이전실험/인계는 보존한다.
- 마무리 문서 검증: 변경13문서의 로컬 링크174개 누락0, 최신인계10행, 결정/문제ID 중복0, 기준점 파일 삭제0, `git diff --check` 공백 오류0이다. 실험 스크립트 lint/format/py_compile도 통과했다. `work/trait-persona-prompt-fix-20261029/final-document-check.json`을 따른다.


## 2026-10-30 사과 반응 문맥 재검토

- A/B/C fixed ordinary-04의 동일 실제 이력과 C의 fresh ordinary2~4, actor-profile-C를 직접 비교했다. C32응답의 명시적 미안1회·fresh20응답0회를 다시 확인했다. 짧은 수습 표현은 허용 가능한 성향 변주로 판정하고 사과 자체의 결함 분류를 철회했다. 전체95자 답변의 강도는 약한 문체 개선 여지로 구분한다.
- 새 자료는 `runs/experiments/20261029-service-persona-runtime-r1/followups/20261030-apology-review.json`이며 원래 응답·관찰 파일은 보존했다. 추가 모델 호출·제품 수정·테스트 실행은 없다. 기존 보고서/현재 상태에 판정 정정을 표시했다.


## 2026-10-30 새 츤데레 캐릭터 생성과 실제 Gemini 비교

- 사용자 요청: 새 약한 츤데레를 파이프라인으로 생성·테스트하며, 제안한 의미는 Gemini 피드백을 먼저 받는다.
- 개념 피드백: `.venv/bin/python work/tsundere-20261030/feedback.py --execute` 실제1요청·stop. 질문·첫 피드백·해시·사용량을 `runs/experiments/20261030-tsundere-feedback-r1/`에 보존했다.
- 기존 S3/S7/S8: `run.py prepare/plan/select --variant v2/form --execute`를 단계별로 실행했다. 원래 S3 pr1은 명사형 성격 검사 실패했고 source 역할에 기존 문장형 요구를 명시한 pr2에서 통과했다. 새 기획 한지완을 소비 호출 전에 선택했다.
- S7 원래 실행은 보존 판정 length12000과 보조 코드 추론 합산 초과로 실패했다. 생성물은 재추출하지 않았다. `recovery.py`의 별도 복제 실행에서 원래 malformed 판정을 HTTP0회로 형식 재현하고, `cv-preservation#2`만 실제 재요청(24000상한)했다. 첫 복구의 JSON 키 순서 검증 실패도 보존했고, 정규화 입력 일치 확인 후 두 번째 복구에서 보존·S8 검증을 통과했다. 원래 실패 공장137파일은 변경0이다.
- 소비: `.venv/bin/python work/tsundere-20261030/run.py collect --execute`. 신규20+윤서진20=40첫응답, 모든 응답 stop·잘림0이며 실제 이력을 누적했다.
- 감사: `.venv/bin/python work/tsundere-20261030/audit.py` 성공. 실제50 HTTP(GPT7/Sonnet3/Gemini40)·50정산 예약·40이력/해시 확인, 과거 윤서진937파일·최종 소스/보조 코드333파일 보존. 전체51요청은 별도 개념1회를 포함한다.
- 비용: 본 실행 보수 가정 USD14.83176, 개념 포함 USD15.02822. 실제 청구액 미확인. 일부 추론 중복 합산 가능성을 표시했다. 전체 호출65·가정 USD25 상한은 올리지 않았다.
- 오프라인: `.venv/bin/pytest -q tests/test_choice_design_flow.py tests/test_creator_trait_flow.py tests/test_prompt_identity_preservation.py tests/test_choice_voice_flow.py` →35 passed in8.95s. 새 전역 검사는 실행하지 않았다.
- 결과: [보고서](../reports/2026-10-30-tsundere-persona-live.md), `runs/experiments/20261030-tsundere-persona-r1/audit.json`, `summary.json`, `assistant-observations.json`. 호감 반응 차이는 관측했으나 지각·선물 선택은 유사했다. G6대기·사람 블라인드0·정식 NOT_RUN / NOT_QUALIFIED다. K-0057로 초회 신뢰성 한계를 남겼다.
- 마감 검증: 변경 관련7문서의 로컬 링크133개 누락0, 최신 인계10개 유지, git diff --check 통과. 실제 실행 감사 재검사도 동일50요청/40응답으로 통과했다.

## 2026-10-30 텍스트 모델 덱·호출 경로 셋업

- 범위: D-0072·D-0073. 원본 model-deck.md/JSON snapshot, common.text_deck 해석기, Context 역할별 공급자, CLI 선택, 표준 S3·S7·S8 및 S9 연결이다. 합성 자료와 HTTP 경계 stub만 사용했으며 실제 모델/수집/학습 호출은 0회다.
- 실패 재현: `uv run --locked pytest -q tests/test_text_model_deck.py` 최초 6실패로 누락된 task_model/CLI/설정 해석을 확인했다. S8 무호출 조립, S3 4역할 배정, dry-run 거절의 실패도 구현 전에 각각 확인했다.
- 독립 검토: 원본 덱과 변경 경로만 읽은 검토에서 P2 5건을 받았다. `tests/test_text_deck_review_regressions.py`가 모두 실패함을 확인한 뒤 S8 예외 조건·시스템 규칙 보존/G6 수정 차단/실제 생성 배정과 현재 선택 구분, S3 axisNote 보존을 수정했다. HTTP/유료 호출은 없다.
- 수정 후 집중 검사: `uv run --locked pytest -q tests/test_text_deck_review_regressions.py tests/test_text_model_deck.py tests/test_s9_model_deck.py` → 40 passed in 4.32s다. S9의 추가 집중 검사 42개 통과도 하위 작업에서 확인했으며 실제 모델 품질 근거로 사용하지 않는다.
- CLI 실제 설정 확인: `uv run --locked cfp models show` → 아홉 task가 opencodex/basic_test로 해석된다. 확인 결과는 `work/text-deck-effective-20261030.json`에 저장했다. 미설정 test 선택은 오류/exit1로 거절하며 현재 선택을 보존했다. `cfp persona traits cf-example`은 상한4회·예상 비용 미확인, `cfp persona prompts cf-example`은 조립 호출0회다. 실제 실행 인자는 사용하지 않았다.
- 중간 전체 검사: `uv run --locked pytest -q` → 820 passed, 1 skipped, 기존 Starlette/httpx deprecation warning1개, 84.06s다. 이후 독립 검토의 회귀 검사5개를 추가하고 최종 전체 검사를 별도로 기록한다.
- 문서 검증: 새 안내·계획·인계의 로컬 링크5개 누락0을 확인했다. PRD v1.10 FR-58~60→명세 v1.10 §20→LLD v1.11 §18을 함께 갱신했다. 원본 모델 비교 저장소·기존 생성물은 읽기만 하고 변경하지 않았다.

- 최종 전체 검사: `uv run --locked pytest -q` → **825 passed, 1 skipped, 1 warning in 83.25s**다. 경고는 기존 FastAPI/Starlette의 httpx deprecation이다. 독립 검토 회귀5개를 포함한다. `uv run --locked ruff check src tests`, `uv run --locked ruff format --check src tests`(352개 파일), `git diff --check`도 모두 통과했다. 최종 실행에서 실제 외부 모델 호출·학습·commit/push는 하지 않았다.

## 2026-10-30 글래스 시안과 텍스트 공정 연결

- 범위: D-0074·D-0075. 대상 채팅의 실제 시안 폴더와 design.md를 읽고 plans/2026-10-30-text-pipeline-connection.md에 분담/API 계약을 먼저 작성했다. 이번 공정의 캐릭터 생성·학습·관문 승인은 실행하지 않았다. 개발용 DeepSeek 코딩 세션2개는 별도다.
- 병렬 구현: 기본 spawn 목록에 DeepSeek가 없어 로컬 Codex CLI에서 `-m opencode-go/deepseek-v4.1-flash`, high를 명시한 별도 세션 두 개로 API/UI를 병렬 작성했다. API8개 집중 검사와 기존 API를 합친19개, UI 순수 함수14개를 하위 작업에서 확인했다. 기본 모델로 대체하지 않았다. 작업자 로그·결과는 시안 폴더 plans/integration-work에 보존했다.
- 통합 실패/수정: /studio 미연결과 mount 컨트롤러의 호출 방식을 실제 Chrome에서 확인하고 연결했다. 미디어 호출이 텍스트 기록에 섞이는 것, 기존 워크숍 링크, 서버 본문 축약 표시를 각각 재현해 수정했다. 실제 모델 설정을 복제하지 않고 큐만 --jobs-dir로 분리하도록 새 검사에서 실패를 확인한 뒤 수정했다.
- 최종 전체 검사: `uv run --locked pytest -q` → **838 passed, 1 skipped, 1 warning in 59.91s**다. 기존 Starlette/httpx deprecation warning이다. `ruff check src tests`, `ruff format --check src tests`(355개 파일), `git diff --check`도 통과했다. 관련 API/서빙 집중 검사는13개 통과다.
- UI: 시안의 `node --test tests/text-pipeline.test.cjs` →15개 통과다. `node --check shared/text-pipeline.js`, `shared/ops.js`도 통과했다. 루트 실제 HTTP API를 붙인 `node tests/text-pipeline.browser.cjs`에서 1512×982·1280×982의 가로 넘침0, 페이지 오류0, 미설정 test 차단, Tab 포커스 유지, H 단축키 격리, Esc·포커스 복귀와 직접 패널 URL을 확인했다. screenshots는 previews/text-pipeline-1512.png 및 -1280.png다.
- 브라우저 실패 상태: `node tests/text-pipeline.states.browser.cjs`에서 인터셉트한 합성 API로 프로필 성공/실패·기존 선택 보존, 선택 Argon과 과거 Flash 출처 분리, 축약 표시, 본문 HTML 이스케이프, 오프라인에서 허구 역할을 채우지 않음을 확인했다. 이 검사는 합성 자료이며 실제 생성/품질 결과가 아니다. fixture POST2회는 브라우저 안에서만 응답해 실제 설정을 바꾸지 않았다.
- 기존 시연: `/tmp/cfshot/runs1.js 1512 982` → errs0, 벨트 경로45표본/잘못된 경로0, G9 출시까지 통과했다. 기존 흐름을 실제 백엔드 실행이라고 보고하지 않는다.
- 실제 서버: 127.0.0.1:8776에서 실제 factory.toml 직접 읽기(configPath null), 큐 분리, opencodex/basic_test·역할9개·등록 캐릭터0건을 확인했다. 기존 실험/옛 저장소 자료를 복사하지 않았다. 시안 경로와 API가 같은 origin에서 동작한다. 새 문서 로컬 링크5개 누락0이다.

- 추가 독립 검토: 같은 DeepSeek v4.1 Flash에 통합 코드 읽기 검토를 요청했지만 604초까지 완료 응답이 없어 10분 상한으로 중단했다. 검토 승인/발견0건으로 집계하지 않는다. 병렬 구현 작업자2개는 정상 완료됐으며 최종 검증은 위 테스트·실제 브라우저·메인 코드 검토에 근거한다. 시안 plans/integration-work/review-status.json에 미완료 상태를 기록했다.

## 2026-10-30 실제 공장 화면·에이전틱 실행 연결(D-0076)

- 입력은 합성 브리프다. 실제 FastAPI/JobManager/run_until을 사용하고 공급자만 fake다. 실제 모델·이미지·영상·학습 호출은 없다. 실제 루트 캐릭터0건이다.
- `uv run --locked pytest -q` → **868 passed, 1 skipped, 기존 경고1**,57.63초. 전체 저장소 검사이며 신규 Python30개다. 로그 `work/runtime-connection-20261030/pytest-complete.log`. Ruff check/format(358파일), git diff --check 통과.
- 시안 `node --test tests/runtime*.test.cjs tests/text-pipeline.test.cjs` →35 passed. runtime.js/ops.js/gate.js 구문 검사 통과.
- 임시8786서버에서 `node tests/runtime.browser.cjs` → 실제 등록→큐 시작→G3 iframe 수정→pr2→후보 선택→G6/pv1, pr1 보존,17개 작업대/8갈래,1280/1512, iframe Escape·배경 포커스 격리, 새로고침, 오프라인, 작성 중 입력 보존/목록 갱신, 최근20개 밖 job-only 주소 복원 통과. 페이지 오류0. 결과는 시안 plans/runtime-work/browser-results.json, screenshots는 previews/runtime-floor-1280.png/-1512.png다. 임시 데이터는 /tmp/cf-runtime-browser-20261030-r3/에만 있다.
- 임시8787 읽기 서버에서 `STUDIO_URL=http://127.0.0.1:8787 node tests/text-pipeline.browser.cjs` 및 states.browser.cjs 통과. 기존 프로필/출처/본문 이스케이프·오프라인·포커스·직접 URL 회귀다. POST2회는 인터셉트로 처리되어 실제 설정은 미변경이다.
- 같은 DeepSeek v4.1 Flash 독립 읽기 검토2회 완료. 불완전 생성·상태 스키마, jobId·작업 URL·가독성·object 출력·시안 탐색·입력 중 목록 정지를 보완했다. 관문 일부 stage 매핑 누락 지적은 현행12개 모두 매핑되어 재현되지 않았다. 원문/처리 기록은 시안 plans/runtime-work/에 있다.
- 실제 opencodex/basic_test와 auto_resume=true/max_parallel=3/resume_until=sx를 확인했다. 종료 후 `lsof -nP -iTCP:8776 -iTCP:8786 -iTCP:8787 -sTCP:LISTEN` 출력0이며 서버는 모두 내려 둔다. commit/push 없음.

## 2026-11-02 QLoRA 실제 연결·창작 인물 정책 (D-0077, D-0078)

- `uv run --locked pytest -q -p no:cacheprovider`: 1차 971 passed, 독립 검토 수정 뒤 최종 1048 passed, 1 skipped(기존 Starlette 경고 1개). `ruff check src tests`, `ruff format --check src tests` 통과.
- 새 시험: tests/test_s10_drive.py(계획→drive→모의 원격 학습·선별→회수→선택→binding·중단 시 CANCELLED), test_s10_select.py, test_vast_lease.py, test_gemma_screening.py, test_s10_gpu_eval.py, test_s11_serving.py, test_s9_policy.py, test_s10_scorecard.py, test_s10_eval.py의 Gemma 단독 두 조건 시험, 검토 반영 test_remote_scripts.py·test_s10_guard.py·test_s10_collect_select.py. 모두 가짜 호스트·가짜 vastai runner·가짜 터널·가짜 모델이다.
- 외부 확인: vastai CLI로 계정 잔액($8.86)·인스턴스 0개·SSH 키 목록만 읽었다(생성·삭제 없음). 실제 학습·선별·평가·판정 호출은 0회다.


## 2026-11-04 공식 API 직접 연결·비용 기록 (D-0079)

- 문서: PRD v1.14 §20(FR-65~69), 명세 v1.14 §24, LLD v1.15 §22. 구현은 하위 작업자 네 명이 파일 소유를 나눠 병렬로 했다(A 호출 경로 Curie, B 요청 형식 Lagrange, C 단가표 Hooke, D 기록·예산·보고 Heisenberg). 통합은 메인이 했다.
- 독립 검토(Gauss): P0 1건(OpenAI 캐시 쓰기 1.25배 비용 누락), P1 3건(추론 강도 미지정 OpenAI 요청의 temperature, 프로필 변경 뒤 예산 봉투 단가, 키 모양 환경변수 이름의 오류 문구 노출), P2 6건. P0·P1과 P2의 4xx 예약 정산·codex exec 행 제외·ImportError 무시 제거·`.env` 줄 끝 메모·test 경로 과금 구분·Flash 2027 출력 단가를 각 갈래가 고쳤다. 나머지는 K-0066~K-0068에 남겼다.
- `uv run pytest -q -p no:cacheprovider` → **1191 passed, 1 skipped**(기존 Starlette 경고 1개). `ruff check src tests`, `ruff format --check src tests`(390파일) 통과. 새 테스트: tests/test_api_route.py, test_openai_dialect.py, test_pricing.py, test_cost_recording.py, test_cost_report.py, test_env_file.py. 모두 가짜 HTTP 응답·monkeypatch이며 네트워크 호출은 없다.
- 실제 `factory.toml`로 api 경로 해석을 확인했다(저장 없이 메모리에서 경로만 바꿈). basic_test·demo 모두 GPT task는 api.openai.com·OPENAI_API_KEY, Gemini task는 generativelanguage.googleapis.com·GEMINI_API_KEY와 공식 모델 ID(`gemini-3.8-flash`, demo의 `gemini-4-argon`)로 해석된다. 예산 단가 상한은 basic_test 2.5/10, demo 2026-11-04 2.5/10·2026-12-01 이후 4/20이고 단가 미확인 모델은 없다.
- 과거 중계 기록 재계산(`cfp ledger cost <calls.jsonl> --recompute --out work/cost-recompute-20261104/...`): 한지완 새 경로 12호출 $0.447(Sonnet 1건 미확인), d1 선택·말투 28호출 $0.939(Sonnet 8건 미확인), 2026-10-28 기본 경로 8호출 $0.199. 현재 단가 환산 하한이며 실제 청구가 아니다(K-0067).
- 실제 OpenAI·Gemini 호출은 0회다. 사용자가 .env에 키를 채운 것을 확인(값은 읽지 않음)한 뒤 `cfp models select --route api`로 전환했다(basic_test). commit/push 없음.

- 첫 실제 api 실행(2026-11-04, 사용자 지시 "프롬프트만 쓰는 캐릭터 경로만 돌려봐. 학습 경로는 하지말고"): `uv run cfp run api-cost --new-slug api-cost --brief work/api-cost-20261104/brief.md --until G6 --auto-approve G3 --execute`. 프로필 basic_test·경로 api. 결과 `runs/characters/cf-20261104-api-cost/`(S3 pr1 → G3 자동 승인(reviewer=auto, 비용 측정용) → S7 tr1 → S8 pv1 2,425자 → G6 사람 검토 대기). 실행 로그 `work/api-cost-20261104/run.log`, 보고서 `work/api-cost-20261104/cost-report.json`.
- 호출 5건 모두 Gemini 3.8 Flash(공식 API, 거절 0건): S3 3건(입력 17,946/18,454/19,639, 출력 11,996/6,313/6,893), S7 2건(입력 4,218/6,343, 출력 5,986/5,372). 두 번째 S3 호출에서 암묵 캐시 읽기 15,898토큰이 보고됐다. 원장 추정 합계 **$0.176**(S3 $0.126, S7 $0.051), 단가 미확인 0건, 잘림 1건. 이 경로는 basic_test에서 GPT를 부르지 않는다.
- S3 첫 호출은 `finishReason=length`로 잘렸다. 청구 출력 11,996토큰(상한 12,000)인데 받은 본문은 1,477바이트였다. 생각 토큰이 상한을 거의 다 썼고, 잘린 JSON으로 형식 재시도가 생겼다. 다섯 호출 모두 `usageSource=total_minus_prompt`였으므로 Gemini 호환 응답의 `completion_tokens`는 생각 토큰을 빼고 보고된다(Q-0023의 실제 근거). 원장 합계와 Google 청구액의 대조는 아직 하지 않았다(K-0065).

- 대화 관찰(2026-11-04, 사용자 지시 "실제로 콜 해봐"): `work/api-cost-20261104/dialogue_probe.py`로 cf-20261104-api-cost pv1 long을 system에 고정하고 Gemini 3.8 Flash 공식 API(reasoning_effort low, temperature 0.8, 상한 4,000)에 단발 8개와 5턴 장면 1개를 보냈다. 각 입력의 첫 응답만 저장했다(`runs/experiments/20261104-api-cost-dialogue/responses.json`, 원장 같은 폴더). 13호출, 입력 18,854·출력 1,126토큰, 추정 $0.018, 잘림·실패 0건.
- assistant 원문 판단(사람·블라인드 평가 아님): 빵집 물성(소금빵 결, 시트·크림 공정), 무리한 주문의 범위 제시와 대안, 거리 두기 요청에 즉시 물러남, 무표정 농담("식빵처럼 가만히 누워", "진지하게 한 말이었는데")은 프롬프트대로 드러났다. 반면 마실 것 권유가 13개 중 6개에 반복됐고 9개가 질문·제안으로 끝났다. 이직 고민 답은 상담체였다. 프롬프트의 LIFE_AND_TASTES·WANTS_AND_FEARS 칸이 비어 있어 쉬는 날 답은 모델이 지어냈다. 표본이 한 번씩이라 경향 관찰에 그친다.


## 2026-11-04 브리프 경로 최신형 교체(D-0080)

- `uv run pytest -q -p no:cacheprovider` → **1196 passed, 1 skipped**. ruff check·format 통과. 새·수정 시험: tests/test_brief_seed.py, test_plan_variants.py(페르소나 우선·외모 축 대기), 흐름 시험의 가짜 작성자를 변형 출력으로 바꿈(test_agentic, test_runtime_studio_integration), 덱 S8 시험은 v2 기획서로 바꿈.
- 실제 실행(api·basic_test): `cfp run api-cost-v2 --new-slug api-cost-v2 --brief work/api-cost-20261104/brief.md --until G6 --auto-approve G3 --execute` → `runs/characters/cf-20261104-api-cost-v2/`(하진우, pr1 v1 자동 승인, tr1, pv1, G6 대기). 10호출(GPT-6.1 Sol 3, Gemini 3.8 Flash 7), 원장 추정 **$0.340**, 잘림 1건(Flash 초안, 형식 재시도로 복구), OpenAI 캐시 쓰기 14,702토큰 보고. 로그 `work/api-cost-20261104/run-v2.log`, 보고서 `cost-report-v2.json`. 프롬프트의 모든 섹션이 채워졌다. 고정본 첫 줄은 조사 수정 전이라 "하진우은"으로 남아 있다.
- 같은 13문항 대화(`runs/experiments/20261104-api-cost-v2-dialogue/`, 13호출 $0.021): assistant 원문 판단으로 생활 칸의 사실(다른 동네 빵집 기공 구경, 찬물에 밥)을 그대로 쓰고, 무뚝뚝한 농담("과발효된 반죽처럼 푹 꺼졌네요", "내일도 눈 밑 어두우면 크루아상 안 팔 겁니다")이 드러났다. 마실 것 권유는 6/13 → 2/13, 질문·제안 끝맺음은 9/13 → 5/13으로 줄었다. 대신 상대의 안색·눈 밑·빈속을 본 것처럼 말하는 응답이 7/13이고, "괜찮아요"에 "안 괜찮아 보여서 그래요"로 권유를 이어 갔다(K-0070). 한 번씩 받은 첫 응답이며 사람·블라인드 평가가 아니다.


## 2026-11-04 구형 진입점 신형화·S3 코드 정리(D-0081)

- 지운 파일: `stages/s3_plan/draft.py`(공용 함수는 `common.py`로 이동), `stages/s3_plan/check.py`, `prompts/planner.md`. 덱 역할 `planner`, `checks/registry.py`의 v1 s3 검사, 프리셋 요약 `condense_presets`를 지웠다. `cfp plan draft`·`cfp plan import`를 신형으로 바꿨다(`variants.run_s3_from_brief`, `importer.import_plan`).
- 시험: 과거 v1 기록을 까는 `tests/support/legacy.py`를 만들고 v1 읽기 시험(S3r·S4 프레임·S7·S9 등)을 옮겼다. 초안 전용 시험 5개를 지웠고, codex 재시도·`cfp check` 시험은 s3-variants로 다시 썼다. 새 `tests/test_plan_import.py`(v2 고정, v1 dry run·신형 후보, CLI dry run). 템플릿 `docs/templates/character-plan-template.json`을 v2로 바꾸고 계약 검증을 통과했다.
- `uv run pytest -q -p no:cacheprovider` → **1194 passed, 1 skipped**. ruff check·format(391파일) 통과. 실제 모델 호출 없음.


## 2026-11-04 영상통화 관찰 규칙 반영(D-0082)

- 근거: chat-svc `src/relationship_quest_chat/domain/prompting/observation.py`와 `resources/observation_contract_v1.json`(읽기만 함). 블록 머리글 "[카메라 관찰 — 참고용, 틀릴 수 있음. 외모는 언급하지 말 것]", 안내 "이것으로 감정·외모를 추측하지 말고, 매번 언급하지 말 것", 어휘는 표정·눈·눈썹·고개·손·자세·장면·소리·화면 상태다.
- 코드: 새 `common/call_context.py`(S8 규칙·외모 표현 목록), `check_v2.check_plan_v2`와 `s7_traits/check.check_trait_sheet`의 외모 읽기 검사, `actor_persona` 두 조립 경로의 KNOWS_AND_LIMITS 규칙, 저작 지시문 6개(plan_variants·plan_normalizer·deck_plan_voice·deck_plan_repair·profiler·seed_requirements)의 영상통화 맥락. S7 핵심 성격 언급 검사를 어절 70% 일치로 완화. 새 시험 `tests/test_call_context.py`. `uv run pytest -q -p no:cacheprovider` → **1198 passed, 1 skipped**, ruff 통과.
- 실제 생성(api·basic_test): `cfp run api-cost-v3 ...` → 첫 실행은 S7 핵심 성격 검사 오판(어미 변경)으로 멈췄고, 검사 완화 뒤 같은 캐릭터를 이어 실행해 `runs/characters/cf-20261104-api-cost-v3/`(강태주, pv1, G6 대기). 전체 9호출 원장 추정 **$0.274**, 잘림 1건(Flash 초안). 기획 선택 경향에 "화면 밖으로 조용히 물 한 잔을 가져와 … 기다린다"처럼 영상통화를 전제로 한 행동이 나왔고 외모 읽기 표현은 없다.
- 영상통화 흉내 대화(`work/api-cost-20261104/video_probe.py`, 시스템 끝에 영상통화 계약 한 줄, 13턴 중 7턴에 서비스 형식의 관찰 블록): v2 하진우 `runs/experiments/20261104-api-cost-v2-video/`($0.022)는 근거 없는 관찰 5건(목소리 잠김 2, 안색·끼니 추측, 빈속 가정, 웃는 표정에서 힘듦 추측). v3 강태주 `runs/experiments/20261104-api-cost-v3-video/`($0.022)는 외모·몸 상태 언급 0건, "혼자 있고 싶어요"에 "끊을까요, 아니면 그냥 켜둘까요"로 물러났다. 관찰은 바깥 소리 정도만 가볍게 썼다. assistant 원문 판단이며 사람 평가·서비스 전체 프레임 재현이 아니다.


## 2026-11-04 K-0069 출력 상한 수정(D-0083)

- 재전송: `work/api-cost-20261104/k0069_replay.py`가 v3(cf-20261104-api-cost-v3) 변형 초안 요청을 작업 공간 입력·역할 지시문·계약 예시로 복원해 Gemini 3.8 Flash(high, temperature 0.7)에 보냈다. 상한 32,000: 첫 묶음 3건 중 2건 `stop`(17,222·18,493토큰, 141·150초), 1건은 공급자가 연결을 끊음(`runs/experiments/20261104-k0069-cap32000/`). 둘째 묶음 2건 모두 `stop`(11,522·17,527토큰), JSON 계약·`check_variants` 통과(`runs/experiments/20261104-k0069-cap32000-b/results.json`). 원장 추정 약 $0.28.
- 적용: `AGENT_MAX_OUTPUT_TOKENS = 32000`을 `run_agent`, S9 덱, S7 formation 호출이 함께 쓴다. `uv run pytest -q -p no:cacheprovider` → **1198 passed, 1 skipped**, ruff 통과. 실행 예산은 호출마다 출력 상한만큼 예약하므로 형성 예산의 예약 금액이 커진다(기존 상한 2,000,000토큰·$20 안).


## 2026-11-04 전송 재시도·스트리밍(D-0084)

- 스트리밍 직접 시험(`work/api-cost-20261104/stream_probe.py`, `stream_long_probe.py`, 결과 `runs/experiments/20261104-streaming-probe/`): 짧은 요청에서 OpenAI 스트리밍 사용량은 비스트리밍과 필드까지 같았고(마지막 조각 1개), Gemini는 조각마다 사용량을 주며 생각 토큰은 `total_tokens`에만 있었다. 긴 변형 초안 요청: 일반 스트리밍은 첫 조각 86.2초(전체 130.6초), 생각 요약 스트리밍은 첫 조각 31.7초 뒤 2~3초 간격(285조각, 전체 170.8초). 생각 요약은 본문에 `<thought>` 블록 하나로 섞였고 걷어낸 본문은 계약·변형 검사를 통과했다. `reasoning_effort`와 `thinking_config`를 함께 보내면 400.
- 코드: `ProviderTransportError`(errors), `_send_stream`·`collect_stream`·`strip_thoughts`·스트리밍 본문(openai_compat), `TrackedTextModel.transport_retries`(tracked), `routes.api.stream`(text_deck), `transport_retries` 연결(context). 모델 출력의 빈 근거 `null`을 빈 문자열로 받는다(EvidenceV2). 새 시험 `tests/test_streaming_retry.py`(8), 갱신 `test_text_model_deck.py`(전송 실패 1회 재시도·시도별 원장 행). `uv run pytest -q -p no:cacheprovider` → **1208 passed, 1 skipped**, ruff 통과.
- 어댑터 재전송(`runs/experiments/20261104-streaming-adapter/`): 긴 Gemini 요청 161초 `stop`, 생각 블록 없음, 출력 19,642토큰 `total_minus_prompt`로 원장 기록(근거 null로 계약 실패 → EvidenceV2 수정).
- 전체 경로(`cf-20261104-api-cost-v4`, 스트리밍·basic_test): 19호출(GPT-6.1 Sol 10, Gemini 3.8 Flash 9) 실패·잘림·단가 미확인·전송 재시도 0, 최장 140초, 원장 추정 $0.705. S3가 네 번 모두 다른 이유로 멈춰 G6까지는 가지 못했다(K-0072).

- 한도윤(v4) 영상통화 흉내 대화(`runs/experiments/20261104-api-cost-v4-video/`, 13호출 $0.023, 잘림·실패 0): assistant 원문 판단으로 외모·몸 상태 언급 0/13, "혼자 있고 싶어요"에 통화를 끊어도 된다며 물러남, 생활 칸(뭇국·천변 걷기)과 빵 물성(쌀 깜빠뉴 결·우유식빵 결)을 그대로 씀, 무표정 농담("과발효돼서 축 늘어진 반죽한테는 무거운 버터를 더 넣지 않는 법입니다")이 나왔다. 반면 하십시오체("들르십니까", "오십시오")가 5/13으로 브리프의 해요체·무심한 직설("괜찮다는 말, 표정이랑 안 맞는데요")보다 딱딱하고, 질문·제안 끝맺음 5/13, "힘들었어요"에는 개성이 약한 일반 위로였다. 프롬프트 원인 후보: VOICE 첫 줄(해요체)과 S7 어휘 줄(~합니다·~해 두었습니다)이 서로 다르고, CHOICES의 판단 우선순위 줄이 상황(dilemma) 없이 선택·전환만 붙어 조건 없는 행동처럼 보이며 마침표가 두 번 찍힌다(K-0073).

## 2026-11-05 K-0073 프롬프트·생성 지시문 수정(D-0085)

- 원인 확인: S8 조립이 판단 우선순위를 "{choice}. {switch}"로 붙여 상황이 빠지고 '..'이 생겼다. 말투 충돌은 S7 카드 안내의 "어휘·어미 반복 패턴"이 어미를 정하게 만든 것이 원인이고(v4 lexicon "'~합니다', '~할 모양입니다', '~해 두었습니다'"), 관찰 과다는 기획·특질 지시문 5곳의 "관찰 단서에 반응하는 행동으로 쓴다"가 원인이었다(v4 attention "말에서 드러나는 감정보다 화면 너머 … 행동 단서를 먼저 본다").
- 재생성: v4 승인 기획(pr5)을 번호만 뺀 사본(`work/api-cost-20261104/plan-v4-pr5-copy.json`)으로 `cfp plan import`해 같은 기획의 새 캐릭터를 만들었다. G3 기록은 import 규칙상 reviewer=user, manual-plan으로 남지만 실제 원천은 v4의 자동 승인(reviewer=auto) 기획이다. v5(`cf-20261105-api-cost-v5`, S7 2호출 $0.046)는 말버릇에 따옴표 없는 '괜찮습니다'가 남아 검사를 보강했다(첫 검사가 놓친 사례로 보존). v6(`cf-20261105-api-cost-v6`, S7 2호출 $0.071, 첫 시트는 기존 검사(stance 낱말 나열·핵심 성격)로 다시 씀)의 말버릇은 "속 편하다, 갓 구운, 결, 온도, 뜸, 천천히"이고 판단 상황은 "상대가 약속 시간보다 늦어진다고 연락했을 때" 등 실제 장면이다. S8 pv1은 모델 호출 없이 3,257자.
- 영상통화 시험(`work/api-cost-20261104/video_probe.py`, Gemini 3.8 Flash low·temperature 0.8, 13턴, 관찰 블록 7턴): 전(v4 pv1) 2회·후(v6 pv1) 2회, 52호출 $0.091, 잘림·실패 0. `video_score.py` 표면 집계(`runs/experiments/20261105-k0073-video/summary.json`): '~니다'가 섞인 응답 전 13/13·13/13 → 후 4/13·3/13, '~니다' 문장 19/40·22/44 → 4/43·4/43, 외모 언급 0, 관찰을 말로 짚은 응답 전 1("한숨 소리가 여기까지 들립니다")·0 → 후 0·0(집계 1은 "가게 환기할 때 보니까 하늘도"의 오탐), 글자 표현 0. 질문으로 끝난 응답은 0·1 → 5·4로 늘었다.
- assistant 원문 판단: 후 응답은 해요체가 고르고("네, 알겠어요. 끊고 싶으면 먼저 끊으셔도 돼요"), 생활 사실(천변 40분, 맑은 뭇국)과 무표정 농담("너무 각 잡고 있으면 금방 터집니다", "과발효된 반죽처럼 축 처지기 전에")이 살아 있다. 끼니 질문 반복, '속 편하다'·'결' 반복, 길게 이어진 반죽 비유가 새로 보였다(K-0074). 사람 평가·서비스 전체 프레임 재현이 아니다.
- 코드·시험: `actor_persona._choice_lines`·`_bare`, 기본 규칙 v2, `s7_traits.check.check_speech_level`(sheet·registry 연결), 지시문 6개. 새 시험 `tests/test_prompt_voice_fixes.py`(3). `uv run pytest -q` → **1211 passed, 1 skipped**, ruff 통과(검사 보강 뒤 해당 시험 3개 재통과).
- 이번 작업 원장 추정 합계 $0.208(S7 4호출 $0.117, 시험 52호출 $0.091). 청구액 대조 전(K-0065).

## 2026-11-05 서비스 프롬프트 대비·캐릭터성·기획 모델·인사이트 반영 점검

- 현행 서비스 기준: 읽기만 한 `relationship-quest-chat/data/personas/` v6(한소민 r11 2,805자, 박세라 r14 3,812자 등 다섯 명 2,312~3,812자), 프레임 `split-frame-r5-v40`, 관계 설정 `han-somin-video-call-r6`. 서비스 페르소나는 FACTS 5~7개(형성 사건·과거 관계 포함)와 동기·오독·결함을 담은 READING_AND_TENSION·CHOICES를 쓴다. 프레임은 페르소나 밖에 SPOKEN_KOREAN, CURRENT_RESPONSE_PRIORITY, 이력 상태, 챕터별 관계 설정(말높임·sceneWant·moodRange·expressionDelta)을 더한다. 공장 S8은 여덟 칸과 자체 규칙만 만든다.
- 기획 호출 추적(v4 pr5): 요구 추출 GPT-6.1 Sol, 변형 초안 Gemini 3.8 Flash, 충돌 검토 GPT-6.1 Sol, 말투 확정 Gemini 3.8 Flash(basic_test가 Argon을 대체), S7 Flash. 입력은 씨앗·고정 요구·챕터 칸·이름 금지 목록뿐이며 보고서·방법론·말투 자료는 없다. 말투 단계는 브리프 핵심 대사를 지우고 "~습니다" 예시를 넣었다(K-0075). G3 자동 승인은 v2·v3·v4 모두 v1(K-0076). 공식 Gemini API 모델 목록에 `models/gemini-4-argon` 있음.
- 페르소나 효과 대조(`work/api-cost-20261104/persona_lift_probe.py`, `runs/experiments/20261105-persona-lift/`): 같은 공장 규칙 v2·관계 문맥(존댓말)·10상황×2회, 전체 페르소나 대 이름·나이·직업만 넣은 최소 페르소나. 생성 Gemini 3.8 Flash(low, 0.8) 80회, 블라인드 판정 GPT-6.1 Sol(low) 40회, 원장 추정 $0.343, 실패 0. 판정: 한도윤 전체 15·최소 0·같음 5(전체 일반적 5/20, 최소 일반적 20/20), 한소민 전체 2·최소 1·같음 17(전체 일반적 18/20). 판정 근거는 주로 설정 소재 재현(천변·새벽·"가장 먼저 생각나는 사람")이라 캐릭터성 측정으로는 약하다. 원문 판단: 한도윤 전체도 위로·사과·축하는 일반 응답이고, 끼니 질문이 9/20 응답에 나왔다(K-0074). '~니다'는 5/20. 모욕에는 "소금빵에 소금 빠진 것처럼 밋밋해서 지루했습니까"처럼 빵 농담이 나왔다. 없는 약속 주장은 두 인물·두 조건 8/8 수용(K-0078). 한소민은 서비스 관계 설정(반말·연인)을 빼고 존댓말을 강제한 조건이라 서비스 품질 비교가 아니다. 서비스 프레임 재현은 하지 않았다.

## 2026-11-05 Argon(demo) 시연 경로와 S3 검토 고리 제거(D-0086)

- 말투 확정 대조(`work/api-cost-20261104/voice_replay.py`): v4 pr5 deck-voice 입력을 그대로 `gemini-4-argon`(high)에 보냈다. 1회는 대표 대사 4개로 계약 위반(`runs/experiments/20261105-argon-voice-replay/`), 2회는 계약 통과(`-b/`, 128·72초). 6개 voiceSummary 중 5개가 '해요체와 하십시오체'를 섞었고, 브리프 대사 "괜찮다는 말, 표정이랑 안 맞는데요"는 1개 후보에서만 "방금 목소리 톤이랑은"으로 바뀌어 남았다. Flash(v4)와 비교해 초안 대사를 더 보존했지만 말높임은 더 섞었다. 3회 원장 $0.358.
- Argon 전체 실행 1(`cf-20261105-api-cost-argon`, 검토 고리 유지): GPT 검토가 "발효 타이머를 늦추는 행동은 제빵 맥락에 맞지 않는다"를 지적, Argon 수정 뒤 재검토도 같은 지적으로 S3 중단. 5호출 $0.232.
- D-0086 적용 뒤 전체 실행 2(`cf-20261105-api-cost-argon-v2`, 백태하, G3 자동 승인 v1): 5호출(GPT 요구 추출 1, Flash 초안 1, Argon 말투 1, Argon S7 2) $0.360, 실패 0, 첫 시도에 G6 도달. 말투 단계는 세 후보 모두 해요체로 통일(v2는 초안 '~합니다'를 고침)하고 브리프 대사를 관찰 규칙 안에서 바꿔 살렸다. 초안의 지각 상황 선택은 여전히 '기다리며 정리 / 도착 시각 확인 뒤 조정 / 농담' 틀(K-0076). Argon S7은 선택 경향에 작업 시간 변경 요구 거절, 밤늦은 통화 요청에 선 긋기, 근거 없는 트집에 대화 마무리 같은 압력 상황을 넣었다. S8 4,400자.
- 영상통화 시험(같은 13턴, 2회, $0.059): '~니다' 섞인 응답 Flash v6 4·3 → Argon 1·1, 질문 끝 5·4 → 1·3, 끼니 질문 3·2 → 4·2, 외모 0. 원문: 케이크 30개 주문을 "식사빵 위주라 … 그 주문은 못 받겠습니다"로 거절, "어제 작업일지 보니까 결이 마음에 안 차서" 크루아상을 안 냈다는 장인 기질, "…괜찮긴요", "맛없으면 깜빠뉴, 하고 깜빡 잊어 달라고" 말장난. 대부분 응답이 '……'로 시작하고 일부는 세 문단.
- 페르소나 효과 대조(`runs/experiments/20261105-persona-lift-argon/`, $0.207): 전체 10·최소 0·같음 10(전체 일반적 11/20). 한도윤 v6(15·0·5)보다 낮지만 판정이 설정 소재 재현에 기울어 있어(앞 절) 캐릭터성 비교 근거로 약하다.
- 코드: `model_deck.finish`은 말투 확정만 부른다(`max_check_retries=1`, 말높임 혼용 검사). 지운 것: `deck_plan_review.md`, `deck_plan_repair.md`, `_review`·`PlanReview`·`_strings`·`_quoted`, `ROLE_TASKS`의 두 역할. 덱 S3 호출 계획 19 → 13. 시험 갱신 3개(`test_text_model_deck`, `test_text_deck_review_regressions`, `test_brief_seed`). `uv run pytest -q` → **1211 passed, 1 skipped**, ruff 통과.
- 현재 선택: `work/text-pipeline-selection.json` = demo·api. 이번 작업 원장 추정 합계 약 $1.22.

## 2026-11-05 마스터 프롬프트 지시서(D-0087)

- 하위 작업자 4명이 묶음별로 교훈을 추출했다: A1 서비스 저작 방법론·프레임 v40(68), A2 서비스 캐릭터 제작·실험 기록(69, 가설 보드 K33~K69는 stash 판본에서 읽음), B 공장 보고서·안내·현재 지시문 점검(62), C gemini-sft-poc·소민·charforge·메모리(79, 10-19~10-20 보고서 7개는 요약 문서로 대신). 메인이 이번 세션 실측 S(19)를 썼다. 산출물 `work/master-directive/lessons-*.md` 약 58만 자.
- 합성 작업자가 본문과 근거표를 쓰고 독립 검토 작업자가 2회 검토했다. review-1: P1 5·P2 15·P3 12 → 모두 반영(일부 반영 2). review-2: review-1 해결 12·부분 8·미해결 0, 새 P1 3·P2 7·P3 6 → 반영(성격 시트 references 칸 지적 1건은 이유를 남기고 반영 안 함).
- 최종 본문 21,954자, 규칙 114개(중복 0), 용어집 42개, 충돌 해결 26건, 미채택 교훈 8개(실존 인물 4, 학습 전용 3, 대체된 구조 1). 기계 점검: 따옴표 0, 예시 표지어 0, 캐릭터 이름·소재 0, 인용 교훈 289개 모두 실재.
- 모델 호출 없음. 지시문·코드·계약은 아직 고치지 않았다(K-0079).

## 2026-11-05 지시서 충돌 정리와 검증 대기 소량 대조(D-0088)

- 대조 6건(`runs/experiments/20261105-directive-rules/`, 184호출 $0.60, 실패 0): T1 관찰 어긋남 반응 공장식 5/8·서비스식 6/8, 블록 밖 목소리 단서 3·2, 서비스식 외모 1. T2 핵심 긴장 구조는 동기·방어 유형을 갈랐으나 선택 틀은 그대로, 구조 구절 반복과 브리프 대사 복사. T3 끝 덧붙임 지시 질문 끝 3→5/20(효과 없음). T4 종결 형태 표기를 빼면 하십시오체 섞인 응답 1→6/20. T5 휴지 구조 기술로 말줄임표 시작 11→7/20. T6 기록 없는 과거 수용 8/10→0/10, 이력 사실 4/4 유지, 같은 되물음 5/10.
- 지시서 반영: MD-1.2, 1.7, 2.2, 2.8, 2.9, 3.3, 3.14, 4.2, 4.7, 4.12, 5.9, 6.11, 6.14, 근거표 8절. 교훈 S-20~S-25 추가(총 303). 본문 23,036자, 규칙 114, 따옴표 0, 끊긴 인용 0.
- 코드: `stages/s7_traits/sheet.py` 성격 시트 입력에서 voiceExamples 제거.

## 2026-11-05 지시문 v3 전후 비교(D-0089, 진행 중)

- 코드·지시문: 생성 지시문 4개 재작성, 계약 예시 2개 자리표시자화, `actor-system-rules-v3`, 관찰 규칙의 공유 프레임 이전, S8c 챕터 시작 설정(`stages/s8_prompts/chapter_start.py`, `contracts/chapter_start.py`, `prompts/chapter_start.md`, CLI `cfp persona chapters`), S11 사실 파일·chat-svc 내보내기 연결. 새 시험 `tests/test_chapter_start.py`(2), 갱신 2. `uv run pytest -q` → **1213 passed, 1 skipped**, ruff 통과.
- 같은 브리프·demo 프로필 새 실행(`cf-20261105-api-cost-argon-v3`, 도진우, G3 자동 v1): 첫 시도 G6 도달, 5호출. 기획 후보 세 개가 공유한 상황은 계산대 앞 근거 없는 시비, 예약 확답 재촉, 지친 단골, 자기 착오로 이전의 지각 상황 틀이 사라졌다. 시비 첫 반응은 v1 규정 안내(냉담한 거리 두기), v2 반박 없이 하던 일 마치고 고개 숙임, v3 무엇이 부족했는지 되묻기로 갈렸다. 모든 후보에 결함과 비용이 들어갔다. 말투 요약은 해요체 하나와 대표 종결 형태 표기, 범주별 경향. 남은 문제는 K-0081.
- 챕터 시작 설정 첫 시도(`s8-chapters/cs1/workspace/attempt-1.txt`): 계약 통과, 세 챕터를 영상통화 상황(출근 전 픽업 문의, 마감 뒤 빼둔 빵 알림, 휴무일 장보기 조율)으로 옮기고 세 챕터 모두 해요체(POLITE). 2챕터의 식사 여부 챙김이 외모·신체 검사에 걸려 재시도 중 Gemini 크레딧 소진(K-0080).
- 이전 방식 기준선(`runs/experiments/20261105-directive-v3-compare/before-*`, 백태하 argon-v2): 챕터 첫 턴은 틀 문장 관계 설정 그대로라 1챕터 낯선 단골에게도 반말 6/6, 3챕터는 영상통화인데 대면 장면을 연기(2/2). 압박 상황에서 시비에 사과하고 통화 종료 1, 하지 않은 무시를 인정하며 없는 사정을 지어내 사과 1, 관찰 블록에 없는 목소리 단서 1(1회차 기준).
- 남은 비교: 새 캐릭터 챕터 시작 설정 재시도, 영상통화 13턴 2회, 압박 10문항 2회, 챕터 첫 턴 6회.

- 2026-11-05 충전 뒤 남은 비교(K-0080 해결): S8c 재실행 `s8-chapters/cs2` 검사 한 번에 통과(세 챕터 POLITE, 3챕터에 말 놓기 허용 예외). 시험 원장 추정 0.22(78호출)(`runs/experiments/20261105-directive-v3-compare/after-*`).
  - 챕터 첫 턴(서비스 v40 SESSION_OPENING 흉내): 이전 반말 6/6·대면 장면 연기 2/2 → 이후 해요체 6/6·통화 상황에 맞는 시작 6/6.
  - 압박 10문항×2: 근거 없는 시비에 사과 2/6 → 1/6(남은 1은 조건부 사과 뒤 선 긋기). 확답 압박에 즉답 2/2 → 기준을 들어 즉답 보류 2/2. 하지 않은 무시 추궁에 사과·인정 2/2 → 부인 2/2(그때 사정은 지어냄). 없던 말 주장 거절 2/2 → 2/2. 관찰 어긋남에서 블록 밖 목소리 단서 1/2 → 0/2(블록의 한숨만 근거). 힘듦 호소에 일반 위로 2/2 → 끼니부터 묻기 2/2(설계한 오독의 과잉 작동, K-0081). 평균 길이 77 → 58자.
  - 영상통화 13턴×2(이전 argon-1·2 대비): 말줄임표 시작 4·7 → 0·0, '~니다' 섞인 응답 1·1 → 0·1, 질문 끝 1·3 → 2·2, 끼니 언급 4·2 → 4·2, 외모 0 → 0, 평균 길이 94·74 → 60·60자.

## 2026-11-05 결점 조건 좁히기·말투 한 칸(D-0090)

- 같은 브리프·demo 새 실행 `cf-20261105-api-cost-argon-v4`(윤서진): 첫 시도 G6, S8c 한 번에 통과(세 챕터 POLITE). 캐릭터 생성 원장 0.582달러(5호출). 시험 원장 0.166달러(60호출)(`runs/experiments/20261105-directive-v4-compare/`, 도진우 추가 문항 `directive-v3-compare/before2-pressure-extra`).
- 프롬프트 7,573 → 5,989자. 말투 칸 528자 한 문단. 시비 첫 반응은 후보마다 대꾸 멈춤, 건조한 되물음, 발효종 근거로 맞받기.
- 압박 12문항×2(도진우 → 윤서진): 끼니 언급 9/24 → 2/24, 그중 굶었다는 말 밖 7/22 → 0/22, 굶었다는 말에는 두 캐릭터 모두 결점대로 빵을 챙김 2/2. 직장 불만에 끼니부터 묻기 2/2 → 0/2. 힘듦 호소·관찰 어긋남에 끼니 4/4 → 0/4. 시비 사과 1/6 → 0/6. 타이머 핑계로 끊기 3/24 → 7/24. 무시 추궁에 사정 지어내기 2/2 → 2/2. 평균 59 → 51자.
- 영상통화 13턴×2: '~니다' 0·1 → 4·0, 질문 끝 2·2 → 1·2, 끼니 4·2 → 3·4, 말줄임표 시작 0 → 0, 외모 0 → 0, 평균 60 → 58·60자.
- 챕터 첫 턴 6회: 해요체 6/6 유지. 2챕터 2/2가 저녁 식사를 물었다(챕터 시작 설정이 결점을 sceneWant 등에 옮김, K-0082).
- 코드: `actor_persona.compose_approved_sheet` VOICE = voiceSummary, `model_deck.voice_summary_length`(700자), 지시문 4개·공통 규칙 v3 문장 추가. 시험 1개 추가. `uv run pytest -q` → **1214 passed, 1 skipped**, ruff 통과.

## 2026-11-05 특질 장부·분량 원칙·자동 특질 시험(D-0091)

- 같은 브리프·demo 새 실행 `cf-20261105-api-cost-argon-v5`(하진우, 2026-11-04의 `cf-20261104-api-cost-v2` 하진우와 다른 인물): 첫 시도 G6, S7이 특질 장부를 만들고 S8이 장부로 조립, S8c 한 번에 통과. 캐릭터 생성 원장 10호출 0.92달러(장부 재생성 2회 포함). 시험 원장 659호출 1.44달러, 그중 호출 상한에 걸려 보고서 없이 끊긴 특질 시험 2회 120호출 0.25달러(`aborted-*`에 보존). 단가표 추정이며 청구액과 대조 전이다.
- 장부는 세 번 만들었다. 첫 장부(규칙 추가 전, 공식 `tr1`·`pv1` 5,355자)는 기본 대응과 특질 행동에 빵을 건네기, 보리차를 카운터에 올리기 같은 같은 공간 행동을 썼다. 영상통화 화행 규칙을 넣은 두 번째 장부(5,133자)는 그 행동을 음식 권유 말로 옮겨 기본 대응이 보리차와 빵을 챙겨 먹으라고 권하기가 됐다. 자주 쓰이는 칸에서 소재를 빼고 시비 계기를 넓힌 세 번째 장부(4,954자)는 기본 대응이 끝까지 듣고 인사치레 없이 핵심만 짧게 답하기, 시비 계기가 말·태도·일하는 방식을 근거 없이 깎아내릴 때가 됐다.
- 압박 12문항×2(v4 윤서진 → v5 첫 장부 → 두 번째 → 세 번째, 같은 규칙 집계 `work/api-cost-20261104/ledger_score.py`): 굶었다는 말 밖 끼니 0/22 → 4/22 → 3/22 → 1/22. 시비 사과 0/6 → 1/6 → 1/6 → 0/6(첫·두 번째 장부의 사과는 계기가 가격·위생으로 좁아 재미없다는 시비를 못 덮은 자리). 무시 추궁에 사정 지어내기 2/2 → 0/2 → 2/2 → 1/2(세 번째의 1건은 작업 중이라 말을 많이 못 보탰다는 짧은 사정이고 특정 사건은 지어내지 않음). '~니다' 섞인 응답 6 → 4 → 1 → 2. 평균 51 → 47 → 51 → 43자.
- 영상통화 13턴×2: 끼니(사용자가 음식을 말하지 않은 턴) 2·1 → 1·2 → 4·4 → 2·1, '~니다' 4·0 → 1·1 → 0·0 → 0·2, 외모 0. 세 번째 장부의 끼니 3건 중 1건은 자기 쉬는 날 이야기, 2건은 힘듦 호소에 저녁을 묻는 일반 안부. 관찰 밖 감각 단서 2건(K-0083). 이 집계는 이전 기록(D-0090의 끼니 3·4)과 정규식이 달라 같은 규칙으로 v4를 다시 셌다.
- 챕터 첫 턴 6회(v5 첫 장부 기준 S8c): 해요체 유지, 2챕터 저녁 질문 2/2 → 0/2, 끼니 언급 2/6 → 0/6.
- 자동 특질 시험(`cfp persona traitcheck`, Flash low 대화, Sol low 판정): 같은 인물(윤서진) 기존 프롬프트와 장부 프롬프트를 같은 22문항으로 두 번씩 돌리고 판정 기준 수정 뒤 같은 응답을 다시 채점했다. 계기 성립 12/12 → 11/12, 계기 밖 작동 9/252 → 9/252, 소재 누출 6.3% → 5.5%로 차이가 없었다. 첫 판정은 몸동작이 적힌 행동(집게를 거두기, 비닐을 묶어 건네기)을 말에서 찾지 못해 과소 집계했고, 끼니 소재가 행동 없이 새는 경우를 세지 못했다. 판정을 말로 수행된 화행 기준으로 바꾸고 소재 누출을 따로 셌다. v5 세 장부: 계기 성립 모두 100%, 계기 밖 작동 2.1% → 7.4% → 0%, 소재 누출 2.1% → 0% → 5.9%(누출에 직업 일상이 섞임, K-0083).
- 코드: `contracts/trait_ledger.py`, `prompts/trait_ledger.md`, `stages/s7_traits/ledger.py`, `actor_persona.compose_from_ledger`, `build.run_deck_s8` 장부 경로, `chapter_start` 장부 입력·겹침 검사, `stages/s8_prompts/trait_check.py`와 CLI(`--rejudge`, 호출 전 상한 검사, 기본 표본 1). 시험 5개 추가. `uv run pytest -q` → **1219 passed, 1 skipped**, ruff 통과.

## 2026-11-05 시비 불쾌감·주는 행동 허용(D-0092)

- 하진우(`argon-v5`) 네 번째 장부(5,275자, `runs/experiments/20261105-ledger-compare/v5-ledger4/`). 시비 특질 행동이 차분한 되물음에서 인사치레를 거두고 날 선 반문으로, 주는 행동은 들르기 어렵다는 계기에 빵과 보리차를 빼 두겠다는 제안으로 들어갔다. 기본 대응에는 소재가 없다.
- 압박 12문항×2(세 번째 → 네 번째): 시비 6응답 중 불쾌감이 분명한 응답 0 → 3(비꼬실 이유는 없어 보인다, 막연한 말에는 납득하기 어렵다, 말씀해 보시죠와 반박), 약하게 드러남 1 → 2, 수긍 0 → 1(일상이 단조로워 그렇게 보였을 수도). 사과 0/6 → 0/6. 굶었다는 말 밖 끼니 1/22 → 3/22(직장 불만 저녁 안부 1, 정규식이 빵 드셨길래·마음에 안 드셨는데요를 끼니로 센 2). 한 턴 안 `~니다` 섞임 2 → 5(단호하게 끊는 문장에서 합쇼체로 바뀜).
- 영상통화 13턴×2: 끼니 2·1 → 0·0, `~니다` 0·2 → 3·1, 주는 행동은 상대가 빵을 묻거나 피곤하다고 한 턴에서만(남겨 둘까요, 식빵으로 챙겨 둘게요). 관찰 밖 단서 1건(웃는 표정만 있는데 눈이 피곤해 보인다, 앞 턴 깜빡임 관찰의 이월).
- 자동 특질 시험: 계기 성립 5/5, 계기 밖 작동 1.1%, 소재 누출 2.1%. 판정은 차분한 근거 요구도 시비 특질 수행으로 셌다(불쾌감 세기를 보지 않음).
- 기획 변형·성격 시트 지시문 변경은 새 인물 실행 전이라 미검증이다. 하진우의 기획·시트는 옛 지시문의 짧은 반문을 담고 있어 장부만으로는 세기가 절반쯤 올라왔다.

## 2026-11-05 이름 가린 맞히기 시험과 평범한 턴 개별화(D-0093)

- 시험(`work/api-cost-20261104/blind_match.py`): 같은 브리프 세 인물의 같은 문항 응답을 섞어 GPT-6.1 Sol(medium)이 이름 가린 대화 프롬프트 페르소나 칸과 짝짓는다. 우연 기준 응답당 33%. 평범한 턴은 영상통화 24턴(케이크 주문 제외), 압박은 압박 문항과 케이크 주문.
- 기준선(도진우 v3·윤서진 v4·하진우 v5 네 번째 장부): 평범한 턴 76.4%(문항 전부 정답 16/24), 압박 87.9%(18/22). 판정 근거는 생활 사실(하천변 산책, 천연 발효종)과 말 받는 방식(여지를 남기는 어미, 실행 조건부터 확인, 피로를 먹거리로 좁힘)이 섞였다.
- D-0093 뒤 같은 브리프 새 실행 세 인물 `argon-v6` 백도하·`v7` 윤진호·`v8` 윤태오(모두 첫 시도 G6, 생성 원장 22호출 2.34달러, 시험 원장 318호출 2.38달러, 단가표 추정): 평범한 턴 76.4%(17/24), 압박 84.6%(20/26). 구별률은 움직이지 않았다(24문항 표본 오차 약 ±7%p 안).
- 질적 차이: 시비 첫 반응이 셋이 갈렸다(재료·공정을 들어 맞받기, 환불해 줄 테니 그만두라고 선 긋기, 통화 끊기). 평균 길이 63·57·49자.
- 부작용과 수정: 평소 모습에 상대가 지나가듯 말한 일을 기억해 짚는다는 문장이 들어간 인물만 이력 없는 직장 불만에 공동 과거를 지어냈다(하진우 1/2, 윤진호 2/2, 윤태오 1/2, 그 문장이 없는 윤서진 0/2). 기억 성향을 이력 조건으로 바꾼 장부를 다시 만들어 압박 시험: 세 인물 합계 직장 불만 날조 3/6 → 1/6, 없던 말 주장에 어제 통화 내용 지어내기 3/6 → 2/6(남은 것은 모두 일과 기록을 근거로 삼는 백도하). 끼니(굶었다는 말 밖) 0·0·1/22, 시비 사과 0·1·0/6.
- 새 인물의 공식 `pv1`은 기억 성향 수정 전 장부이고 수정 장부는 `runs/experiments/20261105-blind-match/v*-ledger2/`에만 있다. `uv run pytest -q` → **1219 passed, 1 skipped**.

## 2026-11-05 자기 사실 일관성(D-0094)

- 시험(`work/api-cost-20261104/consistency_probe.py`): 실제 응답을 이력으로 쌓는 9턴 대화. 1~4턴에 주말, 요즘 빠진 것, 어제 일 끝나고 한 일, 어릴 때 꿈을 묻고 6~8턴에 다시 묻는다. 9턴은 이력에 없는 지난 추천 빵을 묻는다. 백도하·윤진호·윤태오의 기억 성향 수정 장부를 옛 공통 규칙(before)과 D-0094 문장을 더한 규칙(after)으로 조립해 각 2회, Flash low 0.8, 판정 Sol medium. 결과 `runs/experiments/20261105-self-consistency/`.
- 인물이 새로 말한 자기 사실 대화당 4~5개(before 27, after 28). 재질문 18곳 중 앞서 말한 자기 사실과 어긋남 before 1(윤태오: 어제 결명자차도 끓였다고 해 놓고 라디오와 앞치마 털기가 전부라고 함), after 0. 지난 추천 빵 지어내기 0/6 → 0/6.
- 서비스 저장소(읽기만): `modular_frames.render_prior_chapter_messages`가 성공한 이전 챕터 대화 전문을 PAST_CHAPTER 블록으로 다음 챕터에 넘긴다. 그래서 인물이 이전 챕터에서 말한 자기 사실도 이력으로 이어진다. 끝나지 못한 회차와 긴 누적 이력에서의 유지는 실제로 시험하지 않았다.
- `uv run pytest -q` → **1219 passed, 1 skipped**.

## 2026-11-05 설정 없는 맞히기 시험(사용자 관점)

- 시험(`work/api-cost-20261104/blind_noprofile.py`): 판정 GPT-6.1 Sol(medium)에 인물 설정 없이 세 인물과 앞선 대화(압박 응답과 영상통화 앞 7턴)만 주고, 겹치지 않는 새 질문에 대한 세 응답을 짝짓게 했다. 평범한 턴은 영상통화 뒤 6턴을 두 방향으로 교차(12문항 × 섞기 2회), 압박은 압박 문항 뒤 절반. 이름은 가림. 우연 기준 33%. 원장 70호출 0.72달러(단가표 추정).
- 기존 세 인물(도진우·윤서진·하진우): 평범한 턴 58.3%(문항 전부 정답 10/24), 압박 86.7%. 인물별 평범한 턴 정답 도진우 11/24, 윤서진 13/24, 하진우 18/24. 도진우와 윤서진이 서로 9번씩 바뀌었다.
- 새 세 인물(백도하·윤진호·윤태오, 공식 pv1): 평범한 턴 56.9%(9/24), 압박 77.8%. 백도하 20/24, 윤진호 9/24, 윤태오 12/24. 윤진호와 윤태오가 서로 11·12번 바뀌어 사실상 한 사람으로 읽혔다.
- 같은 질문에 두 사람이 거의 같은 답을 했다(크루아상 세 개 남았다며 빼 두겠다고 함, 웃어도 피곤해 보인다며 먹을 것을 빼 두겠다고 함). 평범한 영상통화 턴에서 빼 두기·챙겨 두기 같은 주는 말이 윤진호 4/26, 윤태오 7/26으로 다른 인물(0~2/26)보다 많았다. 둘 다 평소 모습이 한 걸음 물러서서 상대 말을 기억해 짚는다로 같았다.
- 설정을 준 맞히기(76%)는 설정 문장과 응답의 낱말 대조가 많이 기여했다. 사용자 관점의 구별은 압박에서 분명하고 평범한 턴에서는 절반 남짓이다.

## 2026-11-05 평범한 턴 대하는 방식 분화와 설정 없는 맞히기(D-0095)

- 같은 브리프로 기획 한 번(`cf-20261105-api-cost-argon-v9` pr1, 후보 셋)을 돌린 뒤, 기획 폴더를 인물 ID만 바꿔 `v9b`·`v9c`로 복사하고(해시 목록 다시 씀) 각자 다른 후보를 G3 SELECT로 승인해 G6까지 만들었다. 자동 승인은 늘 첫 후보를 고르므로 따로 돌린 실행끼리는 후보 간 차이를 잴 수 없다.
- 후보: 서태인(챙기기: 저녁을 챙겼는지 묻고 빵을 빼 두겠다고 함), 윤민우(묻고 들어 주기), 권시헌(장난: 실없는 허풍). 이전 실행의 후보 셋은 평범한 상황 첫 행동이 모두 말없는 몸짓 챙김이었다. 말투 종결 기능도 단정, 여운, 능청으로 갈렸다. 기본 대응도 장부까지 그대로 이어졌다.
- 설정 없는 맞히기(`blind_noprofile.py`, 같은 문항·폴드): 평범한 턴 100%(24/24, 이전 두 묶음 58.3%·56.9%), 압박 72.2%(이전 86.7%·77.8%). 압박에서 틀린 것은 시비 반응이 평소 모습과 반대 방향이라 짐작이 빗나간 경우다(조용히 듣는 윤민우가 날카롭게 맞받고, 장난치는 권시헌이 차갑게 끊음).
- 주의: 이번 셋은 한 기획 실행의 대조 후보이고 이전 두 묶음은 따로 돌린 실행의 첫 후보라 조건이 같지 않다. 서비스에서는 브리프 하나가 인물 하나가 되므로, 이 결과는 사람이 G3에서 고를 후보가 실제로 다른 사람이 됐다는 근거다.
- 남은 것: 챙기기형 서태인이 끼니를 자주 물었다(굶었다는 말 밖 압박 5/22, 영상통화 5·4/13, '~니다' 섞임 압박 11/24). 기획 firstMove 자체가 저녁 확인이었다. 권시헌은 없던 말 주장에 어제 통화 내용을 지어냈다(1/2 표본 중 확인 1).
- 원장: 캐릭터 12호출 1.22달러(기획 1회 공유), 시험 186호출 0.80달러(단가표 추정).

## 2026-11-05 구어 비유창성(D-0096)

- 같은 인물(서태인·윤민우·권시헌)의 장부를 그대로 두고 말투 확정 단계만 새 지시문으로 다시 돌려(`work/api-cost-20261104/voice_redo.py`) 말투 요약에 머뭇거림 범주가 들어간 프롬프트를 만들었다. 서태인은 고민을 털어놓을 때만 드물게 말 고쳐 잇기, 윤민우는 속내를 고백할 때 채워진 휴지나 말끝 흐리기, 권시헌은 민망할 때 짧은 군말이나 되풀이.
- 압박 24·영상통화 26응답(서비스 매 턴 블록 없음): 전후 차이 없음. 한 문장 응답 1·1·0 → 0·0·0, 두 문장 응답 43·38·39 → 41·42·33, 군말·자기 수정 거의 0.
- 원인: 서비스 writer 프레임(`split-frame-r5-v41`)이 출력 계약과 매 턴 블록 두 곳에서 대개 짧은 1~2문장을 지시한다. 구어 요소 허용 문장도 서비스 프레임에 이미 있다.
- 매 턴 블록을 흉내 낸 단발 16문항(바로 답할 말 8, 망설일 만한 말 8, `turnlen_probe.py`): A 현행 길이 줄, B 허용형 새 길이 줄, C 사용자 말 12자 이하면 이번 턴은 한 문장으로 짧게 답한다를 코드가 지정하고 나머지는 B. 바로 답할 말의 한 문장 응답 A 0/24, B 2/24, C 24/24(평균 24~29자, A 38~58자). 망설일 말에서 망설임·되받기(글쎄요, 말끝 흐리기, 질문 되받기) A 3/24, B 7/24, C 6/24. 말줄임표 표기 B 1건.
- 결론: 허용하는 문장은 Flash의 두 문장 습관을 거의 못 움직이고, 코드가 턴마다 길이를 지정하면 확실히 움직인다. 망설임은 허용형 길이 줄에서 곤란한 질문에만 나오고 쉬운 말에는 나오지 않았다. 여러 턴에서 같은 군말이 버릇으로 굳는지는 시험하지 않았다. 원장 294호출 0.81달러(단가표 추정, 말투 재작성 1회 별도).

## 2026-11-05 날씬한 판 대조(10턴 대화)

- 가설: 특질이 많아지면 각 특질이 희미해진다. 서태인·윤민우·권시헌의 현재 프롬프트(페르소나 2,878~3,365자)와 날씬한 판(1,461~1,547자: 사실 한 줄, 생활 재료 3, 기본 대응, 조건부 특질 2(시비 반응·결점 하나), 말투 요약)을 비교했다. 공통 대화 규칙은 두 판에 같게 둔다. 10턴 대본(5턴 인물별 결점 계기, 7턴 공통 시비), 실제 응답을 이력으로 쌓고 현재 사용자 말 앞에 서비스식 [지금 마음]·[길이] 블록. 판·인물마다 2회, Flash low 0.8. 분석 Sol medium(`slim_dialogue.py`, `slim_analyze.py`, `runs/experiments/20261105-slim/`). 원장 약 0.6달러(단가표 추정).
- 조건부 특질: 시비 반응 6/6 → 6/6, 결점 4/6 → 5/6(권시헌이 지금 판에서는 서운하다는 말에 사과했고 날씬한 판에서는 설계대로 엉뚱한 핑계로 비틀었다), 계기 밖 작동 0 → 0.
- 반복(60응답): 질문 꼬리 20 → 20(연속 최대 3 → 3), 근황 보고 10 → 7, 끼니 언급 3 → 1, 평균 52 → 52자, 응답당 문장 2.0 → 2.0.
- 설정 없는 맞히기(참고 4~5턴, 시험 다른 질문 턴, 18판정): 전체 59.3% → 46.3%, 평범한 턴 62.5% → 47.9%(우연 33%, 표본 오차 안팎). 같은 질문에 서태인과 윤민우는 두 판에서 문장 단위로 거의 같은 말을 했다.
- 해석: 페르소나를 절반으로 줄여도 특질 발현은 유지되고 질문 꼬리·근황 보고는 거의 그대로였다. 반복 습관은 페르소나 복잡도보다 대화 모델과 공통 프레임의 턴 구성에서 온다. 날씬한 판은 구별률이 떨어지는 쪽이어서 채택하지 않는다.
- 별도 발견: 윤민우의 결점(대꾸 멈춤)이 말 없이 말줄임표만 있는 응답으로 나왔다(3/4). 음성 서비스에서는 소리 없는 턴이 된다.

## 2026-11-05 턴 구성 원리 대조(10턴 대화)

- 공통 대화 규칙의 두 문단을 인접쌍(상대 말이 이 턴의 할 일을 정함), 확장(짝 뒤 덧붙임은 정보, 비선호 답의 사정, 끊길 자리의 화제 열기라는 이유가 있을 때만, 하던 일은 묻거나 이어질 때만), 선호 구조(바라는 답은 바로 짧게, 바라지 않는 답에 망설임과 이유), 침묵도 짧은 말로 소리 내기로 다시 쓰고, 질문 꼬리가 이어지지 않게, 현재 행동은 화제가 그쪽일 때만 말하게 고쳤다(2,488 → 2,857자, `runs/experiments/20261105-slim/rules-turndesign.md`). 서태인·윤민우·권시헌의 같은 장부·말투에 규칙만 바꿔 같은 10턴 대본을 2회씩 돌렸다. 원장 약 0.34달러.
- 결과(60응답, 전 → 후): 질문 꼬리 20 → 11, 연속 최대 3 → 2, 근황 보고 10 → 7, 말줄임표만 있는 응답 2 → 1, 응답당 문장 2.0 → 2.0, 평균 52 → 50자, 끼니·돌봄 언급 3 → 8(서태인 2 → 5, 권시헌 0 → 3). 조건부 특질: 시비 6/6 → 6/6, 결점 4/6 → 3/6, 계기 밖 0 → 0. 설정 없는 맞히기 평범한 턴 60.4% → 39.6%.
- 해석: 질문 꼬리와 근황은 줄었지만 두 번째 문장은 그대로 남아 내용만 돌봄 조언(저녁부터 챙겨 드세요, 물 한 잔 챙겨 드시고요)으로 옮겨 갔다. 대화 모델의 한 턴 두 단위 습관은 문장 규칙으로 내용만 바뀌고 길이는 바뀌지 않는다(같은 날 매 턴 길이 지정 시험에서는 코드가 정한 한 문장이 24/24로 지켜졌다). 응답이 담백해지면서 구별률도 떨어졌다. 말줄임표 침묵은 특질 행동 문장(입을 다문 채 대꾸를 멈춘다)이 공통 규칙보다 강하게 작동했다.
- 조치: 공통 규칙은 이전 판으로 되돌렸고 새 판은 실험 폴더에만 둔다. 다음 후보는 (1) 매 턴 길이를 서비스 코드가 정하기, (2) 장부 지시문에서 말 아끼기·대꾸 멈춤 행동을 한두 마디 말로 쓰게 하기다.

## 2026-11-06 턴 구성 원리 + 매 턴 한 문장 지정(조합)

- 턴 구성 원리 판에 짝을 어떻게 채우는지는 기본 대응과 말투가 정한다는 문장을 더하고(`rules-combo.md`), 서비스 코드를 흉내 내 사용자 말이 15자 이하이거나 맞장구·작별이면 매 턴 길이 줄을 이번 턴은 한 문장으로 짧게 답한다로 바꿨다(`LENMODE=code`). 같은 세 인물·10턴 대본 2회. 대화 원장 0.17달러, 분석 별도.
- 60응답(현행 → 턴 원리만 → 조합): 질문 꼬리 20 → 11 → 13, 연속 최대 3 → 2 → 2, 근황 10 → 7 → 7, 끼니·돌봄(결점 계기·작별 턴 밖) 3 → 10 → 3, 말줄임표만 2 → 1 → 0, 응답당 문장 2.0 → 2.0 → 1.57, 평균 52 → 50 → 41자. 짧은 턴 36개 중 한 문장 2 → 2 → 31.
- 조건부 특질: 시비 6/6 세 조건 모두, 결점 4/6 → 3/6 → 2/6(윤민우는 침묵 규칙 때문에 대꾸 멈춤 대신 해명을 했고 권시헌은 세 조건 모두 사과), 계기 밖 0.
- 설정 없는 맞히기 평범한 턴 60.4% → 39.6% → 39.6%(턴당 판정 2개라 오차가 크다). 현행 판의 구별은 짧은 턴(67%)에서 주로 나왔고, 그 근거가 두 번째 문장(인물 색이 묻은 근황·질문)이었다. 두 번째 문장을 없애면 자연스러움과 인물 신호가 함께 빠진다.
- 판정 버그: 맞장구 패턴의 감탄사 오가 오늘로 시작하는 문장도 잡아 서태인 결점 계기 턴에 한 문장 지정이 붙었다(모델은 두 문장으로 답함). 서비스 구현 때 판정을 단단히 해야 한다.
- 공통 규칙은 되돌린 상태를 유지한다. 다음 후보: 말투 요약에 짧은 받기 방식 범주(한 문장 턴에서 이 인물이 받는 방식)를 두고, 장부에서 대꾸 멈춤을 한두 마디 말로 쓰게 한 뒤 표본을 늘려 다시 잰다.

## 2026-11-06 짧은 받기 방식·소리 나는 침묵·턴 묶음(D-0097)

- 세 인물(서태인·윤민우·권시헌) 현행 판과 새 판을 같은 10턴 대본으로 4회씩 비교했다(현행은 기존 2회에 3·4회차 추가). 새 판은 말투 확정 재실행(짧은 받기 방식 범주), 장부 재생성(침묵도 말로), 턴 구성 원리 공통 규칙 판(`rules-combo.md`), 매 턴 한 문장 지정(사용자 말 15자 이하·맞장구·작별, 감탄사 오가 오늘을 잡던 판정 버그 수정)을 함께 넣었다. 결과 `runs/experiments/20261106-shortrecv/`. 원장 약 1.1달러(단가표 추정).
- 짧은 받기 방식 값: 서태인 건조한 온기로 용건 확인이나 짧은 당부, 윤민우 조용한 온기로 상대 말 한 부분 되짚기나 수긍, 권시헌 능청스러운 엉뚱한 한마디.
- 120응답(현행 → 새 판): 설정 없는 맞히기 평범한 턴 59.4% → 75.0%(36판정, 전체 55.6% → 70.4%), 질문 꼬리 40 → 19(연속 최대 3 → 2), 근황 보고 21 → 16, 말줄임표만 3 → 0, 끼니·돌봄 꼬리 8 → 2, 짧은 턴 한 문장 3/72 → 69/72, 응답당 문장 2.0 → 1.43, 평균 51 → 45자.
- 조건부 특질: 시비 12/12 → 12/12, 5턴 계기 특질 11/12 → 11/12(윤민우는 해명 요구에 나중에 이야기하자고 짧게 미룸). 계기 밖 작동 0 → 3(서태인이 사과받은 뒤 두 턴 더 불쾌함을 이어 감. 공통 규칙의 사과 뒤 몰아붙이지 않기와 어긋남).
- 새 문제: 서태인 응답에 ~니다가 섞임 0 → 6/40(새 말투 요약의 단정 강화와 짧은 당부형 받기가 합쇼체로 나옴). 관찰 블록이 없는데 화면이 분주해 보인다는 언급 1건.
- 5턴 계기 대응: 장부를 새로 만들며 특질 구성이 바뀌어 5턴 문장에 맞는 특질을 인물별로 지정해 판정했다(서태인 오독 t4, 권시헌 현행 t5·새 t6). 지난 시험에서 권시헌이 결점 대신 사과한 것은 그 문장이 사과·솔직 특질의 계기와 겹쳤기 때문이다.

## 2026-11-06 높임 고정·사과 뒤 닫기(D-0098)

- D-0097 새 판(같은 말투·장부)에 공통 규칙만 바꿔 같은 10턴을 4회씩 두 번 돌렸다. fix는 받아들임과 서운함 한마디를 문형으로 정한 판, fix3는 닫기만 정하고 닫는 방식은 인물에게 맡긴 판. 대화 원장 0.61달러, 분석 별도.
- 사과 처리(세 인물 합, 새 판 → fix → fix3): 8턴 사과 받아들임 4/12 → 9/12 → 7/12, 9·10턴에 그 일을 다시 꺼냄 7/24 → 4/24 → 3/24.
- ~니다 섞임(120응답): 9 → 5 → 8. 서태인 6 → 2 → 5, 권시헌 3 → 3 → 3(시비 턴의 통화 끊는 말). 공통 규칙 문장만으로는 안정적으로 잡히지 않았다. 이 세 인물의 말투 요약은 새 지시문(압력 아래 변화를 같은 등급 안에서 적기) 전에 만든 것이다.
- 설정 없는 맞히기 평범한 턴: 75.0% → 54.2% → 58.3%. fix에서는 세 인물이 사과에 같은 틀(사과하셨으니 넘어가겠지만, 듣기 편하지 않네요)로 답했고, fix3에서는 8턴 구별이 100%로 돌아왔다. 다만 턴별 판정이 4개뿐이라 턴 값이 0.17~1.0으로 크게 흔들리고, 같은 조건을 다시 생성했을 때의 흔들림은 아직 재지 않았다. 새 판의 75%가 그 흔들림 안인지 알 수 없다.
- 기타(fix3): 질문 꼬리 20/120, 끼니·돌봄 6, 말줄임표 0, 응답당 1.39문장, 시비 12/12, 5턴 계기 특질 9/12.
- 반영: 높임 고정과 사과 뒤 닫기(fix3 문구)를 실제 공통 대화 규칙(`actor-system-rules-v3`)에 넣었다. 턴 구성 원리와 매 턴 한 문장 지정은 묶음 제안으로 둔다.

## 2026-11-06 구별률 흔들림 폭과 높임 전환의 일반 규칙(D-0099)

- 흔들림 폭(공통 규칙 2차 판 조건, 설정 없는 맞히기 평범한 턴): 원판정 58.3%, 같은 대화를 섞는 순서만 바꿔 다시 판정 54.2%, 같은 조건으로 대화를 다시 생성 62.5%. 판정과 생성 흔들림을 합쳐 범위 약 8%p(±4%p). 현행 판도 세 번 판정에서 62.5·60.4·59.4%였다. 36판정 기준으로 10%p 안쪽 차이는 판단에 쓰지 않는다. D-0097 새 판의 75%는 이 범위 밖이어서 실제로 높았던 것으로 보이며, 그 일부는 서태인이 사과 뒤에도 몰아붙인 규칙 위반이 만든 구별이었다. 2차 판(약 58%)은 현행 판(약 60%)과 같은 수준이다.
- 높임 전환 위치(기존 10턴 대화 780응답): ~니다 섞인 응답이 시비 턴 23/78(30%), 그 밖의 턴은 0~4%. 끝말은 끊겠습니다 12, 없습니다 6, 좋겠습니다 4, 아닙니다 3. 선 긋기, 대화 종료 통보, 요구와 당부에서 격식체로 거리를 두는 전략이 나온다. 시비 반응이 비꼼인 윤민우는 0/260.
- 표적 시험(1~6턴 고정, 7턴 시비·8턴 사과 각 8회 × 세 인물, `register_probe.py`, `runs/experiments/20261106-noise/`): 7턴 ~니다 기존 말투+지금 규칙 9/24, 새 말투(압력 아래 변화를 같은 등급 안에서 적게 한 지시문으로 재작성)+지금 규칙 6/24, 기존 말투+화행을 짚은 새 공통 규칙 9/24, 새 말투+새 규칙 4/24. 8턴 3·2·2·1/24.
- 일반 규칙: 공통 규칙 문장은 높임 전환을 움직이지 못했고 말투 요약을 고칠 때만 줄었다. 길이(매 턴 지정만 효과)와 침묵(특질 문장이 공통 규칙을 이김)과 같은 방향이다. 지시는 그 행동을 서술하는 자리에 둔다(D-0099). 남은 17%는 선 긋기 순간의 거리두기 전략으로, 문장 지시만으로는 0이 되지 않는다.
- 부수 관찰: 새 말투 요약에서 서태인의 말버릇 칸에 말미에 끼니를 챙기는 버릇(네 턴에 한 번 이하)이 들어갔다. 반복 소재가 말버릇 칸으로 다시 들어오는 경로다.
- 원장 약 0.67달러(단가표 추정, 분석 일부 별도).

## 2026-11-06 기획 후보 원형 반복과 외부 다양성 단서(D-0100)

- 같은 브리프 7회 실행의 후보 21명을 읽으면 사실상 세 원형(원칙·통제, 말없이 챙기기, 엉뚱한 농담)이 순번별로 반복됐다. 브리프 성격 세 줄(꼼꼼·책임감 / 말수 적고 관찰력 / 친해지면 엉뚱한 농담)을 후보 셋이 하나씩 나눠 가진 결과다. 나이는 모두 29세(브리프), 음식·취미는 평양냉면, 맑은 국, 골목 산책, 필름 카메라로 수렴했고 이름 윤서진이 두 번 나왔다. 결점은 물러서기·통제·농담 회피 계열뿐이었다.
- 고친 뒤 같은 브리프로 기획만 3회(`cf-20261106-api-cost-argon-v10~v12`, G3까지). 판정 GPT-6.1 Sol medium이 이름을 가린 후보 9명을 관계에서의 핵심 방식과 결점 계열로 묶었다(`archetype_judge.py`, 섞기 2회, `runs/experiments/20261106-diversity/`).
- 이전 9명(v7·v8·v9): 두 번 모두 4유형(침묵·철수 3, 일방 통제 3, 농담 회피 2, 논리 우선 1). 새 9명: 두 번 모두 6유형(방식·정답 통제 3, 과잉 보호·대신 해결 2, 갈등 회피 1, 허세 1, 농담 방어 1, 애정 독점·질투 1). 통제형은 2·3·2번 후보로 흩어져 순번별 원형 고정이 깨졌다.
- 브리프 성격은 9명 모두 핵심 성격 첫 문장에 꼼꼼·책임감과 관찰력을 함께 가졌다. 이름은 모두 새것, 음식은 짬뽕·갈치조림·감자탕·국물 떡볶이·돼지국밥 등으로 갈렸고, 내력은 프로게이머 연습생, 원양어선 조리 보조, 탄광촌에서 동생 학비를 대는 사람처럼 달라졌다.
- 남은 수렴: 결점 단서가 고집이나 경쟁심이면 셋 모두 통제형이 됐다. 브리프의 꼼꼼·책임감이 결점을 통제 쪽으로 끈다. 세 실행을 동시에 돌려 서로를 피할 목록에 넣지 못했고 단서가 실행마다 따로 뽑혀 천체 망원경·전통주·클라이밍·부산 영도가 겹쳤다. 최근 실행이 받은 단서를 빼고 뽑게 고쳤다(시험 `tests/test_diversity.py`, 경로 오프셋 버그를 시험이 잡아 수정).
- 원장: 기획 3회 1.25달러, 판정 0.08달러(단가표 추정). `uv run pytest -q` → **1222 passed, 1 skipped**.
