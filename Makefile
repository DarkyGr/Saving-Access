# Save Pass — Password Manager
# Makefile for common development tasks

.PHONY: up down test-backend test-frontend test-e2e lint smoke-prod backup seed create-admin install-backend install-frontend help

# Default target
help:
	@echo "Available targets:"
	@echo "  up               - Start all services with Docker Compose"
	@echo "  down             - Stop and remove all containers"
	@echo "  test-backend     - Run backend pytest suite"
	@echo "  test-frontend    - Run frontend Vitest suite"
	@echo "  test-e2e         - Run Playwright end-to-end tests (starts its own servers)"
	@echo "  lint             - ruff (backend) + eslint (frontend)"
	@echo "  smoke-prod       - Build and smoke-test the production stack (Docker)"
	@echo "  backup           - Take a production backup now (restore: scripts/restore-backup.sh)"
	@echo "  seed             - Seed default profiles in the running backend container"
	@echo "  create-admin     - Create an Admin account (USERNAME=.. EMAIL=..)"
	@echo "  install-backend  - Install Python dependencies in a venv"
	@echo "  install-frontend - Install Node.js dependencies"

## Docker Compose targets

up:
	docker compose up --build -d

down:
	docker compose down

## Test targets

test-backend:
	cd backend && python -m pytest tests/ -v

test-frontend:
	cd frontend && npm run test

test-e2e:
	cd frontend && npx playwright test

lint:
	cd backend && ruff check .
	cd frontend && npm run lint

smoke-prod:
	./scripts/smoke-prod.sh

backup:
	docker compose -f docker-compose.prod.yml --env-file .env.prod exec backup sh /usr/local/bin/backup.sh once

## Admin tasks (Docker)
seed:
	docker compose exec backend python -m app.cli seed

create-admin:
	docker compose exec backend python -m app.cli create-admin --username $(USERNAME) --email $(EMAIL)

## Local install targets (without Docker)

install-backend:
	cd backend && pip install -r requirements.txt

install-frontend:
	cd frontend && npm install
