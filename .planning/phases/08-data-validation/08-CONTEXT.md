# Phase 8: Data Validation - Context

**Gathered:** 2026-02-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Pydantic schema enforcement and cross-field integrity checks for all scraped data. Every record is validated before database insertion, catching data quality issues immediately. This phase does NOT add new scraping capabilities, new data fields, or pipeline orchestration (Phase 9).

</domain>

<decisions>
## Implementation Decisions

### Validation strictness
- **Unusual but valid values:** Warn and insert — log a warning but allow the record (unusual doesn't mean wrong)
- **Structural violations:** Zero tolerance — wrong types, missing required fields, negative kill counts always reject the record
- **Forfeit matches:** Separate lighter Pydantic model for forfeits — only validates the fields that exist (teams, score, date)
- **Overtime matches:** Separate OT validation path with its own constraints (economy resets, round count expectations distinct from regulation)

### Failure handling
- **Failed records:** Both log to file AND store in quarantine table — real-time monitoring plus queryable batch review
- **Pipeline behavior:** Never halt on validation failures — always continue, review failures after run completes
- **Reprocessing:** No special reprocess command needed — just re-run the pipeline; existing UPSERT logic handles re-processing naturally

### Validation scope
- **Cross-field checks enforced:**
  - Round totals match score (sum of round_history entries equals final map score)
  - Player count per team = 5 for every non-forfeit map
  - Economy-round alignment (economy rows exist for each round in round_history, no extras)
- **Kill/death cross-checks:** NOT enforced — suicides, team kills, and bomb deaths cause legitimate mismatches
- **Rating bounds:** NOT explicitly enforced (covered by warn-and-insert for unusual values)
- **Performance metrics (KPR, DPR, impact):** Allow nulls — some old or low-tier matches may genuinely lack performance pages
- **Cross-page consistency (e.g., team names across pages):** Claude's discretion

### Retroactive validation & reporting
- **Run summary reports:** Not needed — individual log lines per failure are sufficient
- **Standalone validate command:** Claude's discretion
- **Rule migration (re-validate old data with new rules):** Claude's discretion
- **Architecture (separate layer vs integrated into parsers):** Claude's discretion

### Claude's Discretion
- Quarantine table schema (minimal IDs vs full data snapshot) — pick the right balance of storage vs usefulness
- Whether to include cross-page consistency checks (team names matching across overview/stats pages)
- Whether to build a standalone `validate` CLI command for retroactive DB validation
- Whether new validation rules should retroactively scan existing data
- Whether validation sits as a separate layer between parsing and persistence, or is integrated into parsers via Pydantic model returns

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 08-data-validation*
*Context gathered: 2026-02-16*
