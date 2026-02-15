"""
Deep-dive analysis of economy page data structures.
Extracts and documents the FusionCharts JSON config and equipment category tables.
"""

import gzip
import json
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

DATA_DIR = Path("data/recon")

SAMPLES = {
    "economy-162345.html.gz": {"mapstatsid": 162345, "score": "16-14", "era": "2023", "notes": "OT 30 rounds"},
    "economy-164779.html.gz": {"mapstatsid": 164779, "score": "8-13", "era": "2023", "notes": "Early CS2"},
    "economy-164780.html.gz": {"mapstatsid": 164780, "score": "9-13", "era": "2023", "notes": ""},
    "economy-173424.html.gz": {"mapstatsid": 173424, "score": "9-13", "era": "2024", "notes": ""},
    "economy-174112.html.gz": {"mapstatsid": 174112, "score": "13-8", "era": "2024", "notes": ""},
    "economy-174116.html.gz": {"mapstatsid": 174116, "score": "6-13", "era": "2024", "notes": ""},
    "economy-179210.html.gz": {"mapstatsid": 179210, "score": "8-13", "era": "2024", "notes": ""},
    "economy-188093.html.gz": {"mapstatsid": 188093, "score": "4-13", "era": "2024", "notes": "LAN"},
    "economy-206389.html.gz": {"mapstatsid": 206389, "score": "19-17", "era": "2025", "notes": "OT 36 rounds"},
    "economy-206393.html.gz": {"mapstatsid": 206393, "score": "13-4", "era": "2025", "notes": ""},
    "economy-219128.html.gz": {"mapstatsid": 219128, "score": "13-11", "era": "2026", "notes": "Tier-1 LAN"},
    "economy-219151.html.gz": {"mapstatsid": 219151, "score": "8-13", "era": "2026", "notes": "Tier-1 LAN"},
}


def load_soup(filename):
    with gzip.open(DATA_DIR / filename, "rt", encoding="utf-8") as f:
        html = f.read()
    return BeautifulSoup(html, "lxml"), html


