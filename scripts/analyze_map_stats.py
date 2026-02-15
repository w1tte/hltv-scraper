#!/usr/bin/env python3
"""
Temporary analysis script for HLTV map stats pages.
Loads ALL mapstats-*-stats.html.gz samples and systematically discovers CSS selectors.

Output: printed analysis that will be used to create the selector map document.
"""

import gzip
import re
from pathlib import Path
from bs4 import BeautifulSoup

RECON_DIR = Path("data/recon")

def load_samples():
    """Load all map stats HTML samples."""
    samples = {}
    for f in sorted(RECON_DIR.glob("mapstats-*-stats.html.gz")):
        mapstatsid = f.name.split("-")[1]
        html = gzip.decompress(f.read_bytes()).decode("utf-8")
        soup = BeautifulSoup(html, "lxml")
        samples[mapstatsid] = soup
        print(f"Loaded {f.name} ({len(html):,} chars)")
    return samples

def test_selector(samples, selector, label="", limit_text=80):
    """Test a CSS selector across all samples, return results."""
    results = {}
    for sid, soup in samples.items():
        elements = soup.select(selector)
        texts = []
        for el in elements:
            t = el.get_text(strip=True)[:limit_text]
            texts.append(t)
        results[sid] = {"count": len(elements), "texts": texts, "elements": elements}
    return results

def print_selector_results(samples, selector, label=""):
    """Print selector test results in a compact format."""
    results = test_selector(samples, selector)
    counts = [r["count"] for r in results.values()]
    consistent = len(set(counts)) == 1
    print(f"\n  {'[OK]' if consistent else '[VARY]'} {label or selector}")
    for sid, r in results.items():
        preview = r["texts"][:3]
        if len(r["texts"]) > 3:
            preview.append(f"... +{len(r['texts'])-3} more")
        print(f"    {sid}: count={r['count']}  values={preview}")
    return results

def analyze_section1_metadata(samples):
    """Section 1: Match/map metadata at top of page."""
    print("\n" + "="*80)
    print("SECTION 1: MATCH/MAP METADATA")
    print("="*80)

    # Team names
    print_selector_results(samples, ".team-left", "Team left container")
    print_selector_results(samples, ".team-right", "Team right container")
    print_selector_results(samples, ".team-left .teamName", "Team left name (.teamName)")

    # Try alternative team name selectors
    for sel in [".team-left a", ".team-left .bold", ".team-right .bold",
                ".team-left .team-name", ".team-right .team-name"]:
        print_selector_results(samples, sel, f"Team name alt: {sel}")

    # Let's look at team container structure
    print("\n  --- Team container HTML snippet (first sample) ---")
    first_soup = list(samples.values())[0]
    team_left = first_soup.select_one(".team-left")
    if team_left:
        print(f"    {team_left.prettify()[:1000]}")
    team_right = first_soup.select_one(".team-right")
    if team_right:
        print(f"    {team_right.prettify()[:1000]}")

    # Match info box
    print_selector_results(samples, ".match-info-box", "Match info box")
    print_selector_results(samples, ".match-info-box-con", "Match info box container")

    # Match info rows
    print_selector_results(samples, ".match-info-row", "Match info rows")

    # Check match-info-row contents
    print("\n  --- Match info rows content (first sample) ---")
    for row in first_soup.select(".match-info-row"):
        label = row.select_one(".match-info-row-label")
        right = row.select_one(".right")
        print(f"    Label: {label.get_text(strip=True) if label else 'N/A'} | "
              f"Right: {right.get_text(strip=True) if right else 'N/A'}")

    # Half results
    print_selector_results(samples, ".match-info-row .right", "Half results (right)")

    # Map name
    for sel in [".match-info-box .mapname", ".match-info-box-con .mapname",
                ".match-info-row .mapname", ".mapname"]:
        print_selector_results(samples, sel, f"Map name: {sel}")

    # Overtime indicator
    print("\n  --- Checking for overtime indicators ---")
    ot_samples = ["162345", "206389"]  # Known OT maps
    for sid in ot_samples:
        if sid in samples:
            soup = samples[sid]
            info_rows = soup.select(".match-info-row")
            print(f"  Overtime sample {sid} match-info-rows:")
            for row in info_rows:
                print(f"    {row.get_text(strip=True)[:100]}")

    # Standard headline
    print_selector_results(samples, ".standard-headline", "Standard headline")

