# Phase 8: Data Validation - Research

**Researched:** 2026-02-16
**Domain:** Pydantic v2 data validation for scraped CS2 match data
**Confidence:** HIGH

## Summary

Phase 8 adds Pydantic v2 model validation as a layer between parsing and database persistence. The project already has Pydantic 2.12.5 installed (but not yet listed as a dependency in pyproject.toml). The codebase currently uses plain dataclasses for parser return types and plain dicts for database insertion -- validation will wrap these dicts in Pydantic models before they reach the repository layer.

The standard approach is: define Pydantic BaseModel classes matching each database entity (matches, maps, player_stats, round_history, economy, vetoes, match_players, kill_matrix), with field-level type constraints via `Field(ge=0)` etc., cross-field logic via `@model_validator(mode='after')`, and a warn-and-insert mechanism for unusual-but-valid values using Python's `warnings` module. A quarantine table stores serialized failed records with error details for later investigation.

**Primary recommendation:** Create one Pydantic model per database table, validate dicts via `Model.model_validate(data_dict)` in the orchestrator layer (between parsing and `repo.upsert_*()`), catch `ValidationError` to quarantine failures, and use `warnings.warn()` inside validators for unusual-but-valid values that should still be inserted.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | >=2.10 (have 2.12.5) | Data validation via type-annotated models | Industry standard for Python data validation; already installed |
| pydantic-core | >=2.41 (have 2.41.5) | Rust-based validation engine (auto-installed with pydantic) | Required by pydantic; provides speed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| warnings (stdlib) | built-in | Emit soft warnings for unusual-but-valid data | When values are valid but surprising (extreme ratings, unusual round counts) |
| logging (stdlib) | built-in | Log validation failures with context | Already used throughout project |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pydantic | attrs + cattrs | Less built-in validation; would need manual validators |
| Pydantic | marshmallow | Pydantic v2 is faster, already installed, better typing support |
| Pydantic | dataclasses + manual | Pydantic handles coercion, error aggregation, and JSON serialization natively |

**Installation:**
```bash
# Already installed, just add to pyproject.toml dependencies
# pydantic>=2.10
```

## Architecture Patterns

### Recommended Project Structure
```
src/scraper/
    models/
        __init__.py           # Re-exports all models
        match.py              # MatchModel, ForfeitMatchModel
        map.py                # MapModel
        player_stats.py       # PlayerStatsModel
        round_history.py      # RoundHistoryModel
        economy.py            # EconomyModel
        veto.py               # VetoModel
        match_player.py       # MatchPlayerModel
        kill_matrix.py        # KillMatrixModel
    validation.py             # validate_and_collect() wrapper, quarantine logic
    quarantine.py             # Quarantine table schema + repository methods
```

### Pattern 1: Validation Layer Between Parser and Repository

**What:** Validate dicts after parsing but before database insertion.
**When to use:** Every orchestrator that calls `repo.upsert_*()`.
**Example:**
```python
# Source: Pydantic docs (model_validate pattern)
from pydantic import ValidationError
from scraper.models import MatchModel

def validate_match(data: dict) -> tuple[dict | None, list[str]]:
    """Validate match data, return (validated_dict, warnings)."""
    warnings_list = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = MatchModel.model_validate(data)
            warnings_list = [str(w.message) for w in caught]
        return model.model_dump(), warnings_list
    except ValidationError as e:
        return None, [str(e)]
```

### Pattern 2: Pydantic Model with Field Constraints and Cross-Field Validators

