.PHONY: dev-up dev-down test test-unit test-integration test-feature test-failure test-e2e test-browser test-cov lint benchmark-onboarding benchmark-knowledge-base livekit-worker deploy-validate deploy-smoke prove-real-voice uptime-check client-demo

dev-up:
	docker compose up -d postgres redis
	@echo "Run: pip install -e '.[dev,livekit]' && alembic upgrade head && uvicorn voxforge.main:app --reload --app-dir src"

dev-down:
	docker compose down

client-demo:
	bash scripts/client_demo.sh

test:
	pytest -v --tb=short --ignore=tests/browser

test-all:
	pytest -v --tb=short

test-unit:
	pytest tests/unit -v --tb=short

test-integration:
	pytest tests/integration -v --tb=short

test-feature:
	pytest tests/feature -v --tb=short -m feature

test-failure:
	pytest tests/failure -v --tb=short -m failure

test-e2e:
	pytest tests/e2e -v --tb=short -m e2e

test-browser:
	chmod +x scripts/run_browser_tests.sh
	./scripts/run_browser_tests.sh

test-cov:
	python scripts/generate_coverage_report.py --fail-under=70

lint:
	ruff check src tests
	ruff format --check src tests

typecheck:
	pyright

livekit-worker:
	python -m voxforge.infrastructure.livekit.worker dev

deploy-validate:
	ENV_FILE=.env.production APP_ENV=production PYTHONPATH=src python3 scripts/validate_production_env.py

deploy-smoke:
	chmod +x scripts/validate-prod-smoke.sh
	./scripts/validate-prod-smoke.sh

prove-real-voice:
	chmod +x scripts/prove-real-voice.sh
	./scripts/prove-real-voice.sh

uptime-check:
	chmod +x scripts/uptime-ready-check.sh
	./scripts/uptime-ready-check.sh

benchmark-onboarding:
	python scripts/benchmark_onboarding.py --iterations 10 --warmup 2

benchmark-onboarding-json:
	python scripts/benchmark_onboarding.py --iterations 10 --warmup 2 --json

benchmark-onboarding-memory:
	python scripts/benchmark_onboarding.py --iterations 10 --warmup 2 --memory --json

benchmark-knowledge-base:
	python scripts/benchmark_knowledge_base.py --iterations 100

benchmark-knowledge-base-json:
	python scripts/benchmark_knowledge_base.py --iterations 100 --json

knowledge-worker:
	python -m voxforge.infrastructure.knowledge.worker
