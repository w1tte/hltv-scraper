"""Find matches marked 'scraped' that are actually incomplete, wipe their
partial data, and reset them to 'pending' for re-scraping.

A non-forfeit match is complete when every playable map has:
  - player_stats rows
  - economy rows
  - player_stats.kpr is NOT NULL (perf data was scraped)

Also resets all 'failed' matches to 'pending'.

Usage:
    docker compose run --rm scraper python reset_incomplete.py
"""
import sys
sys.path.insert(0, "src")

from scraper.db import Database


def main():
    db = Database()
    db.initialize()
    conn = db.conn
    cur = conn.cursor()

    # 1. Find non-forfeit "scraped" matches missing player_stats on any map
    cur.execute("""
        SELECT DISTINCT sq.match_id
        FROM scrape_queue sq
        JOIN maps m ON m.match_id = sq.match_id AND m.mapstatsid IS NOT NULL
        LEFT JOIN player_stats ps ON ps.match_id = m.match_id AND ps.map_number = m.map_number
        WHERE sq.status = 'scraped' AND sq.is_forfeit = 0 AND ps.match_id IS NULL
    """)
    missing_stats = {r[0] for r in cur.fetchall()}

    # 2. Find non-forfeit "scraped" matches missing economy on any map
    cur.execute("""
        SELECT DISTINCT sq.match_id
        FROM scrape_queue sq
        JOIN maps m ON m.match_id = sq.match_id AND m.mapstatsid IS NOT NULL
        LEFT JOIN economy e ON e.match_id = m.match_id AND e.map_number = m.map_number
        WHERE sq.status = 'scraped' AND sq.is_forfeit = 0 AND e.match_id IS NULL
    """)
    missing_econ = {r[0] for r in cur.fetchall()}

    # 3. Find non-forfeit "scraped" matches where perf data is missing (kpr NULL)
    cur.execute("""
        SELECT DISTINCT sq.match_id
        FROM scrape_queue sq
        JOIN maps m ON m.match_id = sq.match_id AND m.mapstatsid IS NOT NULL
        JOIN player_stats ps ON ps.match_id = m.match_id AND ps.map_number = m.map_number
        WHERE sq.status = 'scraped' AND sq.is_forfeit = 0 AND ps.kpr IS NULL
    """)
    missing_perf = {r[0] for r in cur.fetchall()}

    incomplete = missing_stats | missing_econ | missing_perf
    print(f"Incomplete 'scraped' matches: {len(incomplete)}")
    print(f"  - missing player_stats: {len(missing_stats)}")
    print(f"  - missing economy:      {len(missing_econ)}")
    print(f"  - missing perf (kpr):   {len(missing_perf)}")

    if incomplete:
        ids = tuple(incomplete)
        placeholders = ",".join(["%s"] * len(ids))

        with conn:
            with conn.cursor() as c:
                # Delete all partial data for incomplete matches
                for table in ["economy", "kill_matrix", "round_history", "player_stats", "vetoes", "maps", "matches"]:
                    c.execute(f"DELETE FROM {table} WHERE match_id IN ({placeholders})", ids)
                    print(f"  deleted {table}: {c.rowcount:,} rows")
                c.execute(
                    f"UPDATE scrape_queue SET status = 'pending' WHERE match_id IN ({placeholders})",
                    ids,
                )
                print(f"  reset to pending: {c.rowcount}")

    # 4. Reset all 'failed' to 'pending'
    with conn:
        with conn.cursor() as c:
            c.execute("UPDATE scrape_queue SET status = 'pending' WHERE status = 'failed'")
            print(f"\nReset {c.rowcount} failed matches to pending")

    # Summary
    cur.execute("SELECT status, count(*) FROM scrape_queue GROUP BY status ORDER BY status")
    print("\nFinal queue:")
    for status, count in cur.fetchall():
        print(f"  {status}: {count:,}")

    db.close()


if __name__ == "__main__":
    main()