**What:** Define models with ge/le/gt/lt constraints on fields, plus `@model_validator` for cross-field rules.
**When to use:** Every entity model.
**Example:**
```python
# Source: Pydantic docs (validators, fields)
from pydantic import BaseModel, Field, model_validator, field_validator
from typing_extensions import Self

class MapModel(BaseModel):
    match_id: int = Field(gt=0)
    map_number: int = Field(ge=1, le=5)
    mapstatsid: int | None = Field(default=None, gt=0)
    map_name: str
    team1_rounds: int | None = Field(default=None, ge=0)
    team2_rounds: int | None = Field(default=None, ge=0)
    team1_ct_rounds: int | None = Field(default=None, ge=0)
    team1_t_rounds: int | None = Field(default=None, ge=0)
    team2_ct_rounds: int | None = Field(default=None, ge=0)
    team2_t_rounds: int | None = Field(default=None, ge=0)
    scraped_at: str
    updated_at: str  # Set to scraped_at on insert
    source_url: str | None = None
    parser_version: str | None = None

    @model_validator(mode='after')
    def check_half_scores_sum(self) -> Self:
        """CT + T rounds should equal total for each team (regulation only)."""
        if (self.team1_ct_rounds is not None and self.team1_t_rounds is not None
                and self.team1_rounds is not None):
            reg_sum = self.team1_ct_rounds + self.team1_t_rounds
            if reg_sum > self.team1_rounds:
                raise ValueError(
                    f"team1 half scores ({reg_sum}) exceed total ({self.team1_rounds})"
                )
        return self
```

### Pattern 3: Warn-and-Insert for Unusual Values

**What:** Use `warnings.warn()` inside validators for values that are valid but surprising.
**When to use:** Rating values outside typical bounds, unusually high kill counts, etc.
**Example:**
```python
import warnings

class PlayerStatsModel(BaseModel):
    # ... fields ...
    rating_2: float | None = None
    rating_3: float | None = None

    @model_validator(mode='after')
    def warn_unusual_rating(self) -> Self:
        """Warn but don't reject unusual rating values."""
        for field_name, value in [("rating_2", self.rating_2), ("rating_3", self.rating_3)]:
            if value is not None and (value < 0.1 or value > 3.0):
                warnings.warn(
                    f"Unusual {field_name}={value} for player {self.player_id} "
                    f"(match {self.match_id}, map {self.map_number})",
                    stacklevel=2,
                )
        return self
```

### Pattern 4: Batch Validation with Quarantine

**What:** Validate a collection of dicts, quarantine failures, pass successes through.
**When to use:** In every orchestrator before the atomic `upsert_*_complete()` call.
**Example:**
```python
from pydantic import ValidationError

def validate_batch(
    items: list[dict],
    model_cls: type[BaseModel],
    context: dict,  # match_id, map_number, etc.
) -> tuple[list[dict], list[dict]]:
    """Validate a batch, return (valid_dicts, quarantine_records)."""
    valid = []
    quarantined = []
    for item in items:
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                validated = model_cls.model_validate(item)
                valid.append(validated.model_dump())
                for w in caught:
                    logger.warning("Validation warning: %s", w.message)
        except ValidationError as e:
            quarantined.append({
                "entity_type": model_cls.__name__,
                "raw_data": json.dumps(item, default=str),
                "error_details": str(e),
                "match_id": context.get("match_id"),
                "map_number": context.get("map_number"),
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.error(
                "Validation failed for %s (match %s, map %s): %s",
                model_cls.__name__,
                context.get("match_id"),
                context.get("map_number"),
                e,
            )
    return valid, quarantined
```

### Pattern 5: Separate Forfeit Model

**What:** A lighter model for forfeit matches that only validates the fields that exist.
**When to use:** When `is_forfeit` is True on the match overview result.
**Example:**
```python
class ForfeitMatchModel(BaseModel):
    """Lighter validation for forfeit matches -- fewer required fields."""
    match_id: int = Field(gt=0)
    date: str
    event_id: int = Field(gt=0)
    event_name: str
    team1_id: int = Field(gt=0)
    team1_name: str
    team2_id: int = Field(gt=0)
    team2_name: str
    team1_score: int | None = None  # May be absent on full forfeit
    team2_score: int | None = None
    best_of: int = Field(ge=1, le=5)
    is_lan: int = Field(ge=0, le=1)
    # No cross-field score checks -- forfeits have irregular scores
```

### Anti-Patterns to Avoid

