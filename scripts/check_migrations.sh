#!/usr/bin/env sh
# Blocks backend startup if Alembic is not at HEAD.
# To bypass: make dev BYPASS_UPDATE=1  (sets BYPASS_MIGRATION_CHECK=1 in the container)

if [ "$BYPASS_MIGRATION_CHECK" = "1" ]; then
    printf '\033[33m⚠  WARNING: Alembic migration check bypassed (BYPASS_UPDATE=1).\033[0m\n'
    exit 0
fi

printf 'Checking Alembic migrations…\n'

if ! uv run alembic check; then
    printf '\n\033[31m✘  DEPLOYMENT BLOCKED: database migrations are out of date.\033[0m\n'
    printf '   Apply pending migrations:  make migrate\n'
    printf '   Or bypass this check:      make dev BYPASS_UPDATE=1\n\n'
    exit 1
fi

printf '\033[32m✔  All migrations are up to date.\033[0m\n'
