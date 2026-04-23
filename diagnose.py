"""
SurplusIQ — Diagnostic Script
Opens Real Foreclosure pages in browser and saves HTML + screenshot
So we can see exactly what structure to scrape

Run: python diagnose.py
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT = Path.home() / "Desktop" / "surplusiq" / "data" / "diagnostics"
OUTPUT.mkdir(parents=True, exist_ok=True)

COUNTIES = [
    {"name": "Miami-Dade", "url": "https://miami-dade.realforeclose.com"},
    {"name": "Cuyahoga",   "url": "https://cuyahoga.realforeclose.com"},
]


async def diagnose_county(county: dict, pw):
    name = county["name"]
    base = county["url"]
    print(f"\n🔍 Diagnosing {name}...")

    browser = await pw.chromium.launch(
        headless=False,  # Show browser so you can see what loads
        args=["--no-sandbox"]
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1400, "height": 900},
    )
    page = await context.new_page()

    results = {}

    # ── Page 1: Main auction preview page ────────────────────────────
    url1 = f"{base}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW"
    print(f"  → Loading: {url1}")
    await page.goto(url1, timeout=30000)
    await page.wait_for_timeout(4000)

    # Screenshot
    ss1 = OUTPUT / f"{name.lower().replace('-','_')}_preview.png"
    await page.screenshot(path=str(ss1), full_page=True)
    print(f"  📸 Screenshot saved: {ss1.name}")

    # Save HTML
    html1 = await page.content()
    html_file1 = OUTPUT / f"{name.lower().replace('-','_')}_preview.html"
    html_file1.write_text(html1)
    print(f"  💾 HTML saved: {html_file1.name} ({len(html1)} chars)")

    # Extract all links with AUCTIONDAYID
    links = await page.query_selector_all("a[href*='AUCTIONDAYID']")
    day_ids = []
    for link in links:
        href = await link.get_attribute("href")
        if href:
            import re
            m = re.search(r"AUCTIONDAYID=(\d+)", href)
            if m:
                day_ids.append(m.group(1))
    print(f"  Found AUCTIONDAYID links: {day_ids[:5]}")

    # Extract ALL links on the page
    all_links = await page.query_selector_all("a")
    link_hrefs = []
    for a in all_links[:50]:
        href = await a.get_attribute("href")
        text = await a.inner_text()
        if href:
            link_hrefs.append({"text": text.strip(), "href": href})

    results["page1_url"]   = url1
    results["day_ids"]     = day_ids
    results["links"]       = link_hrefs
    results["html_length"] = len(html1)

    # ── Page 2: Try status=sold or results page ───────────────────────
    url2 = f"{base}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&STATUS=SOLD"
    print(f"\n  → Loading: {url2}")
    await page.goto(url2, timeout=30000)
    await page.wait_for_timeout(3000)

    ss2 = OUTPUT / f"{name.lower().replace('-','_')}_sold.png"
    await page.screenshot(path=str(ss2), full_page=True)
    print(f"  📸 Screenshot saved: {ss2.name}")

    html2 = await page.content()
    html_file2 = OUTPUT / f"{name.lower().replace('-','_')}_sold.html"
    html_file2.write_text(html2)
    print(f"  💾 HTML saved: {html_file2.name} ({len(html2)} chars)")

    # ── Page 3: Try calendar/results directly ────────────────────────
    url3 = f"{base}/index.cfm?zaction=AUCTION&Zmethod=RESULTS"
    print(f"\n  → Loading: {url3}")
    try:
        await page.goto(url3, timeout=20000)
        await page.wait_for_timeout(3000)
        ss3 = OUTPUT / f"{name.lower().replace('-','_')}_results.png"
        await page.screenshot(path=str(ss3), full_page=True)
        html3 = await page.content()
        html_file3 = OUTPUT / f"{name.lower().replace('-','_')}_results.html"
        html_file3.write_text(html3)
        print(f"  📸 + 💾 Results page captured")
    except Exception as e:
        print(f"  ⚠ Results page failed: {e}")

    # ── Collect all table/row info from current page ──────────────────
    tables = await page.query_selector_all("table")
    print(f"\n  Tables on page: {len(tables)}")
    for i, tbl in enumerate(tables[:5]):
        rows = await tbl.query_selector_all("tr")
        sample_text = ""
        if rows:
            sample_text = (await rows[0].inner_text())[:100].strip()
        print(f"    Table {i}: {len(rows)} rows | first row: {sample_text}")

    # ── Print first 3000 chars of body text ───────────────────────────
    body_text = await page.inner_text("body")
    print(f"\n  Body text preview (first 1500 chars):")
    print("  " + body_text[:1500].replace("\n", "\n  "))

    results["page3_body_preview"] = body_text[:3000]

    # Save full results
    results_file = OUTPUT / f"{name.lower().replace('-','_')}_results.json"
    results_file.write_text(json.dumps(results, indent=2))
    print(f"\n  ✅ Diagnostics complete for {name}")

    await browser.close()
    return results


async def main():
    print("=" * 60)
    print("  SurplusIQ Diagnostic — Real Foreclosure Page Inspector")
    print("=" * 60)
    print(f"\nOutput folder: {OUTPUT}")
    print("Browser windows will open — don't close them until done\n")

    async with async_playwright() as pw:
        for county in COUNTIES:
            await diagnose_county(county, pw)
            await asyncio.sleep(2)

    print("\n" + "=" * 60)
    print("  DONE — Check these files:")
    print(f"  {OUTPUT}")
    for f in sorted(OUTPUT.glob("*.png")):
        print(f"    📸 {f.name}")
    for f in sorted(OUTPUT.glob("*.json")):
        print(f"    📋 {f.name}")
    print("\nPaste the terminal output above back to Claude.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
