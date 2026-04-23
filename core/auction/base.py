"""
SurplusIQ — Auction Scraper Base Class
Abstract interface all county scrapers inherit from.

Every scraper promises to return a list of RawSale dicts with this shape:
{
    "county_id":        str,
    "case_number":      str,
    "address":          str,
    "opening_bid":      float,
    "final_sale_price": float,
    "winner_name":      str,
    "sale_date":        str (ISO),
    "auction_day_id":   str,
    "detail_url":       str,
    "is_third_party":   bool,
    "raw_text":         str,  # For debugging
}

Subclasses must implement:
- get_auction_days() — returns list of auction day IDs for the past N days
- scrape_auction_day(day_id) — returns list of raw sales for that day
"""

import asyncio
import json
import re
import sys
from abc import ABC, abstractmethod
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
RAW_DIR      = DATA_DIR / "raw"
DIAG_DIR     = DATA_DIR / "diagnostics"
for d in (RAW_DIR, DIAG_DIR):
    d.mkdir(parents=True, exist_ok=True)


# Plaintiff/lender keywords — if winner matches these, NOT a third-party sale
PLAINTIFF_KEYWORDS = [
    "bank", "n.a.", "n.a", "trust", "financial", "federal", "national",
    "mortgage", "fannie", "freddie", "wells fargo", "chase", "citibank",
    "us bank", "u.s. bank", "pennymac", "newrez", "ocwen", "nationstar",
    "mr. cooper", "lakeview", "freedom", "plaintiff", "certificate",
    "no bid", "no sale", "cancel",
]


def clean_dollar(s) -> float:
    """Convert '$123,456.78' to float. Returns 0.0 on any failure."""
    if not s:
        return 0.0
    try:
        return float(re.sub(r"[^\d.]", "", str(s)))
    except ValueError:
        return 0.0


def is_third_party(winner: str) -> bool:
    """True if the winner name looks like a genuine third-party bidder."""
    if not winner or len(winner.strip()) < 3:
        return False
    w = winner.lower().strip()
    for kw in PLAINTIFF_KEYWORDS:
        if kw in w:
            return False
    return True


class AuctionScraperBase(ABC):
    """Base class all county auction scrapers inherit from."""

    def __init__(self, county_config):
        self.county = county_config
        self.county_id   = county_config.id
        self.county_name = county_config.name
        self.state       = county_config.state
        self.base_url    = county_config.auction_url
        self.has_captcha = county_config.has_captcha
        self.vpn_blocked = county_config.vpn_blocked

        # Diagnostic folder for this county
        self.diag_dir = DIAG_DIR / self.county_id
        self.diag_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    async def get_auction_days(self, page: Page, days_back: int = 7) -> list:
        """Return a list of auction day IDs to scrape (typically last N days)."""
        raise NotImplementedError

    @abstractmethod
    async def scrape_auction_day(self, page: Page, day_id: str) -> list:
        """Scrape all properties sold on a specific auction day. Return list of raw sale dicts."""
        raise NotImplementedError

    async def setup_browser(self, playwright, headless: bool = True) -> tuple[Browser, BrowserContext, Page]:
        """Create browser with county-appropriate settings."""
        # CAPTCHA counties always run headed so user can solve manually
        run_headless = headless and not self.has_captcha

        browser = await playwright.chromium.launch(
            headless=run_headless,
            slow_mo=250,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
        )
        page = await context.new_page()
        return browser, context, page

    async def handle_captcha(self, page: Page) -> None:
        """Pause pipeline for manual CAPTCHA solve if detected."""
        try:
            content = await page.content()
            captcha_hints = ["captcha", "recaptcha", "hcaptcha", "verify you", "i'm not a robot"]
            if any(h in content.lower() for h in captcha_hints):
                print(f"\n⚠️  [{self.county_name}] CAPTCHA detected.")
                print(f"    Solve it in the browser window, then press ENTER here...")
                input()
                print(f"    ✓ Continuing {self.county_name}...")
        except Exception:
            pass

    async def save_diagnostic(self, page: Page, label: str) -> None:
        """Save screenshot + HTML for debugging."""
        try:
            ss_path   = self.diag_dir / f"{label}.png"
            html_path = self.diag_dir / f"{label}.html"
            await page.screenshot(path=str(ss_path), full_page=True)
            html_path.write_text(await page.content())
            print(f"    📸 Saved diagnostic: {ss_path.relative_to(PROJECT_ROOT)}")
        except Exception as e:
            print(f"    ⚠ Could not save diagnostic: {e}")

    def save_raw_output(self, sales: list) -> Path:
        """Save raw scraped sales to JSONL for next pipeline stage."""
        today = date.today().isoformat()
        out_file = RAW_DIR / f"{self.county_id}_{today}.jsonl"
        with open(out_file, "w") as f:
            for sale in sales:
                f.write(json.dumps(sale) + "\n")
        print(f"    💾 Saved {len(sales)} sales → {out_file.relative_to(PROJECT_ROOT)}")
        return out_file

    async def scrape(self, headless: bool = True, days_back: int = 7) -> list:
        """Main entry point — runs the full scrape for this county."""
        print(f"\n🏛  Scraping {self.county_name}, {self.state}")
        print(f"    URL: {self.base_url}")

        if self.vpn_blocked:
            print(f"    ⚠️  WARNING: {self.county_name} blocks VPNs. Turn off VPN before running.")

        all_sales = []

        async with async_playwright() as pw:
            browser, context, page = await self.setup_browser(pw, headless=headless)

            try:
                # Phase 1: Establish session by visiting home page
                print(f"    → Loading home page...")
                await page.goto(self.base_url, timeout=30000)
                await page.wait_for_timeout(2500)

                # Phase 2: Get auction days
                day_ids = await self.get_auction_days(page, days_back=days_back)
                print(f"    → Found {len(day_ids)} auction days")

                if not day_ids:
                    await self.save_diagnostic(page, "no_auction_days")
                    return []

                # Phase 3: Scrape each day
                for day_id in day_ids:
                    try:
                        sales = await self.scrape_auction_day(page, day_id)
                        # Add metadata
                        for sale in sales:
                            sale.setdefault("county_id",   self.county_id)
                            sale.setdefault("county_name", self.county_name)
                            sale.setdefault("state",       self.state)
                            sale.setdefault("is_third_party", is_third_party(sale.get("winner_name", "")))
                            sale.setdefault("scraped_at",  datetime.now().isoformat())
                        all_sales.extend(sales)
                        print(f"    → Day {day_id}: {len(sales)} sales")
                        await asyncio.sleep(1.5)
                    except Exception as e:
                        print(f"    ⚠ Day {day_id} failed: {e}")
                        continue

            except Exception as e:
                print(f"    ❌ Scrape failed: {e}")
                await self.save_diagnostic(page, "error")
            finally:
                await browser.close()

        # Save output
        self.save_raw_output(all_sales)

        # Summary
        third_party_count = sum(1 for s in all_sales if s.get("is_third_party"))
        print(f"\n  ✅ {self.county_name}: {len(all_sales)} total, {third_party_count} third-party")
        return all_sales