def analyze_section2_scoreboard(samples):
    """Section 2: Per-player scoreboard."""
    print("\n" + "="*80)
    print("SECTION 2: PER-PLAYER SCOREBOARD")
    print("="*80)

    # Stats table
    print_selector_results(samples, ".stats-table", "All stats tables")
    print_selector_results(samples, ".stats-table.totalstats", "Stats table (totalstats)")

    # Check table headers
    print("\n  --- Table headers (first sample) ---")
    first_soup = list(samples.values())[0]
    for i, table in enumerate(first_soup.select(".stats-table.totalstats")):
        print(f"\n  Table {i+1}:")
        headers = table.select("th")
        for h in headers:
            classes = h.get("class", [])
            print(f"    <th class='{' '.join(classes)}'>{h.get_text(strip=True)}</th>")

    # Player rows
    print_selector_results(samples, ".stats-table.totalstats tr", "Table rows (all)")
    print_selector_results(samples, ".stats-table.totalstats tbody tr", "Table rows (tbody)")

    # Player name and ID
    print_selector_results(samples, ".st-player", "Player cell (.st-player)")
    print_selector_results(samples, ".st-player a", "Player link (.st-player a)")

    # Check player ID source
    print("\n  --- Player ID source (first sample, first table) ---")
    first_table = first_soup.select_one(".stats-table.totalstats")
    if first_table:
        for row in first_table.select("tbody tr")[:2]:
            player_link = row.select_one(".st-player a")
            if player_link:
                href = player_link.get("href", "")
                print(f"    Player: {player_link.get_text(strip=True)} | href: {href}")
            # Check for data-player-id
            player_id_el = row.select_one("[data-player-id]")
            if player_id_el:
                print(f"    data-player-id: {player_id_el.get('data-player-id')}")

    # Stats columns
    stat_cols = [
        (".st-kills", "Kills"),
        (".st-assists", "Assists"),
        (".st-deaths", "Deaths"),
        (".st-kdratio", "K/D ratio"),
        (".st-kddiff", "K/D diff"),
        (".st-adr", "ADR"),
        (".st-fkdiff", "FK diff"),
        (".st-rating", "Rating"),
    ]
    for sel, label in stat_cols:
        print_selector_results(samples, sel, f"{label} ({sel})")

    # KAST
    for sel in [".st-kast", ".st-kast-pct", "td.st-kast"]:
        print_selector_results(samples, sel, f"KAST: {sel}")

    # Rating description
    print_selector_results(samples, ".ratingDesc", "Rating description")

    # Check for flash assists column
    for sel in [".st-flashassists", ".st-flash-assists", "td[class*=flash]"]:
        print_selector_results(samples, sel, f"Flash assists: {sel}")

    # Which team is which table?
    print("\n  --- Team-to-table mapping (first sample) ---")
    for i, table in enumerate(first_soup.select(".stats-table.totalstats")):
        # Check surrounding context
        parent = table.parent
        if parent:
            # Look for team identifier near the table
            prev_sibs = []
            for sib in table.previous_siblings:
                if hasattr(sib, 'get_text'):
                    t = sib.get_text(strip=True)
                    if t:
                        prev_sibs.append(t[:50])
                if len(prev_sibs) >= 3:
                    break
            print(f"  Table {i+1} preceding text: {prev_sibs[:2]}")

        # Get first player from each table
        first_player = table.select_one("tbody tr .st-player a")
        if first_player:
            print(f"  Table {i+1} first player: {first_player.get_text(strip=True)}")

    # Row count per table
    print("\n  --- Row count per table (all samples) ---")
    for sid, soup in samples.items():
        tables = soup.select(".stats-table.totalstats")
        row_counts = [len(t.select("tbody tr")) for t in tables]
        print(f"    {sid}: {len(tables)} tables, rows per table: {row_counts}")

    # Full row HTML snippet
    print("\n  --- Full row HTML snippet (first sample, first row) ---")
    first_table = first_soup.select_one(".stats-table.totalstats")
    if first_table:
        first_row = first_table.select_one("tbody tr")
        if first_row:
            print(first_row.prettify()[:2000])

    # Check all td classes in a row
    print("\n  --- All td classes in first row ---")
    if first_table:
        first_row = first_table.select_one("tbody tr")
        if first_row:
            for td in first_row.select("td"):
                classes = td.get("class", [])
                text = td.get_text(strip=True)[:50]
                print(f"    class='{' '.join(classes)}' text='{text}'")

