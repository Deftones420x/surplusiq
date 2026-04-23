"""
SurplusIQ — Clerk Docket Scraper
Checks county clerk portals for claim status and certificate of disbursement
Handles FL (OSCAR, CORE, Broward Web2, myEClerk) and OH (CP Docket, FCJS) systems
"""

import asyncio
import re
import json
from datetime import date, datetime
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

# ── Clerk Systems ─────────────────────────────────────────────────────
CLERK_SYSTEMS = {
    # Florida
    "oscar": {
        "name":       "Miami-Dade OSCAR",
        "search_url": "https://www2.miami-dadeclerk.com/ocs/Search.aspx",
        "method":     "oscar_search",
    },
    "broward_portal": {
        "name":       "Broward Clerk Web2",
        "search_url": "https://www.browardclerk.org/Web2/CaseSearchECA/Search",
        "method":     "broward_search",
    },
    "core_duval": {
        "name":       "Duval CORE",
        "search_url": "https://core.duvalclerk.com/CoreCivil/CaseSearch",
        "method":     "core_search",
    },
    "lee_portal": {
        "name":       "Lee County eFiling",
        "search_url": "https://efiling.leeclerk.org/CourtRecords/Search",
        "method":     "lee_search",
    },
    "orange_eclerk": {
        "name":       "Orange myEClerk",
        "search_url": "https://myeclerk.myorangeclerk.com/Cases/Search",
        "method":     "orange_search",
    },
    # Ohio
    "cuyahoga_docket": {
        "name":       "Cuyahoga CP Docket",
        "search_url": "https://cpdocket.cp.cuyahogacounty.us/Search.aspx",
        "method":     "cuyahoga_search",
    },
    "franklin_fcjs": {
        "name":       "Franklin FCJS",
        "search_url": "https://fcdcfcjs.co.franklin.oh.us/CaseInformationOnline/caseSearch",
        "method":     "franklin_search",
    },
    "montgomery_clerk": {
        "name":       "Montgomery Clerk",
        "search_url": "https://www.mcohio.org/government/elected_officials/clerk_of_courts/civil_division/case_search.php",
        "method":     "montgomery_search",
    },
    "summit_clerk": {
        "name":       "Summit County Clerk",
        "search_url": "https://www.summitcountyclerk.com/civil-case-search",
        "method":     "summit_search",
    },
    "hamilton_clerk": {
        "name":       "Hamilton courtclerk.org",
        "search_url": "https://courtclerk.org/records-search",
        "method":     "hamilton_search",
    },
}

COUNTY_CLERK_MAP = {
    "miami-dade-fl":  "oscar",
    "broward-fl":     "broward_portal",
    "duval-fl":       "core_duval",
    "lee-fl":         "lee_portal",
    "orange-fl":      "orange_eclerk",
    "cuyahoga-oh":    "cuyahoga_docket",
    "franklin-oh":    "franklin_fcjs",
    "montgomery-oh":  "montgomery_clerk",
    "summit-oh":      "summit_clerk",
    "hamilton-oh":    "hamilton_clerk",
}

# Keywords for claim analysis
CLAIM_KEYWORDS     = ["motion to disburse", "claim to surplus", "petition", "competing claim", "claim surplus"]
DISBURSED_KEYWORDS = ["order disbursing", "funds disbursed", "check issued", "surplus paid"]
SURPLUS_KEYWORDS   = ["surplus", "certificate of disbursement", "excess proceeds", "excess funds"]
CERT_KEYWORDS      = ["certificate of disbursement", "cert of disbursement", "certificate of title surplus"]


async def handle_captcha_pause(page, system_name: str):
    """Pause for manual CAPTCHA solve."""
    try:
        content = await page.content()
        if any(kw in content.lower() for kw in ["captcha", "challenge", "verify you are"]):
            print(f"\n⚠️  CAPTCHA on {system_name}! Solve in browser then press ENTER...")
            input()
    except Exception:
        pass


