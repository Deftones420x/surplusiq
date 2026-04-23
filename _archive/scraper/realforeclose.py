"""
SurplusIQ — Real Foreclosure Scraper v2
Navigates the calendar UI properly and extracts sold auction results.
"""

import asyncio
import json
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

COUNTIES = [
    {"id": "miami-dade-fl",  "name": "Miami-Dade",  "state": "FL", "auction_url": "https://miami-dade.realforeclose.com",  "has_captcha": False, "doc_days": 14},
    {"id": "broward-fl",     "name": "Broward",     "state": "FL", "auction_url": "https://broward.realforeclose.com",     "has_captcha": False, "doc_days": 7},
    {"id": "duval-fl",       "name": "Duval",       "state": "FL", "auction_url": "https://duval.realforeclose.com",       "has_captcha": False, "doc_days": 5},
    {"id": "lee-fl",         "name": "Lee",         "state": "FL", "auction_url": "https://lee.realforeclose.com",         "has_captcha": True,  "doc_days": 7},
    {"id": "orange-fl",      "name": "Orange",      "state": "FL", "auction_url": "https://orange.realforeclose.com",      "has_captcha": False, "doc_days": 2},
    {"id": "cuyahoga-oh",    "name": "Cuyahoga",    "state": "OH", "auction_url": "https://cuyahoga.realforeclose.com",    "has_captcha": True,  "doc_days": 10},
    {"id": "franklin-oh",    "name": "Franklin",    "state": "OH", "auction_url": "https://franklin.realforeclose.com",    "has_captcha": False, "doc_days": 10},
    {"id": "montgomery-oh",  "name": "Montgomery",  "state": "OH", "auction_url": "https://montgomery.realforeclose.com",  "has_captcha": False, "doc_days": 10},
    {"id": "summit-oh",      "name": "Summit",      "state": "OH", "auction_url": "https://summit.realforeclose.com",      "has_captcha": False, "doc_days": 10},
    {"id": "hamilton-oh",    "name": "Hamilton",    "state": "OH", "auction_url": "https://hamilton.realforeclose.com",    "has_captcha": True,  "doc_days": 10},
]

PLAINTIFF_KEYWORDS = [
    "bank", "n.a.", "trust", "financial", "federal", "national",
    "mortgage", "fannie", "freddie", "wells fargo", "chase", "citibank",
    "us bank", "u.s. bank", "pennymac", "newrez", "ocwen", "nationstar",
    "mr. cooper", "lakeview", "freedom", "plaintiff", "certificate", "no bid",
]


def is_third_party(winner: str, plaintiff: str = "") -> bool:
    if not winner or len(winner.strip()) < 3:
        return False
    w = winner.lower().strip()
    p = plaintiff.lower().strip() if plaintiff else ""
    if p and (p[:20] in w or w[:20] in p):
        return False
    for kw in PLAINTIFF_KEYWORDS:
        if kw in w:
            return False
    return True


def clean_dollar(s: str) -> float:
    if not s:
        return 0.0
    try:
        return float(re.sub(r"[^\d.]", "", str(s)))
    except ValueError:
        return 0.0


