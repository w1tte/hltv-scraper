# Technology Stack

**Project:** HLTV.org CS2 Match Data Scraper
**Researched:** 2026-02-14
**Overall Confidence:** HIGH

---

## Executive Recommendation

Use a **two-tier HTTP strategy**: `curl_cffi` for fast, fingerprint-safe bulk requests as the primary transport, with `SeleniumBase UC Mode` as a fallback for pages that trigger Cloudflare Turnstile challenges. Parse HTML with `selectolax` for speed (falling back to `BeautifulSoup4` for complex DOM traversal). Validate scraped data with `Pydantic` models. Store in `SQLite` via raw `sqlite3` (standard library) with `Peewee` ORM for schema management and queries. Use `tenacity` for retry/backoff logic.

---

## Recommended Stack

### Python Runtime

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | >= 3.10, target 3.12 | Runtime | 3.10 is the minimum for `curl_cffi 0.14+` and `tenacity 9.1+`. Target 3.12 for best performance (PEP 709 inlined comprehensions, improved error messages). 3.13+ works but free-threaded mode is experimental and unnecessary here. | HIGH |

### HTTP Transport (Primary): curl_cffi

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| [curl_cffi](https://github.com/lexiforest/curl_cffi) | 0.14.0 | Primary HTTP client with TLS fingerprint impersonation | Impersonates real browser TLS/JA3/HTTP2 fingerprints at the network level. HLTV uses Cloudflare, and `curl_cffi` can pass Cloudflare's passive TLS fingerprinting without launching a real browser. Much faster than browser automation (~50ms vs ~2-5s per request). Familiar `requests`-like API. Supports async via asyncio. | HIGH |

**Why curl_cffi over alternatives:**

| Alternative | Why Not |
|-------------|---------|
| `requests` | No TLS fingerprint impersonation. Cloudflare instantly detects the default Python TLS stack. Will get 403 on HLTV. |
| `httpx` | Better async support than `requests`, but same TLS fingerprint problem. Cloudflare blocks it. |
| `aiohttp` | Fast async HTTP, but no fingerprint impersonation. The `hltv-async-api` project uses it and resorts to retry-and-pray on 403s. |
| `cloudscraper` | Solves basic Cloudflare JS challenges but has not kept up with Cloudflare's 2025-2026 updates. Relies on JS interpreters (js2py) that frequently break. Maintenance is sporadic. |
| `requests` + `curl_cffi` together | Unnecessary. `curl_cffi` has a `requests`-compatible API. No reason to use both. |

**Key curl_cffi configuration for HLTV:**

```python
from curl_cffi import requests as curl_requests

session = curl_requests.Session(
    impersonate="chrome124",  # Impersonate recent Chrome TLS fingerprint
    timeout=30,
)
response = session.get("https://www.hltv.org/matches")
```

### HTTP Transport (Fallback): SeleniumBase UC Mode

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| [SeleniumBase](https://seleniumbase.io/) | 4.46.5 | Fallback browser automation for Cloudflare Turnstile challenges | When `curl_cffi` gets a 403/challenge page, SeleniumBase UC Mode launches a real Chrome instance that passes Cloudflare's full challenge flow including Turnstile. UC Mode patches ChromeDriver to be undetectable, handles driver downloads automatically, and has built-in CAPTCHA-clicking helpers. More stable for production than `nodriver`. | HIGH |

**Why SeleniumBase UC Mode over alternatives:**

| Alternative | Why Not |
|-------------|---------|
| `nodriver` | Technically excellent (async, no Selenium dependency, direct CDP). But last PyPI release is Nov 2025 (0.48.1) and the project has periods of maintenance gaps. SeleniumBase has more active maintenance (Feb 2026 release) and better documentation. Consider `nodriver` if SeleniumBase UC mode stops working. |
| `Playwright` (vanilla) | Excellent browser automation but lacks built-in anti-detection. Cloudflare detects default Playwright easily. Requires `playwright-stealth` plugin which is poorly maintained. |
| `Camoufox` | Promising concept (anti-detect Firefox at C++ level) but currently in unstable beta (v146.0.1-beta.25). Maintainer had a medical emergency, community fork exists but experimental. Not production-ready in Feb 2026. Revisit in 6 months. |
| `undetected-chromedriver` | Predecessor to `nodriver`. Effectively deprecated in favor of `nodriver` and SeleniumBase UC Mode. No reason to use directly. |
| Vanilla `Selenium` | Trivially detected by Cloudflare. The `navigator.webdriver` flag and ChromeDriver artifacts are immediately flagged. |

**Key SeleniumBase UC Mode configuration:**

```python
from seleniumbase import Driver

driver = Driver(uc=True, headless=True)
driver.uc_open_with_reconnect("https://www.hltv.org/matches", reconnect_time=3)
html = driver.page_source
driver.quit()
```

### HTML Parsing (Primary): selectolax

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| [selectolax](https://github.com/rushter/selectolax) | 0.4.6 | Fast HTML parsing with CSS selectors | 20-30x faster than BeautifulSoup for CSS selector queries. Built on C-level Modest/Lexbor engines. HLTV match pages have large, complex HTML tables -- speed matters for bulk historical scraping (thousands of pages). CSS selectors cover 95%+ of HLTV extraction needs. | HIGH |

### HTML Parsing (Secondary): BeautifulSoup4

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| [beautifulsoup4](https://pypi.org/project/beautifulsoup4/) | 4.14.3 | Complex DOM navigation fallback | For the 5% of cases where you need sibling/parent traversal, `.find_next_sibling()`, or navigating poorly structured HTML that CSS selectors handle awkwardly. The HLTV match detail page has some nested structures where BS4's tree navigation is more readable. Massive community -- every HLTV scraper example uses it, so debugging is easier. | HIGH |
| [lxml](https://pypi.org/project/lxml/) | 6.0.2 | BS4's parser backend | Use `lxml` as BS4's parser (not `html.parser`) for 5-10x speed improvement. Also needed if any XPath queries are required. | HIGH |

**Why not just one parser:**

- `selectolax` alone: Handles 95% of cases faster. But it lacks BS4's tree navigation API (`.parent`, `.find_next_sibling()`). Some HLTV pages have table structures where CSS selectors get verbose.
- `BS4` alone: Works fine but 20-30x slower. For scraping 50,000+ historical match pages, the parsing time difference is material (minutes vs hours).
- **Recommended pattern**: Use `selectolax` as default. Import `BeautifulSoup` only in parser functions that need DOM traversal.

### Data Validation: Pydantic

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| [pydantic](https://pydantic.dev/) | 2.12.5 | Data validation and type coercion for scraped data | Scraped data is inherently messy -- missing fields, wrong types, unexpected formats. Pydantic validates at the boundary between "raw HTML" and "structured data". Catches data quality issues immediately instead of discovering them downstream in analysis/ML. JSON schema generation is a bonus for documentation. | HIGH |

**Why Pydantic over alternatives:**

| Alternative | Why Not |
|-------------|---------|
| Python `dataclasses` | No runtime validation. A missing field or wrong type silently passes. For scraped data from HTML (which changes without notice), runtime validation is critical. |
| `attrs` | Good library but Pydantic has better validation, coercion (string "1.23" to float), and ecosystem adoption. |
| Manual validation | Error-prone, repetitive, harder to maintain. Pydantic models serve as both validation AND documentation of the data schema. |

**Example model for HLTV match data:**

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class PlayerStats(BaseModel):
    name: str
    kills: int
    deaths: int
    adr: float
    kast: float  # percentage as decimal
    rating: float  # HLTV 2.1 rating

class MapResult(BaseModel):
    map_name: str
    team1_score: int
    team2_score: int
    team1_players: list[PlayerStats]
    team2_players: list[PlayerStats]

class MatchResult(BaseModel):
    hltv_match_id: int
    date: datetime
    event: str
    team1: str
    team2: str
    team1_score: int
    team2_score: int
    best_of: int
    maps: list[MapResult]
    url: str
```

### Database: SQLite + Peewee ORM

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| `sqlite3` | stdlib | Database engine | Zero-config, single-file, perfect for a single-user scraping project. Fast enough for millions of rows. No server to maintain. Portable -- copy the .db file anywhere. Architecture research already decided on SQLite. | HIGH |
| [peewee](https://docs.peewee-orm.com/) | 3.19.0 | ORM for schema management and queries | Lightweight single-file ORM purpose-built for SQLite. Simpler than SQLAlchemy for a project of this scope. Built-in migration support via `playhouse`. Expressive query API. The `dataset` module provides high-level JSON/CSV import-export, useful for feeding data to analysis tools. | MEDIUM |

**Why Peewee over alternatives:**

| Alternative | Why Not |
|-------------|---------|
| `SQLAlchemy` | Overkill for a single-user SQLite scraping project. The session/engine/connection pool abstractions add complexity without benefit for SQLite. Peewee is ~6,600 lines vs SQLAlchemy's ~100,000+. |
| `sqlite-utils` | Excellent CLI tool by Simon Willison but more suited to ad-hoc data exploration than structured application code. No ORM -- you work with dicts, not models. Consider it as a complementary tool for data exploration after scraping. |
| Raw `sqlite3` only | Works but you end up writing your own migration system, query builder, and connection management. Peewee gives you these for free with minimal overhead. |
| `dataset` (library) | High-level but hides schema. For a project feeding ML pipelines, explicit schema control matters. |

**Why MEDIUM confidence on Peewee:** Peewee vs raw `sqlite3` is a judgment call. If the project stays small (< 10 models), raw `sqlite3` with handwritten SQL is a valid alternative with fewer dependencies. Peewee shines when schema evolves or queries get complex. The recommendation is Peewee, but switching to raw `sqlite3` later is trivial since Peewee uses standard SQLite underneath.

### Retry & Rate Limiting: tenacity

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| [tenacity](https://tenacity.readthedocs.io/) | 9.1.4 | Retry with exponential backoff | HLTV rate-limits aggressively. `tenacity` provides declarative retry logic with exponential backoff + jitter. Handles transient 403s, 429s, and network errors without custom retry loops. Well-maintained (Feb 2026 release). | HIGH |

**Configuration for HLTV:**

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
)
def fetch_match_page(url: str) -> str:
    ...
```

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| [tqdm](https://pypi.org/project/tqdm/) | latest | Progress bars | Bulk scraping thousands of pages needs visual progress feedback. Shows ETA, rate, completed count. | HIGH |
| [python-dateutil](https://pypi.org/project/python-dateutil/) | latest | Date parsing | HLTV displays dates in various formats ("2 days ago", "Jan 15th", etc.). `dateutil.parser` handles ambiguous date formats robustly. | HIGH |
| [fake-useragent](https://pypi.org/project/fake-useragent/) | latest | User-agent rotation | Rotate realistic user-agent strings to avoid fingerprinting on that vector. Less critical when `curl_cffi` impersonates browsers, but useful for the `User-Agent` header itself. | LOW |
| [pytest](https://pypi.org/project/pytest/) | latest | Testing | Test parsers against saved HTML fixtures. Essential for catching breakage when HLTV changes their HTML structure. | HIGH |

---

## What NOT to Use

### Scrapy

**Do not use Scrapy.** While it is the most popular Python scraping framework, it is wrong for this project for two reasons:

1. **Cloudflare bypass is painful in Scrapy.** Scrapy's middleware architecture makes it hard to integrate browser-based Cloudflare bypass. You end up fighting the framework to do something it was not designed for.
2. **Overkill for a single-site scraper.** Scrapy's power is in crawling thousands of different sites with link-following spiders. HLTV scraping is a known set of URL patterns with structured pages. A simpler request-parse-store loop is more maintainable.
3. **Learning curve without payoff.** Scrapy has its own async loop (Twisted), item pipelines, middleware chains, and settings system. For one site, this is overhead.

### cloudscraper

**Do not use cloudscraper as a primary tool.** It was popular in 2020-2023 but has not kept up with Cloudflare's 2024-2026 detection updates. It relies on `js2py` to solve JavaScript challenges, which frequently breaks on newer Cloudflare versions. The library has sporadic maintenance. `curl_cffi` handles the TLS fingerprinting layer better, and SeleniumBase handles the JS challenge layer better. `cloudscraper` sits in an awkward middle ground.

### requests / httpx (without fingerprint impersonation)

**Do not use vanilla `requests` or `httpx` for HLTV.** Both use Python's default TLS stack, which Cloudflare fingerprints and blocks instantly. You will get 403 errors on every request. The only way to make them work is behind a commercial proxy service that does its own TLS rewriting, which adds cost and latency.

### Playwright (vanilla, without anti-detect patching)

**Do not use vanilla Playwright for HLTV.** Cloudflare detects standard Playwright via JavaScript environment inspection (`navigator.webdriver`, missing browser APIs, etc.). The `playwright-stealth` plugin is poorly maintained and was deprecated upstream (puppeteer-extra-stealth) in February 2026. If you want Playwright-style browser automation, use Camoufox (when it stabilizes) or SeleniumBase UC Mode.

---

## Tiered Approach: When to Use What

The stack is designed as layers. Use the lightest layer that works:

```
Tier 1: curl_cffi (fast, no browser)
  |
  | If 403 / challenge page detected
  v
Tier 2: SeleniumBase UC Mode (real browser, slower)
  |
  | If UC Mode fails (rare, advanced Cloudflare)
  v
Tier 3: Manual intervention or proxy service (last resort)
```

**Expected HLTV behavior based on community experience:**
- Most HLTV pages serve fine with proper TLS fingerprinting (`curl_cffi`). HLTV's Cloudflare is configured for basic bot protection, not enterprise-level.
- Rate limiting kicks in at roughly 20-30 requests/minute without delays. Use 3-6 second delays between requests.
- Occasional Turnstile challenges appear during high-traffic periods or from datacenter IPs. This is where SeleniumBase fallback activates.
- **Confidence on HLTV-specific behavior: MEDIUM** -- based on community scraper reports and the `hltv-async-api` project's approach (retry on 403 with escalating delays). Exact thresholds need empirical testing.

---

## Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Core HTTP transport
pip install curl_cffi==0.14.0

# Fallback browser automation
pip install seleniumbase==4.46.5

# HTML parsing
pip install selectolax==0.4.6
pip install beautifulsoup4==4.14.3
pip install lxml==6.0.2

# Data validation
pip install pydantic==2.12.5

# Database ORM
pip install peewee==3.19.0

# Retry logic
pip install tenacity==9.1.4

# Utilities
pip install tqdm python-dateutil

# Development
pip install pytest

# Install browser for SeleniumBase (one-time)
seleniumbase install chromedriver
```

**requirements.txt:**
```
curl_cffi>=0.14.0,<1.0
seleniumbase>=4.46,<5.0
selectolax>=0.4.6,<1.0
beautifulsoup4>=4.14,<5.0
lxml>=6.0,<7.0
pydantic>=2.12,<3.0
peewee>=3.19,<4.0
tenacity>=9.1,<10.0
tqdm>=4.0
python-dateutil>=2.0
```

**dev-requirements.txt:**
```
pytest>=8.0
```

---

## Version Compatibility Matrix

| Library | Min Python | Max Python | Notes |
|---------|-----------|-----------|-------|
| curl_cffi 0.14 | 3.10 | 3.14 | **This sets our minimum at Python 3.10** |
| seleniumbase 4.46 | 3.9 | 3.14 | |
| selectolax 0.4.6 | 3.9 | 3.14 | |
| beautifulsoup4 4.14 | 3.x | 3.14 | Very permissive |
| lxml 6.0 | 3.8 | 3.14 | |
| pydantic 2.12 | 3.9 | 3.14 | |
| peewee 3.19 | 2.7+ | 3.14 | Very permissive |
| tenacity 9.1 | 3.10 | 3.14 | Also sets minimum at 3.10 |

**Constraining factor:** `curl_cffi` 0.14+ and `tenacity` 9.1+ both require Python >= 3.10. Target **Python 3.12** for the best balance of compatibility and performance.

---

## Sources

### Verified via PyPI (HIGH confidence)
- [curl_cffi 0.14.0](https://pypi.org/project/curl-cffi/) - Released 2025-12-16
- [SeleniumBase 4.46.5](https://pypi.org/project/seleniumbase/) - Released 2026-02-11
- [selectolax 0.4.6](https://pypi.org/project/selectolax/) - Released 2025-12-06
- [beautifulsoup4 4.14.3](https://pypi.org/project/beautifulsoup4/) - Released 2025-11-30
- [lxml 6.0.2](https://pypi.org/project/lxml/) - Released 2025-09-22
- [pydantic 2.12.5](https://pypi.org/project/pydantic/) - Released 2025
- [peewee 3.19.0](https://pypi.org/project/peewee/) - Released 2026-01-07
- [tenacity 9.1.4](https://pypi.org/project/tenacity/) - Released 2026-02-07
- [nodriver 0.48.1](https://pypi.org/project/nodriver/) - Released 2025-11-09 (evaluated, not recommended)
- [Playwright 1.58.0](https://pypi.org/project/playwright/) - Released 2026-01-30 (evaluated, not recommended alone)

### Verified via GitHub/official docs (HIGH confidence)
- [curl_cffi GitHub](https://github.com/lexiforest/curl_cffi) - Browser impersonation capabilities
- [SeleniumBase UC Mode docs](https://seleniumbase.io/help_docs/uc_mode/) - Undetected Chrome mode
- [nodriver GitHub](https://github.com/ultrafunkamsterdam/nodriver) - Successor to undetected-chromedriver
- [Camoufox GitHub](https://github.com/daijro/camoufox) - Anti-detect browser (beta, not recommended yet)

### Community/ecosystem research (MEDIUM confidence)
- [Playwright vs Selenium 2026 - BrowserStack](https://www.browserstack.com/guide/playwright-vs-selenium)
- [Bypass Cloudflare 2026 - Scrape.do](https://scrape.do/blog/bypass-cloudflare/)
- [curl_cffi for Cloudflare - Datahut](https://www.blog.datahut.co/post/web-scraping-without-getting-blocked-curl-cffi)
- [HTML parser comparison - Medium](https://medium.com/@yahyamrafe202/in-depth-comparison-of-web-scraping-parsers-lxml-beautifulsoup-and-selectolax-4f268ddea8df)
- [Nodriver for web scraping - BrightData](https://brightdata.com/blog/web-data/nodriver-web-scraping)

### Existing HLTV scraper projects (MEDIUM confidence for patterns)
- [hltv-async-api](https://github.com/akimerslys/hltv-async-api) - Async approach, aiohttp + BS4, retry on 403
- [jparedesDS/hltv-scraper](https://github.com/jparedesDS/hltv-scraper) - Selenium + undetected-chromedriver + BS4
- [HLTV.org-Scraper](https://github.com/gelbling/HLTV.org-Scraper) - Scrapy-based (Python 3.8 era)
- [nmwalsh/HLTV-Scraper](https://github.com/nmwalsh/HLTV-Scraper) - Multi-threaded, pure Python

---

## Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Python version | HIGH | Verified minimum requirements across all libraries via PyPI |
| curl_cffi as primary transport | HIGH | Well-documented, actively maintained, purpose-built for TLS impersonation. Verified via PyPI and GitHub. |
| SeleniumBase as fallback | HIGH | Actively maintained (Feb 2026), UC Mode well-documented, widely used for Cloudflare bypass |
| selectolax for parsing | HIGH | Version and benchmarks verified. Clear performance advantage for bulk parsing. |
| Pydantic for validation | HIGH | Industry standard, verified version, obvious fit for scraped data validation |
| Peewee for SQLite ORM | MEDIUM | Good fit but debatable vs raw sqlite3. Recommendation based on schema evolution needs. |
| tenacity for retries | HIGH | Verified version, standard library for this purpose, well-maintained |
| HLTV-specific Cloudflare behavior | MEDIUM | Based on community scraper patterns, not direct testing. Exact rate limits and challenge triggers need empirical validation in Phase 1. |
| Camoufox as future option | LOW | Currently in beta, maintenance disrupted. Flagged for re-evaluation only. |
