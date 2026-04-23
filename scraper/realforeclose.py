"""
SurplusIQ — Real Foreclosure Scraper
Scrapes sold auction results from {county}.realforeclose.com
Identifies third-party bidder sales and extracts case data
"""

import asyncio
import json
import re
import time
from datetime import datetime, date
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ── Paths ────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── Counties config (inline so scraper is self-contained) ────────────
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

# Keywords that indicate the plaintiff/lender won (NOT a third-party sale)
PLAINTIFF_KEYWORDS = [
    "plaintiff", "mortgagee", "bank", "n.a.", "n.a", "trust",
    "llc", "lender", "financial", "federal", "national", "mortgage",
    "fannie", "freddie", "wells fargo", "chase", "citibank", "bac",
    "us bank", "u.s. bank", "pennymac", "newrez", "sls", "phh",
    "ocwen", "nationstar", "mr. cooper", "lakeview", "freedom",
    "no bid", "certificate", "certificate of title to plaintiff",
]


def is_third_party(winner_name: str, plaintiff_name: str) -> bool:
    """Return True if winning bidder appears to be a third party."""
    if not winner_name:
        return False
    w = winner_name.lower().strip()
    p = plaintiff_name.lower().strip() if plaintiff_name else ""

    # Direct plaintiff match
    if p and (p in w or w in p):
        return False

    # Common plaintiff/lender patterns
    for kw in PLAINTIFF_KEYWORDS:
        if kw in w:
            return False

    return True


def clean_dollar(s: str) -> float:
    """Convert '$123,456.78' string to float."""
    if not s:
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", str(s))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


async def handle_captcha(page, county_name: str):
    """Pause for manual CAPTCHA solve if detected."""
    try:
        # Check for common CAPTCHA indicators
        content = await page.content()
        captcha_indicators = ["captcha", "recaptcha", "hcaptcha", "challenge", "verify you are human"]
        if any(ind in content.lower() for ind in captcha_indicators):
            print(f"\n⚠️  CAPTCHA detected on {county_name}!")
            print("   Please solve the CAPTCHA in the browser window.")
            print("   Press ENTER here when done...")
            input()
            print(f"   ✓ Continuing {county_name} scrape...")
    except Exception:
        pass