- **Validation inside parsers:** Do NOT put Pydantic models inside `parse_match_overview()` etc. Keep parsers as pure functions returning dataclasses/dicts. Validation sits in the orchestrator layer.
- **Halting on first failure:** Never `raise` from the orchestrator on validation failures. Always continue processing other records and quarantine failures.
- **Validating provenance fields:** `scraped_at`, `updated_at`, `source_url`, `parser_version` are metadata. Validate their presence (not null) but don't enforce value constraints beyond type checking.
- **Strict type mode:** Do NOT use `ConfigDict(strict=True)` globally. The existing code passes ints where floats are expected (e.g., `adr=0` instead of `adr=0.0`). Pydantic's default coercion mode handles this correctly.
- **Kill/death cross-checks:** Per user decision, do NOT validate that team kills sum equals team deaths sum. Suicides, team kills, and bomb deaths cause legitimate mismatches.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Field type validation | Manual isinstance() checks | Pydantic `Field(ge=0)` constraints | Pydantic handles coercion, error messages, and aggregation |
| Cross-field validation | Manual if/else chains | `@model_validator(mode='after')` | Clean, declarative, part of the model definition |
| Error aggregation | Collecting errors in a list manually | Pydantic `ValidationError.errors()` | Returns structured list with field location, message, and input value |
| Dict-to-model conversion | Manual dict unpacking | `Model.model_validate(data_dict)` | Handles extra keys, missing keys, type coercion |
| Model-to-dict for DB | Manual dict building | `model.model_dump()` | Handles None, serialization, aliases |
| Validation error serialization | Custom error formatting | `str(validation_error)` | Human-readable multi-line error report with field paths |

**Key insight:** Pydantic v2 does everything needed here. The only custom code is the quarantine table, the warn-and-insert wrapper, and the cross-field business rules (round totals, player counts, economy alignment).

## Common Pitfalls

### Pitfall 1: Pydantic Rejects None for Optional Fields Without Default
**What goes wrong:** Declaring `field: int | None` without `= None` makes the field required (must be provided) but allows None as a value. If the dict omits the key entirely, validation fails.
**Why it happens:** Pydantic distinguishes between "field not provided" and "field is None."
**How to avoid:** Always use `field: int | None = None` for truly optional fields. For fields that must be present but can be None (like `team1_score` on forfeit matches), use `field: int | None` without default.
**Warning signs:** `ValidationError` with `missing` error type on fields you expected to be optional.

### Pitfall 2: Float Coercion Surprises
**What goes wrong:** Pydantic coerces `int` to `float` by default, but `str` to `float` only in non-strict mode.
**Why it happens:** The parsers return `float(text)` from HTML, which is always a float. But some fields like `adr` might be passed as `0` (int) from default values.
**How to avoid:** Use default (non-strict) mode. Fields typed as `float | None` will accept both int and float inputs.
**Warning signs:** Unexpected `ValidationError` on fields that were working in tests.

### Pitfall 3: Overtime Breaks Cross-Field Validation
**What goes wrong:** A rule like "CT rounds + T rounds == total rounds" fails for overtime matches because CT/T breakdown only covers regulation.
**Why it happens:** The half-score breakdown on HLTV only includes regulation halves. OT rounds are extra.
**How to avoid:** The rule should be: `ct_rounds + t_rounds <= total_rounds` (not ==). OT rounds cause the total to exceed the sum of CT+T. Single OT matches with one container don't even break out the OT rounds.
**Warning signs:** Valid overtime matches being quarantined.

### Pitfall 4: Economy Rows May Be Fewer Than Round History
**What goes wrong:** Validating that economy row count == round_history row count fails for MR12 overtime matches.
**Why it happens:** MR12 OT economy data is unavailable on HLTV. Economy pages only show 24 regulation rounds. Round history has all rounds (regulation + OT).
**How to avoid:** Economy rows should be validated as a subset of round history rounds (every economy round must exist in round_history, but not every round_history round needs an economy row).
**Warning signs:** Quarantining all MR12 overtime economy data.

