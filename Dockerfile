FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install system deps needed for building (wireguard-tools for wg CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev wireguard-tools nftables iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./

# Install dependencies (production only, no dev group)
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# Copy application code
COPY wiregui/ wiregui/
COPY alembic/ alembic/
COPY alembic.ini ./

FROM python:3.13-slim AS runner

WORKDIR /app

# Runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wireguard-tools nftables iproute2 libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy uv and virtualenv from builder
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/wiregui /app/wiregui
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

# Ensure the venv is on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Create logs directory
RUN mkdir -p /app/logs

ARG VERSION=0.0.0-dev
ENV WG_VERSION=$VERSION

EXPOSE 13000
EXPOSE 51820/udp

# Run migrations then start the app
CMD ["sh", "-c", "alembic upgrade head && python -m wiregui.main"]
