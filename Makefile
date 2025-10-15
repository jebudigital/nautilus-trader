.PHONY: install install-dev test lint format type-check clean run-dev run-test

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pip install -r requirements-dev.txt

# Testing
test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=src/crypto_trading_engine --cov-report=html

# Code quality
lint:
	flake8 src/ tests/

format:
	black src/ tests/
	isort src/ tests/

type-check:
	mypy src/

# Development
run-dev:
	trading-engine --environment dev --log-level DEBUG

run-test:
	trading-engine --environment test --log-level INFO

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .coverage
	rm -rf htmlcov/