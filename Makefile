.PHONY: help install dev lint typecheck test build clean publish

PYTHON ?= python3
VERSION := $(shell $(PYTHON) -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install spec-orch (user)
	$(PYTHON) -m pip install .

dev: ## Install with all dev dependencies
	$(PYTHON) -m pip install -e ".[dev]"

lint: ## Run ruff linter and formatter check
	ruff check src/ tests/
	ruff format --check src/ tests/

typecheck: ## Run mypy type checker
	mypy src/spec_orch/

test: ## Run unit tests
	pytest tests/unit/ -v --tb=short

build: ## Build sdist and wheel
	$(PYTHON) -m build
	twine check dist/*

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

publish: build ## Publish to PyPI (requires credentials)
	twine upload dist/*

version: ## Show current version
	@echo $(VERSION)

brew-formula: build ## Generate Homebrew formula resources
	@echo "After publishing to PyPI, generate resource stanzas with:"
	@echo "  pip install homebrew-pypi-poet && poet spec-orch"
