.PHONY: help install migrate dev dev-up dev-down dev-logs \
       test test-unit test-e2e test-e2e-headed \
       test-stack-up test-stack-seed test-stack-down test-stack-logs test-stack-verify \
       prod-build \
       clean

# Default target
help:
	@echo "WireGUI — available targets:"
	@echo ""
	@echo "  Development (app runs on host, infra in Docker):"
	@echo "    make install          Install dependencies (uv sync)"
	@echo "    make migrate          Run database migrations"
	@echo "    make dev              Start infra + mock IdPs, run app locally"
	@echo "    make dev-up           Start infra only (Postgres, Valkey, mock IdPs)"
	@echo "    make dev-down         Stop all containers"
	@echo "    make dev-logs         Tail container logs"
	@echo ""
	@echo "  Testing:"
	@echo "    make test             Run unit + e2e tests"
	@echo "    make test-unit        Run unit tests only"
	@echo "    make test-e2e         Run e2e tests (headless)"
	@echo "    make test-e2e-headed  Run e2e tests in headed mode (visible browser)"
	@echo ""
	@echo "  Integration stack (containerized WireGUI + WG clients + VictoriaMetrics):"
	@echo "    make test-stack-up    Seed DB, build, start everything"
	@echo "    make test-stack-down  Stop and remove containers + volumes"
	@echo "    make test-stack-logs  Tail logs"
	@echo "    make test-stack-verify  Verify metrics flowing to VictoriaMetrics"
	@echo ""
	@echo "  Production:"
	@echo "    make prod-build       Build production Docker image"
	@echo ""
	@echo "  Housekeeping:"
	@echo "    make clean            Remove generated files, caches, volumes"

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

install:
	uv sync

migrate:
	uv run alembic upgrade head

dev-up:
	docker compose up -d postgres valkey mock-oidc mock-saml

dev-down:
	docker compose down

dev-logs:
	docker compose logs -f

dev: dev-up migrate
	uv run python -m wiregui.main

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test-unit:
	uv run pytest tests/ --ignore=tests/e2e --ignore=tests/integration -v --tb=short

test-e2e:
	uv run pytest tests/e2e/ -v --tb=short

test-e2e-headed:
	uv run pytest tests/e2e/ --headed --slowmo 300 -v --tb=short

test: test-unit test-e2e

# ---------------------------------------------------------------------------
# Integration test stack (real WireGuard + mock clients + VictoriaMetrics)
# ---------------------------------------------------------------------------

test-stack-up: test-stack-seed
	docker compose up -d --build wiregui client1 client2 client3
	@echo ""
	@echo "Integration stack running:"
	@echo "  WireGUI:          http://localhost:13000  (admin@test.local / admin123)"
	@echo "  VictoriaMetrics:  http://localhost:8428"
	@echo "  Mock clients:     3 peers generating traffic every 3s"

test-stack-seed:
	@echo "[*] Starting infrastructure..."
	docker compose up -d postgres valkey victoriametrics
	@echo "[*] Waiting for Postgres..."
	@until docker compose exec -T postgres pg_isready -U wiregui > /dev/null 2>&1; do sleep 1; done
	@echo "[*] Running migrations..."
	uv run alembic upgrade head
	@echo "[*] Seeding server keypair, admin user, and client devices..."
	PYTHONPATH=. uv run python docker/mock-clients/setup.py

test-stack-down:
	docker compose down -v

test-stack-verify:
	uv run pytest tests/integration/ -v --tb=short

test-stack-logs:
	docker compose logs -f wiregui client1 client2 client3 victoriametrics

# ---------------------------------------------------------------------------
# Production
# ---------------------------------------------------------------------------

PROD_IMAGE ?= wiregui
PROD_TAG ?= latest

prod-build:
	docker build --no-cache -t $(PROD_IMAGE):$(PROD_TAG) .

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov
	rm -rf docker/mock-clients/configs/
	rm -rf .nicegui/
