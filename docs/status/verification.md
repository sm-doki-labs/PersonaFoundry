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
- 원장: 기획 3회 1.25달러, 판정 0.08달러(단가표 추정). `uv run pytest -q` → **1231 passed, 1 skipped**.

## 2026-11-07 진행 화면과 단계 이력(D-0101)

- 서버 시험: `uv run --locked pytest -q -p no:cacheprovider` → **1230 passed, 1 skipped**(새 `tests/test_web_history.py` 8개 포함). 로그 `work/factory-flow-20261107/pytest-full-2.log`. `ruff check src tests`, `ruff format --check`, `git diff --check` 통과.
- 화면 시험: `cd studio && node --test tests/flow.test.cjs tests/runtime.test.cjs tests/runtime-host.test.cjs tests/runtime-integration-contract.test.cjs tests/text-pipeline.test.cjs` → 41 passed(새 flow 6개). 실제 서버 그래프로 팀 사이 선 10개, 목표 범위, 대기 시간·재시도·새 판·실패·유료 보류 표시, 할 일 순서, 결정 알림을 확인했다.
- 가짜 공급자 완주(브라우저): `uv run --locked python work/factory-flow-20261107/e2e_server.py --root /tmp/cf-flow-e2e-r1 --port 8796`. `tests/test_offline_pipeline.setup`의 합성 캐릭터(가상 순위 목록, 가짜 글·이미지·영상·판정·학습)를 모든 단계 PENDING·작업 0건으로 띄우고, 영상 공급자에 paid=true를 붙였다(자동 재개 켬, 재개 목표 sx). Codex 내장 브라우저에서 `/studio/factory.html`만 조작해 시작 전 화면 → "끝까지" 실행 → G1 → G3 → G6 수정 요청(pv1 반려 → pv2 생성) → G6 → G4a → G7a → G4b → G7 → G4 → G5 → G8(블라인드 20쌍) → G9 순서로 12개 관문을 결정하고, 유료 단계 s5·s6을 실행 확인으로 돌렸다. 결과: `cf-20261107-poc-female` 17/17 단계와 12/12 관문 APPROVED, sx APPROVED. 단계 이력에 s8 1회차(pv1, 결정 REJECTED)와 2회차(pv2, APPROVED)가 남았다. 원장 3,034호출, 추정 비용 $0(가짜 공급자, 단가 미확인 0). 조작 기록 `work/factory-flow-20261107/e2e-steps.json`, 캡처 `work/factory-flow-20261107/shots/`(03 실행 확인과 검토, 04 검토 여러 건, 05 G6 검토 영역, 06 유료 확인, 07 완료, 08 완료 390px).
- 빈 화면·등록·연결 끊김: 빈 루트 `/tmp/cf-flow-empty-r1`(가짜 공급자 설정) 서버 8797에서 첫 화면(캐릭터 없음) → 새 캐릭터 등록(`cf-20261107-flow-check`, 작업 0건 유지) → 목표 "프롬프트 승인까지"를 고르면 3단계·검토 2번과 범위 밖 팀이 흐려짐을 확인했다(캡처 01, 02). 서버를 강제 종료하자 머리줄이 "다시 연결하는 중"으로 바뀌었다(캡처 09). Ctrl-C 종료는 열린 SSE 연결 때문에 끝나지 않았다(K-0087).
- 실행하지 않은 것: 실제 모델·이미지·영상·학습 호출, 어두운 화면 설정 캡처, 실패·반려의 브라우저 표시(K-0086). 실제 `runs/characters`는 건드리지 않았다.

## 2026-11-07 Foundry 브랜드·3단 화면·관문 화면 테마(D-0102)

- 서버 시험: `uv run --locked pytest -q -p no:cacheprovider` → **1230 passed, 1 skipped**. 로그 `work/factory-flow-20261107/pytest-full-3.log`. `ruff check src tests`, `ruff format --check src tests`(407 files), `git diff --check` 통과.
- 화면 시험: `cd studio && node --test tests/flow.test.cjs tests/runtime*.test.cjs tests/text-pipeline.test.cjs` → 42 passed(flow 7개, 새 시험은 토큰 두 사본 일치와 관문 덮어쓰기가 `body.fd` 안에만 있는지 확인).
- 가짜 공급자 완주, 밝은 화면(브라우저 1512×982): `uv run --locked python work/factory-flow-20261107/e2e_server.py --root /tmp/cf-flow-e2e-light --port 8796`. D-0101과 같은 합성 캐릭터(모든 단계 PENDING, 영상 paid=true, 자동 재개 sx)를 `/studio/factory.html`에서만 조작했다. G1 → G3 → G6 수정 요청 → G6 → G4a → G7a → G4b → G7 → G4 → G8 → s5 실행 확인 → G5 → s6 실행 확인 → G5b → G9 → 완료. 결과: `cf-20261107-poc-female` 17/17 단계, 12/12 관문 APPROVED, sx APPROVED. s8 회차 이력에 pv1 REJECTED → pv2 APPROVED. 콘솔 오류 없음. 캡처 `work/factory-flow-20261107/shots-light/`(01 시작 전, 02 첫 검토, 03 G1 검토 시트, 04 검토 여러 건, 05 G6 시트, 06 G8 시트, 07 유료 확인, 08 완료).
- 가짜 공급자 완주, 어두운 화면: 같은 서버 스크립트 `--root /tmp/cf-flow-e2e-dark --port 8798`, 어두운 화면으로 바꾼 뒤 같은 순서로 완주했다. 결과는 밝은 화면과 같다(17/17, 12/12, sx APPROVED, s8 pv1 REJECTED → pv2 APPROVED, 콘솔 오류 없음). 시트 안 관문 화면도 어두운 토큰으로 열렸다. 조작 기록 `work/factory-flow-20261107/e2e-steps-dark.json`, 캡처 `work/factory-flow-20261107/shots-dark/`(같은 이름).
- 좁은 폭: 새 합성 루트 `/tmp/cf-flow-narrow`(포트 8799, 시작 전 상태)에서 1280px은 사이드바가 아이콘 줄로 줄고 3단이 유지되며, 390px은 사이드바 대신 캐릭터 고르기 목록이 나오고 그래프가 한 줄로 쌓이는 것을 밝은·어두운 화면 모두 확인했다. 390px에서는 테마 버튼이 보이지 않는다(K-0088). 캡처 `work/factory-flow-20261107/shots-narrow/`(light-1280, dark-1280, light-390, dark-390).
- 서버 8796·8798·8799는 Ctrl-C가 열린 SSE 연결 때문에 끝나지 않아(K-0087) 프로세스를 강제 종료했다.
- 실행하지 않은 것: 실제 모델·이미지·영상·학습 호출, 실패·반려의 브라우저 표시(K-0086), 따로 연 관문 화면(`/gate.html`, 글래스 모양 유지)의 회귀 캡처, 다른 브라우저 엔진. 실제 `runs/characters`는 건드리지 않았다.

## 2026-11-07 실패·반려 브라우저 확인, 캐릭터 개요·받은 일, 그래프 보기, 페르소나 검토(D-0103)

- 서버 시험: `uv run --locked pytest -q -p no:cacheprovider` → **1237 passed, 1 skipped**(새 `tests/test_stage_failure_state.py` 2개, `test_web_queue` 목록 held 확인 포함). 로그 `work/factory-flow-20261107/pytest-full-4.log`. `ruff check src tests`, `ruff format --check src tests`(418 files), `git diff --check`, 토큰 두 사본 `cmp` 통과.
- 화면 시험: `cd studio && node --test tests/flow.test.cjs tests/runtime*.test.cjs tests/text-pipeline.test.cjs` → 43 passed(flow 8개).
- 실패 주입 서버: `work/factory-flow-20261107/e2e_fail_server.py --root /tmp/cf-fail-light2 --port 8801 --fail s7`(루트에 `FAIL-s7`이 있는 동안 s7 가짜 에이전트가 형식에 맞지 않는 답을 낸다. `--reuse`는 같은 루트를 다시 띄운다). 고치기 전에는 s7이 RUNNING으로 남고 작업은 `AgentFormatError`로 실패했다(K-0089, 캡처 `shots-fail/light-01-failed-raw.png`). 고친 뒤 s7이 1·2회차 CHECK_FAILED로 기록되고 장면 갈래는 G4a 대기까지 계속 돌았다. 실패 이유는 쉬운 문장, 원문은 기술 정보로 보였다(밝은 `light-02-failed`, 어두운 `dark-02-failed`, 390폭 `light-03-failed-390`·`dark-03-failed-390`). `FAIL-s7`을 지우고 다시 실행하자 3회차 통과(`light-04-retry-recovered`). 이때 다시 실행이 s7만 돌아 s8이 조용히 멈추는 것을 확인해, 다시 실행을 목표까지로 바꾸고 '이어서 실행' 알림을 더했다(`light-05-stalled-resume`). 이어서 실행 → s8 → G6.
- 반려: G6에서 반려 2번(pv1 → pv2 → pv3). 가짜 공급자가 새 판을 바로 만들어 처음에는 시트가 닫히지 않고 알림도 없었다. 관문 화면이 결정을 부모에 알리게 고친 뒤 시트가 닫히고 '처음부터 다시 만들도록 보냈어요' 알림과 회차 이력(1·2회차 다시 만들기, 3회차 대기)이 보였다(`light-07-rejected`). 반려 버튼은 확인 창이 뜨고 취소하면 G3이 AWAITING_HUMAN(pr1)으로 남았다.
- 개요·받은 일: 같은 서버에 `cafe-owner`, `night-runner`를 등록·실행해 3명으로 `#all`·`#all/mine`을 확인했다. 목록 API에 held가 없어 지금 보는 캐릭터만 유료 확인을 세던 것을 서버에서 고쳤다. 받은 일에서 검토 종류 '얼굴 고르기 · 2건'으로 거르고 검토하기 → 시트에 '다음 건 · night-runner (1건 남음)' → 결정 → 알림의 다음 건 → 두 번째 결정까지 이어졌다(`light-08-overview`, `light-09-inbox-batch`, `light-10-batch-sheet`, `light-11-batch-next-note`, 어두운 `dark-06-overview`, 390폭 `dark-07-overview-390`·`light-14-overview-390`). brief만 있는 캐릭터에 '이어서 실행'이 잘못 뜨던 것을(외모 축은 s2 승인 뒤 기획) 서버의 lastJob.blocked로 빼도록 고쳤다.
- 그래프 보기: 확대 150%에서 연결선이 칸을 따라감, 화살표 이동, 크게 보기·Esc 복귀, 어두운 크게 보기(`light-12-zoom-150`, `light-13-focus`, `dark-04-focus`). 유료 '비용 확인' → '견적 없음' 패널 → 취소(`dark-05-paid-confirm`). 시트를 닫으면 배경 inert가 풀렸다. 끌기·휠 이동은 코드로만 확인했다(브라우저 자동 조작 도구에 끌기 시험을 하지 않았다).
- 페르소나 검토(서브에이전트, 읽기 전용, 캡처·코드만): 기획 PD(Claude Opus 5.5), 운영 엔지니어(GPT-6 Astra), 첫 관객·접근성(GPT-6.1 Sol). 셋 다 상위 개요(목록–상세)·받은 일 대기열·유료 두 단계 확인·초점 문제를 짚었고, 확대는 둘이 찬성·하나가 과하다고 봤다. 반영한 것과 남긴 것(K-0090~K-0093)은 D-0103·알려진 문제에 적었다. 대비 수치·화면 읽기 동작은 검토자의 추정이고 측정하지 않았다.
- 실행하지 않은 것: 실제 모델·유료 공급자 호출, 화면 읽기 프로그램 실측, 다른 브라우저 엔진. 실제 `runs/characters`는 건드리지 않았다.