# ─────────────────────────────────────────────────────────────────────
# Concrete implementation placeholder for RealForeclose
# Once VA provides verified URLs, we plug them in here.
# ─────────────────────────────────────────────────────────────────────

class RealForecloseScraper(AuctionScraperBase):
    """
    Scraper for counties on the Real Foreclosure platform.
    Works for: Miami-Dade, Broward, Duval, Lee, Orange (FL)
               Cuyahoga, Franklin, Montgomery, Summit, Hamilton (OH)

    Each county shares the same platform so URL patterns are identical —
    only the subdomain changes.
    """

    async def get_auction_days(self, page: Page, days_back: int = 7) -> list:
        """
        Navigate the calendar and extract AUCTIONDAYID values for recent dates.

        PLACEHOLDER — this needs to be verified against real page structure
        once VA confirms the exact URL pattern.
        """
        day_ids = []
        today = date.today()

        # Try URL patterns in priority order
        url_patterns = [
            f"{self.base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW",
            f"{self.base_url}/index.cfm?zaction=USER&zmethod=CALENDAR",
        ]

        for url in url_patterns:
            try:
                await page.goto(url, timeout=25000)
                await page.wait_for_timeout(3000)
                await self.handle_captcha(page)

                content = await page.content()

                # Skip if we're on marketing/login page
                if ("User Name" in content and "User Password" in content
                        and "KNOWING THERE" in content):
                    continue

                # Extract AUCTIONDAYID references
                for match in re.finditer(r"AUCTIONDAYID=(\d+)", content):
                    did = match.group(1)
                    if did not in day_ids:
                        day_ids.append(did)

                if day_ids:
                    break

            except Exception as e:
                print(f"    ⚠ URL pattern failed: {url}: {e}")
                continue

        # If calendar navigation didn't work, try date-based URLs
        if not day_ids:
            for n in range(days_back):
                check_date = today - timedelta(days=n)
                dt_url = (
                    f"{self.base_url}/index.cfm?zaction=AUCTION"
                    f"&Zmethod=PREVIEW&AUCTIONDATE={check_date.strftime('%m/%d/%Y')}"
                )
                try:
                    await page.goto(dt_url, timeout=15000)
                    await page.wait_for_timeout(2000)
                    content = await page.content()
                    for match in re.finditer(r"AUCTIONDAYID=(\d+)", content):
                        did = match.group(1)
                        if did not in day_ids:
                            day_ids.append(did)
                except Exception:
                    continue

        return day_ids[:days_back + 3]  # Slightly more than asked for

    async def scrape_auction_day(self, page: Page, day_id: str) -> list:
        """
        Scrape properties sold on a specific auction day.

        PLACEHOLDER — the exact DOM structure needs verification from VA
        screenshots. This is a best-effort implementation that tries multiple
        selectors.
        """
        sales = []

        # Try URLs in priority order (sold filter first)
        urls = [
            f"{self.base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID={day_id}&STATUS=SOLD",
            f"{self.base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID={day_id}",
        ]

        for url in urls:
            try:
                await page.goto(url, timeout=25000)
                await page.wait_for_timeout(3000)
                await self.handle_captcha(page)

                content = await page.content()
                if not self._is_valid_auction_page(content):
                    continue

                # Try multiple item selectors
                item_selectors = [
                    ".AUCTION_ITEM",
                    ".AITEM",
                    "[id^='itemDIV']",
                    "tr.Row",
                    "tr.altRow",
                    "[class*='auction-item']",
                ]

                items = []
                for sel in item_selectors:
                    items = await page.query_selector_all(sel)
                    if items:
                        break

                if not items:
                    # Fallback to regex extraction
                    sales.extend(self._regex_extract(content, day_id))
                    if sales:
                        break
                    continue

                for item in items:
                    try:
                        sale = await self._parse_item(item, day_id)
                        if sale:
                            sales.append(sale)
                    except Exception:
                        continue

                if sales:
                    break

            except Exception as e:
                print(f"      Day {day_id} URL error: {e}")
                continue

        return sales

    def _is_valid_auction_page(self, html: str) -> bool:
        """Check if we're actually on an auction page, not marketing/login."""
        if len(html) < 5000:
            return False
        if "User Name" in html and "User Password" in html and "KNOWING THERE" in html:
            return False
        return True

    async def _parse_item(self, item, day_id: str) -> Optional[dict]:
        """Parse a single auction item element."""
        text = (await item.inner_text()).strip()
        if not text or len(text) < 30:
            return None

        # Case number
        case_match = re.search(r"(\d{4}-[A-Z]{2,4}-\d{4,})", text)
        if not case_match:
            return None
        case_num = case_match.group(1)

        # Dollar amounts
        dollars = re.findall(r"\$([\d,]+(?:\.\d{2})?)", text)
        amounts = sorted([clean_dollar(d) for d in dollars if clean_dollar(d) > 500])
        if len(amounts) < 2:
            return None

        final_sale = amounts[-1]
        opening_bid = amounts[-2] if len(amounts) >= 2 else 0
        if final_sale <= opening_bid:
            return None

        # Address
        address = ""
        for line in text.split("\n"):
            line = line.strip()
            if re.search(r"\d+.*\b(ST|AVE|BLVD|DR|RD|LN|CT|WAY|PL|CIR|STREET|AVENUE)\b", line, re.IGNORECASE):
                address = line
                break

        return {
            "case_number":      case_num,
            "address":          address,
            "opening_bid":      opening_bid,
            "final_sale_price": final_sale,
            "winner_name":      "",  # RealForeclose often omits winner on main page
            "auction_day_id":   day_id,
            "sale_date":        date.today().isoformat(),  # Refined later
            "detail_url":       f"{self.base_url}/index.cfm?zaction=AUCTION&Zmethod=DETAILS&AUCTIONDAYID={day_id}",
            "raw_text":         text[:500],
        }

    def _regex_extract(self, html: str, day_id: str) -> list:
        """Fallback extraction using regex on raw HTML."""
        sales = []
        seen = set()
        pattern = re.compile(
            r"(\d{4}-[A-Z]{2,4}-\d{4,})"
            r".{10,600}?"
            r"\$([\d,]+(?:\.\d{2})?)"
            r".{1,300}?"
            r"\$([\d,]+(?:\.\d{2})?)",
            re.DOTALL
        )
        for m in pattern.finditer(html):
            case_num = m.group(1)
            if case_num in seen:
                continue
            seen.add(case_num)

            opening = clean_dollar(m.group(2))
            final = clean_dollar(m.group(3))
            if final <= opening or opening < 500:
                continue

            sales.append({
                "case_number":      case_num,
                "address":          "",
                "opening_bid":      opening,
                "final_sale_price": final,
                "winner_name":      "",
                "auction_day_id":   day_id,
                "sale_date":        date.today().isoformat(),
                "detail_url":       "",
                "raw_text":         "",
                "extraction_method": "regex",
            })
        return sales


# ─────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Run: python -m core.auction.base <county_id> [--headed]"""
    # Import here to avoid circular imports
    sys.path.insert(0, str(PROJECT_ROOT))
    from config.counties import get_county

    county_id = sys.argv[1] if len(sys.argv) > 1 else "miami-dade-fl"
    headless = "--headed" not in sys.argv

    county = get_county(county_id)
    scraper = RealForecloseScraper(county)
    results = asyncio.run(scraper.scrape(headless=headless))

    print(f"\n{'='*60}")
    print(f"  RESULTS: {county.name}")
    print(f"{'='*60}")
    print(f"  Total sales:     {len(results)}")
    print(f"  Third-party:     {sum(1 for s in results if s.get('is_third_party'))}")

    if results:
        top5 = sorted(results, key=lambda s: s.get("final_sale_price", 0), reverse=True)[:5]
        print(f"\n  Top 5 by sale price:")
        for s in top5:
            surplus = s.get("final_sale_price", 0) - s.get("opening_bid", 0)
            print(f"    ${s.get('final_sale_price', 0):>10,.0f}  surplus ${surplus:>10,.0f}  {s.get('case_number')}")
