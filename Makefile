.PHONY: help dev test test-fast test-cov lint format typecheck check clean install docker-build docker-run eval

# Default target
help:
	@echo "Incident Copilot - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install dependencies"
	@echo "  make install-dev   Install with dev dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make dev           Start development server"
	@echo "  make format        Auto-format code (black + isort)"
	@echo "  make lint          Run linters (ruff)"
	@echo "  make typecheck     Run type checker (mypy)"
	@echo "  make check         Run all checks (lint + typecheck + test)"
	@echo ""
	@echo "Testing:"
	@echo "  make test          Run all tests"
	@echo "  make test-fast     Run unit tests only (skip slow/integration)"
	@echo "  make test-cov      Run tests with coverage report"
	@echo "  make coverage      Generate HTML coverage report"
	@echo "  make eval          Run evaluation harness"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build  Build Docker image"
	@echo "  make docker-run    Run Docker container"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean         Clean build artifacts"
	@echo "  make deps-graph    Generate dependency graph"

# ============================================================================
# Setup
# ============================================================================

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

# ============================================================================
# Development
# ============================================================================

dev:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

format:
	black src tests
	isort --profile black src tests

lint:
	ruff check src tests

typecheck:
	mypy src --ignore-missing-imports

check: lint typecheck test
	@echo "✓ All checks passed!"

# ============================================================================
# Testing
# ============================================================================

test:
	pytest tests/ -v

test-fast:
	pytest tests/ -v -m "not slow and not integration" --ignore=tests/integration

test-cov:
	pytest tests/ --cov=src --cov-report=term-missing

coverage:
	pytest tests/ --cov=src --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

eval:
	python -m src.eval.harness

# ============================================================================
# Docker
# ============================================================================

docker-build:
	docker build -t incident-copilot:latest .

docker-run:
	docker run -p 8000:8000 --env-file .env incident-copilot:latest

docker-compose-up:
	docker-compose up --build

docker-compose-down:
	docker-compose down

# ============================================================================
# Utilities
# ============================================================================

clean:
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

deps-graph:
	python scripts/dependency_graph.py

# Pre-commit
pre-commit:
	pre-commit run --all-files

# Security scan
security:
	bandit -r src -ll
	pip-audit