def main():
    print("=" * 80)
    print("DEEP DIVE: ECONOMY PAGE DATA STRUCTURES")
    print("=" * 80)

    # ========================================
    # 1. FUSIONCHART CONFIG ANALYSIS
    # ========================================
    print("\n" + "=" * 80)
    print("1. FUSIONCHART CONFIG ANALYSIS")
    print("=" * 80)

    for filename, info in SAMPLES.items():
        soup, html = load_soup(filename)

        # Find the data-fusionchart-config attribute
        fc_elements = soup.find_all(True, attrs={"data-fusionchart-config": True})
        print(f"\n--- {filename} ({info['era']}, {info['score']}, {info['notes']}) ---")
        print(f"  FusionChart elements: {len(fc_elements)}")

        for fc_el in fc_elements:
            config_str = fc_el.get("data-fusionchart-config", "")
            try:
                config = json.loads(config_str)
                print(f"  Element: <{fc_el.name}> class={fc_el.get('class', [])}")
                print(f"  Config keys: {list(config.keys())}")
                print(f"  Chart type: {config.get('type')}")
                print(f"  renderAt: {config.get('renderAt')}")

                ds = config.get("dataSource", {})
                print(f"  DataSource keys: {list(ds.keys())}")

                # Chart config
                chart = ds.get("chart", {})
                print(f"  Chart config: yAxisMax={chart.get('yAxisMaxValue')}, yAxisMin={chart.get('yAxisMinValue')}")

                # Categories (round labels)
                categories = ds.get("categories", [])
                if categories:
                    cats = categories[0].get("category", [])
                    labels = [c.get("label", "") for c in cats]
                    print(f"  Round labels: {labels}")
                    print(f"  Round count: {len(labels)}")

                # Datasets (team equipment values per round)
                datasets = ds.get("dataset", [])
                print(f"  Dataset count: {len(datasets)}")
                for i, dataset in enumerate(datasets):
                    series_name = dataset.get("seriesname", f"series-{i}")
                    color = dataset.get("color", "")
                    data = dataset.get("data", [])
                    values = [d.get("value", "") for d in data]
                    # Also check for tooltext
                    tooltexts = [d.get("tooltext", "") for d in data[:3]]
                    print(f"  Dataset {i} '{series_name}' (color={color}):")
                    print(f"    Values ({len(values)}): {values}")
                    print(f"    First 3 tooltexts: {tooltexts}")

                # Full JSON for first sample only
                if filename == "economy-219128.html.gz":
                    print(f"\n  FULL CONFIG JSON:")
                    print(json.dumps(config, indent=2))

            except json.JSONDecodeError as e:
                print(f"  JSON parse error: {e}")
                print(f"  Raw config preview: {config_str[:500]}")

    # ========================================
    # 2. EQUIPMENT CATEGORIES TABLE ANALYSIS
    # ========================================
    print("\n" + "=" * 80)
    print("2. EQUIPMENT CATEGORIES TABLE ANALYSIS")
    print("=" * 80)

    for filename in ["economy-219128.html.gz", "economy-162345.html.gz", "economy-206389.html.gz", "economy-164779.html.gz"]:
        info = SAMPLES[filename]
        soup, html = load_soup(filename)

        print(f"\n--- {filename} ({info['era']}, {info['score']}, {info['notes']}) ---")

        # Find equipment-categories tables
        tables = soup.select("table.equipment-categories")
        print(f"  Equipment tables: {len(tables)}")

        for ti, table in enumerate(tables):
            print(f"\n  Table {ti}:")
            rows = table.find_all("tr")
            print(f"    Rows: {len(rows)}")

            for ri, row in enumerate(rows):
                row_classes = row.get("class", [])
                cells = row.find_all("td")
                print(f"\n    Row {ri} (classes={row_classes}, cells={len(cells)}):")

                for ci, cell in enumerate(cells):
                    cell_classes = cell.get("class", [])
                    title = cell.get("title", "")
                    # Look for images
                    imgs = cell.find_all("img")
                    img_info = [(img.get("src", ""), img.get("alt", ""), img.get("title", ""), img.get("class", [])) for img in imgs]
                    text = cell.get_text(strip=True)
                    print(f"      Cell {ci}: classes={cell_classes}, title='{title}', text='{text}'")
                    for img_src, img_alt, img_title, img_cls in img_info:
                        print(f"        <img src='{img_src}' alt='{img_alt}' title='{img_title}' class={img_cls}>")

    # ========================================
    # 3. TEAM ECONOMY STATS (text-based)
    # ========================================
    print("\n" + "=" * 80)
    print("3. TEAM ECONOMY STATS (div.team-economy-stat)")
    print("=" * 80)

    for filename in ["economy-219128.html.gz", "economy-162345.html.gz", "economy-206389.html.gz", "economy-164779.html.gz"]:
        info = SAMPLES[filename]
        soup, html = load_soup(filename)

        print(f"\n--- {filename} ({info['era']}, {info['score']}, {info['notes']}) ---")

        stat_divs = soup.select("div.team-economy-stat")
        print(f"  Economy stat divs: {len(stat_divs)}")

        for div in stat_divs:
            title_attr = div.get("title", "")
            # Get the label text
            label_span = div.select_one("span > span")
            label = label_span.get_text(strip=True) if label_span else ""
            # Get the value
            value_spans = div.find_all("span", recursive=False)
            value = div.get_text(strip=True)
            # Full HTML for structure analysis
            print(f"    '{label}' -> full_text='{value}', title='{title_attr}'")
            print(f"    HTML: {str(div)[:400]}")

    # ========================================
    # 4. STATS-ROWS CONTAINER (team info)
    # ========================================
    print("\n" + "=" * 80)
    print("4. STATS-ROWS CONTAINERS (team info)")
    print("=" * 80)

    soup, html = load_soup("economy-219128.html.gz")

    stats_rows_containers = soup.select("div.col.standard-box.stats-rows")
    print(f"  Stats-rows containers: {len(stats_rows_containers)}")

    for ci, container in enumerate(stats_rows_containers):
        print(f"\n  Container {ci}:")
        rows = container.select("div.stats-row")
        for row in rows:
            text = row.get_text(strip=True)
            classes = row.get("class", [])
            title = row.get("title", "")
            print(f"    Row: classes={classes}, title='{title}', text='{text[:100]}'")

    # ========================================
    # 5. STANDARD-HEADLINE for page title
    # ========================================
    print("\n" + "=" * 80)
    print("5. STANDARD-HEADLINE")
    print("=" * 80)

    headlines = soup.select("div.standard-headline")
    for h in headlines:
        print(f"  '{h.get_text(strip=True)}'")
        print(f"  HTML: {str(h)[:300]}")

    # ========================================
    # 6. FULL HTML of the economy content section
    # ========================================
    print("\n" + "=" * 80)
    print("6. FULL ECONOMY SECTION HTML")
    print("=" * 80)

    economy_section = soup.select_one("div.stats-match-economy")
    if economy_section:
        # Print structure tree (not full HTML, too large)
        print("  Economy section children tree:")

        def print_tree(el, indent=0):
            if el.name is None:
                return
            classes = el.get("class", [])
            text = el.get_text(strip=True)[:60] if not el.find() else ""
            attrs_of_interest = {k: v for k, v in el.attrs.items() if k in ("title", "src", "href", "alt") and v}
            line = f"{'  ' * indent}<{el.name}> .{' .'.join(classes) if classes else '(no-class)'}"
            if text:
                line += f" text='{text}'"
            if attrs_of_interest:
                for ak, av in attrs_of_interest.items():
                    v = av if isinstance(av, str) else str(av)
                    line += f" {ak}='{v[:80]}'"
            print(line)
            for child in el.children:
                if child.name:
                    print_tree(child, indent + 1)

        # Only print the economy-specific parts (skip the nav menu)
        children = list(economy_section.children)
        for child in children:
            if child.name:
                child_classes = child.get("class", [])
                # Skip the top menu and map selector
                if "stats-match-menu" in child_classes or "stats-match-maps" in child_classes or "section-spacer" in child_classes:
                    print(f"  [skipping <{child.name}> .{' .'.join(child_classes)}]")
                    continue
                print_tree(child, 1)

    # ========================================
    # 7. EQUIPMENT CATEGORY SVG FILENAMES
    # ========================================
    print("\n" + "=" * 80)
    print("7. EQUIPMENT CATEGORY SVG FILENAMES (all unique)")
    print("=" * 80)

    svg_srcs = set()
    for filename in SAMPLES:
        soup, _ = load_soup(filename)
        for img in soup.select("img.equipment-category"):
            svg_srcs.add(img.get("src", ""))

    for src in sorted(svg_srcs):
        print(f"  {src}")

    # ========================================
    # 8. CROSS-SAMPLE: OT round counts in FusionCharts
    # ========================================
    print("\n" + "=" * 80)
    print("8. ROUND COUNTS IN FUSIONCHART DATA (all samples)")
    print("=" * 80)

    for filename, info in sorted(SAMPLES.items()):
        soup, _ = load_soup(filename)
        fc_el = soup.find(True, attrs={"data-fusionchart-config": True})
        if fc_el:
            try:
                config = json.loads(fc_el.get("data-fusionchart-config"))
                cats = config.get("dataSource", {}).get("categories", [{}])[0].get("category", [])
                datasets = config.get("dataSource", {}).get("dataset", [])
                data_counts = [len(d.get("data", [])) for d in datasets]
                print(f"  {filename}: labels={len(cats)}, data_per_series={data_counts}, score={info['score']}")
            except:
                print(f"  {filename}: parse error")
        else:
            print(f"  {filename}: NO FusionChart config found!")

    # ========================================
    # 9. EQUIPMENT TABLE CELL COUNT (all samples)
    # ========================================
    print("\n" + "=" * 80)
    print("9. EQUIPMENT TABLE CELL COUNTS (all samples)")
    print("=" * 80)

    for filename, info in sorted(SAMPLES.items()):
        soup, _ = load_soup(filename)
        tables = soup.select("table.equipment-categories")
        for ti, table in enumerate(tables):
            rows = table.find_all("tr")
            cells_per_row = [len(row.find_all("td")) for row in rows]
            equip_cells = table.select("td.equipment-category-td")
            titles = [td.get("title", "") for td in equip_cells[:5]]
            print(f"  {filename} table{ti}: rows={len(rows)}, cells_per_row={cells_per_row}, equip_cells={len(equip_cells)}")
            print(f"    First 5 titles: {titles}")

    # ========================================
    # 10. FULL EQUIPMENT TABLE HTML for one sample
    # ========================================
    print("\n" + "=" * 80)
    print("10. FULL EQUIPMENT TABLE HTML (economy-219128)")
    print("=" * 80)

    soup, _ = load_soup("economy-219128.html.gz")
    tables = soup.select("table.equipment-categories")
    for ti, table in enumerate(tables):
        print(f"\n--- Table {ti} ---")
        print(str(table)[:5000])


if __name__ == "__main__":
    main()
