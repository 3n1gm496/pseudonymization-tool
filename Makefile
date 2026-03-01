# ═══════════════════════════════════════════════════════════════════════════════
# Pseudonymization Tool v4.0 — Makefile
# ═══════════════════════════════════════════════════════════════════════════════

.PHONY: help start stop restart logs dev test clean install-dev

.DEFAULT_GOAL := help

# ─── Help ─────────────────────────────────────────────────────────────────────

help: ## Show this help message
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════════╗"
	@echo "║       Pseudonymization Tool v4.0 — Quick Commands                ║"
	@echo "╚══════════════════════════════════════════════════════════════════╝"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make start          # Start tool (Docker)"
	@echo "  make dev            # Start dev mode (hot reload)"
	@echo "  make test           # Run tests"
	@echo "  make stop           # Stop all containers"
	@echo ""

# ─── Docker Commands ──────────────────────────────────────────────────────────

start: ## Start the tool (Docker Compose, detached)
	@echo "🚀 Starting Pseudonymization Tool..."
	docker compose up --build -d
	@echo ""
	@echo "✅ Tool started!"
	@echo "   Frontend: http://localhost:8000"
	@echo "   API:      http://localhost:8000/api/health"
	@echo ""
	@echo "View logs:  make logs"
	@echo "Stop:       make stop"

stop: ## Stop all containers
	@echo "🛑 Stopping containers..."
	docker compose down
	@echo "✅ Stopped."

restart: ## Restart containers
	@echo "🔄 Restarting..."
	docker compose restart
	@echo "✅ Restarted."

logs: ## Show container logs (live)
	docker compose logs -f

build: ## Rebuild Docker images
	docker compose build --no-cache

# ─── Development ──────────────────────────────────────────────────────────────

dev: ## Start dev mode (frontend hot reload on :5173, backend on :8000)
	@echo "🧑‍💻 Starting dev stack..."
	@echo "   Frontend: http://localhost:5173 (hot reload)"
	@echo "   Backend:  http://127.0.0.1:8000"
	@echo ""
	./dev-stack.sh

install-dev: ## Install dev dependencies (backend venv + frontend npm)
	@echo "📦 Installing backend dependencies..."
	cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
	@echo "📦 Installing frontend dependencies..."
	cd frontend && npm install
	@echo "✅ Dev environment ready!"

# ─── Testing ──────────────────────────────────────────────────────────────────

test: ## Run all tests
	@echo "🧪 Running tests..."
	cd backend && python -m pytest tests/ -v

test-cov: ## Run tests with coverage report
	@echo "🧪 Running tests with coverage..."
	cd backend && python -m pytest tests/ --cov=app --cov-report=html --cov-report=term

test-functional: ## Run only functional tests
	@echo "🧪 Running functional tests..."
	cd backend && python -m pytest tests/test_functional.py -v

# ─── Cleanup ──────────────────────────────────────────────────────────────────

clean: ## Clean temporary files and caches
	@echo "🧹 Cleaning..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf backend/.venv 2>/dev/null || true
	rm -rf .venv 2>/dev/null || true
	rm -rf frontend/dist 2>/dev/null || true
	rm -rf frontend/node_modules 2>/dev/null || true
	@echo "✅ Cleaned."

clean-docker: ## Remove Docker containers, images, and volumes
	@echo "🧹 Cleaning Docker resources..."
	docker compose down -v --rmi all 2>/dev/null || true
	@echo "✅ Docker cleaned."

# ─── Legacy Support (for non-Docker environments) ─────────────────────────────

legacy-start: ## Start using legacy script (for systems without Docker)
	@echo "⚠️  Using legacy start script (no Docker)..."
	@echo "   Recommended: Use 'make start' with Docker instead"
	@echo ""
	./scripts/legacy/start.sh

legacy-prepare: ## Prepare offline package (for air-gapped installations)
	@echo "📦 Preparing offline package..."
	./scripts/legacy/prepare_offline.sh
	@echo "✅ Offline package ready in wheelhouse/"

# ─── Health Checks ────────────────────────────────────────────────────────────

health: ## Check if service is healthy
	@echo "🏥 Checking health..."
	@curl -fsS http://localhost:8000/api/health && echo "✅ Service is healthy" || echo "❌ Service is down"

ready: ## Check if service is ready
	@echo "🔍 Checking readiness..."
	@curl -fsS http://localhost:8000/api/ready && echo "✅ Service is ready" || echo "⏳ Service is starting..."

# ─── Utility ──────────────────────────────────────────────────────────────────

version: ## Show tool version
	@echo "Pseudonymization Tool v4.0"
	@echo "Python: $$(python3 --version 2>&1 || echo 'Not installed')"
	@echo "Docker: $$(docker --version 2>&1 || echo 'Not installed')"
	@echo "Node:   $$(node --version 2>&1 || echo 'Not installed')"

shell: ## Open shell in running container
	docker compose exec pseudonymization-tool /bin/bash

ps: ## Show running containers
	docker compose ps
