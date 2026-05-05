# SurplusIQ — Florida Workflow Knowledge Base

**Source:** Operational walkthroughs from Eric Richardson (Excess Elite LLC), recorded April 2026.
**Last updated:** May 2026.
**Purpose:** This document is the authoritative source for what makes a Florida surplus lead valid, how to verify it, and what disqualifies it. The system should follow these rules exactly. Do not infer, do not hallucinate, do not skip steps.

---

## Universal Florida Rules

Florida is a **single-tier state**. The opening bid in a foreclosure sale equals the actual debt owed (Final Judgment Amount). This means apparent surplus closely matches real surplus before junior liens are accounted for.

### A Florida surplus exists when:
- Property sold to a **3rd-party bidder** (not plaintiff/bank/lender).
- Final sale price > opening bid (mortgage foreclosure) OR > taxes & costs (tax deed).
- Difference is at least **$10,000** (system threshold).

### Florida kill signals — any of these auto-disqualify the lead:
1. "Motion to Vacate" anywhere in docket.
2. "Order Canceling Sale" / "Sale Canceled".
3. "Order to Disburse Surplus" + "Granted" (already paid out).
4. "Bankruptcy" filing detected on the case.
5. Owner has already filed a surplus claim.
6. "Motion for Surplus Funds" filed by another party (a competing recovery firm beat us).

### Florida proof-of-surplus document — mortgage foreclosure:
**"Certificate of Disbursement"** — this is the document that confirms the surplus exists. Issued 7-14 days after the sale. New sales will not have it yet, so we capture them and re-check later.

### Florida proof-of-surplus document — tax deed:
**"Notice of Surplus"** plus the **claim form** — published in the tax deed file 7-14 days after the sale.

### Florida tax deed lien-holder rule:
Lien holders (NOT homeowners) have **120 days from notice** to file a claim. If they fail to file, they lose their rights — UNLESS they are governmental entities. **Homeowners are NOT bound by this 120-day window.** This was previously misstated; the 120 days applies only to subordinate lien holders.

### Case codes you will see in Florida case numbers:
- `CA` — mortgage foreclosure (civil action).
- `CC` — HOA / condominium association foreclosure.
- `A` (e.g. `2025A00491`) — tax deed.
- `TD` (e.g. `2025-0464TD`) — tax deed (Duval format).
- `O` suffix (e.g. `2024-CA-009603-O`) — Orange County identifier.
- `COWE` (e.g. `COWE-25-085495`) — code-enforcement / lien-related case.

---

## Miami-Dade County

### Auction Calendar
- URL: miamidade.realforeclose.com
- Both mortgage foreclosures AND tax deeds on ONE calendar (unique among FL counties).
- Schedule: daily.

### Case Search Quirks
- CRITICAL: Case numbers must be **split into 3 parts** for the case search query:
  - Year (e.g. `2025`)
  - Sequence (e.g. `004878`)
  - Case code (e.g. `CA-01`)
- Cannot paste whole case number — the system requires the split format.
- This is unique to Miami-Dade. All other Florida counties accept the whole case number.

### Tax Deed Portal
- Separate portal from county case search.
- Search by case number, open the documents tab.
- Look for the Property Information Report (sometimes labeled "Title Search", "Owner & Encumbrance Report", or "PIR").
- The PIR lists liens with book and page numbers — those need follow-up research at the recorder.

### Surplus Verification Steps (Miami-Dade)
1. Find a sale on the auction calendar where third-party bid > opening bid by $10K+.
2. Capture the case number, noting which format (CA / CC / A).
3. Search the case in county case search using the SPLIT format.
4. Open the docket, scan for kill signals FIRST.
5. Check parties — any defendants beyond the homeowner are creditors with potential claim rights.
6. Pull PropertyRadar data for second positions / liens.
7. For tax deeds: open the Property Information Report, scan for liens.
8. If new (less than 7 days old): mark for re-check on Day 7 and Day 14 to find the Certificate of Disbursement / Notice of Surplus.

---

## Broward County

### Auction Calendar
- URL: broward.realforeclose.com (mortgage foreclosures)
- Tax sales are NOT listed on the main foreclose site — they have a separate platform.
- Schedule: daily mortgage; tax sales when scheduled.

### Case Search Quirks
- **CAPTCHA required** on Broward county case search.
- Case numbers can be pasted whole (unlike Miami-Dade).
- Format example: `CACE-23-015282`.

### Surplus Verification Steps (Broward)
1. Find sale where third-party bid > opening bid by $10K+.
2. Solve CAPTCHA, paste whole case number.
3. Open docket, scan for kill signals.
4. Check parties — defendants beyond homeowner indicate creditors.
5. Watch for "Motion to Intervene" — competing recovery firms file these before formal claims. If seen, mark the lead as contested.
6. Pull PropertyRadar for second positions.

