.PHONY: up down logs prod dev test clean

# Development
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
