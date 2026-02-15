"""
Exploratory DOM analysis of HLTV economy page HTML samples.
Phase 3, Plan 06: Map economy page reconnaissance.
"""

import gzip
import json
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup, Comment

DATA_DIR = Path("data/recon")

# Manifest info for each economy sample
SAMPLES = {
    "economy-162345.html.gz": {"mapstatsid": 162345, "match": 2366498, "map": "Nuke", "score": "16-14", "era": "2023", "notes": "OT (30 rounds)"},
    "economy-164779.html.gz": {"mapstatsid": 164779, "match": 2367432, "map": "Nuke", "score": "8-13", "era": "2023", "notes": "Early CS2"},
    "economy-164780.html.gz": {"mapstatsid": 164780, "match": 2367432, "map": "Anubis", "score": "9-13", "era": "2023", "notes": ""},
    "economy-173424.html.gz": {"mapstatsid": 173424, "match": 2371321, "map": "Anubis", "score": "9-13", "era": "2024", "notes": ""},
    "economy-174112.html.gz": {"mapstatsid": 174112, "match": 2371389, "map": "Mirage", "score": "13-8", "era": "2024", "notes": ""},
    "economy-174116.html.gz": {"mapstatsid": 174116, "match": 2371389, "map": "Anubis", "score": "6-13", "era": "2024", "notes": ""},
    "economy-179210.html.gz": {"mapstatsid": 179210, "match": 2373741, "map": "Nuke", "score": "8-13", "era": "2024", "notes": ""},
    "economy-188093.html.gz": {"mapstatsid": 188093, "match": 2377467, "map": "Inferno", "score": "4-13", "era": "2024", "notes": "LAN"},
    "economy-206389.html.gz": {"mapstatsid": 206389, "match": 2384993, "map": "Mirage", "score": "19-17", "era": "2025", "notes": "OT (36 rounds)"},
    "economy-206393.html.gz": {"mapstatsid": 206393, "match": 2384993, "map": "Overpass", "score": "13-4", "era": "2025", "notes": ""},
    "economy-219128.html.gz": {"mapstatsid": 219128, "match": 2389951, "map": "Mirage", "score": "13-11", "era": "2026", "notes": "Tier-1 LAN"},
    "economy-219151.html.gz": {"mapstatsid": 219151, "match": 2389951, "map": "Inferno", "score": "8-13", "era": "2026", "notes": "Tier-1 LAN"},
}


def load_html(filename):
    """Load gzipped HTML file."""
    with gzip.open(DATA_DIR / filename, "rt", encoding="utf-8") as f:
        return f.read()


def extract_economy_section(soup):
    """Try to isolate the economy-specific content area of the page."""
    # Look for the main content area with economy-specific elements
    # Try common HLTV content containers
    candidates = []

    # Look for elements with economy-related classes
    for el in soup.find_all(True, class_=re.compile(r'economy|equip|money|buy', re.I)):
        candidates.append(el)

    # Look for elements with economy-related IDs
    for el in soup.find_all(True, id=re.compile(r'economy|equip|money|buy', re.I)):
        candidates.append(el)

    return candidates


def analyze_all_classes(soup, limit=100):
    """Get all CSS classes sorted by frequency."""
    class_counter = Counter()
    for el in soup.find_all(True, class_=True):
        for cls in el.get("class", []):
            class_counter[cls] += 1
    return class_counter.most_common(limit)


def analyze_data_attributes(soup):
    """Find all data-* attributes."""
    data_attrs = Counter()
    for el in soup.find_all(True):
        for attr in el.attrs:
            if attr.startswith("data-"):
                data_attrs[attr] += 1
    return data_attrs.most_common(100)


def analyze_tables(soup):
    """Analyze all table elements."""
    tables = []
    for table in soup.find_all("table"):
        classes = table.get("class", [])
        parent_classes = table.parent.get("class", []) if table.parent else []
        rows = table.find_all("tr")
        tables.append({
            "classes": classes,
            "parent_classes": parent_classes,
            "num_rows": len(rows),
            "first_row_cells": len(rows[0].find_all(["td", "th"])) if rows else 0,
            "snippet": str(table)[:500]
        })
    return tables


