# 인계 2026-11-13 — Railway 시연 서버 (D-0208)

## 한 일

- 공장 웹앱을 Railway 프로젝트 persona-foundry / 서비스 factory 로 띄웠다: https://factory-production-eff53ef8.up.railway.app
- 파일: `deploy/railway/Dockerfile`, `deploy/railway/deploy.sh`, `deploy/factory.railway.toml`, `railway.json`, `.dockerignore` 허용 목록.
- Railway 서비스 변수: OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY, XAI_API_KEY, FACTORY_IMPORT_TOKEN, FACTORY_IMPORT_BASE_URL, CFP_DISCORD_WEBHOOK_URL, PORT=8080, RAILWAY_DOCKERFILE_PATH. 볼륨 /data.
- 이 저장소 작업 폴더(import-publish)에 `railway link` 가 되어 있다. 다시 올리기: 깨끗한 상태에서 `./deploy/railway/deploy.sh`.
- 서버 안 명령: `railway ssh -- cfp --root /data/factory ...`(SSH 키 codex-mac 등록함). 시작할 때 `/data/factory/factory.toml` 을 서버 설정에 잇는다. 예: `railway ssh -- cfp --root /data/factory preview remove <id>`.

## 확인한 것

[검증 기록](../verification.md) 2026-11-13 D-0208 항목.

## 다음 할 일

1. 서버 화면에서 캐릭터 한 명을 시연 모드로 만들어 테스터 발행까지 간다.
2. 담이(회원 180) 계정으로 앱 목록·통화·영상·음성을 확인한다.
3. 시연 뒤 `cfp preview remove` 로 dev 에서 지운다.
4. K-0126(로그인 없음·볼륨 500MB·railway.json 만료).
