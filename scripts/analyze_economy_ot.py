"""
Verify OT economy data availability.
Check whether OT rounds appear in the economy chart and table data.
"""

import gzip
import json
from pathlib import Path
from bs4 import BeautifulSoup

DATA_DIR = Path("data/recon")


def load_soup(filename):
    with gzip.open(DATA_DIR / filename, "rt", encoding="utf-8") as f:
        html = f.read()
    return BeautifulSoup(html, "lxml"), html


def analyze_ot_sample(filename, expected_rounds, score):
    soup, html = load_soup(filename)

    print(f"\n{'='*60}")
    print(f"File: {filename}")
    print(f"Score: {score} = {expected_rounds} expected rounds")
    print(f"{'='*60}")

    # 1. FusionCharts data
    fc_el = soup.find(True, attrs={"data-fusionchart-config": True})
    if fc_el:
        config = json.loads(fc_el.get("data-fusionchart-config"))
        ds = config.get("dataSource", {})
        cats = ds.get("categories", [{}])[0].get("category", [])
        datasets = ds.get("dataset", [])
        print(f"\nFusionCharts: {len(cats)} round labels")
        print(f"Labels: {[c['label'] for c in cats]}")

        for i, dataset in enumerate(datasets):
            name = dataset.get("seriesname")
            data = dataset.get("data", [])
            print(f"\nDataset '{name}': {len(data)} data points")
            # Show anchorImageUrl for each round (indicates win/loss and side)
            for j, d in enumerate(data):
                anchor = d.get("anchorImageUrl", "none")
                value = d.get("value")
                side_info = anchor.split("/")[-1] if anchor != "none" else "no-icon"
                print(f"  Round {j+1}: ${value} anchor={side_info}")

        # Trendlines
        trendlines = ds.get("trendlines", [])
        if trendlines:
            lines = trendlines[0].get("line", [])
            print(f"\nTrendlines: {len(lines)}")
            for line in lines:
                print(f"  {line.get('displayValue')}: ${line.get('startvalue')}")

    # 2. Equipment tables
    tables = soup.select("table.equipment-categories")
    print(f"\nEquipment tables: {len(tables)}")
    for ti, table in enumerate(tables):
        rows = table.find_all("tr")
        cells_per_row = [len(row.find_all("td")) for row in rows]
        equip_cells = len(table.select("td.equipment-category-td"))
        rounds_per_half = (cells_per_row[0] - 1) if cells_per_row else 0
        print(f"  Table {ti} ('{'First' if ti==0 else 'Second'} half'): {cells_per_row} cells/row = {rounds_per_half} rounds")

    # 3. Check headlines
    headlines = soup.select("div.standard-headline")
    print(f"\nHeadlines:")
    for h in headlines:
        text = h.get_text(strip=True)
        print(f"  - {text}")

    # 4. Team economy stats (should show round numbers for OT)
    stat_divs = soup.select("div.team-economy-stat")
    print(f"\nTeam economy stats:")
    for div in stat_divs[:4]:  # Just first team
        label = div.select_one("span > span")
        label_text = label.get_text(strip=True) if label else ""
        title = div.get("title", "")
        text = div.get_text(strip=True)
        # Parse round numbers from title
        if title.startswith("Rounds: "):
            rounds = [int(r) for r in title.replace("Rounds: ", "").split(",") if r]
            max_round = max(rounds) if rounds else 0
            print(f"  {label_text}: {text} | rounds={rounds} max={max_round}")
        else:
            print(f"  {label_text}: {text} | no rounds")


# Check the three OT samples
# 162345: 16-14 = 30 rounds (MR15 format with OT)
# 206389: 19-17 = 36 rounds (MR12 format with extended OT)
# And a regulation sample for comparison
# 219128: 13-11 = 24 rounds (regulation MR12)

analyze_ot_sample("economy-219128.html.gz", 24, "13-11 (regulation)")
analyze_ot_sample("economy-162345.html.gz", 30, "16-14 (OT)")
analyze_ot_sample("economy-206389.html.gz", 36, "19-17 (OT)")