async def generic_case_search(page, search_url: str, case_number: str, system_name: str) -> str:
    """
    Generic case search approach — works on most Florida clerk portals.
    Tries to find a text input, types the case number, submits, and returns page text.
    """
    try:
        await page.goto(search_url, timeout=25000)
        await page.wait_for_timeout(2000)
        await handle_captcha_pause(page, system_name)

        # Try common input selectors
        input_selectors = [
            "input[name*='case']",
            "input[name*='Case']",
            "input[id*='case']",
            "input[id*='Case']",
            "input[placeholder*='case']",
            "input[placeholder*='Case']",
            "input[type='text']:first-of-type",
            "#CaseNumber",
            "#caseNumber",
            "#txtCaseNumber",
            "input[name='casenum']",
        ]

        input_found = False
        for sel in input_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    await el.fill(case_number)
                    input_found = True
                    break
            except Exception:
                continue

        if not input_found:
            return ""

        # Try to submit
        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Search')",
            "button:has-text('Find')",
            "#btnSearch",
            "#SearchButton",
        ]
        for sel in submit_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    break
            except Exception:
                continue
        else:
            # Fallback: press Enter
            await page.keyboard.press("Enter")

        await page.wait_for_timeout(3000)
        await handle_captcha_pause(page, system_name)

        # Try to click into first result
        result_selectors = [
            "a[href*='case']", "a[href*='Case']",
            "td a", ".result a", ".searchResult a",
        ]
        for sel in result_selectors:
            try:
                link = await page.query_selector(sel)
                if link:
                    await link.click()
                    await page.wait_for_timeout(2500)
                    break
            except Exception:
                continue

        return await page.inner_text("body")

    except PWTimeout:
        print(f"    Timeout on {system_name} for case {case_number}")
        return ""
    except Exception as e:
        print(f"    Error on {system_name}: {e}")
        return ""


async def check_certificate_of_disbursement(page, base_url: str, case_number: str) -> dict:
    """
    Try to find a Certificate of Disbursement for a case.
    This is the official confirmation of surplus funds.
    """
    result = {
        "cert_found":      False,
        "cert_url":        "",
        "surplus_amount":  0.0,
        "cert_text":       "",
    }

    try:
        # Try direct search for cert
        search_url = f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=SEARCH&SearchType=CN&SearchValue={case_number}&Status=CERT"
        await page.goto(search_url, timeout=15000)
        await page.wait_for_timeout(1500)
        content = await page.inner_text("body")

        if any(kw in content.lower() for kw in CERT_KEYWORDS):
            result["cert_found"] = True
            result["cert_text"]  = content[:2000]

            # Try to extract surplus amount from cert text
            amount_match = re.search(
                r"surplus[^\$]*\$?([\d,]+\.?\d*)",
                content, re.IGNORECASE
            )
            if amount_match:
                amt_str = amount_match.group(1).replace(",", "")
                try:
                    result["surplus_amount"] = float(amt_str)
                except ValueError:
                    pass

    except Exception:
        pass

    return result


def analyze_docket_text(text: str) -> dict:
    """
    Parse docket/case text to extract claim status and key filings.
    Returns structured analysis.
    """
    if not text:
        return {"claim_status": "none", "filings": [], "notes": ""}

    text_lower = text.lower()
    filings    = []
    notes      = []

    # Check surplus existence
    has_surplus = any(kw in text_lower for kw in SURPLUS_KEYWORDS)

    # Check for certificate of disbursement
    has_cert = any(kw in text_lower for kw in CERT_KEYWORDS)
    if has_cert:
        filings.append("Certificate of Disbursement found")

    # Check for existing claims
    claim_filed   = any(kw in text_lower for kw in CLAIM_KEYWORDS)
    already_paid  = any(kw in text_lower for kw in DISBURSED_KEYWORDS)

    # Extract any dollar amounts mentioned near "surplus"
    surplus_amounts = []
    for match in re.finditer(r"surplus[^\$\n]{0,20}\$?([\d,]+)", text_lower):
        try:
            amt = float(match.group(1).replace(",", ""))
            if amt > 100:  # Filter noise
                surplus_amounts.append(amt)
        except ValueError:
            pass

    # Detect partial claims (Eric's example: condo assoc filing for subset)
    partial_indicators = [
        "seeking additional advances", "condominium association",
        "hoa", "partial disbursement", "only as to",
        "limited to", "not to exceed",
    ]
    partial_claim = any(kw in text_lower for kw in partial_indicators) and claim_filed

    # Determine final status
    if already_paid:
        status = "disbursed"
        notes.append("Funds appear to have been disbursed")
    elif partial_claim:
        status = "partial"
        notes.append("Partial claim filed — surplus may remain")
        if surplus_amounts:
            notes.append(f"Surplus amounts found: ${max(surplus_amounts):,.0f}")
    elif claim_filed:
        status = "filed"
        notes.append("Claim has been filed")
    elif has_cert:
        status = "none"
        notes.append("Certificate of disbursement found — no claim yet")
    else:
        status = "none"

    # Extract motion/filing dates
    date_pattern = r"(\d{1,2}/\d{1,2}/\d{2,4})"
    dates_found  = re.findall(date_pattern, text)
    if dates_found:
        filings.append(f"Dates in docket: {', '.join(dates_found[:3])}")

    return {
        "claim_status":     status,
        "has_surplus_flag": has_surplus,
        "has_cert":         has_cert,
        "filings":          filings,
        "notes":            " | ".join(notes),
        "surplus_amounts":  surplus_amounts,
        "partial_claim":    partial_claim,
    }