### Pitfall 5: Player Count Validation Must Handle Edge Cases
**What goes wrong:** Validating "exactly 5 players per team" fails for some historical or unusual matches.
**Why it happens:** Some matches have coach stand-ins, substitutions, or technical issues that result in fewer or more player entries. Also, player_stats comes from map stats page while match_players comes from overview page -- the rosters may differ if a sub was used mid-series.
**How to avoid:** Validate at the map level (player_stats for a given match_id + map_number should have exactly 10 rows, split into 2 teams of 5). If not exactly 10, warn-and-insert rather than reject.
**Warning signs:** Quarantining legitimate matches with unusual player counts.

### Pitfall 6: Confusing `updated_at` with `scraped_at`
**What goes wrong:** Both are set to the same value on insert, but `updated_at` changes on UPSERT. Validating them as equal would fail on re-scraped data.
**Why it happens:** The UPSERT SQL sets `updated_at = excluded.scraped_at` on conflict, not `updated_at = excluded.updated_at`.
**How to avoid:** Validate both as non-empty ISO strings. Don't compare them to each other.

## Code Examples

### Complete Match Model
```python
# Source: Derived from migrations/001_initial_schema.sql + repository.py UPSERT_MATCH
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self
import warnings

class MatchModel(BaseModel):
    match_id: int = Field(gt=0)
    date: str  # ISO 8601 date string
    event_id: int = Field(gt=0)
    event_name: str = Field(min_length=1)
    team1_id: int = Field(gt=0)
    team1_name: str = Field(min_length=1)
    team2_id: int = Field(gt=0)
    team2_name: str = Field(min_length=1)
    team1_score: int | None = None  # None on full forfeit
    team2_score: int | None = None
    best_of: int = Field(ge=1, le=5)
    is_lan: int = Field(ge=0, le=1)
    match_url: str | None = None
    scraped_at: str = Field(min_length=1)
    source_url: str | None = None
    parser_version: str | None = None

    @model_validator(mode='after')
    def check_scores_consistency(self) -> Self:
        """Scores must be consistent with best_of format."""
        if self.team1_score is not None and self.team2_score is not None:
            max_maps = (self.best_of + 1) // 2  # e.g., BO3 -> max 2 wins
            if self.team1_score > max_maps or self.team2_score > max_maps:
                raise ValueError(
                    f"Score {self.team1_score}-{self.team2_score} exceeds "
                    f"max wins ({max_maps}) for BO{self.best_of}"
                )
            # Winner should have exactly max_maps wins (except forfeit)
            winner_score = max(self.team1_score, self.team2_score)
            if winner_score < max_maps:
                warnings.warn(
                    f"Winner has {winner_score} wins in BO{self.best_of} "
                    f"(expected {max_maps}) for match {self.match_id}",
                    stacklevel=2,
                )
        return self

    @model_validator(mode='after')
    def check_teams_different(self) -> Self:
        """Teams should have different IDs."""
        if self.team1_id == self.team2_id:
            raise ValueError(
                f"team1_id and team2_id are identical ({self.team1_id})"
            )
        return self
```