def analyze_section3_round_history(samples):
    """Section 3: Round history."""
    print("\n" + "="*80)
    print("SECTION 3: ROUND HISTORY")
    print("="*80)

    print_selector_results(samples, ".round-history-con", "Round history container")
    print_selector_results(samples, ".round-history-team-row", "Round history team rows")
    print_selector_results(samples, ".round-history-outcome", "Round outcomes (total)")
    print_selector_results(samples, ".round-history-half", "Round history half")

    # Half separators
    for sel in [".round-history-bar", ".round-history-separator", ".round-history-ct",
                ".round-history-t"]:
        print_selector_results(samples, sel, f"Half sep: {sel}")

    # Round outcome details
    first_soup = list(samples.values())[0]

    print("\n  --- Round history container HTML snippet (first sample) ---")
    rh_con = first_soup.select_one(".round-history-con")
    if rh_con:
        print(rh_con.prettify()[:3000])

    # Check round outcome attributes/classes
    print("\n  --- Round outcome element details (first sample) ---")
    outcomes = first_soup.select(".round-history-outcome")
    for o in outcomes[:6]:
        classes = o.get("class", [])
        title = o.get("title", "")
        src_img = o.select_one("img")
        img_src = src_img.get("src", "") if src_img else "no img"
        print(f"    classes={classes} title='{title}' img={img_src}")

    # Check unique outcome types across all samples
    print("\n  --- Unique round outcome types across all samples ---")
    all_titles = set()
    all_img_srcs = set()
    for sid, soup in samples.items():
        for o in soup.select(".round-history-outcome"):
            title = o.get("title", "")
            if title:
                all_titles.add(title)
            img = o.select_one("img")
            if img:
                src = img.get("src", "")
                # Extract just the filename
                all_img_srcs.add(src.split("/")[-1] if "/" in src else src)
    print(f"    Unique titles: {sorted(all_titles)}")
    print(f"    Unique img srcs: {sorted(all_img_srcs)}")

    # Overtime analysis
    print("\n  --- Overtime round history analysis ---")
    ot_ids = ["162345", "206389"]
    for sid in ot_ids:
        if sid in samples:
            soup = samples[sid]
            rows = soup.select(".round-history-team-row")
            print(f"\n  OT sample {sid}:")
            print(f"    Team rows: {len(rows)}")
            for i, row in enumerate(rows):
                outcomes = row.select(".round-history-outcome")
                bars = row.select(".round-history-bar")
                halves = row.select(".round-history-half")
                print(f"    Row {i+1}: {len(outcomes)} outcomes, {len(bars)} bars, {len(halves)} halves")
                # Show all child elements
                children = list(row.children)
                child_types = []
                for c in children:
                    if hasattr(c, 'name') and c.name:
                        cls = c.get("class", [])
                        child_types.append(f"{c.name}.{'.'.join(cls)}" if cls else c.name)
                print(f"    Children types: {child_types[:40]}")

    # Regular sample for comparison
    print("\n  --- Regular (non-OT) round history for comparison ---")
    regular_id = "164779"  # 8-13, should be exactly 21 rounds
    if regular_id in samples:
        soup = samples[regular_id]
        rows = soup.select(".round-history-team-row")
        print(f"  Regular sample {regular_id}:")
        for i, row in enumerate(rows):
            outcomes = row.select(".round-history-outcome")
            bars = row.select(".round-history-bar")
            halves = row.select(".round-history-half")
            print(f"    Row {i+1}: {len(outcomes)} outcomes, {len(bars)} bars, {len(halves)} halves")

    # CT/T side round counts
    print("\n  --- CT/T side analysis ---")
    # Check match-info-row for half scores
    for sid in ["164779", "162345", "206389"]:
        if sid in samples:
            soup = samples[sid]
            print(f"\n  Sample {sid}:")
            info_rows = soup.select(".match-info-row")
            for row in info_rows:
                label_el = row.select_one(".match-info-row-label")
                if label_el:
                    label = label_el.get_text(strip=True)
                else:
                    label = "no-label"
                texts = [el.get_text(strip=True) for el in row.select("*")]
                print(f"    {label}: {row.get_text(' | ', strip=True)[:120]}")