async def check_case(lead: dict, playwright_instance, headless: bool = True) -> dict:
    """
    Full clerk check for one lead.
    Gets docket text, analyzes for claims and cert of disbursement.
    """
    updated = lead.copy()
    county_id  = lead.get("county_id", "")
    case_num   = lead.get("case_number", "")
    county_name = lead.get("county_name", "")

    if not case_num:
        updated["clerk_error"] = "no_case_number"
        return updated

    clerk_system_id = COUNTY_CLERK_MAP.get(county_id)
    if not clerk_system_id:
        updated["clerk_error"] = "no_clerk_system"
        return updated

    clerk_config = CLERK_SYSTEMS.get(clerk_system_id, {})
    search_url   = clerk_config.get("search_url", "")
    system_name  = clerk_config.get("name", county_name)

    # CAPTCHA counties run headed
    has_captcha = county_id in ["lee-fl", "cuyahoga-oh", "hamilton-oh"]
    run_headless = headless and not has_captcha

    browser = await playwright_instance.chromium.launch(
        headless=run_headless,
        args=["--no-sandbox"],
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
    )
    page = await context.new_page()

    try:
        print(f"  🔍 {county_name} | {case_num} | {system_name}")

        # Get docket text
        docket_text = await generic_case_search(page, search_url, case_num, system_name)
        updated["docket_text"]    = docket_text[:5000] if docket_text else ""
        updated["docket_checked"] = True
        updated["docket_checked_at"] = datetime.now().isoformat()

        # Analyze the text
        analysis = analyze_docket_text(docket_text)
        updated["claim_status"]     = analysis["claim_status"]
        updated["has_cert"]         = analysis["has_cert"]
        updated["clerk_filings"]    = analysis["filings"]
        updated["clerk_notes"]      = analysis["notes"]
        updated["partial_claim"]    = analysis["partial_claim"]

        # Update surplus amounts if found in docket
        if analysis["surplus_amounts"]:
            updated["docket_surplus_amount"] = max(analysis["surplus_amounts"])

        # Check for certificate of disbursement on auction site
        auction_url = lead.get("auction_url", "")
        if auction_url and not updated.get("cert_found"):
            cert = await check_certificate_of_disbursement(page, auction_url, case_num)
            updated.update(cert)
            if cert["cert_found"]:
                updated["doc_status"]    = "retrieved"
                updated["doc_available"] = True

        if not updated.get("doc_status"):
            updated["doc_status"] = "pending"

    except Exception as e:
        updated["clerk_error"] = str(e)
        print(f"    ❌ Clerk check failed: {e}")
    finally:
        await browser.close()

    return updated


async def run_clerk_checks(leads: list, headless: bool = True) -> list:
    """Run clerk docket checks for all leads."""
    print(f"\n⚖️  Running clerk checks for {len(leads)} leads...")
    checked = []

    async with async_playwright() as pw:
        for i, lead in enumerate(leads):
            print(f"  [{i+1}/{len(leads)}]", end=" ")
            try:
                updated = await check_case(lead, pw, headless=headless)
                checked.append(updated)
            except Exception as e:
                lead["clerk_error"] = str(e)
                checked.append(lead)

            await asyncio.sleep(1.5)  # Rate limiting

    verified    = sum(1 for l in checked if l.get("claim_status") == "none")
    partial     = sum(1 for l in checked if l.get("claim_status") == "partial")
    filed       = sum(1 for l in checked if l.get("claim_status") == "filed")
    disbursed   = sum(1 for l in checked if l.get("claim_status") == "disbursed")

    print(f"\n  ✅ Clerk checks complete:")
    print(f"     No claim:  {verified}")
    print(f"     Partial:   {partial}")
    print(f"     Filed:     {filed}")
    print(f"     Disbursed: {disbursed}")

    return checked


def save_verified(leads: list, date_str: str = None):
    """Save verified leads to JSONL."""
    if not date_str:
        date_str = date.today().isoformat()
    filepath = DATA_DIR / f"verified_{date_str}.jsonl"
    with open(filepath, "w") as f:
        for lead in leads:
            f.write(json.dumps(lead) + "\n")
    print(f"💾 Verified leads saved: {filepath}")
    return filepath


if __name__ == "__main__":
    # Test single case check
    test_lead = {
        "county_id":   "duval-fl",
        "county_name": "Duval",
        "state":       "FL",
        "case_number": "2024-CA-001234",
        "address":     "123 Test St, Jacksonville, FL",
    }
    print("Testing clerk check for Duval County...")
    asyncio.run(run_clerk_checks([test_lead], headless=True))
