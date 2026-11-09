FROM ghcr.io/astral-sh/uv:0.11.28 AS uv
FROM python:3.12-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" CFP_SERVER_MODE=1 CFP_ROOT=/data/factory \
    CFP_CONFIG=/app/deploy/factory.server.toml
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src/ src/
RUN uv sync --locked --no-dev && uv cache clean && \
    groupadd -g 10001 factory && useradd -m -u 10001 -g factory factory && \
    install -d -o factory -g factory /data /data/factory
COPY studio/ studio/
COPY deploy/factory.server.toml deploy/factory.server.toml
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3).close()"
CMD ["sh","-ec","mkdir -p \"$CFP_ROOT\"; exec python -m character_factory_poc.web --root \"$CFP_ROOT\" --config \"$CFP_CONFIG\" --host 0.0.0.0 --port 8080"]