def analyze_scripts(soup):
    """Analyze script tags for embedded data."""
    script_info = []
    for script in soup.find_all("script"):
        src = script.get("src", "")
        content = script.string or ""
        info = {"src": src, "length": len(content)}

        # Check for FusionCharts
        if "fusionchart" in content.lower() or "fusionchart" in src.lower():
            info["type"] = "fusionchart"
            info["snippet"] = content[:1000]

        # Check for economy-related data
        if any(keyword in content.lower() for keyword in ["economy", "equipment", "buytype", "buy_type", "round", "money"]):
            info["type"] = info.get("type", "economy-related")
            # Try to extract JSON-like data
            json_matches = re.findall(r'(?:var\s+\w+\s*=\s*|)\[{.*?}\]', content[:10000], re.DOTALL)
            if json_matches:
                info["json_data_preview"] = json_matches[0][:500]
            info["snippet"] = content[:2000]

        if content and len(content) > 50:
            info["content_preview"] = content[:300]

        if src or info.get("type") or len(content) > 100:
            script_info.append(info)

    return script_info


def find_economy_specific_elements(soup):
    """Deep search for economy-specific DOM elements."""
    results = {}

    # Search for elements with economy-related text or classes
    economy_keywords = [
        "economy", "equip", "money", "buy", "eco", "force",
        "pistol", "full-buy", "half-buy", "save", "equipment-value",
        "round-history-team-row", "round-history",
        "team-chart", "economy-chart", "equipment"
    ]

    for keyword in economy_keywords:
        # Search by class
        by_class = soup.find_all(True, class_=re.compile(keyword, re.I))
        if by_class:
            results[f"class~={keyword}"] = {
                "count": len(by_class),
                "tags": Counter(el.name for el in by_class).most_common(5),
                "sample_classes": [el.get("class", []) for el in by_class[:3]],
                "sample_html": [str(el)[:300] for el in by_class[:2]]
            }

        # Search by id
        by_id = soup.find_all(True, id=re.compile(keyword, re.I))
        if by_id:
            results[f"id~={keyword}"] = {
                "count": len(by_id),
                "tags": [(el.name, el.get("id")) for el in by_id],
                "sample_html": [str(el)[:500] for el in by_id[:2]]
            }

    return results


def find_fusionchart_data(soup):
    """Look for FusionCharts data attributes and configs."""
    results = []

    # data-fusionchart-config attributes
    for el in soup.find_all(True, attrs={"data-fusionchart-config": True}):
        config = el.get("data-fusionchart-config", "")
        results.append({
            "element": el.name,
            "classes": el.get("class", []),
            "config_length": len(config),
            "config_preview": config[:1000]
        })

    # Alternative: look for FusionCharts in any data attribute
    for el in soup.find_all(True):
        for attr, val in el.attrs.items():
            if isinstance(val, str) and "fusionchart" in attr.lower():
                results.append({
                    "element": el.name,
                    "attribute": attr,
                    "value_length": len(val),
                    "value_preview": val[:500]
                })

    return results


def find_round_related_elements(soup):
    """Find all elements related to rounds."""
    results = {}

    # Look for round number patterns
    round_patterns = [
        re.compile(r'round', re.I),
        re.compile(r'ct-round|t-round', re.I),
        re.compile(r'half', re.I),
    ]

    for pattern in round_patterns:
        matches = soup.find_all(True, class_=pattern)
        if matches:
            results[pattern.pattern] = {
                "count": len(matches),
                "tags": Counter(el.name for el in matches).most_common(5),
                "sample_classes": [el.get("class", []) for el in matches[:5]],
                "sample_html": [str(el)[:400] for el in matches[:3]]
            }

    return results