def analyze_section4_overview_table(samples):
    """Section 4: Overview/comparison table."""
    print("\n" + "="*80)
    print("SECTION 4: OVERVIEW TABLE (TEAM COMPARISON)")
    print("="*80)

    print_selector_results(samples, ".overview-table", "Overview table")
    print_selector_results(samples, ".overview-table tr", "Overview table rows")

    # Check overview table structure
    first_soup = list(samples.values())[0]
    print("\n  --- Overview table HTML snippet (first sample) ---")
    ov_table = first_soup.select_one(".overview-table")
    if ov_table:
        print(ov_table.prettify()[:3000])

    # Row labels
    print("\n  --- Overview table row labels (first sample) ---")
    if ov_table:
        for row in ov_table.select("tr"):
            cells = row.select("td")
            texts = [c.get_text(strip=True) for c in cells]
            print(f"    {texts}")

    # Team columns
    print_selector_results(samples, ".team1-column", "Team 1 column")
    print_selector_results(samples, ".team2-column", "Team 2 column")

    # Consistency check
    print("\n  --- Overview table row count per sample ---")
    for sid, soup in samples.items():
        tables = soup.select(".overview-table")
        for i, t in enumerate(tables):
            rows = t.select("tr")
            print(f"    {sid} table {i+1}: {len(rows)} rows")

def analyze_section5_other_elements(samples):
    """Section 5: Other elements on the page."""
    print("\n" + "="*80)
    print("SECTION 5: OTHER ELEMENTS")
    print("="*80)

    # Stat leader boxes
    print_selector_results(samples, ".most-x-box", "Stat leader boxes")

    # Check stat leader content
    first_soup = list(samples.values())[0]
    print("\n  --- Stat leader boxes (first sample) ---")
    for box in first_soup.select(".most-x-box"):
        print(f"    {box.get_text(' | ', strip=True)[:100]}")

    # Highlighted player
    print_selector_results(samples, ".highlighted-player", "Highlighted player")

    # Performance graph
    print_selector_results(samples, ".graph.small", "Performance graph (small)")
    print_selector_results(samples, "[data-fusionchart-config]", "FusionChart config")

    # Navigation links to sub-pages
    for sel in [".stats-match-map-nav", "a[href*='performance']", "a[href*='economy']",
                ".stats-match-nav", ".nav-tabs a", ".tabs a"]:
        print_selector_results(samples, sel, f"Nav links: {sel}")

    # Check for eco-adjusted toggle
    for sel in [".eco-adjusted", "[class*=eco]", ".toggle", ".switch",
                "[data-toggle]", "[class*=adjusted]"]:
        print_selector_results(samples, sel, f"Eco toggle: {sel}")

    # Check for any data attributes we might have missed
    print("\n  --- Elements with data-* attributes (first sample, unique) ---")
    data_attrs = set()
    for el in first_soup.find_all(True):
        for attr in el.attrs:
            if attr.startswith("data-"):
                data_attrs.add(attr)
    print(f"    {sorted(data_attrs)}")

    # Check for link to match overview page
    for sel in ["a[href*='/matches/']", ".stats-match-map-nav a"]:
        r = test_selector(samples, sel, limit_text=100)
        first_result = list(r.values())[0]
        if first_result["count"] > 0:
            print(f"\n  {sel}:")
            # Show first few hrefs
            for el in first_result["elements"][:5]:
                href = el.get("href", "")
                text = el.get_text(strip=True)[:50]
                print(f"    href={href} text={text}")

    # Check sub-page navigation structure
    print("\n  --- Looking for sub-page tabs/navigation ---")
    # Common nav patterns
    for sel in [".stats-match-map", ".stats-match-maps", ".stats-top-menu",
                ".stats-sub-navigation", "div.stats-match"]:
        r = test_selector(samples, sel)
        fc = list(r.values())[0]["count"]
        if fc > 0:
            print(f"  Found: {sel} (count={fc})")
            el = list(r.values())[0]["elements"][0]
            print(f"    HTML: {str(el)[:500]}")