## 2026-11-08 관문 화면 해요체·블라인드 20쌍(D-0104)

- 서버 시험: `uv run --locked pytest -q -p no:cacheprovider` → **1240 passed, 1 skipped**(새 `tests/test_gate_copy.py` 3개). 로그 `work/factory-flow-20261107/pytest-full-5.log`. `ruff check src tests`, `ruff format --check src tests`(420 files), `git diff --check` 통과. 화면 노드 43 passed. `gate.js`는 `node --check` 통과.
- 준비: `work/factory-flow-20261107/prep_g8.py --root /tmp/cf-g8`가 가짜 공급자 합성 캐릭터 `cf-20261108-poc-female`를 앞 관문 11개를 웹 API로 결정하며 G8 대기까지 돌렸다(학습 제출 켬, 실제 호출 0회). `e2e_fail_server.py --root /tmp/cf-g8 --port 8802 --reuse`로 띄웠다.
- 밝은 화면(1512×982): 진행 화면 시트로 G8을 열어 단축키 1·2·3으로 7쌍(고를 때마다 다음 쌍으로 이동, 고정 막대 7/20, 보내기 잠김·'13쌍이 남았어요'), 나머지 13쌍을 버튼으로 골랐다. 20/20이 되자 지표가 열리고(조건·지표 이름 한국어), 채택 칸으로 초점이 갔고 보내기가 풀렸다. 캡처 `shots-gate/light-01-g8-top`, `light-02-g8-keyboard`, `light-03-g8-all-picked`, `light-04-g8-metrics`.
- 어두운 화면: 다시 연 G8에서 9쌍을 고른 뒤 시트를 닫았다 열자 9/20이 그대로였다. 나머지를 고르고 지표·채택을 본 뒤 보내자 시트가 닫히고 '평가·블라인드 20쌍: 결정을 기록했어요'가 남았으며 G9가 열렸다(`dark-01-g8-progress`, `dark-02-g8-metrics`, `dark-03-g8-adopt`, `dark-04-g8-decided`, `dark-05-g9`).
- 다른 관문 문장: G1·G6·G7a 결정 기록(밝은·어두운), G9(밝은 챕터·관계 단계 한국어). 얼굴 근거는 '목록 위에서 54% 지점이에요', 결정 기록은 '이미 결정했어요 · 고름 · tester · 시각'으로 보였다(`light-05-g1-readonly`, `light-06-g6-readonly`, `light-07-g7a-readonly`, `light-08-g9-chapters`, `dark-06-g1-readonly`, `dark-07-g6-readonly`, `dark-08-g7a-readonly`). 단독 관문 화면(`/gate.html`, 글래스)도 같은 문장으로 열리고 콘솔 오류가 없었다(`glass-01-g9-standalone`).
- 반려 확인 창, 수정 요청 흐름은 이번에 다시 누르지 않았다(D-0103에서 확인). 실제 모델·유료 호출 없음, 실제 `runs/characters` 손대지 않음. 서버 8802는 강제 종료했다(K-0087).

## 2026-11-08 얼굴 고르기 갤러리(D-0105)

- 서버 시험: `uv run --locked pytest -q -p no:cacheprovider` → **1241 passed, 1 skipped**(배분 규칙 시험 1개 추가). 로그 `work/factory-flow-20261107/pytest-full-6.log`. `ruff check src tests`, `ruff format --check src tests`(420 files), `git diff --check` 통과. 화면 노드 43 passed. `gate.js` `node --check` 통과.
- 가짜 공급자: `e2e_fail_server.py --root /tmp/cf-g1-gallery --port 8803`(새 합성 캐릭터) → `until=G1` 작업. 합성 순위 목록은 외모군 3개라 얼굴 9장(3·3·3)이 만들어졌다. 외모군 4개(10장, 3·3·2·2)는 배분 시험으로만 확인했다.
- 밝은 화면(1512×982, 진행 화면 시트): 갤러리 9장·거르기 칩·추천은 얼굴 1에만(`shots-g1/light-01-gallery-empty`). 마우스와 숫자 키로 고르기, S와 ♡로 3장 추리기, 결정 칸에 고른 얼굴·태그·각도·근거, 주 버튼 '얼굴 4로 확정'(`light-02-gallery-shortlist`). 나란히 비교에서 얼굴 4 고르기(`light-03-compare`).
- 어두운 화면: 외모군 B 거르기·2장 추리기(`dark-01-gallery-filter`), 나란히 비교에서 얼굴 5(c2-2) 고르기(`dark-02-compare`), '얼굴 5로 확정' → 시트 닫힘·'얼굴 고르기: 결정을 기록했어요'·S2 기준 사진 완료·G3 열림(`dark-03-decided`). 기록 `gates/G1-rf1.json`은 `selections = [c2, c2-2]`.
- 결정 기록 보기(밝은 화면): 얼굴 5가 고른 상태로 잠겨 보이고 추리기·트레이는 숨는다(`light-04-readonly-record`).
- 시트를 연 직후에는 초점이 부모 창의 닫기 버튼에 있어, 숫자 키는 시트 안을 한 번 누른 뒤 먹는다. 실제 이미지 공급자 호출 없음.

## 2026-11-08 기획안 가로 비교표(D-0106)

- 서버 시험: `uv run --locked pytest -q -p no:cacheprovider` → **1241 passed, 1 skipped**. 로그 `work/factory-flow-20261107/pytest-full-7.log`. `ruff check src tests`, `ruff format --check src tests`, `git diff --check` 통과. 화면 노드 43 passed. `gate.js` `node --check` 통과.
- 가짜 공급자: `e2e_fail_server.py --root /tmp/cf-g1-gallery --port 8803 --reuse`(D-0105에서 G1 결정 뒤 G3 대기). 가짜 기획 3안은 '같은 상황에서 고르는 행동' 3줄만 다르고 19줄이 같다.
- 밝은 화면(1512×982, 시트): '3개 항목이 서로 달라요 · 같은 항목 19개', 다른 항목만 보기로 시작, 숫자 키 2로 안 2 열 강조·결정 칸 요약·'안 2로 확정'(`shots-g3/light-01-only-diff`). 표 폭 599px로 시트 안에 가로 넘침 없이 들어갔다.
- 어두운 화면: 안 3 고르기 → '모두 보기'로 22줄 전부(`dark-01-all-rows`), 고치기 칸 한국어 이름(`dark-02-edit-fields`), '대비되는 면' 한 칸을 고쳐 '안 3으로 확정'(`dark-03-picked-only-diff`) → 시트 닫힘·알림, G3 `selections = [v3]`, 확정 `plan.json`의 `contrastTrait`에 고친 문장이 들어갔다.
- 결정 기록 보기(밝은 화면): 안 3 열이 '고른 안'으로 잠겨 보인다(`light-02-readonly-record`).
- 실제 기획 모델 호출 없음. 후보가 4개 이상이거나 직접 쓴 안(u1)이 함께 있는 경우는 화면으로 보지 않았다.

## 2026-11-08 챕터별 배경 줄(D-0107)

- 서버 시험: `uv run --locked pytest -q` → **1241 passed, 1 skipped**. 로그 `work/factory-flow-20261107/pytest-full-8.log`. `ruff check src tests`, `ruff format --check src tests`, `git diff --check` 통과(저장소 전체 `ruff check .`는 손대지 않은 `scripts/trait_persona_gemini_20261029.py` 줄 길이 17건으로 실패, 이번 변경과 무관). 화면 노드 43 passed. `tests/test_gate_copy.py` 3 passed. `gate.js` `node --check` 통과.
- 가짜 공급자: 밝은 화면은 `e2e_fail_server.py --root /tmp/cf-g1-gallery --port 8803 --reuse`(G3 결정 뒤 G4a 대기), 어두운 화면은 확정 전에 복사한 `/tmp/cf-g4a-dark`(포트 8804). 가짜 배경은 챕터 3개 × 후보 3개, 9:16.
- 밝은 화면(1512×982, 진행 화면 시트): 처음 열면 '0 / 3 챕터 골랐어요'·확정 잠금·'3개 챕터가 남았어요(1장, 2장, 3장)'(`shots-g4a/01-light-empty`). 숫자 키 2로 1장 후보 2 → 2장으로 이동, 2장 직접 적기 → '2 / 3'·'1개 챕터가 남았어요(3장)'·확정 잠금(`02-light-partial`). 3장 후보 3 → '배경 3개로 확정' 풀림·고른 배경 자세히 펼침(`03-light-all-picked`). 확정 → 시트 닫힘·'챕터 배경 고르기: 결정을 기록했어요'·G4b 열림(`04-light-after-confirm`). `selection.json`은 `picks = {ch1: ch1-b2, ch3: ch3-b3}`, `custom = {ch2: …}`, 기록 `gates/G4a-bg1.json`은 `selections = [ch1-b2, ch3-b3, custom:ch2]`·G4a `APPROVED`. 결정 기록 보기에서 고른 배경이 잠겨 보이고 나머지는 흐리며 단축키 안내가 숨는다(`05-light-readonly`).
- 어두운 화면: 빈 메모로 '다시 만들기' → '다시 만들 챕터에 고칠 점을 적어 주세요'·접은 칸 열림·1장 칸 초점. 키보드만으로 1 → 3 → 4(3장 직접 적기, 입력 칸 초점)·글 입력 → '배경 3개로 확정'(`12-dark-all-picked`). 확정 → `picks = {ch1: ch1-b1, ch2: ch2-b3}`, `custom = {ch3: …}`, G4b 대기. 기록 보기(`13-dark-readonly`).
- 휴대폰 폭(390×844, 관문 화면 단독·기록): 줄 머리가 위, 후보는 옆으로 넘기며 고른 후보 자리로 넘어가 있다(`14-dark-phone`).
- 실제 이미지 공급자 호출 없음. 후보가 4개 이상이거나 자동 검사 미통과·검토 의견이 붙은 후보는 화면으로 보지 않았다.

## 2026-11-08 나머지 관문 화면(D-0108~D-0114)

