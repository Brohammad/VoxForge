.DEFAULT_GOAL := help

.PHONY: help dev-up dev-down test test-all test-unit test-integration test-feature test-failure test-e2e test-browser test-cov lint typecheck benchmark-onboarding benchmark-onboarding-json benchmark-onboarding-memory benchmark-knowledge-base benchmark-knowledge-base-json livekit-worker knowledge-worker deploy-validate deploy-smoke prove-real-voice uptime-check client-demo

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-30s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

dev-up: ## Start local Postgres and Redis containers
	docker compose up -d postgres redis
	@echo "Run: pip install -e '.[dev,livekit]' && alembic upgrade head && uvicorn voxforge.main:app --reload --app-dir src"

dev-down: ## Stop local containers
	docker compose down

client-demo: ## Run the command-line client demo
	bash scripts/client_demo.sh

test: ## Run the full suite, excluding browser tests
	pytest -v --tb=short --ignore=tests/browser

test-all: ## Run every test, including browser tests
	pytest -v --tb=short

test-unit: ## Run unit tests
	pytest tests/unit -v --tb=short

test-integration: ## Run integration tests
	pytest tests/integration -v --tb=short

test-feature: ## Run feature/business-flow tests
	pytest tests/feature -v --tb=short -m feature

test-failure: ## Run failure-mode and recovery tests
	pytest tests/failure -v --tb=short -m failure

test-e2e: ## Run end-to-end tests
	pytest tests/e2e -v --tb=short -m e2e

test-browser: ## Run Playwright browser journeys
	chmod +x scripts/run_browser_tests.sh
	./scripts/run_browser_tests.sh

test-cov: ## Run the coverage gate (70% minimum)
	python scripts/generate_coverage_report.py --fail-under=70

lint: ## Check formatting and lint with ruff
	ruff check src tests
	ruff format --check src tests

typecheck: ## Type-check with pyright
	pyright

livekit-worker: ## Run the LiveKit worker in dev mode
	python -m voxforge.infrastructure.livekit.worker dev

deploy-validate: ## Validate a production environment file
	ENV_FILE=.env.production APP_ENV=production PYTHONPATH=src python3 scripts/validate_production_env.py

deploy-smoke: ## Run the production smoke checks
	chmod +x scripts/validate-prod-smoke.sh
	./scripts/validate-prod-smoke.sh

prove-real-voice: ## Prove a deployment uses live providers
	chmod +x scripts/prove-real-voice.sh
	./scripts/prove-real-voice.sh

uptime-check: ## Check readiness against a running deployment
	chmod +x scripts/uptime-ready-check.sh
	./scripts/uptime-ready-check.sh

benchmark-onboarding: ## Benchmark the onboarding pipeline
	python scripts/benchmark_onboarding.py --iterations 10 --warmup 2

benchmark-onboarding-json: ## Benchmark onboarding and print JSON
	python scripts/benchmark_onboarding.py --iterations 10 --warmup 2 --json

benchmark-onboarding-memory: ## Benchmark onboarding and print memory/JSON
	python scripts/benchmark_onboarding.py --iterations 10 --warmup 2 --memory --json

benchmark-knowledge-base: ## Benchmark the knowledge base
	python scripts/benchmark_knowledge_base.py --iterations 100

benchmark-knowledge-base-json: ## Benchmark the knowledge base and print JSON
	python scripts/benchmark_knowledge_base.py --iterations 100 --json

knowledge-worker: ## Run the knowledge ingestion worker
	python -m voxforge.infrastructure.knowledge.worker
