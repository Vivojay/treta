FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY tools ./tools
COPY simulators ./simulators
RUN uv sync --frozen --no-dev && \
    useradd --create-home --uid 10001 treta && \
    chown -R treta:treta /app

USER 10001
EXPOSE 8000
CMD ["uvicorn", "treta.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
