#!/usr/bin/env python3
"""
Programmatic CSS selector analysis for HLTV match overview pages.

Loads all match-*-overview.html.gz samples from data/recon/ and systematically
discovers/verifies CSS selectors using BeautifulSoup. Outputs structured analysis
to stdout for documentation.
"""

import gzip
import re
import json
from pathlib import Path
from bs4 import BeautifulSoup

RECON_DIR = Path("data/recon")

# Match metadata from manifest for reference
MATCH_INFO = {
    2366498: {"teams": "n00rg vs FALKE", "format": "BO1", "edge": "overtime 16-14", "lan": False},
    2367432: {"teams": "9 Pandas vs FORZE", "format": "BO3", "edge": "", "lan": False},
    2371321: {"teams": "Limitless vs BOSS", "format": "BO1", "edge": "tier-3", "lan": False},
    2371389: {"teams": "PARIVISION vs B8", "format": "BO3", "edge": "", "lan": False},
    2373741: {"teams": "Sharks vs Fluxo", "format": "BO1", "edge": "", "lan": False},
    2377467: {"teams": "Tunisia vs kONO", "format": "BO1", "edge": "national-team LAN", "lan": True},
    2380434: {"teams": "adalYamigos vs Bounty Hunters", "format": "BO1", "edge": "FORFEIT", "lan": False},
    2384993: {"teams": "Getting Info vs BOSS", "format": "BO5", "edge": "BO5 + OT + partial forfeit", "lan": False},
    2389951: {"teams": "Vitality vs G2", "format": "BO3", "edge": "tier-1 LAN", "lan": True},
}


def load_samples():
    """Load all match overview HTML samples."""
    samples = {}
    for f in sorted(RECON_DIR.glob("match-*-overview.html.gz")):
        match_id = int(f.name.split("-")[1])
        html = gzip.decompress(f.read_bytes()).decode("utf-8")
        soup = BeautifulSoup(html, "lxml")
        samples[match_id] = soup
    return samples


def test_selector(samples, selector, extract_fn=None, label=""):
    """Test a CSS selector against all samples. Returns results dict."""
    results = {}
    for mid, soup in samples.items():
        elements = soup.select(selector)
        if extract_fn:
            values = []
            for el in elements:
                try:
                    values.append(extract_fn(el))
                except Exception as e:
                    values.append(f"ERROR: {e}")
            results[mid] = {"count": len(elements), "values": values}
        else:
            results[mid] = {"count": len(elements), "texts": [el.get_text(strip=True)[:100] for el in elements[:5]]}
    return results


def print_selector_results(label, results, show_values=True):
    """Print formatted results for a selector test."""
    print(f"\n  {label}:")
    for mid, data in results.items():
        info = MATCH_INFO[mid]
        count = data["count"]
        vals = data.get("values", data.get("texts", []))
        status = "OK" if count > 0 else "MISSING"
        vals_str = str(vals[:3]) if show_values and vals else ""
        if len(vals_str) > 120:
            vals_str = vals_str[:120] + "..."
        print(f"    {mid} ({info['format']:>3}, {info['edge'][:20]:>20}): count={count} {status} {vals_str}")