async def get_auction_day_ids(page, base_url: str, county_name: str) -> list:
    """
    Navigate the calendar and collect AUCTIONDAYID values.
    Tries the current month and previous month.
    """
    day_ids = []
    today = date.today()

    for month_offset in range(0, 3):
        check = today - timedelta(days=30 * month_offset)
        url = f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={check.strftime('%m/%d/%Y')}"
        try:
            await page.goto(url, timeout=25000)
            await page.wait_for_timeout(2500)

            # Find all AUCTIONDAYID links in page
            content = await page.content()
            for m in re.finditer(r"AUCTIONDAYID=(\d+)", content):
                did = m.group(1)
                if did not in day_ids:
                    day_ids.append(did)

            if day_ids:
                print(f"    Found {len(day_ids)} auction day IDs (month -{month_offset})")
                break

        except Exception:
            continue

    # Also try clicking on any calendar day cells that look like auction dates
    if not day_ids:
        try:
            await page.goto(f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW", timeout=20000)
            await page.wait_for_timeout(2000)
            content = await page.content()
            for m in re.finditer(r"AUCTIONDAYID=(\d+)", content):
                did = m.group(1)
                if did not in day_ids:
                    day_ids.append(did)
        except Exception:
            pass

    return day_ids[:20]


async def scrape_auction_day(page, base_url: str, day_id: str, county: dict) -> list:
    """Scrape all sold properties for one auction day."""
    properties = []

    urls = [
        f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID={day_id}",
        f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=RESULTS&AUCTIONDAYID={day_id}",
        f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID={day_id}&STATUS=SOLD",
    ]

    for url in urls:
        try:
            await page.goto(url, timeout=25000)
            await page.wait_for_timeout(3000)
            content = await page.content()

            # Skip login/home pages
            if (("User Name" in content and "User Password" in content)
                    or "KNOWING THERE" in content
                    or len(content) < 5000):
                continue

            # Save debug HTML on first county run
            debug_dir = DATA_DIR / "diagnostics"
            debug_dir.mkdir(exist_ok=True)
            debug_file = debug_dir / f"{county['id']}_day{day_id}.html"
            if not debug_file.exists():
                debug_file.write_text(content)
                await page.screenshot(path=str(debug_dir / f"{county['id']}_day{day_id}.png"))

            props = await extract_properties(page, content, county, day_id, url)
            if props:
                print(f"    Day {day_id}: {len(props)} properties")
                properties.extend(props)
                break

        except PWTimeout:
            continue
        except Exception as e:
            print(f"    Day {day_id} error: {e}")
            continue

    return properties


async def extract_properties(page, html: str, county: dict, day_id: str, url: str) -> list:
    """Extract properties using multiple strategies."""
    results = []

    # ── Strategy 1: Standard AUCTION_ITEM divs ─────────────────────
    items = await page.query_selector_all(
        ".AUCTION_ITEM, .aitem, [class*='ITEM'], "
        "[class*='auction-item'], [id*='ITEM']"
    )

    # ── Strategy 2: Table rows with bid data ───────────────────────
    if not items:
        items = await page.query_selector_all("tr")

    for item in items:
        try:
            text = (await item.inner_text()).strip()
            if not text or len(text) < 15:
                continue
            # Must have a number pattern suggesting a bid amount
            if not re.search(r"\$[\d,]+|\d{5,}", text):
                continue
            # Skip obvious headers
            if any(h in text for h in ["Case #", "Opening Bid", "Final Bid", "Status", "Plaintiff"]):
                continue

            cells = await item.query_selector_all("td")
            if not cells:
                continue

            vals = [(await c.inner_text()).strip() for c in cells]
            if len(vals) < 3:
                continue

            prop = build_property(vals, text, county, day_id, url)
            if prop:
                results.append(prop)

        except Exception:
            continue

    # ── Strategy 3: Regex fallback on raw HTML ─────────────────────
    if not results:
        results = regex_extract(html, county, day_id, url)

    return results


def build_property(vals: list, raw_text: str, county: dict, day_id: str, url: str):
    """Build a property dict from table cell values."""
    try:
        # Find all dollar amounts
        amounts = []
        for v in vals:
            amt = clean_dollar(v)
            if amt > 500:
                amounts.append(amt)

        if not amounts:
            return None

        # Try to identify case number (first cell that looks like a case #)
        case_num = ""
        for v in vals:
            if re.match(r"\d{2,4}[-/]\w{2,4}[-/]\d{3,}", v) or re.match(r"^\d{6,}$", v):
                case_num = v
                break
        if not case_num:
            case_num = vals[0]

        # Address: first cell with a street pattern
        address = ""
        for v in vals:
            if re.search(r"\d+\s+\w+.*\s+(ST|AVE|BLVD|DR|RD|LN|CT|WAY|PL|CIR)\b", v, re.IGNORECASE):
                address = v
                break
        if not address:
            address = vals[1] if len(vals) > 1 else ""

        # Bids
        opening_bid = amounts[0] if amounts else 0
        final_bid   = amounts[-1] if len(amounts) > 1 else 0

        # No surplus possible if final <= opening
        if final_bid <= opening_bid and final_bid > 0:
            # Swap if it looks like the order is reversed
            if final_bid < opening_bid:
                pass  # Keep as is
            else:
                return None

        # Winner: last non-dollar cell
        winner = ""
        for v in reversed(vals):
            amt = clean_dollar(v)
            if amt == 0 and len(v) > 2 and v != case_num:
                winner = v
                break

        # Plaintiff: look for bank/lender name
        plaintiff = ""
        for v in vals:
            v_lower = v.lower()
            if any(kw in v_lower for kw in ["bank", "mortgage", "financial", "trust", "federal"]):
                plaintiff = v
                break

        return {
            "county_id":        county["id"],
            "county_name":      county["name"],
            "state":            county["state"],
            "auction_day_id":   day_id,
            "case_number":      case_num.strip(),
            "address":          address.strip(),
            "plaintiff":        plaintiff.strip(),
            "opening_bid":      opening_bid,
            "final_sale_price": final_bid if final_bid > 0 else opening_bid,
            "winner_name":      winner.strip(),
            "scrape_url":       url,
            "scraped_at":       datetime.now().isoformat(),
            "sale_date":        date.today().isoformat(),
            "raw_cells":        vals[:8],
        }
    except Exception:
        return None


def regex_extract(html: str, county: dict, day_id: str, url: str) -> list:
    """Regex fallback extraction from raw HTML."""
    results = []
    try:
        pattern = re.compile(
            r"(\d{4}[-/]\w{2,4}[-/]\d{4,})"
            r".{5,400}?"
            r"\$([\d,]+(?:\.\d{2})?)"
            r".{1,300}?"
            r"\$([\d,]+(?:\.\d{2})?)",
            re.DOTALL
        )
        seen = set()
        for m in pattern.finditer(html):
            case_num = m.group(1)
            if case_num in seen:
                continue
            seen.add(case_num)
            opening = clean_dollar(m.group(2))
            final   = clean_dollar(m.group(3))
            if final > opening > 100:
                results.append({
                    "county_id":        county["id"],
                    "county_name":      county["name"],
                    "state":            county["state"],
                    "auction_day_id":   day_id,
                    "case_number":      case_num,
                    "address":          "",
                    "plaintiff":        "",
                    "opening_bid":      opening,
                    "final_sale_price": final,
                    "winner_name":      "",
                    "scrape_url":       url,
                    "scraped_at":       datetime.now().isoformat(),
                    "sale_date":        date.today().isoformat(),
                    "source":           "regex",
                })
    except Exception:
        pass
    return results


async def scrape_county(county: dict, pw, headless: bool = True) -> list:
    print(f"\n🔍 Scraping {county['name']} ({county['state']})...")

    # Always show browser for CAPTCHA counties; otherwise respect headless flag
    run_headless = headless and not county["has_captcha"]

    browser = await pw.chromium.launch(
        headless=run_headless,
        slow_mo=300,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
    )
    page = await context.new_page()
    all_props = []

    try:
        # Load home page first to set cookies/session
        print(f"  Loading {county['auction_url']}...")
        await page.goto(county["auction_url"], timeout=30000)
        await page.wait_for_timeout(2000)

        # Take screenshot of home page
        debug_dir = DATA_DIR / "diagnostics"
        debug_dir.mkdir(exist_ok=True)
        await page.screenshot(path=str(debug_dir / f"{county['id']}_home.png"))

        # Get auction day IDs from calendar
        day_ids = await get_auction_day_ids(page, county["auction_url"], county["name"])
        print(f"  Auction days found: {len(day_ids)} — {day_ids[:5]}")

        if not day_ids:
            # Save home HTML for debugging
            (debug_dir / f"{county['id']}_home.html").write_text(await page.content())
            print(f"  ⚠ No auction days found — saved HTML for inspection")
        else:
            for day_id in day_ids:
                props = await scrape_auction_day(page, county["auction_url"], day_id, county)
                all_props.extend(props)
                await asyncio.sleep(1.5)

    except Exception as e:
        print(f"  ❌ {county['name']}: {e}")
    finally:
        await browser.close()

    print(f"  ✅ {county['name']}: {len(all_props)} properties")
    return all_props


async def run_all_counties(county_ids=None, headless=True):
    targets = [c for c in COUNTIES if not county_ids or c["id"] in county_ids]
    all_results = []

    async with async_playwright() as pw:
        for county in targets:
            try:
                results = await scrape_county(county, pw, headless=headless)
                all_results.extend(results)
                out = DATA_DIR / f"raw_{county['id']}_{date.today().isoformat()}.jsonl"
                with open(out, "w") as f:
                    for p in results:
                        f.write(json.dumps(p) + "\n")
                await asyncio.sleep(3)
            except Exception as e:
                print(f"❌ {county['name']}: {e}")

    combined = DATA_DIR / f"raw_all_{date.today().isoformat()}.jsonl"
    with open(combined, "w") as f:
        for p in all_results:
            f.write(json.dumps(p) + "\n")

    print(f"\n✅ Done: {len(all_results)} properties across {len(targets)} counties")
    return all_results


def load_raw(date_str=None):
    if not date_str:
        date_str = date.today().isoformat()
    fp = DATA_DIR / f"raw_all_{date_str}.jsonl"
    if fp.exists():
        with open(fp) as f:
            return [json.loads(l) for l in f if l.strip()]
    results = []
    for fp in DATA_DIR.glob(f"raw_*_{date_str}.jsonl"):
        if "raw_all" not in fp.name:
            with open(fp) as f:
                results.extend(json.loads(l) for l in f if l.strip())
    return results


if __name__ == "__main__":
    county_ids = sys.argv[1:] if len(sys.argv) > 1 else None
    asyncio.run(run_all_counties(county_ids=county_ids, headless=False))