def analyze_page_specific_content(soup):
    """Look at the main content area, ignoring nav/header/footer."""
    # HLTV uses .contentCol or similar for main content
    content_selectors = [
        ".contentCol", "#contentCol",
        ".stats-content", ".match-page",
        ".standard-box", ".columns",
    ]

    results = {}
    for sel in content_selectors:
        found = soup.select(sel)
        if found:
            results[sel] = {
                "count": len(found),
                "children_tags": Counter(child.name for el in found for child in el.children if child.name).most_common(10)
            }

    return results


def extract_chart_js_data(html_text):
    """Search raw HTML text for JavaScript chart data (FusionCharts, Highcharts, etc.)."""
    results = {}

    # Look for FusionCharts.ready() or new FusionCharts()
    fc_pattern = re.compile(r'FusionCharts\s*[\(\.]', re.I)
    fc_matches = list(fc_pattern.finditer(html_text))
    if fc_matches:
        results["fusionchart_instances"] = len(fc_matches)
        for i, m in enumerate(fc_matches[:3]):
            start = max(0, m.start() - 100)
            end = min(len(html_text), m.end() + 2000)
            results[f"fusionchart_context_{i}"] = html_text[start:end]

    # Look for chart data JSON patterns
    chart_data_pattern = re.compile(r'"dataSource"\s*:\s*\{', re.I)
    cd_matches = list(chart_data_pattern.finditer(html_text))
    if cd_matches:
        results["datasource_instances"] = len(cd_matches)
        for i, m in enumerate(cd_matches[:3]):
            start = max(0, m.start() - 50)
            end = min(len(html_text), m.end() + 3000)
            results[f"datasource_context_{i}"] = html_text[start:end]

    # Look for Highcharts
    hc_pattern = re.compile(r'Highcharts', re.I)
    hc_matches = list(hc_pattern.finditer(html_text))
    if hc_matches:
        results["highcharts_instances"] = len(hc_matches)

    # Look for any JSON array that looks like round data
    round_data_pattern = re.compile(r'\[\s*\{[^}]*"round"[^}]*\}', re.I)
    rd_matches = list(round_data_pattern.finditer(html_text))
    if rd_matches:
        results["round_json_instances"] = len(rd_matches)
        for i, m in enumerate(rd_matches[:3]):
            end = min(len(html_text), m.end() + 2000)
            results[f"round_json_context_{i}"] = html_text[m.start():end]

    # Look for equipment value patterns in JS
    equip_pattern = re.compile(r'(?:equipment|equip|money)\s*[=:]\s*[\[\{]', re.I)
    eq_matches = list(equip_pattern.finditer(html_text))
    if eq_matches:
        results["equipment_js_instances"] = len(eq_matches)
        for i, m in enumerate(eq_matches[:3]):
            start = max(0, m.start() - 100)
            end = min(len(html_text), m.end() + 1000)
            results[f"equipment_js_context_{i}"] = html_text[start:end]

    return results


def analyze_team_sections(soup):
    """How are the two teams represented?"""
    results = {}

    # Look for team name elements
    team_patterns = [
        re.compile(r'team1|team-1|teamOne', re.I),
        re.compile(r'team2|team-2|teamTwo', re.I),
        re.compile(r'team.*name', re.I),
        re.compile(r'ct-color|t-color|ct_color|t_color', re.I),
    ]

    for pattern in team_patterns:
        matches_cls = soup.find_all(True, class_=pattern)
        if matches_cls:
            results[f"class~={pattern.pattern}"] = {
                "count": len(matches_cls),
                "sample_html": [str(el)[:400] for el in matches_cls[:3]]
            }
        matches_id = soup.find_all(True, id=pattern)
        if matches_id:
            results[f"id~={pattern.pattern}"] = {
                "count": len(matches_id),
                "sample_html": [str(el)[:400] for el in matches_id[:3]]
            }

    return results


