# SurplusIQ — Ohio Workflow Knowledge Base

**Source:** Operational walkthroughs from Eric Richardson (Excess Elite LLC), recorded April 2026.
**Last updated:** May 2026.
**Purpose:** This document is the authoritative source for what makes an Ohio surplus lead valid, how to verify it, and what disqualifies it. The system should follow these rules exactly. Do not infer, do not hallucinate, do not skip steps.

---

## Universal Ohio Rules — Critical

Ohio is a **TWO-TIER STATE**. The opening bid does NOT equal the debt owed. The opening bid in Ohio is set at **two-thirds of the appraised value**, regardless of how much is actually owed on the property.

### What this means for surplus calculation:
- A "surplus" calculated as `final_sale_price − opening_bid` in Ohio is **inflated and unreliable**.
- The true surplus = `final_sale_price − actual_debt`.
- Actual debt must be sourced from clerk-of-court records, called the **Prayer Amount** or **Final Judgment** depending on the county.
- This second tier of verification is mandatory before any Ohio lead can be graded or shown to the user.

### Ohio kill signals — any of these auto-disqualify the lead:
1. "Motion to Vacate" anywhere in docket.
2. "Sale Vacated" / "Order Vacating Sale".
3. "Motion to Confirm Sale" + "Denied".
4. "Order to Pay Excess Proceeds" + "Granted" (already paid out).
5. "Excess funds sent to State" / "Funds escheated" — the homeowner missed the window.
6. "Bankruptcy" filing on the case.
7. Owner has already filed a claim ("Owner's Claim for Mortgage Surplus" or similar).
8. "Motion to Pay Over to Defendant" + "Granted" (already disbursed).

### Ohio sale schedules — important for scraper timing:
- **Cuyahoga**: Mondays = mortgage foreclosures, Wednesdays = tax sales.
- **Franklin**: Friday sales (less frequent than other counties).
- **Montgomery**: Friday sales only.
- **Summit**: Multiple days per week.
- **Hamilton**: Twice per month — low cadence.

Empty days are normal in Ohio. If the scraper hits a non-sale day for a county, that's not a bug.

---

## Cuyahoga County

### Auction Calendar
- URL: cuyahoga.sheriffsaleauction.ohio.gov
- Mortgage Mondays, tax Wednesdays.

### Prayer Amount — Easy Mode
Cuyahoga is the EASIEST Ohio county to verify because the clerk-of-court search returns a **Prayer Amount** field directly on the case page. No PDF scraping needed.

### Case Number Format
- Mortgage / civil: `CV23976605` — split as `CV` + `23` (year) + `976605` (case number).
- Tax: `CB20...` — civil-bond cases for tax sales.
- For clerk search, enter year + case number separately. Drop the `CV` prefix in the search box.

### Public Resources
- Cuyahoga publishes a **public spreadsheet of all surplus funds** the county is currently holding. URL: search "Cuyahoga County Sheriff Surplus Funds Spreadsheet".
- Includes owner info, case numbers, and exact dollar amounts.
- Use this as a cross-reference against scraped leads.

### Surplus Verification Steps (Cuyahoga)
1. Find third-party sale on auction calendar.
2. Capture case number.
3. Visit Clerk of Court search → Civil → Search by case → enter year + case number.
4. Read the **Prayer Amount** field directly.
5. Calculate true surplus: `final_sale_price − prayer_amount`.
6. Open docket, scan for kill signals.
7. Check parties — IRS, county treasurer, banks, county = creditors with claim rights.
8. PropertyRadar for second positions.
9. Cross-reference against Cuyahoga public surplus spreadsheet.

### Cuyahoga-Specific Note
Cuyahoga does NOT issue a "Notice of Excess Proceeds" document until much later in the lifecycle. Instead, the docket will show "Clerk to Hold Sale Funds" — that's the early indicator that surplus is being held.

---

## Franklin County

### Auction Calendar
- URL: franklin.sheriffsaleauction.ohio.gov
- Friday sales only — less frequent.