### Complete PlayerStats Model
```python
# Source: Derived from migrations/001_initial_schema.sql + 004_performance_economy.sql
class PlayerStatsModel(BaseModel):
    match_id: int = Field(gt=0)
    map_number: int = Field(ge=1, le=5)
    player_id: int = Field(gt=0)
    player_name: str | None = None
    team_id: int | None = Field(default=None, gt=0)
    # Core stats (from map stats page)
    kills: int | None = Field(default=None, ge=0)
    deaths: int | None = Field(default=None, ge=0)
    assists: int | None = Field(default=None, ge=0)
    flash_assists: int | None = Field(default=None, ge=0)
    hs_kills: int | None = Field(default=None, ge=0)
    kd_diff: int | None = None  # Can be negative
    adr: float | None = Field(default=None, ge=0.0)
    kast: float | None = Field(default=None, ge=0.0, le=100.0)
    fk_diff: int | None = None  # Can be negative
    rating_2: float | None = Field(default=None, ge=0.0)
    rating_3: float | None = Field(default=None, ge=0.0)
    # Performance page stats (Phase 7, may be None)
    kpr: float | None = Field(default=None, ge=0.0)
    dpr: float | None = Field(default=None, ge=0.0)
    impact: float | None = None  # Can be negative
    # Phase 6 extended fields
    opening_kills: int | None = Field(default=None, ge=0)
    opening_deaths: int | None = Field(default=None, ge=0)
    multi_kills: int | None = Field(default=None, ge=0)
    clutch_wins: int | None = Field(default=None, ge=0)
    traded_deaths: int | None = Field(default=None, ge=0)
    round_swing: float | None = None  # Signed percentage, can be negative
    mk_rating: float | None = Field(default=None, ge=0.0)
    # Provenance
    scraped_at: str = Field(min_length=1)
    updated_at: str  # Not validated beyond type -- set by SQL
    source_url: str | None = None
    parser_version: str | None = None

    @model_validator(mode='after')
    def check_kd_diff_consistency(self) -> Self:
        """kd_diff should equal kills - deaths when both are present."""
        if self.kills is not None and self.deaths is not None and self.kd_diff is not None:
            expected = self.kills - self.deaths
            if self.kd_diff != expected:
                raise ValueError(
                    f"kd_diff ({self.kd_diff}) != kills ({self.kills}) - "
                    f"deaths ({self.deaths}) = {expected}"
                )
        return self

    @model_validator(mode='after')
    def check_hs_kills_le_kills(self) -> Self:
        """Headshot kills cannot exceed total kills."""
        if self.hs_kills is not None and self.kills is not None:
            if self.hs_kills > self.kills:
                raise ValueError(
                    f"hs_kills ({self.hs_kills}) > kills ({self.kills})"
                )
        return self

    @model_validator(mode='after')
    def warn_unusual_values(self) -> Self:
        """Warn on unusual but valid values."""
        if self.rating_2 is not None and (self.rating_2 < 0.1 or self.rating_2 > 3.0):
            warnings.warn(
                f"Unusual rating_2={self.rating_2} for player {self.player_id}",
                stacklevel=2,
            )
        if self.rating_3 is not None and (self.rating_3 < 0.1 or self.rating_3 > 3.0):
            warnings.warn(
                f"Unusual rating_3={self.rating_3} for player {self.player_id}",
                stacklevel=2,
            )
        if self.adr is not None and self.adr > 200.0:
            warnings.warn(
                f"Unusual adr={self.adr} for player {self.player_id}",
                stacklevel=2,
            )
        return self
```

### Quarantine Table Migration
```sql
-- migrations/005_quarantine.sql
CREATE TABLE IF NOT EXISTS quarantine (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type   TEXT NOT NULL,      -- "MatchModel", "PlayerStatsModel", etc.
    match_id      INTEGER,            -- For easy lookup (nullable if match itself failed)
    map_number    INTEGER,            -- Nullable (not all entities are per-map)
    raw_data      TEXT NOT NULL,      -- JSON dump of the dict that failed validation
    error_details TEXT NOT NULL,      -- str(ValidationError) or error message
    quarantined_at TEXT NOT NULL,     -- ISO 8601 timestamp
    resolved      INTEGER DEFAULT 0  -- 0=pending, 1=resolved (re-processed or dismissed)
);

CREATE INDEX IF NOT EXISTS idx_quarantine_match ON quarantine(match_id);
CREATE INDEX IF NOT EXISTS idx_quarantine_type ON quarantine(entity_type);
CREATE INDEX IF NOT EXISTS idx_quarantine_resolved ON quarantine(resolved);
```