- 서버 시험: `uv run --locked pytest -q` → **1242 passed, 1 skipped**. 로그 `work/factory-flow-20261107/pytest-full-9.log`. `ruff check src tests`, `ruff format --check src tests`, `git diff --check` 통과. 화면 노드 43 passed. `tests/test_gate_copy.py` 4 passed(관문 화면 함수 존재 시험 추가). `gate.js` `node --check` 통과.
- 가짜 공급자: `e2e_fail_server.py --root /tmp/cf-g1-gallery --port 8803 --reuse`로 G4b부터 마지막 내보내기까지 진행 화면 시트에서 결정해 **17/17 완료**했다. 유료 표시 단계(S5·S6)는 가짜 영상 공급자라 비용 0. 관문마다 결정 전 사본을 `/tmp/cf-g4b-snap`·`cf-g4-snap`·`cf-g5-snap`·`cf-g7a-snap`·`cf-g7-snap`·`cf-g9-snap`에 남겼다. 화면은 `work/factory-flow-20261107/shots-gates/`.
- G4b(어두운 화면 고르기·확정, 밝은 화면 기록): 숫자 키 2로 1장 자세 2, 표정 한 칸 고치기(표에 줄 긋기로 반영, 초점 유지), N으로 2장 → 4로 직접 적기 → 3장 1 → '자세 3개로 확정'. `selection.json`은 `picks = {ch1: ch1-p2, ch3: ch3-p1}`, `custom = {ch2: …}`, `tweaks = {ch1: {expression: …}}`.
- G4(밝은 화면 수정 요청, 어두운 화면 승인): 크게 보기에서 1장 괜찮아요 → 2장으로 자동 이동 → 고칠게요·메모 → 3장 괜찮아요 → '챕터 1개 수정 요청'(fr1 기록 `requestedChanges = [ch2]`). 고친 판 fr2에서 2장 카드에 지난 요청이 보이고 1·3장은 미리 괜찮아요 → 2장 괜찮아요 → '챕터 3개 모두 승인'. Escape는 크게 보기만 닫고 시트는 남는다.
- G5(어두운 화면): 가짜 영상이 재생되지 않아 두 칸 모두 '이 영상을 재생하지 못했어요'·파일 링크, '길이·해상도를 못 읽음' 칩, 숫자 키 2 → '영상 2로 확정'.
- G5b(어두운 화면 다시 만들기, 밝은 화면 확정): 칸 열기 → 1(쓰기)·X(빼기)로 다음 칸 자동 이동, 반가움 칸 고칠 점 → '남은 칸 모두 첫 후보로' → '동작 1개 다시 만들기 요청' → 비용 확인 뒤 va2. va2에서 다시 만든 칸 표시, 3장 여섯 칸을 모두 빼면 열 머리 경고·확정 잠금, 하나를 쓰기로 바꿔 '동작 13개로 확정'(기록 `selections` 13개).
- G7a(밝은 화면 묶음 1·2, 어두운 화면 3~5): 1·2·3 키와 고쳐 쓰기 메모, 묶음을 보내면 시트가 남고 다음 묶음 탭으로 이동. 보낸 묶음을 다시 열면 판정·메모가 보인다(처음에는 '판정 없음'으로 나와 서버가 `sentVerdicts`를 주도록 고쳤다).
- G7(어두운 화면 요약, 밝은 화면 판정·승인): 대화 23·답변 46·학습 토큰 '—'·막는 문제 없음·경고 1건, 묶음별 막대. J/3으로 버리기, J/2로 고쳐 쓰기 → 메모 전에는 승인 잠금 → 승인. `qa/G7-ds1.json`에 REJECT·FIX와 메모가 들어갔다.
- G9(어두운 화면 점검표, 밝은 화면 승인): 자동 점검 7개(통과 4, 확인 필요 2: 가짜 공급자 영상 14개·학습 없이 긴 프롬프트, 안내 1: 앱 적재), 사람 확인 3개를 표시해야 승인이 풀림. 항목을 누르면 아래 세부 내용이 열린다. 승인 → 내보내기까지 17/17.
- 결정 기록 보기(관문 화면 단독): G5b·G4·G5·G9·G7이 잠긴 상태로 보인다. 휴대폰 폭(390): G7 받은 편지함은 목록이 가로로 넘어가고, G5b·G4b 표는 최소 폭을 두고 옆으로 넘기며 항목 열이 고정된다. 문서 가로 넘침 없음.
- 실제 모델·이미지·영상 호출 없음(K-0096).

## 2026-11-08 동작 영상 판단 이월(D-0115)

- 서버 시험: `uv run --locked pytest -q` → **1248 passed, 1 skipped**. 로그 `work/factory-flow-20261107/pytest-full-10.log`. `tests/test_actions.py` 63 passed(이월 1건·틀린 값 5건 추가). `ruff check src tests`, `ruff format --check src tests`, `git diff --check` 통과. 화면 노드 43 passed. `gate.js` `node --check` 통과.
- 가짜 공급자: G5·G5b 대기 사본(`/tmp/cf-g5-snap`)을 `/tmp/cf-g5b-light`(포트 8803)·`/tmp/cf-g5b-dark`(8804)로 복사해 진행 화면 시트에서 확인했다. 화면은 `work/factory-flow-20261107/shots-g5b-carry/`.
- 밝은 화면: 18칸을 모두 정하고(쓰기 15·빼기 3) 한 칸에 고칠 점 → '동작 1개 다시 만들기 요청'. `choices/G5b-va1.json`에 쓰기 15·빼기 3. 비용 확인 뒤 va2에서 '17 / 18 칸 정했어요 · 지난 판에서 17칸 이어받음', 다시 만든 칸만 '정하기'(`02-light-va2-prefilled`). '남은 칸 열기'로 그 칸이 지난 요청과 함께 열림 → 1 → '동작 15개로 확정'. `approved-actions.json` 15개·빼기 3개.
- 어두운 화면: 3칸만 정하고(2장 기본 대기 쓰기, 2장 무표정 빼기, 3장 쑥스러움 빼기) 2장 반가움·3장 쑥스러움에 고칠 점 → 요청(`11-dark-partial-request`). va2 `carried`는 쓰기 1·빼기 1이고, 빼기로 정했다 다시 만든 3장 쑥스러움은 넘기지 않았다(`12-dark-va2-prefilled`). 남은 칸 모두 첫 후보로 → '동작 17개로 확정'.
- 확인 중 알게 된 점: 크게 보기 창은 정하면 다음 칸으로 넘어가므로, 메모는 그때 열려 있는 칸에 적힌다(밝은 화면에서 다시 만든 칸이 의도와 달리 '피식'이 됐다). 화면은 열린 칸 기준으로 맞게 동작했다.
- 실제 영상 공급자 호출 없음.

## 2026-11-08 사용성 정리(D-0129)

- 서버 시험: `uv run --locked pytest -q` → **1258 passed, 1 skipped**. 로그 `work/factory-flow-20261107/pytest-full-11.log`. 예상 비용 API 시험 추가. `ruff check src tests`, `ruff format --check src tests`, `git diff --check` 통과. 화면 노드 43 passed(기대값 4곳 갱신). `tests/test_gate_copy.py` 4 passed. `gate.js`·`flow.js` `node --check` 통과.
- 가짜 공급자: 대기 관문이 다른 사본 6개(`/tmp/ux-g3`·`ux-g4`·`ux-g4b`·`ux-g5`·`ux-g7`·`ux-g9`, 포트 8803~8808)로 진행 화면 시트에서 확인했다. 화면은 `work/ux-fix-20261108/`.
- 밝은 화면: 개요 숫자 단위(3명·7건·5/17단계), 이름 없는 캐릭터 '이름 미정 · cafe-owner (11/7)', 사이드바 '사용 안내'. G3에서 안 2 고르면 '보지 않고 첫 후보로 확정'이 숨음, 고치기 칸 종류(글·숫자·한 줄에 하나·고급 2칸), ?로 단축키 창·Esc로 닫힘(시트는 남음), 말투 예시에 한 줄을 더하고 ⌘+Enter → 확정, `plan.json` `voiceExamples`에 새 줄. G7 '직접 본 대화 3 / 20', '아직 안 본 대화 17개는 기본값인 쓰기로 들어가요', 묶음 이름 한국어, 학습 토큰 '—'.
- 어두운 화면: G4 세 챕터 괜찮아요 → Ctrl+Enter 승인 → '방금 한 일'에 '다음 검토 · 프롬프트 승인' → 누르면 G6 시트가 열림. 소개 영상 비용 확인 '이번 실행 예상 비용 $0.82 · 단가 720p 초당 $0.05', '함께 보기' 합계 $11.50·'2개 모두 유료로 실행'(실행하지 않고 취소). G6 수정 요청을 빈 칸으로 누르면 아래 칸으로 옮겨 초점, 적고 누르면 '5초 뒤에 보내요 · 지금 보내기 · 보내기 취소' → 취소 → '보내지 않았어요', 버튼 다시 풀림, G6은 대기 그대로. G5b '모두 쓰기'(2장)·'모두 빼기'(3장) → 3장 경고·확정 잠금, '3장 6칸을 빼기로 바꿨어요 · 되돌리기' → 되돌림, '남은 N칸 첫 후보로 채우기', 칸 크게 보기에서 J로 다음 칸, ?로 동작 영상 단축키 표. G9 승인 뒤 내보내기 안내 문구. 사용 안내 페이지 어두운 테마.
- G4b(밝은 화면): 자세 하나 고르면 일괄 확정 숨김, J로 다음 탭. 반려 버튼은 시험 도구가 확인 창을 자동 승인한 뒤 5초 안에 취소하지 못해 실제로 보내졌다(ps1 반려 → ps2 생성). 반려 확인 창 문구 자체는 화면으로 보지 못했다.
- 휴대폰 폭(390): 개요 숫자 단위, 카드 배치. 실제 모델 호출 없음.
- 화면 작업만 담은 브랜치(`codex/foundry-screens`, 트윈 갈래·시험 경로 코드 제외)에서 다시 돌렸다: 서버 **1244 passed, 1 skipped**(트윈·시험 경로 시험이 빠진 만큼 적다), 화면 노드 43 passed, `ruff check`·`ruff format --check`·`node --check`(gate.js·flow.js)·`git diff --check` 통과.

## 2026-11-08 모델 만들기 보기(D-0130)

- 서버 시험: `uv run --locked pytest -q` → **1251 passed, 1 skipped**(새 `tests/test_web_training.py` 7개 포함). 화면 노드 44 passed. `ruff check`·`ruff format --check`·`node --check`·`git diff --check` 통과.
- 가짜 공급자 브라우저 확인: `work/training-ui-20261108/serve.py`로 합성 캐릭터를 학습 계획(s10t 계획만)까지 만든 서버 4개를 띄우고 `shots.cjs`(Chrome, 1440폭)로 화면만 조작했다. 캡처는 `work/training-ui-20261108/shots/`.
  - 밝은·어두운 화면 각각: 공정 화면의 '학습 비용 확인' 할 일 → 모델 만들기 탭(학습 단계가 먼저 열림) → 학습 시작 확인 → 학습 중(진행 막대 51/300스텝, 1분째) → 데이터셋·재료 읽기 전용 → 학습 중단 확인 → 중단됨(학습 줄 실패 표시, '다시 학습') → 공정 화면(s10t '중단함 · 다시 시작 대기').
  - 어두운 화면: 결과 받기 1번 실패를 넣어 '학습 결과를 받지 못했어요'(맨 위 실패 할 일, 기술 정보 접기) → 공정 화면 할 일의 '다시 받아 오기' → 학습 완료 → 자동 재개로 평가 → 평가 단계가 먼저 열리고 '블라인드 20쌍 고르기'.
  - 밝은 화면: '학습 없이 진행' 확인 → 평가에서 '긴 프롬프트 채택 검토' → 학습 단계 읽기 전용('학습으로 바꾸기') → 390폭.
  - 페이지 오류 0건. 가짜 학습은 GPU를 빌리지 않아 감시·GPU 빌림 칸은 '빌리지 않아요'로, 비용은 $0.00으로 보인다. 실제 GPU·네트워크 호출 없음.

### 실제 재료 연결 가능성 점검(같은 날)

