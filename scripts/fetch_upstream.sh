#!/usr/bin/env bash
# Fetch the PRE-EXISTING QorTime code this repo builds on, without copying it into this repo.
# It lands in ./upstream/qortime (git-ignored) at the last commit before the Meta AI Developer Hackathon
# (ConWan30/qortime 0e87ec3, Sun Oct 25 2026). Nothing from it is committed here.
set -euo pipefail
REF="${QORTIME_UPSTREAM_REF:-0e87ec3be0f8268f41a46d6368861fbc45976dea}"   # set QORTIME_UPSTREAM_REF=main to run the referee-hook integration tests
cd "$(dirname "$0")/.."
rm -rf upstream/qortime && mkdir -p upstream/qortime && cd upstream/qortime
git init -q && git remote add origin https://github.com/ConWan30/qortime.git
git fetch -q --depth 1 origin "$REF" && git checkout -q FETCH_HEAD
echo "upstream qortime at $(git rev-parse --short HEAD)"
cd ../..
# The public VERIFIED match 170123 receipt (signed Oct 23 2026, pre-existing) next to its event-built sidecars.
cp upstream/qortime/site/matches/170123/receipt.json examples/170123/receipt.json