### Validation Integration in Orchestrator
```python
# How match_overview.py would change (conceptual)
from scraper.validation import validate_and_quarantine

# Inside the parse+persist loop, after building match_data dict:
match_result = validate_and_quarantine(
    data=match_data,
    model_cls=ForfeitMatchModel if result.is_forfeit else MatchModel,
    context={"match_id": match_id},
    repo=match_repo,  # For quarantine persistence
)
if match_result is None:
    # Quarantined -- skip this match entirely
    stats["failed"] += 1
    continue

# match_result is now a validated dict, safe to upsert
match_repo.upsert_match_overview(match_result, maps_data, vetoes_data, players_data)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pydantic v1 root_validator | Pydantic v2 `@model_validator(mode='after')` | Pydantic 2.0 (2023) | Different decorator API, returns Self |
| Pydantic v1 validator | Pydantic v2 `@field_validator` | Pydantic 2.0 (2023) | Must be classmethod, mode parameter |
| Schema class (dict) | `model_config = ConfigDict(...)` | Pydantic 2.0 (2023) | No inner Meta/Config class |
| `.dict()` | `.model_dump()` | Pydantic 2.0 (2023) | Old name deprecated |
| `.parse_obj()` | `.model_validate()` | Pydantic 2.0 (2023) | Old name deprecated |

**Deprecated/outdated:**
- `@validator` decorator: replaced by `@field_validator` in v2
- `@root_validator`: replaced by `@model_validator` in v2
- `class Config:`: replaced by `model_config = ConfigDict(...)` in v2
- `.dict()`, `.parse_obj()`, `.schema()`: all renamed with `model_` prefix in v2

## Specific Validation Rules Inventory

Based on analysis of the codebase and CONTEXT.md decisions:

### Structural Validations (Zero Tolerance -- reject)
| Rule | Entity | Fields | Logic |
|------|--------|--------|-------|
| Positive IDs | All | match_id, player_id, team_id, event_id | `Field(gt=0)` |
| Valid map_number | Map, PlayerStats, RoundHistory, Economy | map_number | `Field(ge=1, le=5)` |
| Non-empty provenance | All | scraped_at | `Field(min_length=1)` |
| Non-negative counts | PlayerStats | kills, deaths, assists, hs_kills, etc. | `Field(ge=0)` |
| Valid best_of | Match | best_of | `Field(ge=1, le=5)` |
| Valid is_lan | Match | is_lan | `Field(ge=0, le=1)` |
| kd_diff consistency | PlayerStats | kills, deaths, kd_diff | `kd_diff == kills - deaths` |
| fk_diff consistency | PlayerStats | opening_kills, opening_deaths, fk_diff | `fk_diff == opening_kills - opening_deaths` |
| hs_kills <= kills | PlayerStats | hs_kills, kills | Headshots cannot exceed total kills |
| Different teams | Match | team1_id, team2_id | `team1_id != team2_id` |
| Valid winner_side | RoundHistory | winner_side | Must be "CT" or "T" |
| Valid win_type | RoundHistory | win_type | Must be in {"elimination", "bomb_planted", "defuse", "time"} |
| Valid action | Veto | action | Must be in {"removed", "picked", "left_over"} |
| Valid buy_type | Economy | buy_type | Must be in {"full_eco", "semi_eco", "semi_buy", "full_buy"} |
| Valid matrix_type | KillMatrix | matrix_type | Must be in {"all", "first_kill", "awp"} |
| Valid team_num | MatchPlayer | team_num | `Field(ge=1, le=2)` |

### Cross-Field Validations (Zero Tolerance -- reject)
| Rule | Level | Logic |
|------|-------|-------|
| Score within best_of | Match | `max(team1_score, team2_score) <= (best_of + 1) // 2` |
| Half scores <= total | Map | `ct_rounds + t_rounds <= total_rounds` (not ==, due to OT) |
| Player count per map | Batch (10 PlayerStats per map) | Checked at orchestrator level, not model level |
| Economy-round alignment | Batch (economy round_number in round_history) | Checked at orchestrator level |

### Soft Validations (Warn-and-Insert)
| Rule | Entity | Logic |
|------|--------|-------|
| Unusual rating | PlayerStats | `rating_2 < 0.1 or rating_2 > 3.0` -- warn |
| Unusual ADR | PlayerStats | `adr > 200.0` -- warn |
| Winner score not max | Match | Winner has fewer than `(best_of+1)//2` wins -- warn (forfeit edge case) |
| High round count | Map | `team1_rounds + team2_rounds > 50` -- warn (extreme OT) |

