PYTHON ?= python
NPM ?= npm
COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help install install-backend install-frontend lint format format-check typecheck test test-unit test-integration coverage ci migrate services-up app-up stack-up demo-up async-up down logs

help: ## Show available targets
	@echo "ODIRAG development commands"
	@echo "  make install          Install backend and frontend dependencies"
	@echo "  make ci               Run the local CI-equivalent checks"
	@echo "  make services-up      Start PostgreSQL, Redis, and Qdrant"
	@echo "  make app-up           Build and start the backend and core dependencies"
	@echo "  make stack-up         Build and start the complete Compose platform"
	@echo "  make demo-up          Start the complete stack and seed demo data"
	@echo "  make async-up         Start the Celery worker and scheduler profile"
	@echo "  make down             Stop Compose services"

install: install-backend install-frontend

install-backend: ## Install backend with development dependencies
	cd backend && $(PYTHON) -m pip install -e ".[dev]"

install-frontend: ## Install frontend dependencies from the lock file
	@if [ -f frontend/package-lock.json ]; then cd frontend && $(NPM) ci; else echo "Frontend lock file not present; skipping."; fi

lint: ## Run backend and available frontend linters
	cd backend && $(PYTHON) -m ruff check .
	cd backend && $(PYTHON) -m black --check .
	@if [ -f frontend/package.json ]; then cd frontend && $(NPM) run lint --if-present; fi

format: ## Format backend source
	cd backend && $(PYTHON) -m ruff check --fix .
	cd backend && $(PYTHON) -m black .

format-check: lint

typecheck: ## Run backend and available frontend type checks
	cd backend && $(PYTHON) -m mypy app
	@if [ -f frontend/package.json ]; then cd frontend && $(NPM) run type-check --if-present; fi

test: ## Run the backend test suite
	cd backend && $(PYTHON) -m pytest

test-unit: ## Run backend unit tests only
	cd backend && $(PYTHON) -m pytest tests/unit

test-integration: ## Run tests marked as integration tests
	cd backend && $(PYTHON) -m pytest -m integration

coverage: ## Run backend tests with branch coverage
	cd backend && $(PYTHON) -m pytest --cov=app --cov-report=term-missing --cov-report=html

ci: lint typecheck coverage ## Run the local backend CI checkpoint
	@if [ -f frontend/package-lock.json ]; then cd frontend && $(NPM) ci && $(NPM) run build; fi

migrate: ## Apply all database migrations in the backend environment
	cd backend && $(PYTHON) -m alembic upgrade head

services-up: ## Start Phase 1 infrastructure dependencies
	$(COMPOSE) up -d postgres redis qdrant

app-up: ## Build and start the backend plus core dependencies
	$(COMPOSE) up -d --build backend

stack-up: ## Build and start the complete platform behind Nginx
	$(COMPOSE) build backend
	$(COMPOSE) build frontend
	$(COMPOSE) --profile ui --profile async up -d --no-build

demo-up: ## Start the complete stack and seed the demo dataset
	sh scripts/start_demo.sh

async-up: ## Start the real Celery worker and scheduler runtime
	$(COMPOSE) build backend
	$(COMPOSE) --profile async up -d --no-build worker scheduler

down: ## Stop all services, preserving named volumes
	$(COMPOSE) --profile ui --profile async down

logs: ## Follow logs from the current Compose project
	$(COMPOSE) --profile ui --profile async logs -f
