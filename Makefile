# Docker Compose wrapper commands for the local development workflow.
#
# Dev commands use `docker compose` with no explicit `-f`, so compose.yaml and
# compose.override.yaml (live-reload + bind mount) are auto-merged.
# Prod commands target the base stack only via compose.yaml.

COMPOSE = docker compose
COMPOSE_PROD = docker compose -f compose.yaml

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) down
	$(COMPOSE) up -d

rebuild:
	$(COMPOSE) up -d --build

recreate:
	$(COMPOSE) down -v
	$(COMPOSE) up -d --build --force-recreate

logs:
	$(COMPOSE) logs -f app

ps:
	$(COMPOSE) ps

test:
	$(COMPOSE) run --rm app python -m pytest

shell:
	$(COMPOSE) run --rm app /bin/sh

prod-up:
	$(COMPOSE_PROD) up -d --build

prod-down:
	$(COMPOSE_PROD) down
