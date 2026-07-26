FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev


FROM python:3.13-slim-bookworm AS runtime

RUN groupadd --gid 10001 innova \
    && useradd --uid 10001 --gid innova --create-home --shell /usr/sbin/nologin innova

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --chown=innova:innova app ./app
COPY --chown=innova:innova migrations ./migrations
COPY --chown=innova:innova static ./static
COPY --chown=innova:innova alembic.ini main.py ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER innova

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
