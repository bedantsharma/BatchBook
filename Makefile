# ─────────────────────────────────────────────────────────────────
#  BatchBook — Makefile
#
#  Usage:
#    make dev            Start everything in development mode (hot-reload)
#    make prod           Start everything in production mode (detached)
#    make down           Stop all containers (dev + prod)
#    make frontend       Rebuild & restart frontend only  (default: dev)
#    make backend        Rebuild & restart backend only   (default: dev)
#    make logs           Tail all logs (dev)
#    make logs-f         Tail frontend logs only
#    make logs-b         Tail backend logs only
#    make build          Build all images without starting
#    make clean          Stop containers + remove images + volumes
#    make ps             Show running containers
#
#  Override the target environment for individual service restarts:
#    make frontend MODE=prod
#    make backend  MODE=prod
# ─────────────────────────────────────────────────────────────────

# ── BuildKit — must be on for --mount=type=cache in Dockerfiles to work ──────
export DOCKER_BUILDKIT       := 1
export COMPOSE_DOCKER_CLI_BUILD := 1

# Default mode for single-service commands (make frontend / make backend)
MODE ?= dev
COMPOSE_FILE = docker-compose.$(MODE).yml

# Colour helpers
CYAN  := \033[0;36m
RESET := \033[0m

.PHONY: dev prod down frontend backend \
        logs logs-f logs-b \
        build build-dev build-prod \
        clean ps help

# ── Full stack ────────────────────────────────────────────────────

## Start everything in development mode (foreground — Ctrl+C to stop)
dev:
	@echo "$(CYAN)▶ Starting BatchBook in DEV mode…$(RESET)"
	docker compose -f docker-compose.dev.yml up --build

## Start everything in development mode (detached / background)
dev-d:
	@echo "$(CYAN)▶ Starting BatchBook in DEV mode (detached)…$(RESET)"
	docker compose -f docker-compose.dev.yml up --build -d

## Start everything in production mode (always detached)
prod:
	@echo "$(CYAN)▶ Starting BatchBook in PROD mode…$(RESET)"
	docker compose -f docker-compose.prod.yml up --build -d
	@echo "$(CYAN)✔ Frontend → http://localhost:80$(RESET)"
	@echo "$(CYAN)✔ Backend  → http://localhost:8000$(RESET)"

# ── Individual service reload ─────────────────────────────────────
# These rebuild the image and restart just that one container.
# Default MODE=dev. Override with: make frontend MODE=prod

## Rebuild & restart the frontend container
frontend:
	@echo "$(CYAN)▶ Reloading frontend ($(MODE))…$(RESET)"
	docker compose -f $(COMPOSE_FILE) up -d --build frontend

## Rebuild & restart the backend container
backend:
	@echo "$(CYAN)▶ Reloading backend ($(MODE))…$(RESET)"
	docker compose -f $(COMPOSE_FILE) up -d --build backend

# ── Stop ─────────────────────────────────────────────────────────

## Stop all containers (dev and prod)
down:
	@echo "$(CYAN)▶ Stopping all containers…$(RESET)"
	-docker compose -f docker-compose.dev.yml  down
	-docker compose -f docker-compose.prod.yml down

# ── Logs ─────────────────────────────────────────────────────────

## Tail all logs (dev stack)
logs:
	docker compose -f docker-compose.dev.yml logs -f

## Tail frontend logs only (dev stack)
logs-f:
	docker compose -f docker-compose.dev.yml logs -f frontend

## Tail backend logs only (dev stack)
logs-b:
	docker compose -f docker-compose.dev.yml logs -f backend

# ── Build (no start) ─────────────────────────────────────────────

## Build all images for both dev and prod
build: build-dev build-prod

build-dev:
	@echo "$(CYAN)▶ Building DEV images…$(RESET)"
	docker compose -f docker-compose.dev.yml build

build-prod:
	@echo "$(CYAN)▶ Building PROD images…$(RESET)"
	docker compose -f docker-compose.prod.yml build

# ── Status ───────────────────────────────────────────────────────

## Show all running BatchBook containers
ps:
	@echo "── DEV ────────────────────────────────────────────────"
	-docker compose -f docker-compose.dev.yml  ps
	@echo "── PROD ───────────────────────────────────────────────"
	-docker compose -f docker-compose.prod.yml ps

# ── Clean ────────────────────────────────────────────────────────

## Stop containers, remove images, and wipe anonymous volumes
clean:
	@echo "$(CYAN)▶ Cleaning up…$(RESET)"
	-docker compose -f docker-compose.dev.yml  down --rmi local -v
	-docker compose -f docker-compose.prod.yml down --rmi local -v
	@echo "$(CYAN)✔ Done.$(RESET)"

# ── Help ─────────────────────────────────────────────────────────

## Print this help
help:
	@echo ""
	@echo "BatchBook — available make targets"
	@echo ""
	@grep -E '^##' Makefile | sed 's/## /  /'
	@echo ""
