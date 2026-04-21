# Docker Compose wrapper commands for the local development workflow.

COMPOSE = docker compose -f compose.yaml

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) down
	$(COMPOSE) up -d

rebuild:
	$(COMPOSE) up -d --build

logs:
	$(COMPOSE) logs -f app

ps:
	$(COMPOSE) ps

test:
	$(COMPOSE) run --rm app python -m pytest

shell:
	$(COMPOSE) run --rm app /bin/sh
