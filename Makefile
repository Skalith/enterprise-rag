.DEFAULT_GOAL := help
COMPOSE ?= docker compose

.PHONY: help up down restart build logs ps seed dev dev-stop test test-cov lint migrate migrate-rev migrate-stamp typecheck shell clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Build and start all services in the background
	@test -f .env || (echo "No .env found - run: cp .env.example .env" && exit 1)
	$(COMPOSE) up -d --build

down: ## Stop and remove containers (volumes are kept)
	$(COMPOSE) down

restart: ## Restart all services
	$(COMPOSE) restart

build: ## Rebuild images without starting
	$(COMPOSE) build

logs: ## Tail logs (usage: make logs or make logs s=backend)
	$(COMPOSE) logs -f --tail=100 $(s)

ps: ## Show service status
	$(COMPOSE) ps

dev: ## Run backend + celery worker + frontend locally in one tmux session (infra must be up)
	./scripts/dev.sh

dev-stop: ## Stop the local tmux dev session
	./scripts/dev.sh stop

seed: ## Create roles + default super_admin (see ADMIN_* in .env)
	$(COMPOSE) exec backend python -m scripts.seed_admin

test: ## Run backend tests inside the backend container
	$(COMPOSE) exec backend sh -c "pip install -q -r requirements-dev.txt && python -m pytest tests -v"

test-cov: ## Run backend tests with a coverage report
	$(COMPOSE) exec backend sh -c "pip install -q -r requirements-dev.txt && python -m pytest tests --cov=app --cov-report=term-missing"

lint: ## Lint backend with ruff (must be installed locally)
	ruff check backend --select E9,F63,F7,F82

migrate: ## Apply DB migrations (alembic upgrade head) in the backend container
	$(COMPOSE) exec backend alembic upgrade head

migrate-rev: ## Autogenerate a migration (usage: make migrate-rev m="add column")
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(m)"

migrate-stamp: ## Mark an existing database as fully migrated without running SQL
	$(COMPOSE) exec backend alembic stamp head

typecheck: ## Type-check the frontend
	cd frontend && npm run typecheck

shell: ## Open a shell in the backend container
	$(COMPOSE) exec backend bash

clean: ## Stop containers AND delete data volumes (destructive)
	@read -p "This deletes all database, vector and file data. Continue? [y/N] " a; [ "$$a" = "y" ] && $(COMPOSE) down -v || echo "Aborted."