- 학습 화면 값의 출처를 코드로 대조했다: 예상 비용·시간(`gemma_qlora.plan`), GPU 이름·시간당 단가·빌린 시각·반납 시각(`lease.json`), 자동 반납 마감(`guard.json`), 전송 해시(`transfers`), 스텝(원격 `state.json`·`checkpoint-plan.json`를 읽도록 이번에 더함, 실제 원격으로는 미확인), 체크포인트 표(`checkpoint-selection.json`)는 실제 코드가 쓰는 값이다. 쓴 돈은 추정이다.
- 결함 수정: GPU를 빌리고 올리는 동안 실행 기록이 아직 PLANNED라 화면이 '비용 확인 대기'로 보였다. 임대 기록이 살아 있으면 '학습 중'으로 보이게 고치고 시험을 더했다(1252 passed, 1 skipped).
- 재료 연결 실험: gemini-sft-poc 선별 결과로 AI Hub SNS 세션 10개·NIKL 구간 10개를 원문에서 꺼내 S9 후보 형식으로 바꿨다(0.5초). 그대로 넣으면 4~12턴 제한에 모두 걸려 SNS 0건이었고, 12턴 구간 78개로 자르면 가짜 작성 모델로 base에 실제 원문 사용자 턴을 쓴 5건이 들어갔고 데이터셋 화면에 그대로 보였다(K-0103). 원문은 `/tmp`에만 두었다.

## 2026-11-08 SNS·말뭉치 긴 세션 자르기(D-0131)

- 서버 시험 **1254 passed, 1 skipped**(`tests/test_s9_data.py`에 구간 자르기·버린 이유·분할 묶음·경고 2개 추가), 화면 노드 44 passed, ruff·format·node --check·git diff --check 통과.
- 실제 재료 실행: `real_sources.py`로 AI Hub SNS 이어 붙인 세션 40개와 NIKL 구간 30개(18~152턴, 중앙값 38턴)를 자르지 않고 S9 후보 파일로 넣고(`/tmp`), 가짜 작성 모델로 학습 계획까지 돌렸다(목표 120대화). 가짜 작성 모델은 같은 문장을 되풀이해 반복 검사 상한만 실험용으로 200으로 올렸다(`serve.py --relax-repeat`).
  - 후보 70개 → 구간 267개(긴 대화 70개 모두 자름) → base에 36구간이 들어갔다. 세션 순서로 돌려 놓기 전에는 36구간이 7세션에서만 나왔고, 고친 뒤에는 35세션에서 나왔다. 같은 세션이 학습·검증·평가에 걸친 경우 0.
  - 상한 200: '상한 200개를 넘은 구간 67개는 쓰지 않았어요', 상한 40: '…227개는 쓰지 않았어요' 경고가 데이터셋 경고와 재료 칸('70대화 → 267구간 → 36 쓴 구간')에 보였다. 밝은(상한 200)·어두운(상한 40) 화면 캡처 `work/training-ui-20261108/shots/*-real*.png`, 페이지 오류 0.
  - 넣은 36구간은 모두 AI Hub SNS였고 NIKL은 0이었다(파일 앞쪽 출처가 먼저 쓰임, K-0103 남은 부분). 재료가 들어가는 클러스터는 base뿐이다.

## 2026-11-08 SNS·말뭉치 출처 섞기(D-0134)

- 서버 시험 **1257 passed, 1 skipped**(`tests/test_s9_data.py`에 출처 섞기·말뭉치만 있을 때·통화 글자 표기 차단·작성 요청 채널 3개 추가), 화면 노드 44 passed, ruff·format·node --check·git diff --check 통과.
- 실제 재료 실행: D-0131과 같은 후보 파일(AI Hub SNS 세션 40개 + NIKL 구간 30개, `/tmp/tui-real-raw.jsonl`)과 같은 조건(`serve.py --target 120 --relax-repeat`, 가짜 작성 모델)으로 다시 돌렸다.
  - 구간 267개 = SNS 180 + 말뭉치 87. 상한 200: 넣은 후보 200 = SNS 160 + 말뭉치 40, 상한 40: SNS 32 + 말뭉치 8. 두 경우 모두 base에 쓴 36구간 = **SNS 29 + 말뭉치 7(19%)**. 전에는 말뭉치 0이었다.
  - 같은 세션이 두 분할에 걸친 경우 0. 말뭉치 7구간은 모두 학습으로 갔다(검증 0, K-0104).
  - 작성 요청에 말뭉치 구간이 `origin=NIKL, channel=call`로 실린 것은 시험으로 확인했다. 실제 작성 모델이 통화 장면을 입말로 쓰는지는 보지 않았다.
  - 밝은(상한 200)·어두운(상한 40) 화면에서 재료 칸 '출처별: SNS(문자) 29 · 81%, 말뭉치(통화) 7 · 19%'와 데이터셋 경고 줄을 봤다. 캡처 `work/training-ui-20261108/shots/*-mix*.png`, 페이지 오류 0.

## 2026-11-08 흐름 뼈대 재작성과 10글자 겹침 검사(D-0135)

- 서버 시험 **1258 passed, 1 skipped**(겹침·뼈대·메시지 수 검사 시험 1개 추가, SNS 재작성·검사·화면 읽기 시험 4개를 새 규칙으로 고침), 화면 노드 44 passed, ruff·format·node --check·git diff --check 통과.
- 가짜 작성 모델은 이제 양쪽 대사를 새로 쓰고 뼈대 3줄을 낸다. `sns_bad_first`는 원문 사용자 턴을 베껴 겹침 검사에 걸리고 다시 쓴 응답이 들어가는 것을 시험으로 확인했다.
- 실제 재료 실행: D-0134와 같은 후보 파일·조건(AI Hub SNS 40세션 + NIKL 30구간, `serve.py --target 120 --relax-repeat`, 가짜 작성 모델). 쓴 36구간(SNS 29 + 말뭉치 7) 모두 다시 쓰는 방식 `SKELETON`, 원본과 이어서 같은 가장 긴 곳 3글자(기준 10), 막힌 대화 0, 같은 세션이 두 분할에 걸친 경우 0.
- 겹침 검사가 실제 원문에서 잡는 범위: 출처 섞기 뒤 실제 구간 225개(SNS 180 + 말뭉치 45)에서 상대 말 1,281개 가운데 894개(70%)가 정규화 뒤 10글자 이상이다. 옛 방식처럼 상대 말을 그대로 두면 225구간 중 220구간(98%)이 막힌다. 나머지 5구간(SNS)은 상대 말이 모두 10글자 미만이라 베껴도 못 잡는다.
- 밝은(상한 200)·어두운(상한 40) 화면과 어두운 휴대폰 폭(390px)에서 재료 칸 '흐름 뼈대만 쓰고 양쪽 대사를 새로 써요', '원문과 이어서 같은 곳은 가장 길어도 3글자예요(10글자부터 막아요) · 36대화 확인', 뼈대 예시 상자를 봤다. 가로 넘침 없음, 페이지 오류 0. 캡처 `work/training-ui-20261108/shots/*-skel*.png`. 예시 뼈대는 가짜 작성 모델의 고정 문구다.

## 2026-11-08 통화 장면 표기 허용(D-0136)

- 서버 시험 **1258 passed, 1 skipped**(통화 장면 차단 시험을 '통화 장면에서도 ㅋㅋ·ㅠㅠ·^^·이모지 허용' 시험으로 바꿈), 화면 노드 44 passed, ruff·format·git diff --check 통과.
- 같은 실제 재료·조건으로 다시 돌려 36구간(SNS 29 + 말뭉치 7), 흐름 뼈대 재작성, 가장 긴 겹침 3글자, 막힘 0. 밝은(상한 200)·어두운(상한 40) 화면 재료 칸에 '말뭉치 구간은 통화 장면으로 써요. ㅋㅋ·이모지는 문자 장면과 똑같이 써요'가 보였다. 캡처 `work/training-ui-20261108/shots/*-marks*.png`, 페이지 오류 0.
- 실제 작성 모델이 통화 장면에 표기를 어떻게 쓰는지와 음성 합성이 표기를 어떻게 읽는지는 보지 않았다(K-0105).

## 2026-11-08 그림 이모지만 막기(D-0137)

- 서버 시험 **1258 passed, 1 skipped**(표기 시험을 'ㅋㅋ·ㅠㅠ·^^·♥는 통과, 😊·❤️·🎉는 SNS·합성 모두 `no_emoji`로 막힘'으로 바꿈, S8 공통 규칙 참조가 `builtin:actor-system-rules-v4`인지 확인), 화면 노드 44 passed, ruff·format·git diff --check 통과.
- 같은 실제 재료·조건으로 다시 돌려 36구간(SNS 29 + 말뭉치 7), 흐름 뼈대 재작성, 가장 긴 겹침 3글자, 막힘 0. 밝은(상한 200)·어두운(상한 40) 화면 재료 칸에 '말뭉치 구간은 통화 장면으로 써요. ㅋㅋ·ㅠㅠ는 문자 장면과 똑같이 쓰고 그림 이모지는 쓰지 않아요'가 보였다. 캡처 `work/training-ui-20261108/shots/*-emoji*.png`, 페이지 오류 0.
- 실제 작성 모델과 실제 대화 모델이 v4 규칙에서 표기를 어떻게 쓰는지, 음성 합성이 ㅋㅋ를 어떻게 읽는지는 보지 않았다(K-0105).

## 2026-11-08 실제 작성 모델 흐름 뼈대 재작성 4대화(D-0135)

- 조건: 공장 텍스트 덱 basic_test 프로필의 작성 모델 `google-antigravity/gemini-3.8-flash`(OpenCodex 경로, 응답 모델 같음), 인계안은 `gpt-6.1-sol`(scenarios). 캐릭터 권시헌(`cf-20261105-api-cost-argon-v9c`, G6 대기)을 `/tmp/cf-realwrite`로 복사해 복사본에서만 G6를 승인 상태로 두고, 짧은 system의 표기 문장을 v4 문장으로 바꿔 넣었다. 재료는 AI Hub SNS 2구간 + NIKL 2구간(모두 12메시지). 실행 스크립트 `work/training-ui-20261108/real_writer.py`, 비교 화면 `work/training-ui-20261108/real-writer-compare.html`·`shots/real-writer-*.png`.
- 공장 검사에서 4대화 모두 `max_length`로 막혀 검수·수리 단계는 돌지 않았다. 짧은 system이 5,852자(근사 약 3,900토큰)라 대화를 더하면 상한 4,096을 넘는다(K-0106). 4번째는 메시지 수 12→8로 `source_flow_turns`에도 걸렸다. 비교는 작성 모델의 첫 응답(요청 기록)으로 했다.
- 원문 겹침: 가장 긴 겹침 3·3·6·3글자, 10글자 이상 0.
- 흐름(사람이 읽고 판단, 판정자 1명): SNS 2/2는 원문 흐름을 따랐다(통화 끝내기·붙잡기·사과·확인 / 몸 뻐근함·원인 추측·하던 일로 돌아감). 말뭉치 2/2는 원문 흐름을 버리고 인계안 장면 목록의 상황('없던 약속을 사실처럼 말하기', '회사에서 남의 실수를 떠안음')으로 바꿨다. 4번째는 뼈대도 원문이 아니라 새 대화를 요약했다(K-0107).
- 말 길이: 원문 상대/캐릭터 중앙값 14.5~29.5/16~25.5자 → 새 대화 30~48/50~53.5자. 원문보다 2~3배 길고 정돈된 문장이다. 관계는 원문(연인 반말)이 아니라 캐릭터 설정(존댓말, 시헌 씨)을 따랐다.

## 2026-11-08 한소민 구성 반영: 학습용 짧은 프롬프트·흐름 시드·작가 지침·검사기(D-0138)

