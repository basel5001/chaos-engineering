.PHONY: help install dev lint test build run clean docker

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -r requirements.txt

dev: ## Install development dependencies
	pip install -r requirements-dev.txt
	pip install -e .

lint: ## Run linter
	ruff check src/ tests/
	ruff format --check src/ tests/

format: ## Auto-format code
	ruff format src/ tests/
	ruff check --fix src/ tests/

test: ## Run tests
	pytest tests/ -v --cov=src --cov-report=term-missing

test-ci: ## Run tests for CI (with JUnit output)
	pytest tests/ -v --cov=src --cov-report=xml --junitxml=test-results.xml

typecheck: ## Run type checker
	mypy src/

build: ## Build Docker image
	docker build -t chaos-engineering:latest .

run: ## Run a dry-run experiment
	python -m src.runner.cli --manifest manifests/experiment-pod-kill.yml --dry-run

run-analyze: ## Run experiment with AI analysis
	python -m src.runner.cli --manifest manifests/experiment-pod-kill.yml --dry-run --analyze

dashboard: ## Serve the dashboard locally
	python -m http.server 8080 --directory src/dashboard/

docker-up: ## Start with docker-compose
	docker compose up -d

docker-down: ## Stop docker-compose
	docker compose down

clean: ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -f test-results.xml coverage.xml
