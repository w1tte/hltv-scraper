#!/usr/bin/env python3
"""Detailed veto structure analysis for HLTV match overview pages."""

import gzip
import re
from pathlib import Path
from bs4 import BeautifulSoup

RECON_DIR = Path("data/recon")

def load_samples():
    samples = {}
    for f in sorted(RECON_DIR.glob("match-*-overview.html.gz")):
        match_id = int(f.name.split("-")[1])
        html = gzip.decompress(f.read_bytes()).decode("utf-8")
        soup = BeautifulSoup(html, "lxml")
        samples[match_id] = soup
    return samples


def main():
    samples = load_samples()

    # The initial analysis showed TWO .veto-box per page
    # First one is the format/metadata box, second one is the actual vetoes
    # Let's verify and look at the second one

    for mid, soup in samples.items():
        print(f"\n{'='*60}")
        print(f"Match {mid}")
        print(f"{'='*60}")

        veto_boxes = soup.select(".veto-box")
        print(f"Total .veto-box elements: {len(veto_boxes)}")

        for i, vbox in enumerate(veto_boxes):
            print(f"\n  --- .veto-box[{i}] ---")
            # Print the raw HTML (truncated)
            html = str(vbox)
            html_clean = re.sub(r'\n\s+', '\n', html)
            print(f"  Raw HTML ({len(html)} chars):")
            for line in html_clean.split('\n')[:30]:
                if line.strip():
                    print(f"    {line.strip()}")
            if len(html_clean.split('\n')) > 30:
                print(f"    ... (truncated)")

    # Now look at ranking containers more carefully
    print(f"\n\n{'='*60}")
    print("RANKING ANALYSIS")
    print(f"{'='*60}")

    for mid, soup in samples.items():
        print(f"\nMatch {mid}:")
        # Rankings are inside lineups, not inside team-gradient
        lineups = soup.select_one(".lineups")
        if lineups:
            rankings = lineups.select(".teamRanking a")
            for r in rankings:
                print(f"  Ranking: '{r.get_text(strip=True)}' href={r.get('href', '')}")

        # Check team-gradient for any ranking
        for sel in [".team1-gradient", ".team2-gradient"]:
            container = soup.select_one(sel)
            if container:
                # Print all children structure
                all_text = container.get_text(strip=True)[:100]
                print(f"  {sel}: '{all_text}'")
                divs = container.find_all(recursive=False)
                for d in divs:
                    classes = " ".join(d.get("class", []))
                    text = d.get_text(strip=True)[:80]
                    print(f"    <{d.name} class='{classes}'> {text}")

    # Look at the .played and .optional classes on map holders more carefully
    print(f"\n\n{'='*60}")
    print("PLAYED/OPTIONAL CLASS DETAIL")
    print(f"{'='*60}")

    for mid in [2367432, 2384993]:  # BO3 and BO5
        soup = samples[mid]
        holders = soup.select(".mapholder")
        print(f"\nMatch {mid}:")
        for i, h in enumerate(holders):
            # Check children for .played and .optional
            played_divs = h.select(".played")
            optional_divs = h.select(".optional")
            map_name = h.select_one(".mapname")
            map_text = map_name.get_text(strip=True) if map_name else "N/A"
            # Check .results div classes
            results_div = h.select_one(".results")
            results_classes = " ".join(results_div.get("class", [])) if results_div else "N/A"
            print(f"  Map {i+1} ({map_text}): .played divs={len(played_divs)}, .optional divs={len(optional_divs)}, results classes='{results_classes}'")

    # Look for the map pick indicator - maybe different class
    print(f"\n\n{'='*60}")
    print("MAP PICK INDICATOR SEARCH")
    print(f"{'='*60}")

    for mid in [2389951, 2367432, 2384993]:
        soup = samples[mid]
        holders = soup.select(".mapholder")
        print(f"\nMatch {mid}:")
        for i, h in enumerate(holders):
            map_name = h.select_one(".mapname")
            map_text = map_name.get_text(strip=True) if map_name else "N/A"
            # Look for any text mentioning "pick"
            all_text = h.get_text(strip=True)
            if "pick" in all_text.lower():
                print(f"  Map {i+1} ({map_text}): contains 'pick' text")
            # Look for specific pick indicators
            for cls in ["picked", "left-border", "right-border", "pick-border", "map-pick"]:
                els = h.select(f".{cls}")
                if els:
                    print(f"  Map {i+1} ({map_text}): has .{cls} ({len(els)} elements)")

    # Check forfeit countdown text
    print(f"\n\n{'='*60}")
    print("COUNTDOWN/STATUS TEXT")
    print(f"{'='*60}")
    for mid, soup in samples.items():
        countdown = soup.select_one(".countdown")
        text = countdown.get_text(strip=True) if countdown else "N/A"
        print(f"  {mid}: '{text}'")

    # Check for overall score within specific containers
    print(f"\n\n{'='*60}")
    print("OVERALL SCORE CONTAINERS")
    print(f"{'='*60}")
    for mid in [2389951, 2384993, 2380434]:
        soup = samples[mid]
        print(f"\nMatch {mid}:")
        for team_sel in [".team1-gradient", ".team2-gradient"]:
            container = soup.select_one(team_sel)
            if container:
                # Find the won/lost div
                won = container.select_one(".won")
                lost = container.select_one(".lost")
                tie = container.select_one(".tie")
                if won:
                    print(f"  {team_sel}: .won = '{won.get_text(strip=True)}'")
                if lost:
                    print(f"  {team_sel}: .lost = '{lost.get_text(strip=True)}'")
                if tie:
                    print(f"  {team_sel}: .tie = '{tie.get_text(strip=True)}'")
                if not won and not lost and not tie:
                    # Check all score-like elements
                    divs = container.find_all("div")
                    for d in divs:
                        classes = d.get("class", [])
                        if classes and any(c in ["won", "lost", "tie"] for c in classes):
                            print(f"  {team_sel}: found .{classes} = '{d.get_text(strip=True)}'")


if __name__ == "__main__":
    main()
