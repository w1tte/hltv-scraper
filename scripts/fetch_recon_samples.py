"""Fetch representative HLTV sample pages for Phase 3 reconnaissance.

Temporary script -- not production code. Uses HLTVClient to fetch pages
and saves them as gzipped HTML to data/recon/.

Sample selection covers:
- 3 results listing pages (offsets 0, 100, 5000)
- 6-8 match overview pages spanning eras, formats, edge cases
- Map stats / performance / economy pages for each match's maps

Fetching in multiple sessions with pauses to avoid Cloudflare escalation.
"""

import asyncio
import gzip
import logging
import re
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scraper.http_client import HLTVClient
from scraper.config import ScraperConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"

# ── Sample URLs ──────────────────────────────────────────────────────────
# Curated to cover: era diversity, format diversity, tier diversity, edge cases

RESULTS_PAGES = [
    ("results-offset-0", "https://www.hltv.org/results?offset=0"),
    ("results-offset-100", "https://www.hltv.org/results?offset=100"),
    ("results-offset-5000", "https://www.hltv.org/results?offset=5000"),
]

# Match overview pages -- selected for diversity
MATCH_OVERVIEWS = [
    # Late 2023 (early CS2 era) - BLAST Premier Fall Final 2023, BO3 tier-1 LAN
    # Vitality vs FaZe, Nov 2023
    ("match-2367432-overview", "https://www.hltv.org/matches/2367432/vitality-vs-faze-blast-premier-fall-final-2023"),

    # Mid 2024 - BO1 online qualifier
    # ESL Pro League S19 qualifier match, ~April 2024
    ("match-2371389-overview", "https://www.hltv.org/matches/2371389/heroic-vs-og-esl-pro-league-season-19"),

    # Late 2024 - BO3 tier-1 LAN
    # BLAST Premier World Final 2024, Dec 2024
    ("match-2377467-overview", "https://www.hltv.org/matches/2377467/spirit-vs-faze-blast-premier-world-final-2024"),

    # Recent 2025-2026 - BO3
    # IEM Katowice 2025 or similar recent event
    ("match-2380434-overview", "https://www.hltv.org/matches/2380434/spirit-vs-natus-vincere-iem-katowice-2025"),

    # BO5 - PGL Major Copenhagen 2024 Grand Final
    # Natus Vincere vs FaZe
    ("match-2371321-overview", "https://www.hltv.org/matches/2371321/natus-vincere-vs-faze-pgl-cs2-major-copenhagen-2024"),

    # Overtime match - we'll find one from results pages or use a known one
    # G2 vs Liquid IEM Cologne 2024 had overtime maps
    ("match-2373741-overview", "https://www.hltv.org/matches/2373741/g2-vs-liquid-iem-cologne-2024"),

    # Forfeit/walkover attempt - ESEA matches often have forfeits
    # We'll try a known forfeit; if unavailable, we note it in manifest
    ("match-2366498-overview", "https://www.hltv.org/matches/2366498/ecstatic-vs-into-the-breach-cct-north-europe-series-4"),
]


def save_html(filename: str, html: str) -> Path:
    """Save HTML as gzipped file and return path."""
    path = RECON_DIR / f"{filename}.html.gz"
    path.write_bytes(gzip.compress(html.encode("utf-8")))
    size_kb = path.stat().st_size / 1024
    log.info(f"  Saved {filename}.html.gz ({size_kb:.1f} KB compressed, {len(html)} chars)")
    return path


def extract_mapstatsids(html: str) -> list[tuple[str, str]]:
    """Extract mapstatsid URLs from a match overview page.

    Returns list of (mapstatsid, full_url_path) tuples.
    """
    # Pattern: /stats/matches/mapstatsid/{id}/{slug}
    pattern = r'/stats/matches/mapstatsid/(\d+)/([a-zA-Z0-9-]+)'
    matches = re.findall(pattern, html)
    results = []
    seen = set()
    for msid, slug in matches:
        if msid not in seen:
            seen.add(msid)
            url = f"https://www.hltv.org/stats/matches/mapstatsid/{msid}/{slug}"
            results.append((msid, url))
    return results


async def fetch_session(client: HLTVClient, tasks: list[tuple[str, str]]) -> dict:
    """Fetch a batch of URLs. Returns {filename: (html, chars)} for successes."""
    results = {}
    for filename, url in tasks:
        try:
            log.info(f"Fetching: {url}")
            html = await client.fetch(url)
            save_html(filename, html)
            results[filename] = (html, len(html))
            log.info(f"  OK: {len(html)} chars | Stats: {client.stats}")
        except Exception as e:
            log.error(f"  FAILED: {url} -- {e}")
            results[filename] = None
    return results


