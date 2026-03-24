#!/bin/bash
# Cron wrapper: run the HLTV historical ingest with a non-overlapping lock.
set -uo pipefail

COMPOSE_DIR="$HOME/cs2-trading/hltv-ingest"
LOGFILE="$COMPOSE_DIR/cron-ingest.log"
LOCKFILE="$COMPOSE_DIR/.cron-ingest.lock"

mkdir -p "$COMPOSE_DIR/data/logs"
touch "$LOGFILE"

exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "$(date -Iseconds) SKIP: ingest lock already held" >> "$LOGFILE"
    exit 0
fi

echo "$(date -Iseconds) START: launching historical ingest" >> "$LOGFILE"
cd "$COMPOSE_DIR" || exit 1
docker compose --profile ingest run --rm ingest >> "$LOGFILE" 2>&1
exit_code=$?
echo "$(date -Iseconds) DONE: ingest finished (exit $exit_code)" >> "$LOGFILE"
exit "$exit_code"