### Not Validated (Per User Decision)
| Rule | Reason |
|------|--------|
| Kill/death cross-check between teams | Suicides, TKs, bomb deaths cause legitimate mismatches |
| Rating bounds hard rejection | Unusual values are rare but valid; warn-and-insert instead |

## Architecture Recommendation (Claude's Discretion)

**Recommendation: Separate validation layer, NOT integrated into parsers.**

Rationale:
1. Parsers remain pure functions (HTML in, dataclass out). This preserves testability -- parser tests verify extraction, validation tests verify business rules.
2. Validation sits in the orchestrator layer, where we already have access to match context (match_id, map_number, is_forfeit) needed for intelligent validation routing.
3. The quarantine table needs database access -- orchestrators already have `repo` references.
4. Different callers (Phase 5 orchestrator, Phase 6 orchestrator, Phase 7 orchestrator) can share the same validation models but apply different validation contexts.

**Placement:** After `parse_*()` returns data, before `repo.upsert_*()` is called.

**No standalone CLI validate command:** Not worth the complexity. Re-running the pipeline with UPSERT semantics already handles re-validation naturally. If validation rules change, the next pipeline run will apply them.

**No retroactive scan of existing data:** Same reasoning -- re-run the pipeline. The UPSERT pattern makes this idempotent.

**Cross-page consistency (team names):** Skip for now. Team name mismatches are already handled by the performance_economy orchestrator's positional fallback mechanism. Adding cross-page team name validation would add complexity without preventing data loss.

## Open Questions

1. **`updated_at` field in models:**
   - What we know: The UPSERT SQL sets `updated_at = excluded.scraped_at` on conflict. The orchestrators build dicts with `"scraped_at": now` and rely on SQL to set `updated_at`.
   - What's unclear: Should the Pydantic model include `updated_at` as a field? It's in the UPSERT but currently the dict passes `scraped_at` and the SQL references it via `excluded.scraped_at`.
   - Recommendation: Include `updated_at` in the model but don't validate its value beyond type. The dict currently passes `scraped_at` twice (once as `scraped_at`, once via SQL alias). Keep this pattern -- it works.

2. **Batch-level validation vs row-level:**
   - What we know: "Player count per team = 5" and "economy-round alignment" are batch-level checks (require looking at multiple rows together).
   - Recommendation: Validate individual rows with Pydantic models, then add batch-level checks as plain functions in `validation.py` that run after all individual validations pass. If batch checks fail, quarantine the entire batch (e.g., all player_stats for that map).

## Sources

### Primary (HIGH confidence)
- Pydantic official docs - validators: https://docs.pydantic.dev/latest/concepts/validators/
- Pydantic official docs - models: https://docs.pydantic.dev/latest/concepts/models/
- Pydantic official docs - fields: https://docs.pydantic.dev/latest/concepts/fields/
- Pydantic official docs - validation errors: https://docs.pydantic.dev/latest/errors/validation_errors/
- Codebase analysis: `src/scraper/repository.py` UPSERT SQL statements (define exact field sets)
- Codebase analysis: `migrations/001_initial_schema.sql` + `004_performance_economy.sql` (define DB schema)
- Codebase analysis: `src/scraper/match_parser.py`, `map_stats_parser.py`, `performance_parser.py`, `economy_parser.py` (define data shapes)
- Codebase analysis: `.planning/phases/03-page-reconnaissance/recon/edge-cases.md` (edge cases inventory)

### Secondary (MEDIUM confidence)
- Pydantic v2.12 release notes: https://pydantic.dev/articles/pydantic-v2-12-release
- WebSearch: Pydantic best practices patterns (verified against official docs)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Pydantic 2.12.5 already installed, official docs verified
- Architecture: HIGH - Based on direct codebase analysis of all parsers and orchestrators
- Validation rules: HIGH - Derived from actual UPSERT SQL, DB schema, and recon edge cases
- Pitfalls: HIGH - Derived from actual edge cases documented in Phase 3 recon
- Quarantine pattern: MEDIUM - Custom design, but simple enough to be low-risk

**Research date:** 2026-02-16
**Valid until:** 2026-04-16 (Pydantic v2 is stable; patterns unlikely to change)
