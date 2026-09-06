# Save Pass — Password Manager
# Makefile for common development tasks

.PHONY: up down test-backend test-frontend install-backend install-frontend help

# Default target
help:
	@echo "Available targets:"
	@echo "  up               - Start all services with Docker Compose"
	@echo "  down             - Stop and remove all containers"
	@echo "  test-backend     - Run backend pytest suite"
	@echo "  test-frontend    - Run frontend Vitest suite"
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

## Local install targets (without Docker)

install-backend:
	cd backend && pip install -r requirements.txt

install-frontend:
	cd frontend && npm install