### Broward-Specific Note
The phrase "Order Canceling Sale" appears frequently in Broward dockets. Many third-party sales here get vacated, so kill-signal detection is especially important here. Any cancellation = invalidate the lead, do not pass to dashboard.

---

## Duval County

### Auction Calendar
- Mortgage URL: duval.realforeclose.com
- Tax deed URL: duval.realtaxdeed.com (separate portal — DIFFERENT calendar)
- This is the only FL county where the system splits these completely.

### Case Search Quirks
- No CAPTCHA on case search.
- Case numbers can be pasted whole.
- Mortgage format: `16-2024-CA-006388` style.
- Tax deed format: `2025-0464TD` (TD suffix).

### Tax Deed Portal Specifics
- Use case number to search.
- Look for `OE Report Title Express` link — this lists liens (especially code enforcement and nuisance liens, which are common in Duval).
- Surplus letter / Notice of Surplus published 7-14 days after sale.

### Surplus Verification Steps (Duval)
1. Decide whether the sale is mortgage or tax deed — they're on separate calendars.
2. Find third-party sale > opening bid by $10K+.
3. For mortgage: county case search → docket → scan for kill signals.
4. For tax deed: tax deed portal → look for surplus letter, then OE Report for lien research.
5. Pull PropertyRadar.

### Duval-Specific Watchout
Duval mortgage feed and tax deed feed must be tracked separately in the system. Mixing them without the right flag means we lose context for which lien-holder rules apply.

---

## Lee County

### Auction Calendar
- URL: lee.realforeclose.com
- Schedule: daily.

### Case Search Quirks
- No CAPTCHA.
- Case numbers can be pasted whole.
- Format examples: `24-CA-004695` (mortgage), `23-CC-008396` (HOA).
- Mixed mortgage + HOA cases — `CC` cases are HOA-driven foreclosures.

### Surplus Verification Steps (Lee)
1. Find third-party sale > opening bid by $10K+.
2. County case search → docket → scan for kill signals.
3. Distinguish CA (mortgage) from CC (HOA) — affects how junior liens stack.
4. PropertyRadar for second positions.

### Lee-Specific Note
HOA foreclosures (CC) often have small underlying debt but sell for full market value, creating large surplus opportunities. These tend to be high-quality leads.

---

## Orange County

### Auction Calendar
- Mortgage URL: myorangeclerk.realforeclose.com
- Tax deed: separate Comptroller portal
- Schedule: daily mortgage; tax deeds when scheduled.

### Critical Operational Rules
- **VPN MUST BE OFF.** Orange County actively blocks VPN traffic. The scraper must run from a residential / non-VPN IP.
- **CAPTCHA required** on case search.
- Case numbers can be pasted whole.
- Format example: `2024-CA-009603-O` (note the `-O` suffix indicating Orange).

### Auto-Skip Logic for Orange
Many Orange sales are **timeshare auctions selling for $100**. These are noise. Auto-skip any sale where:
- Final sale price < $1,000 AND
- Property type is timeshare-related (look for "interval", "week", or "timeshare" in description).

### Tax Deed Portal Steps
1. Comptroller site → Tax Deed Sales → search by case number under "Tax Deed Application Number".
2. Status will say "Active Overbid" if surplus exists.
3. Click "View Claims" to see if anyone has filed.
4. Click "View Property Information Report" to find liens.

### Surplus Verification Steps (Orange)
1. Confirm VPN is off.
2. Find third-party sale > opening bid by $10K+ AND not a timeshare.
3. CAPTCHA → case search → docket → kill signal scan.
4. PropertyRadar.

### Orange-Specific Watchout
Many sales here have plaintiff wins or canceled-per-county statuses. Real third-party surplus opportunities are less common than other FL counties. Filter aggressively, expect lower lead volume.

---

## Cross-County Florida Rules

### Re-scan Schedule
New Florida leads must be re-scanned on **Day 3, Day 7, and Day 14** after the sale to detect:
- The Certificate of Disbursement (mortgage) appearing.
- The Notice of Surplus (tax deed) appearing.
- Late-filed Motion to Vacate or Bankruptcy that would invalidate the lead.
- A homeowner or competing firm filing a surplus claim.

### Grading Framework — Florida
- **A+** : Surplus ≥ $100K, no second positions, no kill signals, no competing claims filed.
- **A**  : Surplus ≥ $50K, minor secondary liens (HOA, governmental), no kill signals.
- **B**  : Surplus ≥ $25K, multiple liens or contested party situation, requires more research.
- **C**  : Surplus ≥ $10K, multiple competing parties or significant lien stack — pursue last.

### Required Output Fields per FL Lead
- County, case number, sale date, parcel ID, address.
- Final sale price, opening bid (= debt), gross surplus.
- Kill signals detected (yes/no, list).
- PropertyRadar second-position summary (loan count, total balance, equity).
- Re-scan flags: 3-day, 7-day, 14-day status.
- Owner of record at time of sale.
