#!/bin/bash
# Wrapper that starts Xvfb at a realistic resolution before launching the scraper.
# Usage: ./run.sh [hltv-scraper args...]
#
# Uses 1920x1080x24 virtual display — Chrome window metrics look like a real desktop.
# Without this, default Xvfb is 640x480 which leaks via JS screen.width/height.
#
# Cleanup: on exit (normal or signal), kills any surviving Chrome/Xvfb child
# processes and removes leftover /tmp/.X*-lock and /tmp/uc_* artifacts.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv/bin/hltv-scraper"

cleanup() {
    # Kill any surviving chrome/Xvfb processes (Python's close() handles
    # normal exits; this catches SIGKILL'd runs where close() never ran).
    pkill -9 -f '[Cc]hrome' 2>/dev/null || true
    pkill -9 -f '[Xx]vfb'   2>/dev/null || true
    # Remove stale X lock files and nodriver /tmp/uc_* profile dirs
    rm -f /tmp/.X*-lock 2>/dev/null || true
    rm -rf /tmp/uc_* 2>/dev/null || true
}
trap cleanup EXIT INT TERM

xvfb-run \
  --auto-servernum \
  --server-args="-screen 0 1920x1080x24 -ac" \
  "$VENV" "$@"
