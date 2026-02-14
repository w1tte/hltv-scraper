"""Live integration tests against HLTV.

These tests launch a real Chrome browser (off-screen) and make REAL
requests to HLTV. They take several minutes due to rate limiting delays.

    python -m pytest tests/test_integration.py -v -s -m integration --timeout=600

All tests are marked with @pytest.mark.integration.
"""

import time

import pytest

from scraper.http_client import HLTVClient
from scraper.config import ScraperConfig

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Test URLs -- real, known-good HLTV pages from major 2025 tournaments
# ---------------------------------------------------------------------------
HLTV_TEST_URLS = {
    "results_listing": "https://www.hltv.org/results",
    "match_overview": "https://www.hltv.org/matches/2376513/faze-vs-natus-vincere-blast-premier-spring-final-2025",
    "map_overview": "https://www.hltv.org/stats/matches/mapstatsid/178889/faze-vs-natus-vincere",
    "map_performance": "https://www.hltv.org/stats/matches/performance/mapstatsid/178889/faze-vs-natus-vincere",
    "map_economy": "https://www.hltv.org/stats/matches/economy/mapstatsid/178889/faze-vs-natus-vincere",
}

# Expanded URL list for the 20-page sequence test
HLTV_SEQUENCE_URLS = [
    ("results_offset_0", "https://www.hltv.org/results?offset=0"),
    ("results_offset_100", "https://www.hltv.org/results?offset=100"),
    ("results_offset_200", "https://www.hltv.org/results?offset=200"),
    ("match_overview_1", "https://www.hltv.org/matches/2376513/faze-vs-natus-vincere-blast-premier-spring-final-2025"),
    ("match_overview_2", "https://www.hltv.org/matches/2376088/spirit-vs-the-mongolz-pgl-astana-2025"),
    ("match_overview_3", "https://www.hltv.org/matches/2374881/natus-vincere-vs-spirit-pgl-cs2-major-copenhagen-2024"),
    ("match_overview_4", "https://www.hltv.org/matches/2376514/mouz-vs-vitality-blast-premier-spring-final-2025"),
    ("match_overview_5", "https://www.hltv.org/matches/2376097/faze-vs-spirit-pgl-astana-2025"),
    ("map_overview_1", "https://www.hltv.org/stats/matches/mapstatsid/178889/faze-vs-natus-vincere"),
    ("map_economy_2", "https://www.hltv.org/stats/matches/economy/mapstatsid/177536/spirit-vs-the-mongolz"),
    ("map_overview_3", "https://www.hltv.org/stats/matches/mapstatsid/177536/spirit-vs-the-mongolz"),
    ("map_overview_4", "https://www.hltv.org/stats/matches/mapstatsid/175014/natus-vincere-vs-spirit"),
    ("map_overview_5", "https://www.hltv.org/stats/matches/mapstatsid/178891/mouz-vs-vitality"),
    ("map_performance_1", "https://www.hltv.org/stats/matches/performance/mapstatsid/178889/faze-vs-natus-vincere"),
    ("map_economy_3", "https://www.hltv.org/stats/matches/economy/mapstatsid/175014/natus-vincere-vs-spirit"),
    ("map_performance_3", "https://www.hltv.org/stats/matches/performance/mapstatsid/177536/spirit-vs-the-mongolz"),
    ("map_performance_4", "https://www.hltv.org/stats/matches/performance/mapstatsid/175014/natus-vincere-vs-spirit"),
    ("map_performance_5", "https://www.hltv.org/stats/matches/performance/mapstatsid/178891/mouz-vs-vitality"),
    ("map_economy_1", "https://www.hltv.org/stats/matches/economy/mapstatsid/178889/faze-vs-natus-vincere"),
    ("map_economy_4", "https://www.hltv.org/stats/matches/economy/mapstatsid/178891/mouz-vs-vitality"),
]


def _is_valid_hltv_html(html: str) -> tuple[bool, str]:
    """Check if the response is valid HLTV content, not a Cloudflare challenge."""
    if len(html) < 1000:
        return False, f"Response too short ({len(html)} chars)"

    if "hltv" not in html.lower()[:50000]:
        return False, "Response does not contain 'hltv' (not HLTV content)"

    # Check for challenge indicators in the title area
    title_area = html[:500]
    if "Just a moment" in title_area or "Checking your browser" in title_area:
        return False, "Cloudflare challenge detected in page head"

    return True, "OK"