### Prayer Amount — Hard Mode
Franklin does NOT have a Prayer Amount field. Real debt must be extracted from docket events.

### Procedure to Find Real Debt
1. Open docket events list.
2. `Cmd+F` (or text-search) for the keyword **"Judgment"**.
3. Look for "Motion for Default Judgment" event.
4. Open the linked PDF.
5. Scan PDF text for the principal balance / judgment amount.
6. That dollar figure = the real debt for surplus calculation.

### Case Number Format
- `25CV4230` style for civil cases.
- Search by year + case number.

### Public Resources
- Franklin publishes a **Notice of Excess Proceeds list** showing currently-held surplus funds.
- Currently $7.3M+ in held excess proceeds (as of Eric's walkthrough).

### Surplus Verification Steps (Franklin)
1. Find third-party sale.
2. Open clerk case page → docket events.
3. `Cmd+F` "Judgment" → find Motion for Default Judgment → open PDF → extract debt.
4. Calculate `true_surplus = final_sale_price − debt_from_pdf`.
5. Scan docket for kill signals.
6. Parties review.
7. PropertyRadar.

### Franklin Kill-Signal Examples Eric Walked Through
- "Motion to Withdraw" + "Granted" → sale never finalized, no surplus.
- "Order Withdrawing Motion to Pay Excess Proceeds" + "Cancelling Hearing" → already disbursed.
- "Order to Pay the Excess Proceeds" + recipient name → already paid.

---

## Montgomery County

### Auction Calendar
- URL: montgomery.sheriffsaleauction.ohio.gov
- Friday sales only.

### Operational Quirk — T&C Agreement
Montgomery's site requires accepting a Terms & Conditions agreement before showing the auction calendar. The scraper handles this via the `handle_terms_agreement` function — verify it remains working when changes happen.

### Prayer Amount — Same as Franklin (Hard Mode)
Montgomery does NOT show a Prayer Amount directly. Same procedure as Franklin:
1. Docket events → `Cmd+F` "Judgment".
2. Open Motion for Default Judgment PDF.
3. Extract principal balance.

### Case Number Format
- Format example: `2023 CV 02035 (0)` — note the parenthesized suffix.
- Whole case number can be pasted into clerk search.

### Public Resources
- Montgomery publishes an **Excess Funds List** updated monthly.
- $5.8M+ held funds as of March (per Eric's walkthrough — likely higher now).

### Surplus Verification Steps (Montgomery)
1. Find third-party sale on Friday auction.
2. Capture case number including parenthesized suffix.
3. Clerk search (after T&C accept) → paste case number.
4. Open docket → scan for "Motion to Vacate" first (Eric showed an example where Montgomery cases get vacated — kill the lead immediately if seen).
5. `Cmd+F` "Judgment" → Motion for Default Judgment → PDF → extract debt.
6. Calculate true surplus.
7. Parties review.
8. PropertyRadar.

### Montgomery-Specific Watchout
A high percentage of Montgomery third-party sales get **vacated within days**. The Day-3 re-scan is critical to catch these and remove them from the lead pool.

---

## Summit County

### Auction Calendar
- URL: summit.sheriffsaleauction.ohio.gov
- Multiple sale days per week.

### Case Number Format
- Format example: `CV-2025-03-1239`. Year and number split: `2025` + `03-1239`.
- The dash structure inside the case number must be preserved when entering it for search.

### Prayer Amount — Sometimes Available, Sometimes Missing
Summit is the trickiest county for debt extraction:
1. Try the docket judgment-search procedure (same as Franklin / Montgomery).
2. **The Motion for Default Judgment PDF often does not include a dollar amount.**
3. When the debt amount is missing from the PDF, fall back to PropertyRadar:
   - Pull the property's transaction history.
   - Find the original loan amount (Notice of Sale should reference it).
   - Estimate principal — note this is an APPROXIMATION, flag the lead accordingly.

### Public Resources
- Summit County Excess Funds List exists but only covers OWN claims (not all surplus).
- Many Summit surplus funds are sent to the State after the unclaimed window passes.

### Surplus Verification Steps (Summit)
1. Find third-party sale.
2. Try Prayer Amount via docket → judgment search.
3. If PDF lacks dollar amount, pivot to PropertyRadar loan estimate.
4. Mark the lead as "debt-estimated" vs "debt-confirmed" so users know precision level.
5. Kill signal scan.
6. Parties review.

### Summit-Specific Watchout
**"Excess funds sent to fiscal office"** = the county is holding surplus.
**"Excess funds sent to State"** = unclaimed past window, money is now with Ohio Treasurer. Different recovery process required.

---

## Hamilton County

### Auction Calendar
- URL: hamilton.sheriffsaleauction.ohio.gov
- Twice per month — lowest cadence of all our counties.

### CAPTCHA Required
Hamilton's clerk site requires CAPTCHA on case searches. Browser-based scraping must handle this.

### Critical Limitation — Skip the Docket Scrape
**Hamilton's clerk dockets do NOT label documents.** Each entry is just an icon — no description text. To find the judgment amount, every single document must be opened individually. This is impractical at scale.

### Recommended Approach for Hamilton
**DO NOT scrape docket documents for Hamilton.** Instead:
1. Find third-party sale.
2. Capture the case number and address.
3. Skip the clerk docket entirely.
4. Use **PropertyRadar exclusively** for verification:
   - Pull transaction history.
   - Find the original loan / second positions.
   - Compare PropertyRadar's loan info to the final sale price.
5. Grade the lead based on PropertyRadar data alone.

### Public Resources
- Hamilton publishes an Excess Funds List with case numbers and amounts.
- Use this for cross-reference; don't rely on docket parsing.

### Case Number Format
- Format varies; whole case number can typically be pasted into clerk search after CAPTCHA.

### Surplus Verification Steps (Hamilton)
1. Find third-party sale.
2. Capture case number and address.
3. PropertyRadar: pull loan history.
4. If PropertyRadar shows clean property + final sale > likely debt + no second positions → grade as A or B.
5. If second positions or HUD positions exist → grade lower.
6. Cross-reference Hamilton Excess Funds List for case-number match.

### Hamilton-Specific Note
Lower volume but Eric flagged it as a **good county** — third-party sales here are typically real surplus opportunities. The bottleneck is verification time, which the PropertyRadar-only approach solves.

---

## Cross-County Ohio Rules

### Re-scan Schedule
Ohio leads must be re-scanned on **Day 3, Day 7, Day 14, and Day 30** after the sale to detect:
- Late-filed Motion to Vacate (especially Montgomery — high vacate rate).
- Excess funds escheated to State (kills the lead for our normal workflow).
- Owner or competing firm filing a surplus claim.
- Notice of Excess Proceeds finally being published (often weeks late in Cuyahoga).

### Grading Framework — Ohio (true surplus required)
- **A+** : True surplus ≥ $75K (Ohio threshold lower than FL because verification is harder), debt confirmed via clerk, no second positions, no kill signals.
- **A**  : True surplus ≥ $40K, debt confirmed, minor liens.
- **B**  : True surplus ≥ $20K OR debt-estimated lead with strong PropertyRadar signal.
- **C**  : True surplus ≥ $10K with significant complications (Hamilton-style PropertyRadar-only, multiple defendants, etc.).

### Required Output Fields per Ohio Lead
- County, case number, sale date, parcel ID, address.
- Final sale price.
- Opening bid (LABELED AS "2/3 appraised — not real debt").
- True debt (from prayer amount or PDF or PropertyRadar).
- Debt source: `prayer_field` / `pdf_extract` / `propertyradar_estimate`.
- True surplus.
- Kill signals detected (yes/no, list).
- PropertyRadar second-position summary.
- Re-scan flags: 3, 7, 14, 30 day status.
- Whether the lead appears on the county's published Excess Funds List.