def analyze_section1_metadata(samples):
    """Section 1: Match metadata analysis."""
    print("\n" + "=" * 80)
    print("SECTION 1: MATCH METADATA")
    print("=" * 80)

    # Team 1 name
    r = test_selector(samples, ".team1-gradient .teamName")
    print_selector_results("Team 1 name (.team1-gradient .teamName)", r)

    # Team 2 name
    r = test_selector(samples, ".team2-gradient .teamName")
    print_selector_results("Team 2 name (.team2-gradient .teamName)", r)

    # Team 1 ID from href
    r = test_selector(samples, ".team1-gradient a[href*='/team/']",
                       extract_fn=lambda el: el.get("href", ""))
    print_selector_results("Team 1 href (.team1-gradient a[href*='/team/'])", r)

    # Team 2 ID from href
    r = test_selector(samples, ".team2-gradient a[href*='/team/']",
                       extract_fn=lambda el: el.get("href", ""))
    print_selector_results("Team 2 href (.team2-gradient a[href*='/team/'])", r)

    # Team rankings
    r = test_selector(samples, ".teamRanking a")
    print_selector_results("Team rankings (.teamRanking a)", r)

    # Alternative: Team rankings with more specific paths
    r = test_selector(samples, ".team1-gradient .teamRanking a")
    print_selector_results("Team 1 ranking (.team1-gradient .teamRanking a)", r)
    r = test_selector(samples, ".team2-gradient .teamRanking a")
    print_selector_results("Team 2 ranking (.team2-gradient .teamRanking a)", r)

    # Winner indicator - .won class
    print("\n  Winner indicator (.won class):")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        t1_won = soup.select(".team1-gradient .won")
        t2_won = soup.select(".team2-gradient .won")
        # Also check parent containers
        t1_grad = soup.select_one(".team1-gradient")
        t2_grad = soup.select_one(".team2-gradient")
        t1_has_won = "won" in (t1_grad.get("class", []) if t1_grad else [])
        t2_has_won = "won" in (t2_grad.get("class", []) if t2_grad else [])
        print(f"    {mid} ({info['format']:>3}): .team1 .won={len(t1_won)}, .team2 .won={len(t2_won)}, "
              f"team1-gradient.won={t1_has_won}, team2-gradient.won={t2_has_won}")

    # Let's look at how the won class actually appears
    print("\n  Winner - examining score containers:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        # Check elements with 'won' class anywhere in the team gradient area
        for team_sel in [".team1-gradient", ".team2-gradient"]:
            container = soup.select_one(team_sel)
            if container:
                won_els = container.select("[class*='won']")
                for el in won_els:
                    print(f"    {mid} ({info['format']:>3}): {team_sel} -> {el.name}.{el.get('class')} text='{el.get_text(strip=True)[:50]}'")

    # Match date
    r = test_selector(samples, ".timeAndEvent .date[data-unix]",
                       extract_fn=lambda el: el.get("data-unix", ""))
    print_selector_results("Match date (.timeAndEvent .date[data-unix])", r)

    # Event name
    r = test_selector(samples, ".timeAndEvent .event a")
    print_selector_results("Event name (.timeAndEvent .event a)", r)

    # Event ID from href
    r = test_selector(samples, ".timeAndEvent .event a[href*='/events/']",
                       extract_fn=lambda el: el.get("href", ""))
    print_selector_results("Event href (.timeAndEvent .event a[href*='/events/'])", r)

    # Format and LAN/Online - .preformatted-text
    r = test_selector(samples, ".preformatted-text")
    print_selector_results("Format text (.preformatted-text)", r)

    # Let's look at the actual text content more carefully
    print("\n  Format text - full content:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        els = soup.select(".preformatted-text")
        for el in els:
            text = el.get_text(strip=True)
            print(f"    {mid} ({info['format']:>3}): '{text}'")

    # Also check for a .match-page element or similar that might contain format
    r = test_selector(samples, ".padding.preformatted-text")
    print_selector_results("Alt format (.padding.preformatted-text)", r)


def analyze_section2_maps(samples):
    """Section 2: Map holders and scores."""
    print("\n" + "=" * 80)
    print("SECTION 2: MAP HOLDERS AND SCORES")
    print("=" * 80)

    # Map holders
    r = test_selector(samples, ".mapholder")
    print_selector_results("Map holders (.mapholder)", r)

    # Map names
    r = test_selector(samples, ".mapholder .mapname")
    print_selector_results("Map names (.mapholder .mapname)", r)

    # Detailed map info per sample
    print("\n  Map details per sample:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        holders = soup.select(".mapholder")
        print(f"\n    {mid} ({info['format']:>3}, {info['edge'][:30]}):")
        for i, holder in enumerate(holders):
            map_name = holder.select_one(".mapname")
            map_name_text = map_name.get_text(strip=True) if map_name else "N/A"

            # Scores
            left_score = holder.select_one(".results-left .results-team-score")
            right_score = holder.select_one(".results-right .results-team-score")
            left_text = left_score.get_text(strip=True) if left_score else "N/A"
            right_text = right_score.get_text(strip=True) if right_score else "N/A"

            # Half scores
            half_scores = holder.select(".results-center-half-score")
            half_texts = [hs.get_text(strip=True) for hs in half_scores]

            # Stats link
            stats_link = holder.select_one(".results-stats a[href]") or holder.select_one("a.results-stats[href]")
            stats_href = stats_link.get("href", "") if stats_link else "N/A"

            # Check for pick info
            pick_el = holder.select_one(".results-center .pick")
            pick_text = pick_el.get_text(strip=True) if pick_el else ""

            print(f"      Map {i+1}: {map_name_text:>10} | Score: {left_text}-{right_text} | "
                  f"Halves: {half_texts} | Stats: {stats_href[:60]} | Pick: {pick_text}")

    # Check which team is left vs right
    print("\n  Team left/right mapping:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        t1_name_el = soup.select_one(".team1-gradient .teamName")
        t2_name_el = soup.select_one(".team2-gradient .teamName")
        t1_name = t1_name_el.get_text(strip=True) if t1_name_el else "?"
        t2_name = t2_name_el.get_text(strip=True) if t2_name_el else "?"
        print(f"    {mid}: team1={t1_name}, team2={t2_name}")

    # results-stats link patterns
    print("\n  Stats link href patterns:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        stats_links = soup.select(".results-stats[href]") + soup.select("a.results-stats[href]")
        if not stats_links:
            # Try broader search
            stats_links = soup.select("[href*='mapstatsid']")
        hrefs = [a.get("href", "") for a in stats_links]
        print(f"    {mid} ({info['format']:>3}): {hrefs}")

    # Check unplayed maps (for BO3/BO5)
    print("\n  Unplayed map detection:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        holders = soup.select(".mapholder")
        for i, holder in enumerate(holders):
            map_name = holder.select_one(".mapname")
            map_text = map_name.get_text(strip=True) if map_name else ""
            left_score = holder.select_one(".results-left .results-team-score")
            left_text = left_score.get_text(strip=True) if left_score else ""
            # Check for "TBD" or empty or "-"
            if map_text in ("TBD", "") or left_text in ("-", ""):
                classes = " ".join(holder.get("class", []))
                print(f"    {mid} map {i+1}: name='{map_text}' score='{left_text}' classes='{classes}'")
                # Print raw HTML snippet (abbreviated)
                html_snip = str(holder)[:300]
                print(f"      HTML: {html_snip}")


def analyze_section3_vetoes(samples):
    """Section 3: Veto sequence."""
    print("\n" + "=" * 80)
    print("SECTION 3: VETO SEQUENCE")
    print("=" * 80)

    # Veto box
    r = test_selector(samples, ".veto-box")
    print_selector_results("Veto box (.veto-box)", r)

    # Detailed veto analysis
    print("\n  Veto structure per sample:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        veto_box = soup.select_one(".veto-box")
        if not veto_box:
            print(f"\n    {mid} ({info['format']:>3}, {info['edge'][:25]}): NO VETO BOX FOUND")
            # Try alternate selectors
            alt_veto = soup.select_one(".standard-box.veto-box") or soup.select_one("[class*='veto']")
            if alt_veto:
                print(f"      Found alternate: {alt_veto.name}.{alt_veto.get('class')}")
            continue

        print(f"\n    {mid} ({info['format']:>3}, {info['edge'][:25]}):")

        # Direct children
        children = veto_box.find_all(recursive=False)
        print(f"      Direct children: {len(children)}")
        for j, child in enumerate(children):
            text = child.get_text(strip=True)[:80]
            classes = " ".join(child.get("class", []))
            print(f"        [{j}] <{child.name} class='{classes}'> {text}")

        # Try to find veto lines
        veto_lines = veto_box.select("div")
        print(f"      All div children: {len(veto_lines)}")
        for vline in veto_lines[:10]:
            text = vline.get_text(strip=True)
            if text and len(text) > 5:
                classes = " ".join(vline.get("class", []))
                print(f"        <div class='{classes}'> {text[:80]}")

    # Print raw veto box HTML for key samples (BO1, BO3, BO5)
    key_samples = {
        "BO1": 2366498,
        "BO3": 2389951,
        "BO5": 2384993,
        "FORFEIT": 2380434,
    }
    print("\n  Raw veto HTML snippets:")
    for label, mid in key_samples.items():
        soup = samples[mid]
        veto_box = soup.select_one(".veto-box")
        if veto_box:
            html = str(veto_box)
            # Remove excessive whitespace
            html = re.sub(r'\n\s*\n', '\n', html)
            print(f"\n    --- {label} (match {mid}) ---")
            print(f"    {html[:1500]}")
            if len(html) > 1500:
                print(f"    ... ({len(html)} chars total)")
        else:
            print(f"\n    --- {label} (match {mid}) --- NO VETO BOX")


def analyze_section4_rosters(samples):
    """Section 4: Player rosters."""
    print("\n" + "=" * 80)
    print("SECTION 4: PLAYER ROSTERS")
    print("=" * 80)

    # Player containers
    r = test_selector(samples, "div.players")
    print_selector_results("Player containers (div.players)", r)

    # More specific: try .lineups
    r = test_selector(samples, ".lineups")
    print_selector_results("Lineups container (.lineups)", r)

    # Player cells
    r = test_selector(samples, ".players .player")
    print_selector_results("Player cells (.players .player)", r)

    # Text-ellipsis inside player area
    r = test_selector(samples, ".players .text-ellipsis")
    print_selector_results("Player names (.players .text-ellipsis)", r)

    # data-player-id
    r = test_selector(samples, "[data-player-id]",
                       extract_fn=lambda el: el.get("data-player-id", ""))
    print_selector_results("data-player-id attributes", r)

    # Player links with /player/ in href
    r = test_selector(samples, "a[href*='/player/']")
    print_selector_results("Player links (a[href*='/player/'])", r, show_values=False)

    # Detailed player roster per sample
    print("\n  Detailed roster analysis:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        print(f"\n    {mid} ({info['format']:>3}, {info['edge'][:25]}):")

        # Find player containers
        player_containers = soup.select("div.players")
        if not player_containers:
            # Try alternative
            player_containers = soup.select(".lineups .players")
        if not player_containers:
            player_containers = soup.select(".lineups")

        for ci, container in enumerate(player_containers[:4]):
            # Try to find team name associated with this container
            # Look for team header nearby
            classes = " ".join(container.get("class", []))
            print(f"      Container {ci} (class='{classes}'):")

            # Find player elements
            player_els = container.select("[data-player-id]")
            if not player_els:
                player_els = container.select("a[href*='/player/']")

            for pel in player_els[:6]:
                pid = pel.get("data-player-id", "")
                href = pel.get("href", "")
                name_el = pel.select_one(".text-ellipsis") or pel
                name = name_el.get_text(strip=True)
                # Flag/nationality
                flag = pel.select_one("img.flag")
                flag_title = flag.get("title", "") if flag else ""
                print(f"        Player: {name:>15} | ID: {pid:>6} | href: {href:>30} | flag: {flag_title}")

    # Check how team1 vs team2 players are distinguished
    print("\n  Team attribution for players:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        # Look at lineup structure
        lineups = soup.select_one(".lineups")
        if lineups:
            # Check children structure
            teams = lineups.select(".players")
            print(f"    {mid}: .lineups has {len(teams)} .players divs")
            for ti, team in enumerate(teams):
                # Check for table structure
                table = team.select_one("table")
                tbody = team.select_one("tbody")
                trs = team.select("tr")
                player_count = len(team.select("[data-player-id]"))
                print(f"      .players[{ti}]: table={table is not None}, tbody={tbody is not None}, "
                      f"trs={len(trs)}, players_with_id={player_count}")

    # Print raw roster HTML for one sample
    print("\n  Raw roster HTML snippet (match 2389951 - Vitality vs G2):")
    soup = samples[2389951]
    lineups = soup.select_one(".lineups")
    if lineups:
        html = str(lineups)[:3000]
        html = re.sub(r'\n\s*\n', '\n', html)
        print(f"    {html}")


def analyze_section5_other(samples):
    """Section 5: Other elements."""
    print("\n" + "=" * 80)
    print("SECTION 5: OTHER ELEMENTS")
    print("=" * 80)

    # Head-to-head
    r = test_selector(samples, ".head-to-head-listing")
    print_selector_results("Head-to-head (.head-to-head-listing)", r)

    r = test_selector(samples, ".head-to-head-listing tr")
    print_selector_results("H2H rows (.head-to-head-listing tr)", r)

    # Streams
    r = test_selector(samples, ".stream-box")
    print_selector_results("Stream boxes (.stream-box)", r)

    r = test_selector(samples, ".streams")
    print_selector_results("Streams container (.streams)", r)

    # Demo/GOTV/pickup links
    r = test_selector(samples, "[href*='demo']")
    print_selector_results("Demo links ([href*='demo'])", r)

    r = test_selector(samples, "[href*='gotv']")
    print_selector_results("GOTV links ([href*='gotv'])", r)

    # Highlight replay
    r = test_selector(samples, "[data-highlight-embed]")
    print_selector_results("Highlight embeds ([data-highlight-embed])", r)

    # Additional metadata
    r = test_selector(samples, ".match-info-box")
    print_selector_results("Match info box (.match-info-box)", r)

    # Standard box sections
    r = test_selector(samples, ".standard-box")
    print_selector_results("Standard boxes (.standard-box)", r, show_values=False)

    # Ads/promos
    r = test_selector(samples, "[class*='ad-']")
    print_selector_results("Ad elements ([class*='ad-'])", r, show_values=False)

    r = test_selector(samples, "[class*='sponsor']")
    print_selector_results("Sponsor elements ([class*='sponsor'])", r, show_values=False)


def analyze_forfeit_differences(samples):
    """Analyze what's different on forfeit page vs normal."""
    print("\n" + "=" * 80)
    print("FORFEIT/WALKOVER ANALYSIS")
    print("=" * 80)

    forfeit_mid = 2380434
    normal_mid = 2389951  # Vitality vs G2

    forfeit_soup = samples[forfeit_mid]
    normal_soup = samples[normal_mid]

    key_selectors = {
        "Team 1 name": ".team1-gradient .teamName",
        "Team 2 name": ".team2-gradient .teamName",
        "Team 1 href": ".team1-gradient a[href*='/team/']",
        "Team 2 href": ".team2-gradient a[href*='/team/']",
        "Rankings": ".teamRanking a",
        "Date": ".timeAndEvent .date[data-unix]",
        "Event": ".timeAndEvent .event a",
        "Map holders": ".mapholder",
        "Map names": ".mapholder .mapname",
        "Map scores left": ".results-left .results-team-score",
        "Map scores right": ".results-right .results-team-score",
        "Half scores": ".results-center-half-score",
        "Stats links": "a.results-stats[href]",
        "Veto box": ".veto-box",
        "Player containers": "div.players",
        "Player IDs": "[data-player-id]",
        "Head-to-head": ".head-to-head-listing",
        "Streams": ".stream-box",
        "Lineups": ".lineups",
        "preformatted-text": ".preformatted-text",
    }

    print(f"\n  Comparison: Forfeit ({forfeit_mid}) vs Normal ({normal_mid})")
    print(f"  {'Selector':<30} {'Forfeit':>10} {'Normal':>10} {'Status':<15}")
    print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*15}")

    for name, sel in key_selectors.items():
        f_count = len(forfeit_soup.select(sel))
        n_count = len(normal_soup.select(sel))
        status = "SAME" if f_count == n_count else ("MISSING" if f_count == 0 else "DIFFERENT")
        print(f"  {name:<30} {f_count:>10} {n_count:>10} {status:<15}")

    # Check forfeit map holder details
    print(f"\n  Forfeit match map holders:")
    holders = forfeit_soup.select(".mapholder")
    for i, h in enumerate(holders):
        print(f"    Map holder {i}:")
        print(f"      HTML: {str(h)[:500]}")

    # Partial forfeit (BO5)
    print(f"\n  Partial forfeit BO5 ({2384993}):")
    bo5_soup = samples[2384993]
    holders = bo5_soup.select(".mapholder")
    for i, h in enumerate(holders):
        map_name = h.select_one(".mapname")
        map_text = map_name.get_text(strip=True) if map_name else "N/A"
        stats = h.select_one("a.results-stats[href]") or h.select_one(".results-stats[href]")
        has_stats = stats is not None
        left = h.select_one(".results-left .results-team-score")
        right = h.select_one(".results-right .results-team-score")
        l_text = left.get_text(strip=True) if left else "N/A"
        r_text = right.get_text(strip=True) if right else "N/A"
        print(f"    Map {i+1}: {map_text:>10} | Score: {l_text}-{r_text} | Stats link: {has_stats}")


def analyze_deep_structure(samples):
    """Deep structural analysis for key elements."""
    print("\n" + "=" * 80)
    print("DEEP STRUCTURE ANALYSIS")
    print("=" * 80)

    # Analyze overall score container
    print("\n  Overall match score structure:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        # Try common score selectors
        for sel in [".team1-gradient .won", ".team2-gradient .won",
                    ".team1-gradient .lost", ".team2-gradient .lost"]:
            els = soup.select(sel)
            if els:
                for el in els:
                    print(f"    {mid} ({info['format']:>3}): {sel} -> text='{el.get_text(strip=True)}' "
                          f"classes={el.get('class')}")

    # Check for the overall series score (e.g., "2" - "1" in BO3)
    print("\n  Series score elements:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        # Check .team1-gradient and .team2-gradient for score elements
        for team_sel in [".team1-gradient", ".team2-gradient"]:
            container = soup.select_one(team_sel)
            if container:
                # Look for score-related elements
                score_els = container.select("[class*='score']")
                for el in score_els:
                    print(f"    {mid} ({info['format']:>3}): {team_sel} -> "
                          f"{el.name}.{el.get('class')} = '{el.get_text(strip=True)}'")

    # Analyze half-score structure more carefully
    print("\n  Half-score detailed structure:")
    for mid in [2366498, 2389951, 2384993]:  # OT BO1, BO3, BO5
        soup = samples[mid]
        info = MATCH_INFO[mid]
        holders = soup.select(".mapholder")
        print(f"\n    {mid} ({info['format']}, {info['edge'][:30]}):")
        for i, h in enumerate(holders[:3]):
            map_name = h.select_one(".mapname")
            map_text = map_name.get_text(strip=True) if map_name else "N/A"
            # Find ALL half-score related elements
            center = h.select_one(".results-center")
            if center:
                center_html = str(center)[:800]
                center_html = re.sub(r'\n\s*\n', '\n', center_html)
                print(f"      Map {i+1} ({map_text}): .results-center HTML:")
                for line in center_html.split('\n')[:20]:
                    print(f"        {line.strip()}")

    # Check the map pick indicators
    print("\n  Map pick indicators:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        picks = soup.select(".results-center .pick")
        if picks:
            for p in picks:
                print(f"    {mid} ({info['format']:>3}): pick text='{p.get_text(strip=True)}' "
                      f"classes={p.get('class')}")

    # Analyze the results-stats link more carefully
    print("\n  Stats link analysis:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        # Try multiple selector patterns
        for sel in [".results-stats[href]", "a.results-stats", ".results-stats a", "[href*='mapstatsid']"]:
            links = soup.select(sel)
            if links:
                print(f"    {mid} ({info['format']:>3}): {sel} found {len(links)}")
                for l in links[:3]:
                    href = l.get("href", "")
                    print(f"      href='{href}'")


def analyze_additional_selectors(samples):
    """Try additional selectors that might be useful."""
    print("\n" + "=" * 80)
    print("ADDITIONAL SELECTOR EXPLORATION")
    print("=" * 80)

    # Check for countdown/live elements
    r = test_selector(samples, ".countdown")
    if any(d["count"] > 0 for d in r.values()):
        print_selector_results("Countdown (.countdown)", r)

    # Check for match-page wrapper
    r = test_selector(samples, ".match-page")
    print_selector_results("Match page wrapper (.match-page)", r, show_values=False)

    # Check contentCol (main content area)
    r = test_selector(samples, ".contentCol")
    print_selector_results("Content column (.contentCol)", r, show_values=False)

    # Past matches between teams
    r = test_selector(samples, ".past-matches")
    print_selector_results("Past matches (.past-matches)", r, show_values=False)

    # Highlights
    r = test_selector(samples, ".highlight-video")
    print_selector_results("Highlight video (.highlight-video)", r, show_values=False)

    r = test_selector(samples, "[data-highlight-embed]")
    print_selector_results("Highlight embed ([data-highlight-embed])", r, show_values=False)

    # HLTV confirm / popups
    r = test_selector(samples, ".hltv-modal")
    print_selector_results("Modal (.hltv-modal)", r, show_values=False)

    # Map pick / ban indicator detail
    print("\n  Map holder class analysis:")
    for mid, soup in samples.items():
        info = MATCH_INFO[mid]
        holders = soup.select(".mapholder")
        for i, h in enumerate(holders):
            classes = " ".join(h.get("class", []))
            # Check for played vs unplayed indicators
            played_indicator = h.select_one(".played")
            optional = h.select_one(".optional")
            print(f"    {mid} map {i}: classes='{classes}', played={played_indicator is not None}, optional={optional is not None}")


if __name__ == "__main__":
    print("Loading samples...")
    samples = load_samples()
    print(f"Loaded {len(samples)} samples: {sorted(samples.keys())}")

    analyze_section1_metadata(samples)
    analyze_section2_maps(samples)
    analyze_section3_vetoes(samples)
    analyze_section4_rosters(samples)
    analyze_section5_other(samples)
    analyze_forfeit_differences(samples)
    analyze_deep_structure(samples)
    analyze_additional_selectors(samples)

    print("\n\nANALYSIS COMPLETE")
