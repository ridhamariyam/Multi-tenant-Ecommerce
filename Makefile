BACKEND  := backend
VENV_BIN := .venv/bin
COMPOSE  := docker compose
VERSIONS := $(BACKEND)/migrations/versions

API_PORT := $(shell sed -n 's/^API_PORT=//p' .env 2>/dev/null | tail -1)
API_PORT := $(if $(API_PORT),$(API_PORT),58000)

REQUIRE_ENV = @test -f .env \
	|| { echo "error: .env is missing. Run: cp .env.example .env"; exit 1; }
REQUIRE_VENV = @test -x $(BACKEND)/$(VENV_BIN)/pytest \
	|| { echo "error: $(BACKEND)/.venv is missing or incomplete. Run:"; \
	     echo "  python -m venv $(BACKEND)/.venv"; \
	     echo "  $(BACKEND)/$(VENV_BIN)/pip install -r $(BACKEND)/requirements-dev.txt"; \
	     exit 1; }

REQUIRE_ENV_KEYS = @missing=$$(awk -F= 'FNR==NR{if(/^[A-Za-z_][A-Za-z0-9_]*=/) want[$$1]=1; next} /^[A-Za-z_][A-Za-z0-9_]*=/{have[$$1]=1} END{for(k in want) if(!(k in have)) print k}' .env.example .env | sort); \
	test -z "$$missing" \
	|| { echo "error: .env is missing keys that .env.example defines:"; \
	     echo "$$missing" | sed 's/^/  /'; \
	     echo "Append them (the example values are dev-safe) with:"; \
	     echo "  grep -E '^($$(echo "$$missing" | paste -sd'|' -))=' .env.example >> .env"; \
	     exit 1; }

# Two branches that each add a migration off the same parent leave the graph
# with two heads, and `alembic upgrade head` refuses to guess between them.
# Heads are computed from the files -- no container, no DB, so it fails before
# the image rebuild rather than after it.
REQUIRE_ONE_HEAD = @heads=$$(awk ' \
	function parents(line, n, a, i) { n=split(line,a,/[\047\042]/); for(i=2;i<n;i+=2) down[a[i]]=1 } \
	/^revision/ { n=split($$0,a,/[\047\042]/); if(n>=3) rev[a[2]]=1 } \
	/^down_revision/ { parents($$0); in_down=($$0 ~ /= *[(]/ && $$0 !~ /[)]/); next } \
	in_down { parents($$0); if($$0 ~ /[)]/) in_down=0 } \
	END { for(r in rev) if(!(r in down)) print r } \
' $(VERSIONS)/*.py | sort); \
	test $$(echo "$$heads" | wc -l) -eq 1 \
	|| { echo "error: migrations have multiple heads -- alembic upgrade head will fail:"; \
	     echo "$$heads" | sed 's/^/  /'; \
	     echo "Rebase your migration's down_revision onto the other head, or merge them:"; \
	     echo "  cd $(BACKEND) && $(VENV_BIN)/alembic merge heads -m \"merge heads\""; \
	     exit 1; }

.PHONY: dev test lint check

dev:
	$(REQUIRE_ENV)
	$(REQUIRE_ENV_KEYS)
	$(REQUIRE_ONE_HEAD)
	$(COMPOSE) up -d --build --wait
	$(COMPOSE) exec -T api alembic upgrade head
	@echo
	@echo "API      http://localhost:$(API_PORT)"
	@echo "Docs     http://localhost:$(API_PORT)/docs"
	@echo
	@echo "Logs     $(COMPOSE) logs -f api"
	@echo "Seed     $(COMPOSE) exec api python -m app.commands.seed"

# Tests run against a throwaway PostgreSQL and Redis that exist only for the
# run (see backend/scripts/test.sh), never against the app's database. The
# suite's migration test builds a database from the history and runs
# `alembic check` against it, so drift is caught there.
test:
	$(BACKEND)/scripts/test.sh

lint:
	$(REQUIRE_VENV)
	cd $(BACKEND) && $(VENV_BIN)/ruff check .

check:
	$(REQUIRE_VENV)
	cd $(BACKEND) && $(VENV_BIN)/python -m compileall -q app tests
	cd $(BACKEND) && $(VENV_BIN)/ruff check .
	cd $(BACKEND) && $(VENV_BIN)/alembic check
	$(BACKEND)/scripts/test.sh
