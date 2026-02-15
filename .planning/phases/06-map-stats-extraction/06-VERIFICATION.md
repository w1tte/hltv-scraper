---
phase: 06-map-stats-extraction
verified: 2026-02-15T23:39:35Z
status: passed
score: 4/4 must-haves verified
---

# Phase 6: Map Stats Extraction Verification Report

**Phase Goal:** Every played map has its per-player scoreboard and round-by-round history extracted from the map overview page
**Verified:** 2026-02-15T23:39:35Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Scraper extracts full per-player scoreboard (kills, deaths, assists, flash assists, HS kills, K/D diff, ADR, KAST%, first kills diff, rating) | VERIFIED | `PlayerStats` dataclass has all 18 fields. `_extract_scoreboard()` (lines 337-464) extracts each from specific CSS selectors. 51 parser tests pass across 12 real HTML samples including Rating 2.0 and 3.0. Parametrized smoke test confirms 10 players extracted from every sample. |
| 2 | Scraper extracts round-by-round history with outcome types (bomb plant, elimination, defuse, time runout) | VERIFIED | `RoundOutcome` dataclass captures round_number, winner_team_id, winner_side, win_type. `_extract_round_history()` (lines 467-543) maps SVG filenames to outcome types via `OUTCOME_MAP`. Tests verify round counts match scores, sequential numbering through OT, valid win types. |
| 3 | Scraper extracts CT/T side round wins per team | VERIFIED | `_extract_half_breakdown()` (lines 229-296) extracts ct-color/t-color spans, determines starting side, computes per-team CT/T round counts. `TestHalfBreakdown` validates non-negative values, valid starting side, halves sum to regulation. |
| 4 | All extracted map stats are persisted to DB linked to correct match and map | VERIFIED | `run_map_stats()` orchestrator (170 lines) builds dicts with `match_id` and `map_number` from pending queue, calls `upsert_map_stats_complete()` which atomically writes `player_stats` + `round_history` in single transaction. Orchestrator test `test_fetches_parses_persists_map_stats` verifies 10 player_stats rows and round_history rows written, and map no longer pending after persistence. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Exists | Substantive | Wired | Status |
|----------|----------|--------|-------------|-------|--------|
| `src/scraper/map_stats_parser.py` | Pure function parser with 3 dataclasses | YES (543 lines) | YES -- 3 dataclasses, 8 functions, full CSS selector extraction, no stubs | YES -- imported by `map_stats.py`, tested by `test_map_stats_parser.py` | VERIFIED |
| `src/scraper/map_stats.py` | Async orchestrator `run_map_stats()` | YES (170 lines) | YES -- fetch-first batching, per-map error handling, atomic persistence, stats dict return | YES -- imports `parse_map_stats`, calls `get_pending_map_stats()`, `upsert_map_stats_complete()`, `storage.save/load` | VERIFIED |
| `tests/test_map_stats_parser.py` | Parser tests against 12 real HTML samples | YES (336 lines) | YES -- 51 tests across 9 classes, parametrized over all 12 samples | YES -- imports and exercises parser, all 51 pass | VERIFIED |
| `tests/test_map_stats.py` | Orchestrator tests with mocked client and real DB | YES (266 lines) | YES -- 6 tests covering full pipeline, fetch failure, parse failure, storage, stats dict | YES -- imports orchestrator + all dependencies, all 6 pass | VERIFIED |
| `src/scraper/repository.py` (extended) | `get_pending_map_stats()` and `upsert_map_stats_complete()` methods | YES | YES -- NOT EXISTS subquery, atomic multi-table write | YES -- called by orchestrator, tested by 9 new tests in test_repository.py | VERIFIED |
| `src/scraper/config.py` (extended) | `map_stats_batch_size` field | YES | YES -- defaults to 10 | YES -- used by orchestrator's `get_pending_map_stats(limit=config.map_stats_batch_size)` | VERIFIED |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `map_stats.py` | `map_stats_parser.py` | `from scraper.map_stats_parser import parse_map_stats` | WIRED | Line 13 imports, line 100 calls `parse_map_stats(html, mapstatsid)`, result consumed for building persistence dicts |
| `map_stats.py` | `repository.py` | `match_repo.get_pending_map_stats()` and `match_repo.upsert_map_stats_complete()` | WIRED | Line 53 queries pending maps, line 151 persists atomically |
| `map_stats.py` | `storage.py` | `storage.save()` and `storage.load()` with `page_type="map_stats"` | WIRED | Lines 70-75 save, line 95 loads; storage supports `map_stats` page type with mapstatsid parameter |
| `map_stats.py` | `config.py` | `config.map_stats_batch_size` and `config.base_url` | WIRED | Line 53 uses batch size, lines 65-66 construct URL |
| `repository.py` | `player_stats` + `round_history` tables | SQL INSERT via `UPSERT_PLAYER_STATS` and `UPSERT_ROUND` | WIRED | `upsert_map_stats_complete()` iterates both lists in single transaction |
| `repository.py` | `maps` table | `GET_PENDING_MAP_STATS` SQL with NOT EXISTS subquery | WIRED | Returns maps with mapstatsid but no player_stats rows |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| MAPS-01: Per-player scoreboard extraction | SATISFIED | `PlayerStats` has all 10 required stat categories (kills, deaths, assists, flash assists, HS kills, K/D diff, ADR, KAST%, first kills diff, rating). 51 tests pass across 12 samples. |
| MAPS-02: Round-by-round history with outcome types | SATISFIED | `RoundOutcome` captures round_number, winner_team_id, winner_side, win_type. OUTCOME_MAP covers all 5 outcome types (ct_win, t_win, bomb_exploded, bomb_defused, stopwatch). Tests verify counts match scores. |
| MAPS-03: CT/T side round wins per team | SATISFIED | `MapStats` stores team_left_ct_rounds, team_left_t_rounds, team_right_ct_rounds, team_right_t_rounds, team_left_starting_side. `TestHalfBreakdown` validates correctness. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/scraper/map_stats_parser.py` | 353 | `return []` | Info | Defensive guard when <2 scoreboard tables found; logs warning. Not a stub. |
| `src/scraper/map_stats_parser.py` | 482 | `return []` | Info | Defensive guard when no round-history containers; logs warning. Not a stub. |
| `src/scraper/map_stats.py` | 127-129 | `"kpr": None, "dpr": None, "impact": None` | Info | Intentionally left for Phase 7 (Performance extraction). Columns are nullable in schema. Not a Phase 6 gap. |

No blockers or warnings found. All findings are informational.

### Test Results

**Full Phase 6 test suite:** 97/97 passed (195s)
- `tests/test_map_stats_parser.py`: 51 passed (parser across 12 samples)
- `tests/test_map_stats.py`: 6 passed (orchestrator pipeline)
- `tests/test_repository.py`: 40 passed (including 9 new Phase 6 methods)

### Human Verification Required

None. All success criteria are structurally verifiable:
- Scoreboard fields verified by dataclass definitions and test assertions against real HTML
- Round history verified by parametrized tests checking count, sequence, and valid outcome types
- CT/T breakdown verified by dedicated test class
- Database persistence verified by orchestrator tests with real SQLite

---

_Verified: 2026-02-15T23:39:35Z_
_Verifier: Claude (gsd-verifier)_
