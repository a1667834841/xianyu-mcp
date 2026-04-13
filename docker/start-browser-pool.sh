#!/usr/bin/env bash
set -eu

export POOL_SIZE="${BROWSER_POOL_SIZE:-1}"
export START_PORT="${BROWSER_CDP_START_PORT:-9222}"
export INTERNAL_START_PORT="${BROWSER_INTERNAL_CDP_START_PORT:-9322}"
export PROFILE_ROOT="${BROWSER_PROFILE_ROOT:-/data/browser-pool}"
export CHROME_BIN="${CHROME_BIN:-google-chrome}"

exec python -m docker.start_browser_pool