- 서버 시험 **1262 passed, 1 skipped**(학습용 짧은 프롬프트 조립·관계 배정, 작가 입력에 원문 없음·시드 재사용, 시드 겹침 검사, 한소민 검사 항목 4개 추가, SNS 재작성 시험을 시드 방식으로 고침), 화면 노드 44 passed, ruff·format·git diff --check 통과.
- 실제 모델 재실행: 같은 캐릭터(권시헌, 임시 복사본에서만 G6 승인)·같은 4구간(SNS 2 + 말뭉치 2). 시드 `gpt-6.1-sol` 1회(4구간, 두 작가 같은 시드), 관계·채널 FAVORABLE/문자·STRONGLY_FAVORABLE/문자·NEUTRAL/통화·FAVORABLE/통화. 스크립트 `work/training-ui-20261108/real_writer2.py`, 비교 `real-writer-compare2.html`·`shots/real-writer2-*.png`.
  - Flash(basic_test, OpenCodex): 작성 1회 → 검수(terra) → 판정(sol) → 수리 → 재검수 통과. Argon(demo): OpenCodex Argon 계정 사용량이 없어(429 insufficient_quota, Retry-After 약 5.7일) 공식 API 경로(D-0079)로 돌렸다. 작성 1회 → 검수 → 판정 → 수리 → 재검수 통과.
  - 학습용 system 최대 3,526자(이전 5,852자). 길이 검사 통과.
  - 흐름: Flash 4/4·Argon 4/4가 시드 사건 순서를 따랐다(작업자 1명이 읽고 판단). 이전(원문 직접)은 말뭉치 2/2가 인계안 상황으로 샜다.
  - 캐릭터 말 중앙값: 이전 51~62자 → Flash 22~36자, Argon 18.5~27자. 원문 겹침 최대 Flash 5·Argon 4글자. 메시지 수 모두 12(원문과 같음).
  - 남은 흠: Flash '잘해요'(잘했어요의 뜻)·'숙소는 어디로 잡을까요' 뒤 과거 장소 답(약한 비약), Argon은 시드 문장을 거의 그대로 옮긴 줄이 있다('올해 앞무렵', '보기 드문 풍경이면 한 번 더 불러 주세요').
  - 비용(원장 추정): 인계안·시드 $0.073, Flash 실행 $0.094, Argon 실행(공식 API) $0.291.

## 2026-11-08 학습용 짧은 프롬프트를 평가·서빙에 연결(D-0139)

- 서버 시험 **1265 passed, 1 skipped**(학습 모델 조건이 학습용 프롬프트로 평가되고 실행이 그 system을 그대로 보냄, 옛 데이터셋은 짧은 프롬프트, 서빙 기록에 같은 프롬프트·조립 규칙, 화면 읽기 모델 학습용 프롬프트 요약), 화면 노드 44 passed, ruff·format·node --check·git diff --check 통과.
- 가짜 공급자 흐름(`serve.py --polls 3 --collect-failures 1`, 학습 → 결과 받기 실패 → 다시 받기 → 평가): 사전 등록의 LONG_BASE는 `s8-prompts/pv1/long.md`, 학습 모델 두 조건은 `s10-eval/ev1/prompts/sft-system-ds1-strongly_favorable.md`(1,546자). 밝은·어두운 화면 평가 단계 비교 카드에 '학습 때와 같은 짧은 프롬프트(1,546자 · 아주 가까운 사이 · 영상통화) + 학습한 말투'가 보였다. 캡처 `work/training-ui-20261108/shots/ev/*`, 페이지 오류 0.
- 실제 GPU 어댑터로 평가하거나 실제 서빙으로 어댑터를 부르지는 않았다. 서빙 기록은 시험의 가짜 어댑터 파일로만 만들었다.

### 2026-11-10 — 모티브 V3 원문 재생성·동일 질문 비교 (D-0163)

