#!/bin/bash
# Cron wrapper: run the HLTV historical ingest if not already running.
set -euo pipefail

COMPOSE_DIR="$HOME/cs2-trading/hltv-ingest"
LOGFILE="$COMPOSE_DIR/cron-ingest.log"

if docker ps --format "{{.Names}}" | grep -q "^hltv-ingest$"; then
    echo "$(date -Iseconds) SKIP: ingest already running" >> "$LOGFILE"
    exit 0
fi

echo "$(date -Iseconds) START: launching historical ingest" >> "$LOGFILE"
cd "$COMPOSE_DIR"
docker compose --profile ingest run --rm ingest >> "$LOGFILE" 2>&1
echo "$(date -Iseconds) DONE: ingest finished (exit $?)" >> "$LOGFILE"