async def main():
    RECON_DIR.mkdir(parents=True, exist_ok=True)

    all_results = {}
    mapstats_to_fetch = []  # (mapstatsid, url, from_match_id)

    config = ScraperConfig()

    # ── Session 1: Results pages + Match overviews ──────────────────────
    log.info("=" * 60)
    log.info("SESSION 1: Results pages + Match overviews")
    log.info("=" * 60)

    async with HLTVClient(config) as client:
        # Results pages
        session1_tasks = [(name, url) for name, url in RESULTS_PAGES]
        res = await fetch_session(client, session1_tasks)
        all_results.update(res)

        # Match overview pages
        for name, url in MATCH_OVERVIEWS:
            try:
                log.info(f"Fetching: {url}")
                html = await client.fetch(url)
                save_html(name, html)
                all_results[name] = (html, len(html))
                log.info(f"  OK: {len(html)} chars | Stats: {client.stats}")

                # Extract mapstatsids for later
                match_id = name.split("-")[1]
                msids = extract_mapstatsids(html)
                if msids:
                    # Take first 2 mapstatsids per match (don't need all maps)
                    for msid, msurl in msids[:2]:
                        mapstats_to_fetch.append((msid, msurl, match_id))
                    log.info(f"  Found {len(msids)} mapstatsids, queued {min(2, len(msids))}")
                else:
                    log.warning(f"  No mapstatsids found for {name} (possible forfeit?)")

            except Exception as e:
                log.error(f"  FAILED: {url} -- {e}")
                all_results[name] = None

    log.info(f"\nSession 1 complete. Pausing 45 seconds before session 2...")
    log.info(f"Files so far: {sum(1 for v in all_results.values() if v is not None)}")
    await asyncio.sleep(45)

    # ── Session 2: Map stats + performance pages ────────────────────────
    log.info("=" * 60)
    log.info("SESSION 2: Map stats + Map performance pages")
    log.info("=" * 60)

    session2_tasks = []
    for msid, base_url, from_match in mapstats_to_fetch:
        # Map stats page
        session2_tasks.append((f"mapstats-{msid}-stats", base_url))

        # Map performance page
        # Convert /stats/matches/mapstatsid/X/slug to /stats/matches/performance/mapstatsid/X/slug
        perf_url = base_url.replace("/stats/matches/mapstatsid/", "/stats/matches/performance/mapstatsid/")
        session2_tasks.append((f"performance-{msid}", perf_url))

    async with HLTVClient(config) as client:
        res = await fetch_session(client, session2_tasks)
        all_results.update(res)

    log.info(f"\nSession 2 complete. Pausing 45 seconds before session 3...")
    log.info(f"Files so far: {sum(1 for v in all_results.values() if v is not None)}")
    await asyncio.sleep(45)

    # ── Session 3: Economy pages ────────────────────────────────────────
    log.info("=" * 60)
    log.info("SESSION 3: Map economy pages")
    log.info("=" * 60)

    session3_tasks = []
    for msid, base_url, from_match in mapstats_to_fetch:
        # Map economy page
        econ_url = base_url.replace("/stats/matches/mapstatsid/", "/stats/matches/economy/mapstatsid/")
        session3_tasks.append((f"economy-{msid}", econ_url))

    async with HLTVClient(config) as client:
        res = await fetch_session(client, session3_tasks)
        all_results.update(res)

    # ── Summary ─────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("FETCH COMPLETE")
    log.info("=" * 60)

    total = len(all_results)
    success = sum(1 for v in all_results.values() if v is not None)
    failed = total - success

    log.info(f"Total attempted: {total}")
    log.info(f"Successful: {success}")
    log.info(f"Failed: {failed}")

    if failed:
        log.info("Failed fetches:")
        for name, val in all_results.items():
            if val is None:
                log.info(f"  - {name}")

    # List all files
    log.info(f"\nFiles in {RECON_DIR}:")
    for f in sorted(RECON_DIR.glob("*.html.gz")):
        size_kb = f.stat().st_size / 1024
        log.info(f"  {f.name}: {size_kb:.1f} KB")

    log.info("\nMapstatsids collected:")
    for msid, url, from_match in mapstats_to_fetch:
        log.info(f"  {msid} (from match {from_match}): {url}")


if __name__ == "__main__":
    asyncio.run(main())
