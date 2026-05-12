"""
SurplusIQ — Miami-Dade County Docket Scraper

Miami-Dade is the easiest Florida county because the clerk OCS portal
exposes a structured Local Case Search and a "Print Case Info" view
that contains all docket events in a single rendered page.

Navigation flow (from reconnaissance May 11, 2026):

  1. https://www2.miamidadeclerk.gov/ocs/
     → Landing page is a SPA

  2. Navigate to Local Case Search
     (state-level search triggers reCAPTCHA, so we MUST use local search)

  3. Form fields:
     - Year input/dropdown:    enter YYYY (e.g. "2017")
     - Case Number text input: enter 6-digit sequence (e.g. "021344")
     - Case Type dropdown:     select "CA" (Circuit Civil)
     → Portal auto-appends "-01" sequence suffix
     → Click search

  4. /ocs/searchResults?qs=<token>
     → Page shows: Case Title, Filing Date, Case Status, Case Type,
       Judicial Section, plus nav links to Dockets | Parties | Hearings

  5. Visit the Dockets sub-page for kill-signal scanning + event list

Case number format from auction scraper:
  Raw:     2017-021344-CA-01
  Parsed:  year=2017, number=021344, type=CA
  Note: the "-01" suffix is the sequence and is auto-appended by the portal

FL "real debt" field:
  Unlike Cuyahoga's structured Prayer Amount, Miami-Dade's Final Judgment
  Amount lives inside the "Final Judgment of Foreclosure" docket entry.
  Strategy: scan event descriptions for $ amounts adjacent to "Final Judgment".
  Fallback: leave prayer_amount=0 and let downstream PropertyRadar
  enrichment supply the debt figure.

Kill signals specific to FL:
  - Motion to Vacate Final Judgment
  - Suggestion of Bankruptcy / Notice of Bankruptcy
  - Voluntary Dismissal
  - Order of Dismissal
  - Lis Pendens Discharged
  - Order Granting Motion to Vacate Sale

NOTE on dismissal-then-reinstatement:
  A case can be dismissed and later reinstated (test case 2017-021344-CA-01
  was dismissed in 2022, reinstated 2025, sold 2026). Kill signals are only
  definitive if they appear AFTER the most recent Certificate of Sale or
  Final Judgment. This module records all kill signals but the classifier
  in base.py decides terminality.
"""

from __future__ import annotations
import re
import asyncio
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout

from .base import DocketScraper, DocketResult, DocketEvent


BASE_URL = "https://www2.miamidadeclerk.gov/ocs"
LANDING_URL = f"{BASE_URL}/"
LOCAL_SEARCH_URL = f"{BASE_URL}/LocalCaseSearch.aspx"  # adjust after first scrape if SPA routes differ


def parse_miami_dade_case_number(raw: str) -> Optional[dict]:
    """
    Parse a Miami-Dade case number into search components.

    Accepts variations:
      '2017-021344-CA-01'   -> {year: 2017, number: 021344, type: CA, seq: 01}
      '2017021344CA01'      -> same
      '2024-004620-CA-01'   -> {year: 2024, number: 004620, type: CA, seq: 01}

    Returns None if not parseable.
    """
    if not raw:
        return None

    # Strip auction suffix like " (12345)" if present
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", raw.strip())
    # Strip dashes and spaces, uppercase
    cleaned = re.sub(r"[-\s]", "", cleaned).upper()

    # Miami-Dade format: YYYY + 6-digit-number + 2-letter-type + 2-digit-seq
    # e.g. 2017021344CA01
    m = re.match(r"^(\d{4})(\d{6})([A-Z]{2})(\d{2})$", cleaned)
    if not m:
        return None

    year = int(m.group(1))
    number = m.group(2)
    case_type = m.group(3)
    seq = m.group(4)

    return {
        "year":      year,
        "number":    number,    # 6-digit string, preserve leading zeros
        "case_type": case_type, # "CA" for Circuit Civil
        "sequence":  seq,       # "01" - auto-appended by portal but kept for reconstruction
    }


