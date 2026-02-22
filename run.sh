#!/bin/bash
# Wrapper that starts Xvfb at a realistic resolution before launching the scraper.
# Usage: ./run.sh [hltv-scraper args...]
#
# Uses 1920x1080x24 virtual display — Chrome window metrics look like a real desktop.
# Without this, default Xvfb is 640x480 which leaks via JS screen.width/height.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv/bin/hltv-scraper"

exec xvfb-run \
  --auto-servernum \
  --server-args="-screen 0 1920x1080x24 -ac" \
  "$VENV" "$@"
