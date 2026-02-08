.PHONY: help install dev test lint format typecheck check clean run docker

# Default target
help:
	@echo "Incident Copilot Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install     Install production dependencies"
	@echo "  make dev         Install development dependencies"
	@echo ""
	@echo "Quality:"
	@echo "  make test        Run all tests"
	@echo "  make test-fast   Run fast unit tests only"
	@echo "  make lint        Run linter (ruff)"
	@echo "  make format      Format code (black + isort)"
	@echo "  make typecheck   Run type checker (mypy)"
	@echo "  make check       Run all checks (lint + typecheck + test)"
	@echo ""
	@echo "Running:"
	@echo "  make run         Run development server"
	@echo "  make docker      Build Docker image"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean       Remove cache files"
	@echo "  make coverage    Generate coverage report"

# Setup
install:
	pip install -e .

dev:
	pip install -e ".[dev]"
	pre-commit install

# Testing
test:
	pytest tests/ -v --tb=short

test-fast:
	pytest tests/test_log_compressor.py tests/test_eval_framework.py tests/test_health.py -v --tb=short -q

test-cov:
	pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

coverage: test-cov
	open htmlcov/index.html

# Linting & Formatting
lint:
	ruff check src tests

lint-fix:
	ruff check src tests --fix

format:
	black src tests
	isort src tests

typecheck:
	mypy src --ignore-missing-imports

# All checks
check: lint typecheck test-fast
	@echo "✅ All checks passed"

# Running
run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Docker
docker:
	docker build -t incident-copilot:latest .

docker-run:
	docker run -p 8000:8000 --env-file .env incident-copilot:latest

# Cleanup
clean:
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .mypy_cache
	rm -rf htmlcov
	rm -rf *.egg-info
	rm -rf dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Eval
eval:
	python -m src.eval.harness

eval-synthetic:
	python -c "from src.eval.harness import run_quick_eval; import asyncio; asyncio.run(run_quick_eval(count=20))"
