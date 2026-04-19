.PHONY: up down logs prod dev test clean install uninstall reinstall test-install test-uninstall

# Installation (local pip)
install:
	cd backend && pip install -r requirements.txt
	@echo "Sentinel Pulse installed. Run 'make dev' to start."

uninstall:
	cd backend && pip uninstall -y sentinel-pulse bracket-bot 2>/dev/null || pip uninstall -y -r <(pip freeze | grep -E "^(sentinel|bracket)") 2>/dev/null || true
	@echo "Sentinel Pulse uninstalled."

reinstall: uninstall install

# Quick bug testing cycle
test-install:
	cd backend && pip install -r requirements.txt
	@echo "Installed dependencies for testing."

test-uninstall:
	@echo "For clean test, manually uninstall packages or use: pip freeze | grep -v sentinel | pip uninstall -y -"
	@echo "Quick reinstall: make test-install"

# Docker Development
up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f

# Production
prod:
	docker compose -f docker-compose.prod.yml up -d --build

prod-down:
	docker compose -f docker-compose.prod.yml down

# Development helpers
dev:
	docker compose up --build -d && docker compose logs -f

test:
	docker compose up -d --wait && \
	curl -sf http://localhost:8001/api/health && \
	echo "\n[PASS] Backend health check" && \
	curl -sf http://localhost:3000 > /dev/null && \
	echo "[PASS] Frontend reachable" && \
	docker compose down -v

clean:
	docker compose down -v --rmi all
	docker system prune -f

# Utilities
restart-backend:
	docker compose restart backend

restart-frontend:
	docker compose restart frontend

mongo-shell:
	docker compose exec mongodb mongosh bracket_bot

# Windows Installer
installer:
	powershell -ExecutionPolicy Bypass -File build-installer.ps1

installer-clean:
	powershell -ExecutionPolicy Bypass -File build-installer.ps1 -Clean
