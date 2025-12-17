#!/usr/bin/env bash
set -euo pipefail

DSN=${PG_DSN:-postgresql://postgres:postgres@localhost:5432/postgres}
psql "$DSN" -f src/tip/db/migrations/001_init.sql
