# Phase 5: Match Overview Extraction - Context

**Gathered:** 2026-02-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Parse match detail pages for teams, scores, format, event, vetoes, rosters, and per-map stats links. This phase fetches and parses match overview pages only — sub-page fetching (map stats, performance, economy) is deferred to Phases 6-7.

</domain>

<decisions>
## Implementation Decisions

### Forfeit & edge-case handling
- Forfeit matches (mapname "Default"): store partial overview data (teams, event, date, forfeit flag). Skip sub-page fetches.
- Deleted matches ("Match deleted" text) or invalid pages: flag as 'deleted'/'invalid' in scrape queue. Don't attempt parsing. Move on.
- Unplayed maps (e.g., map 3 in a 2-0 BO3): store as entries with an unplayed flag. Preserves map pool/pick order info.

### Fetch-parse-store flow
- Fetch-first batching: fetch N match overview pages and store raw HTML, then parse the batch.
- On fetch failure mid-batch (e.g., Cloudflare block): discard the entire partial batch. Retry from scratch next run.
- Phase 5 fetches match overview pages ONLY. Sub-page HTML fetching happens in Phases 6-7.

### Veto parsing
- BO1 matches DO have vetoes (alternating bans until one map remains). Vetoes exist for all competitive matches.
- Store the full ordered veto sequence: every step with team attribution (e.g., "Team A banned Mirage", "Team B picked Inferno").
- If veto box has unexpected/unparseable content: set veto to null, log error. Still store the rest of the match data.

### Data completeness
- LAN/online flag: default to "online" when detection is ambiguous or missing.

### Claude's Discretion
- Forfeit detection: single signal (mapname "Default") vs multi-signal (also check missing divs, page text). Claude picks based on recon reliability.
- Fetch batch size: Claude sizes based on rate limiting patterns and Cloudflare risk.
- Match format source: extract from first veto-box or infer from map count. Claude picks most reliable.
- Required vs optional fields: Claude defines which fields reject a match vs allow null.
- DB commit strategy: per-match or per-batch commit after parsing.
- Scrape queue status progression after successful overview parse.

</decisions>

<specifics>
## Specific Ideas

- BO1 vetoes are alternating bans (not picks) — parser must handle this format alongside BO3/BO5 pick-ban sequences.
- User wants unplayed maps stored to preserve the full map pool context for analysis.
- Batch discard on failure is preferred over keeping partial batches — clean state over partial progress.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 05-match-overview-extraction*
*Context gathered: 2026-02-15*
