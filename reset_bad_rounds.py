"""Reset maps with incomplete round_history or economy data for re-scraping.

Targets maps where:
  1. Round count doesn't match score (round_history race condition)
  2. Economy has fewer rounds than round_history
  3. Economy rounds with only 1 team instead of 2

For each affected map:
  - Deletes player_stats, round_history, economy, kill_matrix rows
  - Resets perf_attempts to 0
  - The scraper picks them up automatically as pending

Usage:
    docker compose run --rm scraper python reset_bad_rounds.py
    # Or with --dry-run to see what would be affected:
    docker compose run --rm scraper python reset_bad_rounds.py --dry-run
"""
import sys
sys.path.insert(0, "src")

from scraper.db import Database


def main():
    dry_run = "--dry-run" in sys.argv
    db = Database()
    db.initialize()
    conn = db.conn
    cur = conn.cursor()

    # 1. Maps where round_history count != score (excluding Default/forfeit maps)
    cur.execute("""
        SELECT m.match_id, m.map_number
        FROM maps m
        JOIN (
            SELECT match_id, map_number, count(*) AS actual
            FROM round_history
            GROUP BY match_id, map_number
        ) rh ON rh.match_id = m.match_id AND rh.map_number = m.map_number
        WHERE m.team1_rounds IS NOT NULL
          AND m.team2_rounds IS NOT NULL
          AND m.team1_rounds + m.team2_rounds != rh.actual
          AND m.map_name != 'Default'
    """)
    bad_rounds = set(cur.fetchall())

    # 2. Maps where economy has fewer rounds than round_history
    cur.execute("""
        SELECT m.match_id, m.map_number
        FROM maps m
        JOIN (
            SELECT match_id, map_number, count(DISTINCT round_number) AS econ_rounds
            FROM economy
            GROUP BY match_id, map_number
        ) e ON e.match_id = m.match_id AND e.map_number = m.map_number
        JOIN (
            SELECT match_id, map_number, count(*) AS rh_rounds
            FROM round_history
            GROUP BY match_id, map_number
        ) rh ON rh.match_id = m.match_id AND rh.map_number = m.map_number
        WHERE rh.rh_rounds > e.econ_rounds
    """)
    bad_econ = set(cur.fetchall())

    # 3. Economy rounds with only 1 team
    cur.execute("""
        SELECT DISTINCT match_id, map_number
        FROM (
            SELECT match_id, map_number, round_number, count(*) AS team_count
            FROM economy
            GROUP BY match_id, map_number, round_number
            HAVING count(*) != 2
        ) sub
    """)
    bad_econ_teams = set(cur.fetchall())

    all_bad = bad_rounds | bad_econ | bad_econ_teams

    print(f"Maps with bad round_history:     {len(bad_rounds):,}")
    print(f"Maps with bad economy count:     {len(bad_econ):,}")
    print(f"Maps with single-team economy:   {len(bad_econ_teams):,}")
    print(f"Total unique maps to reset:      {len(all_bad):,}")

    if not all_bad:
        print("Nothing to reset.")
        db.close()
        return

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        db.close()
        return

    # Delete data for affected maps and reset perf_attempts
    total = {"player_stats": 0, "round_history": 0, "economy": 0, "kill_matrix": 0}
    with conn:
        with conn.cursor() as c:
            for match_id, map_number in all_bad:
                for table in ["economy", "kill_matrix", "round_history", "player_stats"]:
                    c.execute(
                        f"DELETE FROM {table} WHERE match_id = %s AND map_number = %s",
                        (match_id, map_number),
                    )
                    total[table] += c.rowcount
                # Reset perf_attempts so performance page gets re-scraped
                c.execute(
                    "UPDATE maps SET perf_attempts = 0 WHERE match_id = %s AND map_number = %s",
                    (match_id, map_number),
                )

    print(f"\nDeleted rows:")
    for table, count in total.items():
        print(f"  {table}: {count:,}")
    print(f"\nReset {len(all_bad):,} maps for re-scraping")

    # Summary
    cur.execute("SELECT status, count(*) FROM scrape_queue GROUP BY status ORDER BY status")
    print("\nQueue status:")
    for status, count in cur.fetchall():
        print(f"  {status}: {count:,}")

    db.close()


if __name__ == "__main__":
    main()
