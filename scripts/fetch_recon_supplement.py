"""Supplementary fetch script for Phase 3 reconnaissance.

Fills gaps identified after initial fetch:
- Tier-1 LAN match (Major event)
- BO5 match
- Recent 2025+ tier-1 event

Uses exact HLTV match page URLs verified from results pages.
"""

import asyncio
import gzip
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scraper.http_client import HLTVClient
from scraper.config import ScraperConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"


def save_html(filename: str, html: str) -> Path:
    path = RECON_DIR / f"{filename}.html.gz"
    path.write_bytes(gzip.compress(html.encode("utf-8")))
    size_kb = path.stat().st_size / 1024
    log.info(f"  Saved {filename}.html.gz ({size_kb:.1f} KB, {len(html)} chars)")
    return path


def extract_mapstatsids(html: str) -> list[tuple[str, str]]:
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


SUPPLEMENTARY_MATCHES = [
    # BO5 from results page (Getting Info vs BOSS, Night Shift Invitational 2025)
    ("match-2384993-overview", "https://www.hltv.org/matches/2384993/getting-info-vs-boss-night-shift-invitational-2025-north-america"),

    # Recent tier-1: Vitality vs G2 from results-offset-0 (3 stars, BO3)
    ("match-2389951-overview", "https://www.hltv.org/matches/2389951/vitality-vs-g2-iem-katowice-2026"),
]


async def main():
    RECON_DIR.mkdir(parents=True, exist_ok=True)
    config = ScraperConfig()
    mapstats_to_fetch = []

    log.info("=" * 60)
    log.info("SUPPLEMENTARY FETCH: Tier-1 LAN + BO5")
    log.info("=" * 60)

    async with HLTVClient(config) as client:
        # Fetch match overviews
        for name, url in SUPPLEMENTARY_MATCHES:
            try:
                log.info(f"Fetching: {url}")
                html = await client.fetch(url)
                save_html(name, html)

                match_id = name.split("-")[1]
                msids = extract_mapstatsids(html)
                if msids:
                    # Take first 2 mapstatsids
                    for msid, msurl in msids[:2]:
                        mapstats_to_fetch.append((msid, msurl, match_id))
                    log.info(f"  Found {len(msids)} mapstatsids, queued {min(2, len(msids))}")
                else:
                    log.warning(f"  No mapstatsids found for {name}")
            except Exception as e:
                log.error(f"  FAILED: {url} -- {e}")

        # Fetch map pages for each match
        for msid, base_url, from_match in mapstats_to_fetch:
            # Skip if we already have this mapstatsid
            if (RECON_DIR / f"mapstats-{msid}-stats.html.gz").exists():
                log.info(f"  Skipping mapstatsid {msid} (already exists)")
                continue

            # Map stats
            try:
                log.info(f"Fetching map stats: {base_url}")
                html = await client.fetch(base_url)
                save_html(f"mapstats-{msid}-stats", html)
            except Exception as e:
                log.error(f"  FAILED: {base_url} -- {e}")

            # Performance
            perf_url = base_url.replace("/stats/matches/mapstatsid/", "/stats/matches/performance/mapstatsid/")
            try:
                log.info(f"Fetching performance: {perf_url}")
                html = await client.fetch(perf_url)
                save_html(f"performance-{msid}", html)
            except Exception as e:
                log.error(f"  FAILED: {perf_url} -- {e}")

            # Economy
            econ_url = base_url.replace("/stats/matches/mapstatsid/", "/stats/matches/economy/mapstatsid/")
            try:
                log.info(f"Fetching economy: {econ_url}")
                html = await client.fetch(econ_url)
                save_html(f"economy-{msid}", html)
            except Exception as e:
                log.error(f"  FAILED: {econ_url} -- {e}")

    # Summary
    log.info("=" * 60)
    log.info("SUPPLEMENTARY FETCH COMPLETE")
    log.info("=" * 60)
    total_files = len(list(RECON_DIR.glob("*.html.gz")))
    log.info(f"Total files in recon dir: {total_files}")

    log.info("\nMapstatsids collected:")
    for msid, url, from_match in mapstats_to_fetch:
        log.info(f"  {msid} (from match {from_match}): {url}")


if __name__ == "__main__":
    asyncio.run(main())