- 내장 조립 지시 SHA-256: 857d85656fd37e52b5e81029652096528809430b2d6662860c998a3a9b7713f8 (로컬 추천판과 동일). 공장 입력에는 확인된 AI 정체성과 장면을 명시했다.
- 로컬 QA 명령: v3-factory-qa/run generate.py son 또는 friend, 이어 evaluate.py 대상 final, report.py. 두 출처의 S0/G0부터 새로 시작했고 재시도 시 새로 만든 원문 분류만 재사용했다. 원문 비교 세트를 생성에 제공하지 않았다. 공개 사실은 이전에 만든 G0 사실 입력을 사용했다.
- 분류: 인터뷰 등 126개 파일에서 838/838, 카톡 CSV에서 5,318/5,318. 편집·판정 OpenCodex gpt-6.1-sol, 대화 Vertex Gemini 3.8 Flash. 기존 V3 답변과 함께 동일 기준 익명 재채점. 인물별 행동·말투·근거(각 /16): 인터뷰 14·14·13 vs 기존 13·13·12; 카톡 12·8·14 vs 기존 두 판 모두 16·15·16. 사람 블라인드나 운영계 성능 검증은 하지 않았다.
- 전체 합성 테스트: PYTHONPATH=src .venv/bin/python -m pytest -q → 1537 passed, 5 skipped. 원문 기획 지시 변경 후 S3 전용 18개 검사와 실모델 기획·근거 검사도 실행했다.
- 팀 로컬 산출물: v3-factory-qa/비교결과.md, comparison/grades/locked-final, runs/characters/*/s8-prompts. 원문·실제 대사는 저장소에 포함하지 않는다.

## 2026-11-10 — 모티브의 반응 특질 추출 실험(D-0169)

기존 G0·G3·S7을 복사한 로컬 실험 작업공간에서 S8만 실행했다. 발견·편집 OpenCodex gpt-6.1-sol, 별도 검토 Gemini 3.8 Flash. 카톡 마지막 실행은 발견 116/별도 검토 128장면, 후보 2개·채택 0개, 두 묶음에서 확인된 조건부 빈도 차이 0개. 인터뷰는 연속 네 말차례 0개. 조립 입력은 기존판과 동일했다. 사용하지 않은 카톡 네 장면×2턴×2반복을 Gemini 3.8 Flash로 생성해 판 이름을 가리고 원문과 주된 행동을 대조했다. 두 판 모두 각 반복 1/8, 합계 2/16. 로컬 v3-factory-qa/response-lab/{live.py,bench.py,judged.json,특질-검증.md}.

기존 S3 상황 분류에서 기타는 친구 카톡 3,567/5,318개(67.1%), 인터뷰 118/838개(14.1%)였다. 카톡 답 531개에 ‘되묻기’ 표시가 있지만 무엇을 되묻는지는 이 행동명만으로 구분할 수 없다. 이는 기존 분류의 한계이며, 별도로 원문을 읽은 S8 후보가 기각된 유일한 이유로 확인된 것은 아니다.

코드 검사: pytest -q 전체 1,544개 통과·5개 생략·영상 상태 전환(test_light) 1개 실패(기대 failed, 관찰 making). 해당 검사와 새 특질 검사 8개를 함께 다시 돌려 9개 통과했다. 전체 실행에서의 일시 실패 원인은 확인하지 않았다. 특질 관련 ruff 검사와 git diff --check 통과.

## 2026-11-10 — 두 말차례의 관심 대상·대응 (D-0170)

생성용 원문으로 발견·대조 각각 160쌍/인물. OpenCodex 발견 및 기존 V3 조립, Vertex Gemini 3.8 Flash 독립 대조. 카톡 후보 3개 중 1개, 인터뷰 3개 중 2개 채택. 두 인물 모두 원래 조립 입력과 대조해 분석 필드 외 차이 없음 확인. 이전 평가와 다른 장면 각 6개를 Flash(온도 0.8)로 판별 2회씩, 총 48답 생성. 익명 모델 판정: 관심/대응/엄격(각 12개) 카톡 기존 3/2/2 → 실험 4/2/2; 인터뷰 기존 0/2/0 → 실험 2/2/0. 엄격 일치는 두 번 모두 카톡 각 1/6, 인터뷰 각 0/6. 단일 모델 판정이며 사람 식별력이나 배포 효과가 아니다. 로컬 v3-factory-qa/focus-pairs/final_run.py, confirmed-{friend,son}/{locked,observations,judged}.json, 두-말차례-비교.md. 집중 검사 30개 통과. 원문은 저장소에 넣지 않았다.

## 2026-11-11 — 대조 특질을 다음 답을 가린 상태에서 검증 (D-0171)

기존 G0·G3·S7과 V3 조립기 지시를 고정하고 로컬 S8만 실행했다. 생성용 원문에서 160쌍씩 발견했다. 첫 대조 실행은 별도 표본 160쌍, 다음 실행은 동일한 발견 후보를 고정하고 별도 원문 전체(카톡 1,415쌍·인터뷰 427쌍)에서 상대 발화만으로 각 128쌍을 선별했다. 발견·예측은 OpenCodex, 실제 답 판정은 Vertex Gemini 3.8 Flash. 카톡 2후보는 두 갈래 예측이 모두 확보되지 않았다. 인터뷰 1후보는 과장 해석 축소 0/4, 응원에 감사 2/4. 둘 다 채택 0. 비교할 후보가 없다는 것은 인물에게 그 성향이 없다는 의미가 아니다. 자동 검사(진입 경로·개인정보 제외·답 가림·양쪽 근거 및 호출 수 포함) 40개 통과, ruff 및 git diff --check 통과. 팀 로컬 비교 자료: v3-factory-qa/contrast-validation. 예측 재현 근거와 기각 사유는 각 observations.json에 있다.

이전과 같은 실제 장면(인물별 6개×2회)을 고정했다. 대화는 Vertex Gemini 3.8 Flash, 온도 0.8. 기존 V3·직전 focus판의 저장 답변과 이번 대조판 새 답변을 익명으로 섞어 OpenCodex와 Flash가 각각 재채점했다. 두 사람·두 판정자 모두 세 판의 관심 대상과 대응이 모두 일치한 수는 각 2/12(반복마다 1/6)였다. 대조판과 기본 V3는 분석 입력이 같아서 세 번의 채점 결과를 일반적인 성능 추정으로 확대하지 않는다. 보고서: 로컬 v3-factory-qa/contrast-validation/반응-대조-결과.md. 시간 초과로 누락된 카톡 답 하나는 같은 모델·설정의 비스트리밍 응답으로 복구했다.

## 2026-11-11 — 원문 기반 페르소나 설계 자문

개인 카톡 원문을 제외한 인계 문서를 Claude CLI(도구 비활성, 세션 비저장)에 입력했다. 모델 claude-fable-5-2, effort high 요청, 응답 메타데이터에서 해당 모델과 success 확인. [회신 원문](../research/2026-11-11-persona-oneclick-fable-review.md). V3 예시 입력이 직전 상대 말과 대상 답을 묶는지 코드에서 확인했다. 실험안의 품질·비용은 미측정이다.

## 2026-11-11 — 예시 주입 방식 비교 (D-0172 제안)

공장 V3 프롬프트(카톡·인터뷰 각 1개)를 기준으로 예시 넣는 방식만 바꾼 판을 코드로 만들었다(원문 분석 호출 없음). 평가 장면은 생성에 쓰지 않은 대화에서 고정 시드로 뽑은 카톡 40개·인터뷰 30개이고 이전 진단 장면을 뺐다. Vertex Gemini 3.8 Flash(온도 0.8, thinking low)로 장면마다 1회, 카톡 8개 판·인터뷰 9개 판, 합계 590답. 익명 맞대결 채점은 gpt-6.1-sol과 Claude Fable 5.2 각 106묶음(6건씩), 근거 없는 주장 판정은 gpt-6.1-sol 29묶음. 결과 수치와 한계는 [인계](handoffs/handoff-2026-11-11-example-turns.md)에 있다. 두 채점자의 판정 일치는 카톡 반응 78%·말투 71%, 인터뷰 반응 86%·말투 71%였다. 로컬 v3-factory-qa/scene-examples/{exp.py,exp2.py,exp3.py,report.py,예시-비교-결과.md}. 저장소 코드는 바꾸지 않았다.

## 2026-11-11 — 이전 턴 선택 기능(D-0173)과 팬 통화 대본 비교

손흥민 팬 통화 대본 8개 × 2회를 V27과 이전 턴 판 세 묶음으로 실행했다(판마다 74턴, 합계 296턴, Vertex Gemini 3.8 Flash). 익명 통화 맞대결은 묶음마다 16쌍을 gpt-6.1-sol과 Claude Fable 5.2가 각각 채점했고(2쌍씩 8묶음 × 3 × 2), 근거 없는 주장은 통화마다 gpt-6.1-sol 1회(64회), 본인 사칭 판정 3회. 수치는 [인계](handoffs/handoff-2026-11-11-example-turns-option.md)에 있다. 세 번째 묶음은 공장 코드(stages/s8_prompts/example_turns.py)가 실제 생성용 원문에서 만든 것이다.

코드 검사: .venv/bin/python -m pytest -q → 1564 passed, 5 skipped. 새 검사는 뽑는 규칙(출처별 순환, 길이 제한, 개인정보·제3자·시간 공백 제외, 시드 재현), S8이 켰을 때만 파일을 남기는지, 대화 요청이 문답을 이전 턴으로 보내는지와 파일이 비면 기존 경로로 돌아가는지를 본다. 바꾼 파일의 ruff check 통과. 실제 공장 실행(S8 --execute)으로는 돌리지 않았다.

## 2026-11-11 — 팬 통화: 고정 장면 틀·자동 말버릇 정의 (채점 일부 미완)

손흥민 팬 통화 대본 16개 × 2회를 9개 판으로 생성했다(Vertex Gemini 3.8 Flash, 합계 1,173턴). 맞대결·근거 없는 주장·본인 사칭 채점은 로컬 opencodex의 gpt-6-astra(fast 모델 ID, 로그에서 우선 처리 적용 확인)와 gpt-6.1-sol로 했다. 앞의 다섯 후보 판은 144쌍씩 두 채점자 모두 끝났다. 뒤의 세 판은 주 계정 사용량 잠금(HTTP 429)으로 멈췄다. 수치와 채점 수는 [인계](handoffs/handoff-2026-11-11-scene-template.md)와 로컬 v3-factory-qa/scene-examples/장면틀-비교.md에 있다. 저장소 코드는 바꾸지 않았다.

## 2026-11-11 팬 통화 비교 최종 판정 (K-0115)

자동 말버릇을 넣은 판은 V27과의 32쌍 비교에서 통화 적합성은 앞섰지만(Astra 24승 5패 3무, sol 25승 4패 3무), 인물다움은 사전 기준인 두 채점자 각각 승 ≥ 패에 미달했다(Astra 15승 17패, sol 13승 19패). 본인이라고 단정한 답은 0/4건이었다(V27 4/4건). 주어진 자료에 근거가 없는 개인 사실을 단정한 답은 43/138건이었다(V27 48/138건). 응답 시간 중앙값은 2.6초였다(V27 3.1초). 기존 생성물을 그대로 사용했다. 총 272개 통화, 1,173턴의 근거 판정과 두 모델 각각 240쌍의 비교 결과를 대조했다.

- 2026-11-11 · 네 말차례 후속 반응: scripts/evidence_workflow/test_followup.py 2건 통과. 실제 S0에서 앞 세 턴과 네 번째 실제 반응을 분리한 1,946개 창의 ID·문맥을 대조했다. 개인별 분기는 반복 기준 미달로 미승인. [인계](handoffs/handoff-2026-11-11-followup-evidence.md).

## 2026-11-11 원문 근거 표준 공장 연결(D-0174)

- 명령: `.venv/bin/python -m pytest tests/test_evidence_pipeline.py tests/test_evidence_source.py tests/test_evidence_compiler.py tests/test_evidence_export.py tests/test_web_evidence_review.py tests/test_oc2_flow.py tests/test_twin_persona.py tests/test_motif_facts.py tests/test_twin_export.py tests/test_twin_presentation_check.py tests/test_v_make.py tests/test_chapter_start.py tests/test_demo_chat.py tests/test_persona_compiler.py tests/test_rework.py tests/test_web_auto_resume.py tests/test_agentic.py -k 'not test_real_layout' -q --tb=short`
- 결과: 231 passed, 3 skipped, 1 deselected, 46 subtests passed (17.76초). 합성 원문과 fake provider만 사용. 실제 로컬 원문을 읽는 test_real_layout 제외.
- 원문·사실·장면·검토·본문 변경 차단, 예시 설정 거부, 중단 후 후보 재사용, G6 명시 확인, 새 S8에 S8c 재생성, S11→chat-svc 8섹션 일치 확인. 원문은 공개 산출물에 복사되지 않음.
- 변경 코드 Ruff, `node --check src/character_factory_poc/web/static/shared/gate.js` 통과.
- 보존한 합성 증거: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-pipeline-proof/`.
- 실제 새 자동 추출 품질·배포·실제 음성/영상 품질은 이번 검사 범위가 아님.

- 최종 보완 검사: 작은따옴표 예시 차단·사실표 고유명사 따옴표 보존, 대상 통화 장면이 원문 형식보다 우선, 인물별 장면 분리, 낡은 S8 자동 재사용 차단까지 포함한 최종 결과 231 passed. G6 화면은 합성 자료로 1280px/390px 브라우저 확인했고, 후속 맥락 표시·확인란은 추가 동작 테스트로 확인했다.


## 2026-11-11 원문 근거 공정 실제 실행 (n8n 없음)

입력은 승인 sp1/pr4/tr1의 격리 사본, 모델은 google/gemini-3.8-flash다. `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-live/run.py --execute`로 실제 S8 생성 1회, `evaluate.py --execute`와 실패 한 건 재시도로 비교 응답 8개를 생성했다. 총 10시도 중 성공 9·180초 timeout 1이다. 호출 예산 16회/$2, 실패 예약 포함 가정 단가 합계 약 $0.126(실제 청구액 아님).

`/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-live/verify.py` 통과: 원본 3개 해시 보존, 새 pv2 manifest 오류 0, 현재 입력 결속, 사실표 보존, 예시 대화 파일 없음, G6 AWAITING_HUMAN, 일반 시연 차단. 내부 review_preview로만 응답 생성했다. 원문 15개와 생성 응답 8개는 Codex가 직접 읽었다. 새 자동 추출은 과잉 일반화·rule 한계 누락 때문에 품질 승인하지 않았다. 기존 표준판도 한 장면에 근거 없는 졸업 추정이 있어 정답 기준으로 취급하지 않았다. 평가 자료 네 장면은 재사용 회귀 자료이며 새로운 일반화 검증이 아니다.

결과: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/공정_실행검증/실행검증_보고서.md`, `실행검증_기록.json`. 재현 명령·원시 기록은 `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-live`에 있고 비공개 원문을 저장소 테스트 자료에 넣지 않았다. 이번 턴은 실행·검토와 문서 정정이며 공정 코드를 추가 수정하지 않았다. 앞선 231개 오프라인 테스트 결과와 이번 실제 실행을 구별한다.


## 2026-11-11 전체 원문 공정 구현·실행·Gemini 비교(D-0176)

- 입력: 기존 승인 sp1/pr4/tr1의 격리 사본. 생성용 10,254개 중 허용 10,180개, 제외 74개(사유와 ID 보존), 평가용 1,651개는 저작 입력에서 분리. 32묶음, 184관찰, 10후보×32묶음=320대조. 기계적 통과 9·보류 1이며 의미 승인 아님.
- 실제 실행: `.venv/bin/python /Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-full-live/run.py --execute`, 같은 명령으로 미완료 한 건 재개. 실제 공장 run_s8/Vertex google/gemini-3.8-flash를 호출했다. pv4, 8섹션 2,790자, 조건 5항목 보존, 예시 없음, G6 AWAITING_HUMAN. 앞 단계 재생성·서비스 배포는 하지 않았다.
- 검증: `.venv/bin/python /Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-full-live/verify.py`와 `integrity.json`. 원본 해시·새 manifest·현재 결속·전체 포함/제외 분할·사실·조건·일반 시연 차단·내부 미리보기 본문 일치 확인.
- 비교: `.venv/bin/python /Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-full-live/evaluate.py --execute`. 사전 고정 12장면(재사용 4·추가 실제 4·진단 4), 후속 3개×2판=30응답. 두 판 같은 Gemini 온도0.8/low, 원답 미제공. Codex 직접 읽기 결과 `evaluation/direct-blind-review.json`. A/B 판정 저장 후 키 확인이나 평가자는 두 프롬프트를 알고 있어 독립 사람 블라인드 아님. 새 판 대체 권고 없음. 두 판의 미확인 과거 창작 실패 확인.
- 원문 검토: 채택 후보 9개마다 서로 다른 unit 지지 2개씩, 보류 후보의 반례와 추가 지지를 직접 읽었다. 부분 지지의 과잉 인정·저축/소비 혼동이 남았다(K-0116).
- 총 96시도=분석 성공65+비교 성공30+180초 timeout1. 실패 예약 유지. 가정 단가 합계 $3.05047, 청구액 미확인. 보완 전 시작한 중단 캐시64개의 원본을 `cache-before-canonical-fix`에 보존하고 요청 키 순서만 정규화했다(`cache-migration.json`). 모델 응답 불변과 원천 결속 확인 후 미완료 한 건만 재호출.
- 오프라인 전체 회귀: `.venv/bin/python -m pytest -q` → 1743 passed, 5 skipped, 46 subtests passed(188.42초), `/tmp/cf-full-suite-final2.log`. 새 검사는 합성 자료·가짜 공급자로 전체 범위/경계·조건 보존·반례 보류·중단 재개·수정 지시·USER-only 복사·v1/v2 승인/패키지/내보내기를 확인한다. 변경 코드 Ruff, `git diff --check` 통과.
- 결과: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/전체원문_공정_검증/결과_보고서.md`, `Gemini_30응답_직접비교.md`, `오익준_전체원문판_미승인.md`, `실행_검증기록.json`.


## 2026-11-11 원자 특징·독립 확인 공정(D-0177)

- 코드: evidence_atomic.py, evidence-pipeline-v3.md, 기존 S8/시연/패키지/내보내기 v3 연결. 실제 익준 검증 실패로 기본은 v2 유지, v3는 명시 설정이다.
- 실제 실행: `.venv/bin/python /Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-atomic-live/run.py --execute`와 동일 명령으로 미완료 요청 재개. 생성용 허용 10,180메시지, 개발 121unit/27묶음, 확인 40unit/25묶음, 관찰191→후보12→첫대조324/재대조324/확인300. 결과 pv5 CHECK_FAILED,12HELD,정식 long/prompt-pair 없음.
- 실제 결과 검증: `.venv/bin/python /Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-atomic-live/verify_held.py` 및 integrity.json. 원본 해시·원천 결속·분석 산출물 해시·전체 범위·단위 분리·확인 전 후보 잠금·일반시연 차단 통과. 진단판의 사실/조건/예시 부재 확인.
- 진단: diagnostic.py로 보류 후보 12개를 별도 8섹션 3,625자에 조립했다. 이 파일은 공정 통과물이 아니다. baseline.py와 evaluate.py --execute로 동일한 Gemini 3.8 Flash/0.8/low 30응답. 기존 회귀 질문 재사용, 원답 미제공, Codex 직접 평가. 자료는 evaluation/direct-blind-review.json, direct-review.json, initial-source-review.json, final-source-review.json.
- 155요청: 유효 분석108+비교30+형식 탈락 응답9+미확정 예약8(시간초과5,중단 당시3). 상한200회/$20, 가정 단가 합계 $7.068622, 실제 청구 미확인. 초기 무결성 보완 전 캐시53개는 pre-receipt-checkpoint에 원본 보존 후 checkpoint-migration.json에 해시 기록; 출력 변경 없음. 마지막 지연 요청 후 transport timeout만180→300초로 연장했다.
- `.venv/bin/pytest -q` → 1759 passed, 5 skipped, 46 subtests passed,104.04초(`/tmp/cf-atomic-final6-suite.log`). 합성 자료로 v1/v2/v3 실제 단계→승인→패키지→서비스 트리 통합 확인. 실제 서비스 배포/내보내기·음성/영상 미실행. 변경 코드 Ruff와 git diff --check 확인.
- 결과: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/원자특징_표준화_검증/결과_보고서.md`, `Gemini_30응답_직접비교.md`, `오익준_보류후보_진단용.md`, `실행_검증기록.json`.


## 2026-11-11 조건부 기능·말투 공정과 실제 Gemini 비교(D-0178)

- 수정 전 회귀 검사: `tests/test_evidence_tendencies.py` 5실패, compiler 변경 시 불변 revision 충돌 1실패, v4 내보내기 표식 1실패, 오류 인용 격리 누락 1실패를 각각 확인하고 보완했다. 로그는 /Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-tendency-live에 있다.
- `.venv/bin/python -m pytest -q`: 최종 1,768 passed·5 skipped·46 subtests passed, 92.30초. 기존 경고3개. `tests-complete.log`. 새 버전 S8→G6→시연과 합성 공개 패키지→서비스 변환에서 본문 보존을 포함한다.
- 변경 코드/테스트 ruff 검사와 `git diff --check` 통과. 기존 unrelated 변경은 보존했다.
- 실제 실행 `run.py --execute`: 생성용10,254 중10,180메시지,32원문묶음/157단위/2,393응답. 발견27·통합1·개발대조27·확인25의 유효분석80개. 첫 실행은 잘못된 조건 인용으로 CHECK_FAILED; 오류 격리 보완 후 같은 공유 예산과 성공 캐시로 재개했다. 분석 호출91(정상 분석80·별도 거절응답11). 모두 원본 기록 보존.
- `inspect_result.py`: pv6 12 mixed카드,8섹션,5,178자. 사실표 동일, 모든 조건/한계 보존, 예시 artifact 없음, 시연 본문은 종단 줄바꿈 제외 동일, 원천 해시 동일. 잘못된 인용59건을 집계에서 제외했다.
- `evaluate.py --execute`: Gemini google/gemini-3.8-flash,0.8,low,15장면48응답. 사례·기준·프롬프트 고정, 실제 이전 응답을 이어받는 꼬리질문. `direct-review-blind.json` 판독 고정 후 key를 공개해 새3·기존1·차이불명확11. 사람 평가가 아니다.
- 공유 예산139회/180회, 가정 단가 기준약$7.68/$15,139건 모두 SETTLED. 최초 분석 계획90회보다 재개 과정에서1회 더 썼으나 전체 상한은 유지했다. 실제 청구 확인값은 아니다.
- G6는 AWAITING_HUMAN. 실제 승인·배포·음성영상·commit/push 없음. 새 모델 경로를 전역 기본으로 승격하지 않았다. 결과: /Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/조건부말투_공정_Gemini_비교/결과_보고서.md.


## 2026-11-11 — D-0179 사용 조건 추출 표준

- 전체 pytest: 1,785 passed·5 skipped·46 subtests passed·3기존 warnings (141.65초). 변경12개 Python 파일 ruff 및 git diff --check 통과. /tmp/usage-all-verified.log.
- 실제 native S8 pv7·624후보/묶음 대조·11카드·8섹션·5,046자. 사실/역할/장면 동일, 원천해시와 조건보존, 예시없음 검증. G6 미승인.
- Gemini 96최종응답(2가드 거절 추가) 직접 A/B판독30쌍: 기존pv6 12·pv7 4·차이불명확14. 재사용회귀이며 독립합격아님. 원문30개 직접 읽어 의미오독 잔존 확인.
- 181호출 미확정0, 가정비용$7.405498. 모델답변 형식 오류/검증기 오류는 저장캐시로 복구했고 원장상한 유지. 초기실패1건 원문미보관 한계 명시.
- 사용자 결과: /Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/오익준_조건추출_공정_pv7_비교
- 상세 인계: [사용 조건](handoffs/handoff-2026-11-11-register-conditions.md).


## 2026-11-11 — D-0180 pv6 현행 표준

- `.venv/bin/pytest -q tests/test_evidence_usage.py tests/test_evidence_tendencies.py tests/test_evidence_pipeline.py tests/test_evidence_full_pipeline.py tests/test_evidence_export.py tests/test_oc2_flow.py`: 89 passed·3기존 warnings, /tmp/pv6-standard-tests.log. 처음에는 v5를 기본값으로 가정한 테스트1건이 실패했고 명시적 v5 경로로 변경하여 실험 재현 검증을 유지했다. 기본 무설정 경로는 v4이며 전체 흐름 검사로 검증했다.
- 변경 Python파일 ruff / git diff --check 통과.
- 로컬 ReviewScene.compose가 비교 기준 pv6와 정확히 같고 예시 메시지0개·슬랭 오버레이 없음 확인. HTTP chat/meta: 익준pv6 ready, 손흥민pv2 ready. 기존 서버 정상 종료 대기가 끝나지 않아 확인된 해당 로컬 프로세스만 종료하고 새 프로세스로 복구했다.
- 사용자 결과: /Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/현행_표준_pv6


## D-0181 프론트 생성 공정·대화 기록 (2026-11-11)

최종 전체 Python: **1,897 passed, 5 skipped, 46 subtests passed**, 기존 경고3개. 프론트 Node: **154 passed**. Ruff/diff 검사 통과. 중간에 chapterTemplate을 그래프 공용 메타데이터에 넣어 기존 계약 검사4개가 실패했으며, 캐릭터 요약/상세에만 전달하도록 고친 뒤 전체 재검사를 통과했다.

실제 Foundry UI로 합성 친구·인터뷰 각 288메시지 입력→생성용224/보류64→evidence-v4 무예시8섹션→표본12턴→원문 검토 기록→5/5→Gemini채팅을 완료했다. 새대화 후 이전 기록 선택, 서버 재시작 후 새탭 복원을 확인했다. 기존1269파일 SHA 변경0/누락0. 영상 렌더링은 실제 호출하지 않았으며 G6 대기/재개는 합성 검사로 검증했다. 자세한 범위는 D-0181 인계 참고.


### 2026-11-12 옛 워크숍 진입 제거

`pytest -q tests/test_current_factory_entry.py tests/test_web_history.py tests/test_web_gates.py tests/test_web_text_pipeline.py`: 64 passed. `pytest -q tests/test_trait_authoring.py`: 15 passed. `node --test studio/tests/gate.test.cjs`: 5 passed. 새 진입 테스트는 수정 전 3 failed를 확인했다. 기존 경고3개. 8776 기본 주소에서 현재 Foundry와 캐릭터6명 표시 확인. 공장 기존파일2,101개 변경0, 보호백업298개 변경0. 서버 재시작·생성 호출·배포 없음. 이전 중단 작업 검증은 재개하지 않았다.


### 2026-11-12 현재 공장 진입 PR 검증

중단된 공정 변경을 제외한 staged tree를 별도 폴더로 내보내 검증했다. 최종 `python -m pytest -q`: 1,963 passed, 6 skipped, 3 warnings, 46 subtests passed (165.62초). `node --test studio/tests/*.test.cjs`: 177 passed. 변경 Python 파일 ruff와 staged diff 검사 통과. 최초 전체 검사에서 옛 워크숍 경로를 기대한 test_studio_integration 2건이 실패했고, 현재 화면을 기대하도록 수정 후 전체 재검사를 통과했다.

리뷰에서 wheel 설치에 studio 자산이 빠지는 회귀를 확인하여 setuptools data-files와 설치 prefix 탐색을 추가했다. `uv build --wheel` 후 별도 가상환경에 설치하고 소스 체크아웃 밖에서 공장·채팅·검토 HTML과 공장 JS/CSS를 HTTP 200으로 확인했다. 패키지에는 실행용 studio 자산57개를 포함하며 tests/plans/recordings는 넣지 않는다. 기존 작업 폴더와 서버·채팅·pv6는 그대로 보존한다.

## 2026-11-12 — 720p 시작·끝 프레임 기본값

[인계의 명령·입력·결과](handoffs/handoff-2026-11-12-video720-default.md). 오프라인 128+33=161 passed. 변경 Python ruff·diff 검사 통과. `work/video720-frame-test/run.py --execute`: 합성 두 사진, 2초×2편, 공장 OAuth, 각각 720×1280·24fps·49프레임. 동일 첫/끝 및 서로 다른 첫/끝 직접 연락판 확인. 추정 $0.60이며 청구액 확인은 아님. 기존 2,101파일 해시 변화·누락 없음. 실인물 품질·프론트 전체 실행·배포 검증은 하지 않음.

## 2026-11-12 — 720p 두 편 동시 생성

`work/video720-parallel-test/run.py --execute`: 동일 합성 사진·프롬프트, 공장 OAuth·1.5·720p·2초·동시 2건. 2/2 완료, 720×1280·24fps·49장, 전체 37.40초, 추정 $0.60. 출력은 작업 폴더와 사용자 `outputs/video720-parallel-test/`에 저장. [방법·한계·현행 순차 구조](handoffs/handoff-2026-11-12-video-parallel-check.md). 기능 코드 수정과 공장 전체 병렬 실행 검증은 하지 않았다.

## 2026-11-12 — 영상 6건 동시 요청

`work/video720-parallel6-test/run.py --execute`: 공장 OAuth·1.5·720p·2초·동시 6건. HTTP 200 5건/429 1건, 성공 5편 디코딩 완료, 전체 38.56초, 추정 $1.50. 상세 제한 원인은 미확정(K-0122). [입력·결과·한계](handoffs/handoff-2026-11-12-video-parallel6-check.md). 공장 기능 코드와 서버 변경 없음.

## 2026-11-12 — 1초 간격 영상 6건

`work/video720-stagger6-test/run.py --execute`: 직전과 동일한 입력·모델, POST 간격 1.0001~1.0038초, 6/6 접수·다운로드·디코딩 성공. 전체 41.61초, HTTP 429 없음, 720×1280·24fps·49장, 추정 $1.80. 기존 2,101파일 해시 변화 없음. [방법·산출물·한계](handoffs/handoff-2026-11-12-video-stagger6-check.md). 기능 코드·서버 변경 없음.

## 2026-11-12 — D-0190 공장 영상·프롬프트 병렬 적용

전체 `.venv/bin/pytest -q`: 2,204 passed, 6 skipped, 3 warnings, 46 subtests passed (118.67초). 실행본 별도 src 검사63 passed. 변경 파일 ruff·diff 검사 통과, 전체 lint에는 기존/중단 영역 E501 6건이 남아 있다. 실제 S6 `work/video-factory-parallel-live/run.py --execute`: 720p·2초6편, 6/6 HTTP200, 39.62초, 제출 간격1.0002~1.0068초, 추정$1.80, G5b 사람검토대기. 8776 현재화면3개 HTTP200·maxParallel3·pv6/pv2 ready 확인. 기존2,101파일 변화0. 프론트 두 분기 중첩은 합성 API 검사로 확인했으며 전체 실제 LLM+영상 동시 생성은 별도 미실행. [범위·실행본·산출물](handoffs/handoff-2026-11-12-factory-parallel.md).


## 2026-11-12 — D-0191 idle 포함 통화 영상 표준

전체 `.venv/bin/pytest -q`: **2,217 passed, 6 skipped, 3 warnings, 46 subtests passed**, 120.94초. 활성 프론트178 passed(중단 quality-status 테스트 제외). 실제 실행본 src 지정 검사23 passed. 신규 call-loop 검사13 passed. 변경 범위 ruff·git diff --check 통과. 실제 모델 호출은0회다. 원본 캐시의 재개/비재개 공급자 재제출 방지, 불완전 저장 차단, 실제 합성 오디오 제거, 정지·복귀 실패 영상 보류, 시그니처만 수정시1회 생성, 중간 시점/사진해시 변경을 검사했다. 현재 서버37952에서 화면3개 HTTP200·pv6/pv2 ready, 기존2,101파일 변경0. [범위와 산출물](handoffs/handoff-2026-11-12-call-loop-standard.md).


## 2026-11-12 D-0192 기준 사진 확인 공정

- `.venv/bin/pytest -q`: 2238 passed,6 skipped,3 warnings,46 subtests; `/tmp/reference-full-final.log`.
- `node --test` 활성 `studio/tests/*.test.cjs`(중단한 quality-status 제외):191 passed, `/tmp/reference-node-final.log`.
- `.venv/bin/pytest -o pythonpath=work/reference-first-runtime/src tests/test_reference_frontend_flow.py tests/test_reference_master.py tests/test_reference_master_scheduler.py tests/test_call_loop.py -q`:34 passed, `/tmp/reference-runtime-final.log`.
- CUA+독립fake Python8787: 원문/사진 접수한 초안 시작→기준사진표시→확인→영상완료표시, clips.json6개. frontend 단위13개는 revision/hash·409·중복·읽기실패·재개버튼을 검증. 실인물/유료 생성 없음.
- 8776 sources/factory/chat·새정적파일200, 익준pv6/손흥민pv2 readytrue. 보존 manifest2,101항목 변경/누락0.
- 변경 Ruff 및 git diff --check 통과. 결과/사진/로그: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/reference-first-20261112`.

## 2026-11-12 — D-0193 공식 OpenAI API 연결

- 오프라인: `.venv/bin/pytest tests/test_openai_images.py tests/test_twin_precheck.py tests/test_reference_master.py tests/test_reference_master_scheduler.py tests/test_reference_frontend_flow.py tests/test_openai_dialect.py tests/test_codex_image.py tests/test_testpath_seeds.py -q` → 89 passed.
- 실행본: `.venv/bin/pytest -o pythonpath=work/openai-direct-runtime/src tests/test_openai_images.py tests/test_reference_master.py tests/test_openai_dialect.py -q` → 53 passed. 변경 공급자 파일 Ruff 통과.
- 실제: `work/openai-direct-20261112/smoke.py --execute`, 설정은 실행본과 동일한 Provider/Context 포트, 별도 합성 루트에 저장. 공식 모델 목록200, JUDGE4.50초·VISION5.95초·IMAGE18.46초 성공(720×1280 PNG). `smoke-result.json`, `access-check.json`, `smoke-factory/.../ledger/calls.jsonl`을 확인했다. 합성 검사만 했으므로 손흥민 품질 향상으로 해석하지 않는다.
- API 거절/손상 PNG/참조 파일 전달/비용 미확인·명시적 추정값에 따른 사전 확인을 가짜 HTTP와 합성 자료로 검사했다. 최초 검토의 사전 확인 차단·PNG 헤더만 통과 문제는 실패 재현 뒤 수정했다.
- 서버: 8776 PID75055, health configPath=openai-direct-runtime/factory-web.toml, 프론트200, 기존 채팅 메타 pv6/pv2 ready=true. 모든 기존 runs 파일2,423개 해시 변경0. `work/openai-direct-20261112/preservation.json`, `health.json`.

## 2026-11-12 — D-0194 시그니처 참고 사진

- `.venv/bin/pytest tests/test_signature_photo.py tests/test_source_intake.py tests/test_reference_frontend_flow.py tests/test_call_loop.py -q` → 49 passed. 신규8건은 업로드/제거/재접속/인물사진 분리/손상사진/해시변조/S3 사본/등급제한/업로드중 등급변경을 검사한다. 합성 end-to-end는 G4 확인 전 대기 후 영상6개 제출 중 한 개만 2초 keyframe을 받고 모두 같은 시작/끝 사진을 쓰는지 확인했다.
- `node --test studio/tests/signature-photo.test.cjs studio/tests/sources.test.cjs studio/tests/reference.test.cjs` → 70 passed. 신규9건, 기존 화면/기준사진 회귀 포함.
- `.venv/bin/pytest -o pythonpath=work/signature-photo-runtime/src tests/test_signature_photo.py -q` → 8 passed. 변경 Python Ruff와 git diff --check 통과.
- 별도 합성 서버8787에서 CUA 파일 선택→준비됨→새로고침→미리보기 실제 이미지 디코딩 성공을 확인했다. 인물사진 칸은 빈 상태로 남았고 시작은 막혔다. 화면 `work/signature-photo-20261112/ui-preview.png`, 입력은 단색 합성 PNG. 유료 호출0.
- 독립 검토: pending 시그니처 업로드 중 다른 등급 변경 경합1건을 재현 후 차단했고 재검토에서 남은 high/medium 없음.
- 8776 실행본 `work/signature-photo-runtime`, PID77141. 실제 HTML에 업로드 컨트롤, OpenAPI에 photoRole, health에 새 configPath를 확인했다. 기존2,420파일 변경0·익준pv6/손흥민pv2 chatReady 유지. `work/signature-photo-20261112/deployment.json`.
- 재시작 중 기존 서버가 연결 종료를 기다려 새 리스너 시작을 멈췄다. 실행 중 작업이 없고 기존 PID/명령을 확인해 종료한 뒤 복구했다. 임시 검증 서버는 종료했다.

## 2026-11-12 — D-0195 시그니처 중간 프레임 시드

- `tests/test_signature_photo.py` 8건을 새 흐름으로 고친 뒤 실패를 먼저 확인하고 구현했다. 이미지 요청2회(두 번째는 기준 사진+참고 사진), 시드 해시 없이/틀린 해시로 승인 409, 승인 후 시그니처 영상에만 시드가 2초 keyframe으로 들어가고 원본 해시와 다름, 참고 사진 없으면 1회·기존 승인 계약 유지, 기준 사진 흐름 밖 업로드 409.
- 관련 Python 244 passed(시그니처·영상·기준 사진·twin·S4 계열 20파일). Node 72 passed(reference·signature-photo·sources).
- 정적 미리보기로 두 이미지 확인 카드 렌더링 확인: `work/signature-photo-20261112/two-image-card.png`.
- 8776 실행본 `work/signature-seed-runtime` PID81089, OpenAPI ConfirmReference에 signatureSha256. 기존2,420파일 변경0, 익준pv6/손흥민pv2 ready. `work/signature-seed-20261112/deployment.json`. 유료 호출0.

## 2026-11-12 — 손흥민 시그니처 시드 실제 정식 시연

- cf-20261112-motif-94aba10c14124ca2: 원문126+인물사진+찰칵 참고 사진, Lite·INTERVIEW. 14:02 시작→14:19 대화 가능. S4 이미지2장(실제 gpt-image-2.6-sunburst), S6 6/6(grok_oauth), S8 pv1(Gemini 64회). G4·G6는 사용자 지시로 에이전트가 검토 후 화면 승인.
- 시그니처 영상만 시드 keyframe(해시 bb8ff6a7c750 일치), 사각 손 프레임 재현. 인사 과다 숙임 재현. 채팅6문항 직접 판독. 결과·영상·시트: /Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/son-signature-live-20261112. 상세는 handoff-2026-11-12-son-signature-live.md.

## 2026-11-12 — Opus 현행 사용성 QA

- 모델 `anthropic/claude-opus-5-5`, 독립 서브 에이전트. 8776 signature-seed-runtime를 기준으로 Chrome CUA 읽기 전용 검토. 새 제작폼·G6 승인시트·승인대기/완료진행·채팅가능/불가·390×844 모바일 에뮬레이션·키보드 진입을 관측했다. 현재 캡처18장, `work/usability-opus-20261112/01-...18-...png`.
- 부모가 GET health/캐릭터 상태/참조사진 상태를 확인해 `runtime-observation.json`, `selected-states.json`에 저장했다. 실제 화면 캡처01·09·15를 직접 확인했다. 보고서의 모든 초기 항목이 필수라는 표현, 영상자동전환 과거인계 근거, 사진수 혼동을 정정했다. 언어학적 설명·최종프롬프트·생성/품질상태 보존 경계를 추가했다.
- 보고서 `docs/reports/2026-11-12-usability-opus.md`. 전문가 사용성 리뷰이며 실사용자 성공률/전체 기능 통과/접근성 인증을 측정하지 않았다. 코드 수정·유료호출·승인·채팅전송·서버재시작 없음.

### 2026-11-12 장면별 기준 페르소나 공정 (D-0197)

작업 트리의 Python 전체 테스트 2,278개 통과, 6개 건너뜀(하위 검사 46개 통과). 로컬 적용본의 페르소나·장면·검토·기록·내보내기 검사 114개 통과(하위 검사 46개 통과). 합성 문답에서 분류 입력에 답이 없고, 근거 변조 시 G6 승인이 거절되며, 승인 뒤 채팅이 같은 프롬프트를 사용하는 것을 확인했다. 8776 입력 화면 HTTP 200, 두 장면의 S8 분기, 기존 대화 프롬프트 해시와 영상 응답, 설정 파일과 기존 산출물 3,243개의 동일성을 재확인했다. 실제 모델 호출·인물 유사도 비교·시간 재측정은 수행하지 않았다. [인계](handoffs/handoff-2026-11-12-interview-v2-factory.md)

## 2026-11-13 — D-0208 Railway 시연 서버

- 로컬: 같은 묶음으로 `docker build -f deploy/railway/Dockerfile` 성공. 이미지 안 /opt/chat-svc 컴파일러가 기존 캐릭터(481c1c0e…) 버전5·챕터20을 문제0으로 컴파일, `/api/health` 200. 서버 설정으로 공급자 11개(text·judge·dialogue·demo_chat·planner·analyzer·labeler·vision·image·signature_image·video)가 모두 만들어짐.
- Railway: `deploy/railway/deploy.sh`(공장 273bd2c·chat-svc 864e02b6) 빌드·배포 완료. 공개 주소 `/api/health` 200(root /data/factory, configPath /app/deploy/factory.railway.toml), 첫 화면 200. `railway ssh` 로 서버 안에서 chat-svc 컴파일 같은 결과, dev 넣기 서비스 `GET /api/v1/factory-import/state` 200(토큰 통과).
- 미검증: 서버에서 실제 캐릭터 생성(유료 호출), 테스터 발행 한 번, 담이 계정 통화 확인, 실제 Fish 음성.