# ---------------------------------------------------------------------------
# Test 1: All 5 page types reachable
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_page_types_reachable():
    """Fetch all 5 HLTV page types and verify each returns valid HTML.

    This is the critical gate test. The performance page was previously
    blocked by Cloudflare with curl_cffi -- nodriver must solve it.
    """
    results = {}
    failures = []

    async with HLTVClient() as client:
        for page_type, url in HLTV_TEST_URLS.items():
            print(f"\n--- Fetching {page_type} ---")
            print(f"URL: {url}")

            try:
                html = await client.fetch(url)
                is_valid, reason = _is_valid_hltv_html(html)

                results[page_type] = {
                    "status": "OK" if is_valid else "INVALID",
                    "length": len(html),
                    "reason": reason,
                }

                print(f"Status: {'OK' if is_valid else 'INVALID'}")
                print(f"Length: {len(html)} chars")
                print(f"Reason: {reason}")

                if not is_valid:
                    failures.append((page_type, reason))

            except Exception as exc:
                results[page_type] = {
                    "status": "ERROR",
                    "length": 0,
                    "reason": str(exc),
                }
                failures.append((page_type, str(exc)))
                print(f"Status: ERROR")
                print(f"Error: {exc}")

    # Print summary
    print("\n\n=== PAGE TYPE RESULTS ===")
    for page_type, result in results.items():
        print(f"  {page_type:20s} | {result['status']:7s} | {result['length']:>8d} chars | {result['reason']}")

    print(f"\nClient stats: {client.stats}")

    # Assert no failures
    if failures:
        failure_msg = "\n".join(
            f"  - {page_type}: {reason}" for page_type, reason in failures
        )
        pytest.fail(f"Page types failed:\n{failure_msg}")


# ---------------------------------------------------------------------------
# Test 2: Sequential fetch of 20+ pages without escalating blocks
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sequential_fetch_20_pages():
    """Fetch 20+ pages in sequence to verify no escalating Cloudflare blocks.

    Tracks success/failure patterns. Allows up to 10% transient failures but
    fails if there are 3+ consecutive failures (indicating escalation).
    """
    total = len(HLTV_SEQUENCE_URLS)
    successes = 0
    failures = 0
    consecutive_failures = 0
    max_consecutive_failures = 0
    results_log = []

    start_time = time.monotonic()

    async with HLTVClient() as client:
        for i, (label, url) in enumerate(HLTV_SEQUENCE_URLS, 1):
            print(f"\n[{i}/{total}] {label}")
            print(f"  URL: {url}")
            request_start = time.monotonic()

            try:
                html = await client.fetch(url)
                is_valid, reason = _is_valid_hltv_html(html)
                elapsed = time.monotonic() - request_start

                if is_valid:
                    successes += 1
                    consecutive_failures = 0
                    status = "OK"
                    print(f"  Status: OK ({len(html)} chars, {elapsed:.1f}s)")
                else:
                    failures += 1
                    consecutive_failures += 1
                    max_consecutive_failures = max(
                        max_consecutive_failures, consecutive_failures
                    )
                    status = f"INVALID: {reason}"
                    print(f"  Status: INVALID - {reason} ({elapsed:.1f}s)")

            except Exception as exc:
                elapsed = time.monotonic() - request_start
                failures += 1
                consecutive_failures += 1
                max_consecutive_failures = max(
                    max_consecutive_failures, consecutive_failures
                )
                status = f"ERROR: {exc}"
                print(f"  Status: ERROR - {exc} ({elapsed:.1f}s)")

            results_log.append({
                "index": i,
                "label": label,
                "status": status,
                "elapsed": elapsed,
            })

        total_time = time.monotonic() - start_time
        stats = client.stats

    # Print summary
    success_rate = successes / total if total > 0 else 0.0
    avg_delay = total_time / total if total > 0 else 0.0

    print("\n\n=== 20-PAGE SEQUENCE RESULTS ===")
    print(f"  Total pages:              {total}")
    print(f"  Successes:                {successes}")
    print(f"  Failures:                 {failures}")
    print(f"  Success rate:             {success_rate:.1%}")
    print(f"  Max consecutive failures: {max_consecutive_failures}")
    print(f"  Total time:               {total_time:.1f}s")
    print(f"  Avg time per request:     {avg_delay:.1f}s")
    print(f"\nClient stats: {stats}")

    # Assert >= 90% success rate
    assert success_rate >= 0.9, (
        f"Success rate {success_rate:.1%} is below 90% threshold. "
        f"{failures}/{total} requests failed."
    )

    # Assert no 3+ consecutive failures (would indicate escalating block)
    assert max_consecutive_failures < 3, (
        f"Detected {max_consecutive_failures} consecutive failures, "
        f"indicating escalating Cloudflare blocks."
    )


# ---------------------------------------------------------------------------
# Test 3: Client stats tracking accuracy
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_client_stats_tracking():
    """Verify client.stats returns correct counts after fetching a few pages."""
    async with HLTVClient() as client:
        pages_to_fetch = [
            HLTV_TEST_URLS["results_listing"],
            HLTV_TEST_URLS["match_overview"],
            HLTV_TEST_URLS["map_overview"],
        ]

        for url in pages_to_fetch:
            await client.fetch(url)

        stats = client.stats
        print(f"\nClient stats after 3 fetches: {stats}")

        assert stats["requests"] >= 3
        assert stats["successes"] == 3
        assert stats["successes"] + stats["challenges"] == stats["requests"]

        expected_rate = stats["successes"] / stats["requests"]
        assert abs(stats["success_rate"] - expected_rate) < 0.001
        assert stats["current_delay"] > 0