class MiamiDadeDocketScraper(DocketScraper):

    county_id = "miami-dade-fl"
    county_name = "Miami-Dade"

    async def scrape_case(self, case_number: str) -> DocketResult:
        """Run the full scrape against one case. Returns a DocketResult."""
        result = DocketResult(
            county_id=self.county_id,
            case_number=case_number,
            scraped_at=datetime.now().isoformat(),
        )

        parsed = parse_miami_dade_case_number(case_number)
        if not parsed:
            result.classification = "unknown"
            result.classification_reason = f"case number not parseable: {case_number}"
            return result

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1400, "height": 900},
                ignore_https_errors=True,
            )
            page = await context.new_page()

            try:
                # ─── Step 1: Land on the portal and navigate to Local Case Search ───
                # Retry navigation up to 3 times — the SPA sometimes hits a
                # transient chrome-error on first connection before the
                # NetScaler session cookie is established.
                nav_success = False
                last_nav_err = None
                for attempt in range(3):
                    try:
                        await page.goto(
                            LANDING_URL,
                            wait_until="load",
                            timeout=45000,
                        )
                        await page.wait_for_timeout(2500)  # SPA hydration
                        # Verify we actually loaded the portal (not chrome-error)
                        if "miamidadeclerk" in page.url:
                            nav_success = True
                            break
                    except Exception as e:
                        last_nav_err = e
                        await page.wait_for_timeout(2000)
                        continue

                if not nav_success:
                    result.classification = "unknown"
                    result.classification_reason = (
                        f"could not load portal after 3 attempts: "
                        f"{str(last_nav_err)[:120] if last_nav_err else 'unknown'}"
                    )
                    await self._screenshot(page, "ERROR-nav-fail")
                    await browser.close()
                    return result

                await self._screenshot(page, "01-landing")

                # Click through "Local Case Search" link from landing page
                # (the SPA does not honor direct deep links)
                try:
                    await page.click("text=/local case search/i", timeout=10000)
                    await page.wait_for_load_state("load", timeout=15000)
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    result.classification = "unknown"
                    result.classification_reason = f"could not click Local Case Search: {str(e)[:120]}"
                    await self._screenshot(page, "ERROR-no-search-nav")
                    await browser.close()
                    return result

                await self._screenshot(page, "02-search-form")

                # ─── Step 2: Fill the search form ───
                # Year, Case Number, Case Type
                try:
                    # Year - try input first, then select
                    year_filled = await self._fill_or_select(
                        page,
                        selectors=["input[name*='year' i]", "input[id*='year' i]",
                                   "select[name*='year' i]", "select[id*='year' i]"],
                        value=str(parsed["year"]),
                    )

                    num_filled = await self._fill_or_select(
                        page,
                        selectors=["input[name*='caseNum' i]", "input[id*='caseNum' i]",
                                   "input[name*='number' i]", "input[id*='number' i]"],
                        value=parsed["number"],
                    )

                    type_filled = await self._fill_or_select(
                        page,
                        selectors=["select[name*='caseType' i]", "select[id*='caseType' i]",
                                   "select[name*='type' i]", "select[id*='type' i]"],
                        value=parsed["case_type"],
                    )

                    if not (year_filled and num_filled and type_filled):
                        result.classification = "unknown"
                        result.classification_reason = (
                            f"could not fill form: year={year_filled} "
                            f"num={num_filled} type={type_filled}"
                        )
                        await self._screenshot(page, "ERROR-form-fill")
                        await browser.close()
                        return result

                    await self._screenshot(page, "03-form-filled")

                    # Submit
                    submitted = False
                    for sel in ["button:has-text('Search')", "input[type='submit']",
                                "button[type='submit']", "button:has-text('Submit')"]:
                        try:
                            await page.click(sel, timeout=3000)
                            submitted = True
                            break
                        except Exception:
                            continue

                    if not submitted:
                        result.classification = "unknown"
                        result.classification_reason = "could not click submit button"
                        await self._screenshot(page, "ERROR-no-submit")
                        await browser.close()
                        return result

                    await page.wait_for_load_state("networkidle", timeout=20000)
                    await page.wait_for_timeout(1500)
                    await self._screenshot(page, "04-search-results")

                except Exception as e:
                    result.classification = "unknown"
                    result.classification_reason = f"search form error: {str(e)[:120]}"
                    await self._screenshot(page, "ERROR-search-form")
                    await browser.close()
                    return result

                # ─── Step 3: Click into the case from results ───
                # Results page should show one row matching our case
                try:
                    # Try clicking the case number link
                    case_link_text = f"{parsed['year']}-{parsed['number']}-{parsed['case_type']}-{parsed['sequence']}"
                    try:
                        await page.click(f"text={case_link_text}", timeout=5000)
                    except Exception:
                        # Fall back: click first result row
                        await page.click("table tbody tr a, table tbody tr:first-child", timeout=5000)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    await page.wait_for_timeout(1500)
                except Exception as e:
                    result.classification = "unknown"
                    result.classification_reason = f"could not open case: {str(e)[:120]}"
                    await self._screenshot(page, "ERROR-case-link")
                    await browser.close()
                    return result

                result.case_url = page.url
                await self._screenshot(page, "05-case-summary")

                # ─── Step 4: Parse case summary page ───
                await self._scrape_summary_page(page, result)

                # ─── Step 5: Navigate to Dockets sub-page ───
                try:
                    await page.click("a:has-text('Dockets'), a:has-text('Docket')", timeout=5000)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    await page.wait_for_timeout(1500)
                    await self._screenshot(page, "06-dockets")
                    await self._scrape_dockets_page(page, result)
                except Exception:
                    # If we can't reach dockets, we still have summary data
                    pass

                # ─── Step 6: Parties sub-page ───
                try:
                    await page.click("a:has-text('Parties')", timeout=5000)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    await page.wait_for_timeout(1000)
                    await self._screenshot(page, "07-parties")
                    await self._scrape_parties_page(page, result)
                except Exception:
                    pass

            finally:
                await browser.close()

        # ─── Step 7: Run classification ───
        # Use opening bid as proxy sale price for FL — actual sale price comes
        # from auction scraper and is merged later in the loader.
        classification, reason = self.classify(result, final_sale_price=0.0)
        result.classification = classification
        result.classification_reason = reason

        return result

    # ─── Helpers ──────────────────────────────────────────────────────────

    async def _fill_or_select(self, page: Page, selectors: list, value: str) -> bool:
        """Try multiple selectors to fill an input or select a dropdown option."""
        for sel in selectors:
            try:
                element = page.locator(sel).first
                if await element.count() == 0:
                    continue
                tag = await element.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    await element.select_option(value=value, timeout=3000)
                else:
                    await element.fill(value, timeout=3000)
                return True
            except Exception:
                continue
        return False

    async def _scrape_summary_page(self, page: Page, result: DocketResult) -> None:
        """Parse case title, filing date, status from the case summary page."""
        text = await page.inner_text("body")

        # Case title (e.g. "WILMINGTON TRUST COMPANY vs MANUEL ANGEL DURAN et al")
        title_m = re.search(r"([A-Z][^\n]{5,150}vs\.?\s+[A-Z][^\n]{3,150})", text)
        if title_m:
            result.case_title = title_m.group(1).strip()

        # Filing date
        fd_m = re.search(r"Filing Date\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
        if fd_m:
            try:
                dt = datetime.strptime(fd_m.group(1), "%m/%d/%Y")
                result.filing_date = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Case status
        status_m = re.search(r"Case Status\s*:?\s*([A-Z][A-Z ]+)", text, re.IGNORECASE)
        if status_m:
            result.last_status = status_m.group(1).strip()

        # Case type / designation (e.g. "RPMF -Homestead")
        type_m = re.search(r"Case Type\s*:?\s*([A-Z][A-Za-z0-9 \-]+)", text)
        if type_m:
            result.case_designation = type_m.group(1).strip()

    async def _scrape_dockets_page(self, page: Page, result: DocketResult) -> None:
        """Extract docket events, kill signals, and Final Judgment Amount."""
        text = await page.inner_text("body")
        text_lower = text.lower()

        # Kill signal detection (uses base.py KILL_SIGNAL_PATTERNS)
        result.kill_signals = self.detect_kill_signals(text)

        # Proof of surplus detection
        result.proof_of_surplus = self.detect_proof_of_surplus(text)

        # Competing filer detection
        result.competing_filers = self.detect_competing_filers(text)

        # Extract docket events
        # Miami-Dade format typically: MM/DD/YYYY  DIN  Description
        events = []
        event_pattern = re.compile(
            r"(\d{1,2})/(\d{1,2})/(\d{4})\s+\d+\s+([A-Z][^\n]{5,300})",
            re.MULTILINE
        )
        for m in event_pattern.finditer(text):
            mm, dd, yyyy = m.group(1), m.group(2), m.group(3)
            desc = m.group(4).strip()[:200]
            events.append(DocketEvent(
                filing_date=f"{yyyy}-{int(mm):02d}-{int(dd):02d}",
                description=desc,
            ))
        result.events = [e.__dict__ for e in events[:50]]

        # Most-recent activity
        if events:
            sorted_events = sorted(events, key=lambda e: e.filing_date, reverse=True)
            result.last_activity_date = sorted_events[0].filing_date

        # Extract Final Judgment Amount — look for $ amounts near "Final Judgment"
        # FL strategy: find "Final Judgment" + dollar amount within 200 chars
        fj_matches = re.finditer(
            r"final judgment[^\$]{0,200}\$\s*([\d,]+(?:\.\d{2})?)",
            text_lower,
        )
        amounts = []
        for fm in fj_matches:
            try:
                amt = float(fm.group(1).replace(",", ""))
                if amt > 1000:  # filter tiny fees
                    amounts.append(amt)
            except ValueError:
                continue
        if amounts:
            # Take the largest — likely the principal judgment, not interest line items
            result.prayer_amount = max(amounts)
            result.debt_source = "docket_extract"

    async def _scrape_parties_page(self, page: Page, result: DocketResult) -> None:
        """Extract plaintiff/defendants from the Parties sub-page."""
        text = await page.inner_text("body")

        # Plaintiff
        p_m = re.search(r"Plaintiff\s*:?\s*\n?\s*([^\n]+)", text, re.IGNORECASE)
        if p_m:
            result.plaintiff = p_m.group(1).strip()[:200]

        # Defendants
        defendants = []
        for m in re.finditer(r"Defendant\s*:?\s*\n?\s*([^\n]+)", text, re.IGNORECASE):
            name = m.group(1).strip()[:200]
            if name and name not in defendants:
                defendants.append(name)
        result.defendants = defendants

        # Creditor heuristic — same as Cuyahoga
        creditor_keywords = [
            "LLC", "BANK", "TRUSTEE", "IRS", "STATE OF", "COUNTY", "CITY OF",
            "REVENUE", "DEPARTMENT", "ASSOCIATION", "TRUST", "FINANCIAL",
            "MORTGAGE", "CAPITAL", "FUND", "SERVICES", "INC"
        ]
        for name in defendants:
            name_upper = name.upper()
            if any(kw in name_upper for kw in creditor_keywords):
                result.additional_parties.append(name)

    async def _screenshot(self, page: Page, label: str) -> None:
        """Save diagnostic screenshot for debugging."""
        import os
        try:
            diag_dir = "data/diagnostics/miami-dade-fl"
            os.makedirs(diag_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = f"{diag_dir}/{timestamp}-{label}.png"
            await page.screenshot(path=path, full_page=True)
        except Exception:
            pass
