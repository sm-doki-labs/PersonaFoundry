# Railway 시연 서버(D-0208). 기본 Dockerfile 과 같되, 테스터 발행에 쓰는 dev 배포판 chat-svc 컴파일러를
# /opt/chat-svc 에 함께 넣는다. vendor/chat-svc 는 deploy/railway/deploy.sh 가 git archive 로 채운다.
FROM ghcr.io/astral-sh/uv:0.11.28 AS uv
FROM python:3.12-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# 통화 영상 후처리(이어 붙이기·길이 확인)에 ffmpeg·ffprobe 가 필요하다.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/chat-svc
COPY vendor/chat-svc/pyproject.toml vendor/chat-svc/uv.lock vendor/chat-svc/README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY vendor/chat-svc/src/ src/
COPY vendor/chat-svc/data/ data/
RUN uv sync --locked --no-dev && uv cache clean

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" CFP_SERVER_MODE=1 CFP_ROOT=/data/factory \
    CFP_CONFIG=/app/deploy/factory.railway.toml
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src/ src/
RUN uv sync --locked --no-dev && uv cache clean
COPY studio/ studio/
COPY deploy/factory.railway.toml deploy/factory.railway.toml
# Railway 볼륨(/data)은 root 소유로 붙으므로 root 로 실행한다. 서버 안 cfp 명령(preview remove 등)도
# 같은 설정을 읽도록 루트의 factory.toml 을 서버 설정에 잇는다.
EXPOSE 8080
CMD ["sh","-ec","mkdir -p \"$CFP_ROOT\"; ln -sfn \"$CFP_CONFIG\" \"$CFP_ROOT/factory.toml\"; exec python -m character_factory_poc.web --root \"$CFP_ROOT\" --config \"$CFP_CONFIG\" --host 0.0.0.0 --port 8080"]