def analyze_team_identification(samples):
    """Deep dive into how teams are identified and mapped to tables."""
    print("\n" + "="*80)
    print("TEAM IDENTIFICATION DEEP DIVE")
    print("="*80)

    for sid, soup in list(samples.items())[:3]:
        print(f"\n  --- Sample {sid} ---")

        # Team names from page header
        team_left = soup.select_one(".team-left")
        team_right = soup.select_one(".team-right")

        if team_left:
            # Get team name from link text
            link = team_left.select_one("a")
            if link:
                print(f"  Team left: {link.get_text(strip=True)} (href={link.get('href', '')})")
        if team_right:
            link = team_right.select_one("a")
            if link:
                print(f"  Team right: {link.get_text(strip=True)} (href={link.get('href', '')})")

        # Stats tables - which team?
        tables = soup.select(".stats-table.totalstats")
        for i, table in enumerate(tables):
            players = [a.get_text(strip=True) for a in table.select(".st-player a")]
            print(f"  Table {i+1} players: {players}")

        # Check if there's a team indicator above each table
        # Look for elements between/before tables
        content_area = soup.select_one(".columns")
        if content_area:
            for child in content_area.children:
                if hasattr(child, 'name') and child.name:
                    cls = child.get("class", [])
                    text = child.get_text(strip=True)[:80] if child.get_text(strip=True) else ""
                    if text or "stats-table" in " ".join(cls):
                        print(f"  Content area child: <{child.name} class='{' '.join(cls)}'> {text[:50]}")


def analyze_full_page_structure(samples):
    """Analyze the overall page structure to understand layout."""
    print("\n" + "="*80)
    print("FULL PAGE STRUCTURE ANALYSIS")
    print("="*80)

    first_soup = list(samples.values())[0]
    first_sid = list(samples.keys())[0]

    # Find main content area
    for sel in [".contentCol", ".colCon", "#content", "main", ".columns",
                ".match-page", ".stats-match"]:
        els = first_soup.select(sel)
        if els:
            print(f"  {sel}: found {len(els)}")

    # Look at direct children of body or main content
    body = first_soup.select_one("body")
    if body:
        print("\n  --- Top-level body children ---")
        for child in body.children:
            if hasattr(child, 'name') and child.name:
                cls = child.get("class", [])
                cid = child.get("id", "")
                text_preview = child.get_text(strip=True)[:30]
                print(f"    <{child.name} class='{' '.join(cls)}' id='{cid}'> [{text_preview}...]")

    # Look for the stats content wrapper
    for sel in [".stats-section", ".stats-content", ".contentCol .colCon",
                ".standard-box"]:
        els = first_soup.select(sel)
        if els:
            print(f"\n  {sel}: {len(els)} elements found")


if __name__ == "__main__":
    print("Loading map stats samples...")
    samples = load_samples()
    print(f"\nLoaded {len(samples)} samples")
    print("="*80)

    analyze_full_page_structure(samples)
    analyze_section1_metadata(samples)
    analyze_section2_scoreboard(samples)
    analyze_section3_round_history(samples)
    analyze_section4_overview_table(samples)
    analyze_section5_other_elements(samples)
    analyze_team_identification(samples)

    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)