def main():
    print("=" * 80)
    print("HLTV ECONOMY PAGE DOM RECONNAISSANCE")
    print("=" * 80)

    # Start with a detailed analysis of one sample, then cross-verify with others
    primary_file = "economy-219128.html.gz"  # Tier-1 LAN, 2026, most recent
    print(f"\n### PRIMARY ANALYSIS: {primary_file}")
    print(f"    ({SAMPLES[primary_file]})")

    html = load_html(primary_file)
    print(f"    HTML length: {len(html):,} chars")

    soup = BeautifulSoup(html, "lxml")

    # ========================================
    # STEP 1: Full DOM reconnaissance
    # ========================================
    print("\n" + "=" * 80)
    print("STEP 1: FULL DOM RECONNAISSANCE")
    print("=" * 80)

    print("\n--- TOP 80 CSS CLASSES (by frequency) ---")
    top_classes = analyze_all_classes(soup, limit=80)
    for cls, count in top_classes:
        print(f"  {count:5d}x  {cls}")

    print("\n--- ALL data-* ATTRIBUTES ---")
    data_attrs = analyze_data_attributes(soup)
    for attr, count in data_attrs:
        print(f"  {count:5d}x  {attr}")

    print("\n--- ALL TABLES ---")
    tables = analyze_tables(soup)
    for i, t in enumerate(tables):
        print(f"\n  Table {i}: classes={t['classes']}, rows={t['num_rows']}, cols={t['first_row_cells']}")
        print(f"    parent_classes={t['parent_classes']}")
        print(f"    snippet: {t['snippet'][:300]}")

    print("\n--- SCRIPT ANALYSIS ---")
    scripts = analyze_scripts(soup)
    for i, s in enumerate(scripts):
        print(f"\n  Script {i}: src={s.get('src', 'inline')}, len={s['length']}")
        if s.get("type"):
            print(f"    type: {s['type']}")
        if s.get("snippet"):
            print(f"    snippet: {s['snippet'][:500]}")
        elif s.get("content_preview"):
            print(f"    preview: {s['content_preview'][:300]}")

    print("\n--- FUSIONCHART DATA ---")
    fc_data = find_fusionchart_data(soup)
    if fc_data:
        for item in fc_data:
            print(f"  {item}")
    else:
        print("  No FusionCharts data-* attributes found in DOM")

    print("\n--- RAW HTML SEARCH FOR CHART JS ---")
    chart_data = extract_chart_js_data(html)
    for key, val in chart_data.items():
        if isinstance(val, int):
            print(f"  {key}: {val}")
        else:
            print(f"  {key}:")
            print(f"    {str(val)[:1500]}")

    # ========================================
    # STEP 2: Economy-specific elements
    # ========================================
    print("\n" + "=" * 80)
    print("STEP 2: ECONOMY-SPECIFIC ELEMENTS")
    print("=" * 80)

    print("\n--- ECONOMY KEYWORD SEARCH ---")
    econ_elements = find_economy_specific_elements(soup)
    for keyword, info in econ_elements.items():
        print(f"\n  {keyword}: {info['count']} matches")
        print(f"    tags: {info.get('tags', info.get('tags', []))}")
        if info.get('sample_classes'):
            print(f"    sample classes: {info['sample_classes']}")
        for html_snippet in info.get('sample_html', []):
            print(f"    HTML: {html_snippet[:400]}")

    print("\n--- ROUND-RELATED ELEMENTS ---")
    round_elements = find_round_related_elements(soup)
    for pattern, info in round_elements.items():
        print(f"\n  pattern='{pattern}': {info['count']} matches")
        print(f"    tags: {info['tags']}")
        print(f"    sample classes: {info['sample_classes']}")
        for html_snippet in info.get('sample_html', []):
            print(f"    HTML: {html_snippet}")

    # ========================================
    # STEP 3: Team sections
    # ========================================
    print("\n" + "=" * 80)
    print("STEP 3: TEAM ATTRIBUTION")
    print("=" * 80)

    team_info = analyze_team_sections(soup)
    for pattern, info in team_info.items():
        print(f"\n  {pattern}: {info['count']} matches")
        for html_snippet in info.get('sample_html', []):
            print(f"    HTML: {html_snippet}")

    # ========================================
    # STEP 4: Page-specific content area
    # ========================================
    print("\n" + "=" * 80)
    print("STEP 4: CONTENT AREA ANALYSIS")
    print("=" * 80)

    content_info = analyze_page_specific_content(soup)
    for sel, info in content_info.items():
        print(f"\n  {sel}: {info['count']} found")
        print(f"    children: {info['children_tags']}")

    # Look deeper into standard-box elements
    print("\n--- STANDARD-BOX CONTENTS ---")
    for box in soup.select(".standard-box")[:10]:
        headlines = box.select(".standard-headline")
        headline_text = headlines[0].get_text(strip=True) if headlines else "(no headline)"
        inner_html = str(box)[:600]
        print(f"\n  Headline: {headline_text}")
        print(f"  Classes: {box.get('class', [])}")
        print(f"  HTML: {inner_html}")

    # ========================================
    # STEP 5: Cross-verify with multiple samples
    # ========================================
    print("\n" + "=" * 80)
    print("STEP 5: CROSS-SAMPLE VERIFICATION")
    print("=" * 80)

    # Check a few key selectors/patterns across all samples
    cross_check_files = [
        "economy-162345.html.gz",  # OT, 2023
        "economy-164779.html.gz",  # Early CS2, 2023
        "economy-206389.html.gz",  # OT (36 rounds), 2025
        "economy-188093.html.gz",  # LAN, 2024
    ]

    for filename in cross_check_files:
        info = SAMPLES[filename]
        print(f"\n--- {filename} ({info['era']}, {info['map']} {info['score']}, {info['notes']}) ---")
        h = load_html(filename)
        s = BeautifulSoup(h, "lxml")

        # Check same key patterns
        fc = extract_chart_js_data(h)
        print(f"  FusionChart instances: {fc.get('fusionchart_instances', 0)}")
        print(f"  DataSource instances: {fc.get('datasource_instances', 0)}")
        print(f"  Highcharts instances: {fc.get('highcharts_instances', 0)}")
        print(f"  Round JSON instances: {fc.get('round_json_instances', 0)}")
        print(f"  Equipment JS instances: {fc.get('equipment_js_instances', 0)}")

        # Count economy-specific elements
        econ = find_economy_specific_elements(s)
        econ_summary = {k: v['count'] for k, v in econ.items()}
        print(f"  Economy elements: {econ_summary}")

        # Count tables
        tbls = s.find_all("table")
        print(f"  Tables: {len(tbls)}")

        # Check round elements
        rounds = find_round_related_elements(s)
        round_summary = {k: v['count'] for k, v in rounds.items()}
        print(f"  Round elements: {round_summary}")

    # ========================================
    # STEP 6: Deep-dive into the actual data structure
    # ========================================
    print("\n" + "=" * 80)
    print("STEP 6: DEEP DIVE INTO ECONOMY DATA STRUCTURE")
    print("=" * 80)

    # Re-analyze the primary sample with more targeted searches
    # Look for the economy chart container and its data

    # Check for any div/container that holds the economy visualization
    print("\n--- SEARCHING FOR ECONOMY VISUALIZATION CONTAINER ---")
    # Look at all divs with class containing chart
    chart_divs = soup.find_all("div", class_=re.compile(r'chart', re.I))
    for div in chart_divs[:10]:
        print(f"  div.{' '.join(div.get('class', []))} id={div.get('id', '')}")
        print(f"    children: {[(c.name, c.get('class', []), c.get('id', '')) for c in div.children if c.name][:5]}")
        print(f"    HTML: {str(div)[:500]}")

    # Look for canvas elements (chart.js) or svg (d3/highcharts)
    print("\n--- CANVAS/SVG ELEMENTS ---")
    for el in soup.find_all(["canvas", "svg"]):
        print(f"  {el.name} class={el.get('class', [])} id={el.get('id', '')} parent_class={el.parent.get('class', []) if el.parent else []}")

    # Look for any hidden divs or containers with chart data
    print("\n--- HIDDEN/CHART DATA CONTAINERS ---")
    for el in soup.find_all(True, style=re.compile(r'display:\s*none', re.I)):
        if el.get("class") or el.get("id"):
            text = el.get_text(strip=True)[:200]
            print(f"  {el.name} class={el.get('class', [])} id={el.get('id', '')} text={text[:100]}")

    # ========================================
    # STEP 7: Targeted text search for dollar amounts
    # ========================================
    print("\n" + "=" * 80)
    print("STEP 7: DOLLAR AMOUNT SEARCH")
    print("=" * 80)

    # Look for dollar signs or monetary patterns in the HTML
    dollar_pattern = re.compile(r'\$[\d,]+')
    dollar_matches = dollar_pattern.findall(html)
    if dollar_matches:
        counter = Counter(dollar_matches)
        print(f"  Found {len(dollar_matches)} dollar amounts")
        print(f"  Unique: {len(counter)}")
        print(f"  Top 20: {counter.most_common(20)}")
    else:
        print("  No $-prefixed amounts found in raw HTML")

    # Also look for bare numbers that could be equipment values (e.g., 4750, 3100)
    # Typical CS2 equipment values range from ~200 to ~30000
    print("\n--- LOOKING FOR EQUIPMENT VALUE PATTERNS ---")
    # Search in economy-specific areas first
    for el in soup.find_all(True, class_=re.compile(r'equip|econ|money', re.I)):
        text = el.get_text(strip=True)
        if text and any(c.isdigit() for c in text):
            print(f"  {el.name}.{' '.join(el.get('class', []))}: '{text[:200]}'")

    # ========================================
    # STEP 8: Full content area HTML dump for manual inspection
    # ========================================
    print("\n" + "=" * 80)
    print("STEP 8: MAIN CONTENT AREA DUMP (for manual inspection)")
    print("=" * 80)

    # Get the main content column
    content_col = soup.select_one(".contentCol") or soup.select_one("#contentCol")
    if content_col:
        # Find all meaningful divs in content area
        print(f"  Content column: {content_col.name}.{' '.join(content_col.get('class', []))}")
        for child in content_col.children:
            if child.name:
                classes = child.get("class", [])
                text = child.get_text(strip=True)[:100] if child.string != "\n" else ""
                inner_children = [(c.name, c.get("class", [])) for c in child.children if c.name][:5]
                print(f"\n  > {child.name}.{' '.join(classes)}")
                print(f"    text: {text}")
                print(f"    children: {inner_children}")

    # ========================================
    # STEP 9: OT sample comparison
    # ========================================
    print("\n" + "=" * 80)
    print("STEP 9: OVERTIME COMPARISON")
    print("=" * 80)

    # Compare regulation (economy-219151, 8-13 = 21 rounds) vs OT (economy-162345, 16-14 = 30 rounds)
    # vs long OT (economy-206389, 19-17 = 36 rounds)
    for ot_file in ["economy-219151.html.gz", "economy-162345.html.gz", "economy-206389.html.gz"]:
        info = SAMPLES[ot_file]
        h = load_html(ot_file)
        s = BeautifulSoup(h, "lxml")

        print(f"\n  {ot_file} ({info['score']}, {info['notes'] or 'regulation'})")

        # Count round-related elements
        round_els = s.find_all(True, class_=re.compile(r'round', re.I))
        print(f"    Round elements: {len(round_els)}")

        # Look for round numbers
        round_nums = []
        for el in round_els:
            text = el.get_text(strip=True)
            if text.isdigit():
                round_nums.append(int(text))
        if round_nums:
            print(f"    Round numbers found: min={min(round_nums)}, max={max(round_nums)}, count={len(round_nums)}")
        else:
            print(f"    No numeric round labels found in round elements")

        # Check chart data for round count
        fc = extract_chart_js_data(h)
        print(f"    FusionChart instances: {fc.get('fusionchart_instances', 0)}")
        print(f"    DataSource instances: {fc.get('datasource_instances', 0)}")

    # ========================================
    # STEP 10: Historical availability (2023 vs 2026)
    # ========================================
    print("\n" + "=" * 80)
    print("STEP 10: HISTORICAL AVAILABILITY (2023 vs 2026)")
    print("=" * 80)

    for era_file in ["economy-164779.html.gz", "economy-219128.html.gz"]:
        info = SAMPLES[era_file]
        h = load_html(era_file)
        s = BeautifulSoup(h, "lxml")

        print(f"\n  {era_file} ({info['era']}, {info['map']} {info['score']})")
        print(f"    HTML size: {len(h):,} chars")

        # Economy-specific element count
        econ = find_economy_specific_elements(s)
        for k, v in econ.items():
            print(f"    {k}: {v['count']}")

        # Table count and details
        tables = analyze_tables(s)
        print(f"    Tables: {len(tables)}")

        # Chart data
        fc = extract_chart_js_data(h)
        for k, v in fc.items():
            if isinstance(v, int):
                print(f"    {k}: {v}")

    # ========================================
    # STEP 11: Extract actual data from identified structures
    # ========================================
    print("\n" + "=" * 80)
    print("STEP 11: DATA EXTRACTION ATTEMPT")
    print("=" * 80)

    # Based on findings above, try to extract actual economy data
    # This will be populated based on what we find in steps 1-10

    # Try extracting from the primary sample
    h = load_html(primary_file)
    s = BeautifulSoup(h, "lxml")

    # Approach A: Look for structured table data
    print("\n--- Approach A: HTML Tables ---")
    for table in s.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) >= 10:  # Economy data would have many rows
            first_row = rows[0]
            headers = [th.get_text(strip=True) for th in first_row.find_all(["th", "td"])]
            print(f"  Table with {len(rows)} rows, headers: {headers}")
            if len(rows) > 1:
                second_row = rows[1]
                cells = [td.get_text(strip=True) for td in second_row.find_all(["td", "th"])]
                print(f"  First data row: {cells}")

    # Approach B: Look for FusionCharts dataSource JSON
    print("\n--- Approach B: FusionCharts dataSource ---")
    datasource_pattern = re.compile(r'"dataSource"\s*:\s*(\{[^;]*?\})\s*[,\}]', re.DOTALL)
    ds_matches = list(datasource_pattern.finditer(h))
    print(f"  Found {len(ds_matches)} dataSource patterns")
    for i, m in enumerate(ds_matches[:5]):
        # Try to grab a reasonable chunk
        start = m.start(1)
        # Find the end of this JSON object - look for balanced braces
        depth = 0
        pos = start
        while pos < min(len(h), start + 50000):
            if h[pos] == '{':
                depth += 1
            elif h[pos] == '}':
                depth -= 1
                if depth == 0:
                    break
            pos += 1

        json_text = h[start:pos+1]
        print(f"\n  DataSource {i}: {len(json_text)} chars")
        try:
            data = json.loads(json_text)
            print(f"    Keys: {list(data.keys())}")
            if "chart" in data:
                print(f"    Chart config: {json.dumps(data['chart'], indent=2)[:500]}")
            if "categories" in data:
                cats = data["categories"]
                print(f"    Categories: {json.dumps(cats, indent=2)[:500]}")
            if "dataset" in data:
                ds = data["dataset"]
                print(f"    Dataset count: {len(ds)}")
                for j, d in enumerate(ds[:3]):
                    print(f"    Dataset {j}: {json.dumps(d, indent=2)[:500]}")
            if "data" in data:
                print(f"    Data: {json.dumps(data['data'], indent=2)[:500]}")
        except json.JSONDecodeError as e:
            print(f"    JSON parse error: {e}")
            print(f"    Raw preview: {json_text[:500]}")

    # Approach C: Look for inline JS variable assignments with economy data
    print("\n--- Approach C: Inline JS Variables ---")
    # Look for var declarations containing arrays of round data
    var_pattern = re.compile(r'var\s+(\w+)\s*=\s*(\[[^\]]{100,}\])', re.DOTALL)
    var_matches = list(var_pattern.finditer(h))
    print(f"  Found {len(var_matches)} large array variable assignments")
    for m in var_matches[:10]:
        name = m.group(1)
        value = m.group(2)
        print(f"    var {name} = [{len(value)} chars]")
        print(f"    Preview: {value[:500]}")

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
