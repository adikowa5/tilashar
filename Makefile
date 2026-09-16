.PHONY: up down logs migrate seed test fresh

up:            ## поднять всё (postgres + api + web)
	docker compose up -d --build
	@echo "API  http://localhost:8000/docs"
	@echo "WEB  http://localhost:8080"

down:
	docker compose down

logs:
	docker compose logs -f api

migrate:       ## накатить миграции
	docker compose exec api alembic upgrade head

seed:          ## залить темы и слова
	docker compose exec api python -m app.seed

test:          ## тесты бэкенда (sqlite, без docker)
	cd backend && python -m pytest -q

fresh: down    ## снести данные и поднять заново
	docker volume rm -f tilashar-app_pgdata || true
	$(MAKE) up
	sleep 3
	$(MAKE) migrate seed