async def get_auction_day_ids(page, base_url: str, county_name: str) -> list:
    """
    Navigate to the auction calendar and get recent auction day IDs.
    RealForeclose uses AUCTIONDAYID parameter to identify each auction day.
    """
    day_ids = []
    try:
        # Go to the main auction page
        await page.goto(f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW", timeout=30000)
        await page.wait_for_timeout(2000)

        # Look for auction day links in the calendar
        # RealForeclose shows recent auctions in a calendar format
        links = await page.query_selector_all("a[href*='AUCTIONDAYID']")
        for link in links:
            href = await link.get_attribute("href")
            match = re.search(r"AUCTIONDAYID=(\d+)", href or "")
            if match:
                did = match.group(1)
                if did not in day_ids:
                    day_ids.append(did)

        # Also check for date-based navigation
        if not day_ids:
            # Try the results page directly
            results_link = await page.query_selector("a[href*='SOLD'], a[href*='sold'], a[href*='Results']")
            if results_link:
                href = await results_link.get_attribute("href")
                await page.goto(f"{base_url}/{href}", timeout=30000)
                await page.wait_for_timeout(2000)
                links = await page.query_selector_all("a[href*='AUCTIONDAYID']")
                for link in links:
                    href2 = await link.get_attribute("href")
                    match = re.search(r"AUCTIONDAYID=(\d+)", href2 or "")
                    if match:
                        did = match.group(1)
                        if did not in day_ids:
                            day_ids.append(did)

        print(f"  Found {len(day_ids)} auction day IDs for {county_name}")
        return day_ids[:10]  # Last 10 auction days max

    except Exception as e:
        print(f"  ⚠ Could not get auction day IDs for {county_name}: {e}")
        return []


async def scrape_auction_results(page, base_url: str, day_id: str, county: dict) -> list:
    """
    Scrape the sold results for a specific auction day.
    Returns list of raw property dicts.
    """
    properties = []
    url = f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID={day_id}"

    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_timeout(2500)
        await handle_captcha(page, county["name"])

        # RealForeclose shows properties in rows — look for sold items
        # The table typically has columns: case#, address, assessed value,
        # opening bid, final bid, winner
        rows = await page.query_selector_all("tr.AUCTION_ITEM, tr[class*='SOLD'], .AITEM, tr.altRow, tr.Row")

        if not rows:
            # Try alternate selectors
            rows = await page.query_selector_all("table.AUCTION_DETAIL tr, .itemRow, tr[id*='item']")

        for row in rows:
            try:
                row_text = await row.inner_text()
                row_html = await row.inner_html()

                # Skip header rows
                if not row_text.strip() or "Case #" in row_text or "CASE #" in row_text:
                    continue

                # Extract all cells
                cells = await row.query_selector_all("td")
                if len(cells) < 4:
                    continue

                cell_texts = []
                for cell in cells:
                    t = await cell.inner_text()
                    cell_texts.append(t.strip())

                # Parse based on column position (RealForeclose standard layout)
                # Col 0: Case Number
                # Col 1: Property Address
                # Col 2: Assessed/Appraised Value
                # Col 3: Opening Bid / Judgment Amount
                # Col 4: Final Bid / Sale Price
                # Col 5: Winner Name
                # Col 6: Status (SOLD, 3RD PARTY, etc.)

                case_num    = cell_texts[0] if len(cell_texts) > 0 else ""
                address     = cell_texts[1] if len(cell_texts) > 1 else ""
                assessed    = clean_dollar(cell_texts[2]) if len(cell_texts) > 2 else 0.0
                opening_bid = clean_dollar(cell_texts[3]) if len(cell_texts) > 3 else 0.0
                final_bid   = clean_dollar(cell_texts[4]) if len(cell_texts) > 4 else 0.0
                winner      = cell_texts[5] if len(cell_texts) > 5 else ""
                status      = cell_texts[6] if len(cell_texts) > 6 else ""

                # Skip if no final bid or no case number
                if not case_num or final_bid == 0:
                    continue

                # Skip if clearly not sold
                if status and any(s in status.upper() for s in ["CANCEL", "RECESS", "RESET", "CONTINUE"]):
                    continue

                # Try to extract plaintiff from case number page or row
                # Plaintiff is often in a detail link
                plaintiff = ""
                plaintiff_link = await row.query_selector("a[href*='PLAINTIFF'], a[href*='plaintiff']")
                if plaintiff_link:
                    plaintiff = await plaintiff_link.inner_text()

                # Also check for plaintiff in full row text
                if not plaintiff:
                    # Look for "vs" pattern: "BANK OF AMERICA vs JOHNSON"
                    vs_match = re.search(r"(.+?)\s+vs\.?\s+(.+)", row_text, re.IGNORECASE)
                    if vs_match:
                        plaintiff = vs_match.group(1).strip()

                prop = {
                    "county_id":    county["id"],
                    "county_name":  county["name"],
                    "state":        county["state"],
                    "auction_day_id": day_id,
                    "case_number":  case_num.strip(),
                    "address":      address.strip(),
                    "assessed_value": assessed,
                    "opening_bid":  opening_bid,
                    "final_sale_price": final_bid,
                    "winner_name":  winner.strip(),
                    "plaintiff":    plaintiff.strip(),
                    "status":       status.strip(),
                    "scrape_url":   url,
                    "scraped_at":   datetime.now().isoformat(),
                    "sale_date":    date.today().isoformat(),
                }
                properties.append(prop)

            except Exception as e:
                continue

        print(f"    Day {day_id}: {len(properties)} properties found")

    except PWTimeout:
        print(f"  ⚠ Timeout on {county['name']} day {day_id}")
    except Exception as e:
        print(f"  ⚠ Error on {county['name']} day {day_id}: {e}")

    return properties


async def scrape_detail_page(page, base_url: str, case_num: str, county: dict) -> dict:
    """
    Visit the individual auction detail page to get more info:
    plaintiff name, parcel ID, full address, defendant/owner name.
    """
    detail = {}
    try:
        # Search by case number on the county site
        search_url = f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=SEARCH&SearchType=CN&SearchValue={case_num}"
        await page.goto(search_url, timeout=20000)
        await page.wait_for_timeout(1500)

        content = await page.content()

        # Extract plaintiff (lender/foreclosing party)
        plaintiff_match = re.search(
            r"(?:Plaintiff|Lender|Mortgagee)[:\s]+([A-Z][^\n<]{5,80})",
            content, re.IGNORECASE
        )
        if plaintiff_match:
            detail["plaintiff"] = plaintiff_match.group(1).strip()

        # Extract defendant (property owner)
        defendant_match = re.search(
            r"(?:Defendant|Owner|Borrower)[:\s]+([A-Z][^\n<]{3,60})",
            content, re.IGNORECASE
        )
        if defendant_match:
            detail["owner_name"] = defendant_match.group(1).strip()

        # Extract parcel ID
        parcel_match = re.search(
            r"(?:Parcel|Folio|APN|Tax ID)[:\s#]+([A-Z0-9\-\.]{5,25})",
            content, re.IGNORECASE
        )
        if parcel_match:
            detail["parcel_id"] = parcel_match.group(1).strip()

        # Extract sale date from page
        date_match = re.search(
            r"(?:Sale Date|Auction Date)[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})",
            content, re.IGNORECASE
        )
        if date_match:
            detail["sale_date_str"] = date_match.group(1).strip()

    except Exception as e:
        pass

    return detail


async def scrape_county(county: dict, playwright_instance, headless: bool = True) -> list:
    """Full scrape pipeline for one county."""
    print(f"\n🔍 Scraping {county['name']} ({county['state']})...")

    # CAPTCHA counties run headed so user can solve
    run_headless = headless and not county["has_captcha"]

    browser = await playwright_instance.chromium.launch(
        headless=run_headless,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
    )
    page = await context.new_page()

    all_properties = []

    try:
        # Step 1: Get auction day IDs
        day_ids = await get_auction_day_ids(page, county["auction_url"], county["name"])

        if not day_ids:
            print(f"  ⚠ No auction days found for {county['name']} — trying direct results page")
            # Fallback: try direct results URL pattern
            fallback_url = f"{county['auction_url']}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&STATUS=SOLD"
            await page.goto(fallback_url, timeout=20000)
            await page.wait_for_timeout(2000)
            await handle_captcha(page, county["name"])
            # Try to extract from this page directly
            day_ids = ["fallback"]

        # Step 2: Scrape each auction day
        for day_id in day_ids:
            if day_id == "fallback":
                props = await scrape_auction_results(page, county["auction_url"], "0", county)
            else:
                props = await scrape_auction_results(page, county["auction_url"], day_id, county)
            all_properties.extend(props)
            await asyncio.sleep(1.5)  # Be polite

        # Step 3: For each property, try to get detail page info
        print(f"  Fetching detail pages for {len(all_properties)} properties...")
        for i, prop in enumerate(all_properties):
            if prop.get("case_number"):
                detail = await scrape_detail_page(page, county["auction_url"], prop["case_number"], county)
                prop.update(detail)
            if i % 10 == 0 and i > 0:
                print(f"    {i}/{len(all_properties)} details fetched...")
            await asyncio.sleep(0.5)

    except Exception as e:
        print(f"  ❌ Fatal error on {county['name']}: {e}")
    finally:
        await browser.close()

    print(f"  ✅ {county['name']}: {len(all_properties)} total properties scraped")
    return all_properties


async def run_all_counties(county_ids: list = None, headless: bool = True) -> list:
    """
    Run scraper for all (or specified) counties.
    Returns combined list of all scraped properties.
    """
    targets = COUNTIES
    if county_ids:
        targets = [c for c in COUNTIES if c["id"] in county_ids]

    all_results = []

    async with async_playwright() as pw:
        for county in targets:
            try:
                results = await scrape_county(county, pw, headless=headless)
                all_results.extend(results)

                # Save per-county JSONL immediately (so partial runs aren't lost)
                county_file = DATA_DIR / f"raw_{county['id']}_{date.today().isoformat()}.jsonl"
                with open(county_file, "w") as f:
                    for prop in results:
                        f.write(json.dumps(prop) + "\n")
                print(f"  💾 Saved {len(results)} records → {county_file.name}")

                # Pause between counties to avoid hammering the server
                await asyncio.sleep(3)

            except Exception as e:
                print(f"❌ County {county['name']} failed: {e}")
                continue

    # Save combined raw output
    combined_file = DATA_DIR / f"raw_all_{date.today().isoformat()}.jsonl"
    with open(combined_file, "w") as f:
        for prop in all_results:
            f.write(json.dumps(prop) + "\n")

    print(f"\n✅ Scrape complete: {len(all_results)} total properties across {len(targets)} counties")
    print(f"💾 Combined output: {combined_file}")
    return all_results


def load_raw(date_str: str = None) -> list:
    """Load raw scraped data from JSONL file."""
    if not date_str:
        date_str = date.today().isoformat()
    filepath = DATA_DIR / f"raw_all_{date_str}.jsonl"
    if not filepath.exists():
        # Try loading individual county files and merging
        results = []
        for f in DATA_DIR.glob(f"raw_*_{date_str}.jsonl"):
            if "raw_all" not in f.name:
                with open(f) as fp:
                    for line in fp:
                        line = line.strip()
                        if line:
                            results.append(json.loads(line))
        return results
    with open(filepath) as f:
        return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    import sys
    # Optional: pass specific county IDs as args
    # e.g. python scraper/realforeclose.py miami-dade-fl broward-fl
    county_ids = sys.argv[1:] if len(sys.argv) > 1 else None
    asyncio.run(run_all_counties(county_ids=county_ids, headless=True))
