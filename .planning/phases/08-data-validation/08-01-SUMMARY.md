---
phase: 08-data-validation
plan: 01
subsystem: validation
tags: [pydantic, validation, quarantine, models, data-integrity]
depends_on:
  requires: [01-initial-schema, 04-performance-economy-migration]
  provides: [pydantic-models, quarantine-table, quarantine-repository]
  affects: [08-02-validation-wrapper, 08-03-orchestrator-integration]
tech_stack:
  added: [pydantic>=2.10]
  patterns: [model-per-table, field-constraints, cross-field-validators, warn-and-insert]
key_files:
  created:
    - src/scraper/models/__init__.py
    - src/scraper/models/match.py
    - src/scraper/models/map.py
    - src/scraper/models/player_stats.py
    - src/scraper/models/round_history.py
    - src/scraper/models/economy.py
    - src/scraper/models/veto.py
    - src/scraper/models/match_player.py
    - src/scraper/models/kill_matrix.py
    - migrations/005_quarantine.sql
  modified:
    - pyproject.toml
    - src/scraper/repository.py
decisions:
  - id: 08-01-01
    decision: "updated_at defaults to empty string in all models -- SQL handles it via excluded.scraped_at"
    rationale: "Orchestrator dicts don't pass updated_at explicitly; SQL sets it on INSERT/UPDATE"
  - id: 08-01-02
    decision: "No ConfigDict(strict=True) -- default coercion mode handles int-to-float (e.g. adr=0)"
    rationale: "Existing parsers return int for zero-value float fields; Pydantic coerces correctly"
  - id: 08-01-03
    decision: "warnings.warn() inside validators for soft validation, not logger.warning()"
    rationale: "Validation wrapper will catch warnings via catch_warnings context manager"
metrics:
  duration: "14 min"
  completed: "2026-02-16"
---

# Phase 8 Plan 01: Validation Models and Quarantine Summary

Pydantic v2 models for all 8 DB entity types plus forfeit variant, with quarantine table for rejected records.

## What Was Built

### Pydantic Models (9 classes)
- **MatchModel**: Field constraints on IDs (gt=0), scores, best_of (1-5), is_lan (0-1). Cross-field validators: score consistency against best_of, teams must differ. Soft warning when winner score < expected (forfeit edge case).
- **ForfeitMatchModel**: Same fields as MatchModel but no score consistency check. Only validates teams are different.
- **MapModel**: Half-score sum check (ct+t <= total, not ==, because OT rounds are not broken down). Soft warning for >50 total rounds.
- **PlayerStatsModel**: ge=0 on count fields, kd_diff/fk_diff/impact/round_swing allow negatives. Cross-field validators: kd_diff == kills-deaths, fk_diff == opening_kills-opening_deaths, hs_kills <= kills. Soft warnings for extreme ratings (<0.1 or >3.0) and unusual ADR (>200).
- **RoundHistoryModel**: winner_side enum {CT, T}, win_type enum {elimination, bomb_planted, defuse, time}.
- **EconomyModel**: buy_type enum {full_eco, semi_eco, semi_buy, full_buy} or None.
- **VetoModel**: action enum {removed, picked, left_over}.
- **MatchPlayerModel**: team_num (1-2), player_id (gt=0).
- **KillMatrixModel**: matrix_type enum {all, first_kill, awp}, kill counts (ge=0).

### Quarantine Infrastructure
- **migrations/005_quarantine.sql**: Schema version 5. Table with id (autoincrement), entity_type, match_id, map_number, raw_data (JSON), error_details, quarantined_at, resolved flag. Three indexes for match lookup, type filtering, and resolved status.
- **repository.py**: INSERT_QUARANTINE SQL constant, insert_quarantine() and get_quarantine_count() methods on MatchRepository.

### Dependency
- pydantic>=2.10 added to pyproject.toml (already installed as 2.12.5).

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 08-01-01 | updated_at defaults to "" in all models | SQL handles it via excluded.scraped_at; orchestrator dicts don't pass it |
| 08-01-02 | No strict mode -- default coercion | Existing parsers pass int for zero-value float fields |
| 08-01-03 | warnings.warn() for soft validation | Validation wrapper catches via catch_warnings context |

## Deviations from Plan

None -- plan executed exactly as written.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | cf66ea1 | Pydantic v2 models for all 9 entity types + pyproject.toml |
| 2 | bca9190 | Quarantine migration (005) + repository methods |

## Verification Results

All 6 verification checks passed:
1. All 9 model classes import from scraper.models
2. MatchModel rejects match_id=0, same team IDs, score > best_of
3. PlayerStatsModel rejects kd_diff != kills-deaths
4. RoundHistoryModel rejects winner_side="X"
5. Schema version = 5 after migration
6. Repository inserts and counts quarantine records

## Next Phase Readiness

Ready for 08-02 (validation wrapper). Models and quarantine infrastructure are in place. The validation wrapper will:
- Accept dicts, validate via model_validate(), catch ValidationError
- Log warnings from catch_warnings context
- Route failures to quarantine via insert_quarantine()
