# SurplusIQ — System Rules

**Source:** Combined from Eric Richardson's operational walkthroughs and the project SOW.
**Last updated:** May 2026.
**Purpose:** Universal rules that apply across the entire system, regardless of state. These are the guardrails the AI / scraper / loader / dashboard must respect.

---

## 1. What Counts as a Qualifying Lead

A lead is qualifying if and only if ALL of these are true:

1. The auction sold to a **3rd-party bidder** (not plaintiff / bank / HOA-as-plaintiff).
2. The final sale price is greater than the debt:
   - Florida: `final_sale_price > opening_bid` (opening_bid = real debt in FL)
   - Ohio: `final_sale_price > true_debt_from_clerk` (NOT opening_bid; opening_bid in Ohio is fake)
3. The apparent surplus is at least **$10,000**.
4. The sale date is within the last **14 days** (date filter, enforced in loader).
5. NO kill signals are detected on the case (see Section 2).
6. The auction status is "Sold" or "Redeemed" (not "Canceled", "Postponed", "Withdrawn", "Bankruptcy").

If any of these fail, the lead must be excluded from the dashboard and Excel exports.

---

## 2. Universal Kill Signals

Any of these, found in the case docket or auction record, immediately invalidates a lead:

| Kill signal phrase                       | Reason                                       |
|------------------------------------------|----------------------------------------------|
| "Motion to Vacate"                       | Sale being challenged; will likely reverse.   |
| "Order Vacating Sale"                    | Sale already vacated; no surplus exists.      |
| "Order Canceling Sale"                   | Auction was canceled; no surplus.             |
| "Sale Canceled"                          | Same.                                         |
| "Bankruptcy"                             | Federal stay applies; surplus frozen.         |
| "Order to Disburse Surplus" + "Granted"  | Already paid out — too late.                  |
| "Owner's Claim for Mortgage Surplus"     | Homeowner already filed.                      |
| "Motion for Surplus Funds" + "Granted"   | Someone (often a competing firm) won it.      |
| "Excess funds sent to State"             | Money escheated; different recovery process.  |
| "Funds escheated"                        | Same.                                         |

The kill-signal scan should run against:
- The text of all docket events for a case.
- Any PDF judgment documents we open during debt extraction.
- The auction status field itself.

---

## 3. Lead Scoring Framework

Two grading scales apply because Florida and Ohio have different debt verification reliability.

### Florida grading (debt is reliable from opening_bid)

| Tier | Surplus      | Conditions                                                          |
|------|--------------|---------------------------------------------------------------------|
| A+   | ≥ $100,000   | No kill signals. No second positions on PropertyRadar. No competing claims. |
| A    | ≥ $50,000    | Minor liens (HOA, governmental). No kill signals.                   |
| B    | ≥ $25,000    | Multiple liens or contested party situation.                        |
| C    | ≥ $10,000    | Many parties or significant lien stack.                             |

### Ohio grading (debt is estimated; lower thresholds because verification harder)

| Tier | True surplus | Conditions                                                          |
|------|--------------|---------------------------------------------------------------------|
| A+   | ≥ $75,000    | Debt confirmed via clerk. No second positions. No kill signals.     |
| A    | ≥ $40,000    | Debt confirmed. Minor secondary liens.                              |
| B    | ≥ $20,000    | OR debt-estimated via PropertyRadar with strong loan signal.         |
| C    | ≥ $10,000    | PropertyRadar-only verification (e.g., Hamilton) or many defendants. |

### Scoring signals beyond surplus
- 3rd party bidder confirmed: + qualifying signal (without it, lead is rejected, not just lowered).
- Address known: required for skip-tracing.
- Parcel ID known: required for PropertyRadar enrichment.
- No kill signals: required for any tier above C.
- PropertyRadar match found: required for A+ / A in Ohio.

---

## 4. Date Filtering

Hard rule: the dashboard, Excel, and PropertyRadar enrichment never see leads older than 14 days.

- The 14-day filter is enforced in `core/loader.py` based on extracted `sale_date`.
- Raw scraper data is preserved indefinitely in `data/raw/` (we don't lose history).
- Any lead with no parseable `sale_date` is dropped, not promoted as "unknown date".
- The window is configurable via `window_days` parameter on `load_all_leads`, default 14.

---

## 5. Re-scan Schedule

After a lead is first captured, the system should re-check the case at:

- **Day 3** — earliest possible appearance of Certificate of Disbursement / Notice of Surplus.
- **Day 7** — typical publication window.
- **Day 14** — final cutoff for FL standard window; outside this date the lead leaves the dashboard.
- **Day 30** — Ohio-specific check for late motions, vacates, or funds escheated to State.

Each re-scan should:
1. Re-fetch the case docket.
2. Run kill-signal scan against new events.
3. If kill signal detected: remove lead from active dashboard.
4. If proof-of-surplus document published: confirm and lock the surplus number.
5. If competing firm filed: flag the lead but don't auto-remove (user decides).

---

## 6. Dedup Logic

A lead is uniquely identified by `(case_number, county_id)`.

- If the same `(case_number, county_id)` appears in multiple scrapes, the most recent scrape wins.
- The `seen_leads.json` ledger tracks first-seen date per unique lead.
- When pushing to Excess Elite CRM, dedup against Eric's existing records via the API to avoid duplicate entries.

---

## 7. New-Lead Tagging

Whenever a record enters the system for the first time, it is tagged `is_new = True`.
- The tag persists until manually flipped or until the next scrape after a configurable window.
- Default window: **3 days**. Once a lead has been in the system for >3 days, it auto-flips to `is_new = False`.
- Dashboard displays a "NEW" badge on leads where `is_new = True`.

---

## 8. PropertyRadar Enrichment Rules

Before a lead is graded above tier C, it must have PropertyRadar data attached.

### What PropertyRadar provides:
- Owner of record (current).
- Owner mailing address (often different from property address).
- Total loan balance.
- First loan amount, type (purchase / refi / ELOC / HELOC), date.
- Number of loans (>1 means second positions exist).
- Available equity (can be negative — flag commercial / over-leveraged properties).
- Property type (`COM` for commercial, `RES` for residential, etc.).
- AVM (estimated value).

### Decision rules:
- `PType = COM` → flag as commercial. Do not auto-promote to A+ unless Eric explicitly wants commercial leads.
- `AvailableEquity < 0` → property is over-leveraged. Likely no real surplus once liens settle.
- `NumberLoans > 1` AND `TotalLoanBalance > final_sale_price` → senior debt eats the surplus. Mark accordingly.
- `Owner` name contains "LLC", "Inc", "Corp", "Trust", "Estate" → entity owner. Different claim workflow needed (entity docs, trustee, probate).

### Cost discipline:
- PropertyRadar charges $0.01 per record returned.
- Always run with `Purchase=0` (dry-run) first when testing new query logic.
- Live runs only against in-window, qualifying leads — never run enrichment against the full raw dataset.

---

## 9. State-Specific Surplus Terms (for normalization)

Different states use different terminology. The system should normalize all of these to "surplus":

| State          | Term used                       |
|----------------|---------------------------------|
| Florida        | Surplus funds                   |
| Ohio           | Surplus funds / excess proceeds |
| California     | Excess proceeds                 |
| North Carolina | Overage                         |
| Texas          | Excess proceeds                 |
| Generic legal  | Overbid / overage               |

For now SurplusIQ only covers Florida and Ohio. Future state additions should be configured here, not hardcoded in scrapers.

---

## 10. What Counts as a Pre-Surplus Lead (Phase 2)

A pre-surplus lead is a property NOT yet sold but flagged as likely to produce surplus when it does. Triggers include:

- Lis pendens recorded on a property where AVM > debt.
- Homeowner pursuing loan modification.
- Property in pre-foreclosure with low judgment vs market value spread.
- "Estate of [name]" appearing on the deed (probate workflow).
- Notice of Trustee Sale (NTS) filed where original principal vs current value gap > $40K.

Pre-surplus is NOT in Phase 1 scope. Mentioned here so future builds know where it slots into the system.

---

## 11. What the System Must NEVER Do

These are non-negotiable:

1. Show a lead older than 14 days on the dashboard.
2. Pass an Ohio lead through without verifying real debt (or marking it "debt-estimated").
3. Show a lead with a "Motion to Vacate" or "Bankruptcy" in its docket.
4. Tell the user a lead is A+ without PropertyRadar enrichment.
5. Enrich a lead in PropertyRadar with `Purchase=1` if it's outside the 14-day window.
6. Push a duplicate to Eric's CRM that already exists there.
7. Hide the surplus calculation logic — every dollar shown must be traceable to its source.

---

## 12. Integration Points

The knowledge-base files are referenced by:

- `core/loader.py` — kill-signal filtering, date filtering, scoring.
- `core/auction/universal.py` — county-specific scraper rules.
- `core/enrichment/propertyradar.py` — enrichment decision logic.
- `core/dashboard_data.py` — output formatting, NEW tagging.
- `core/audit_dates.py` — verification of scraper accuracy.
- Future: `core/dockets/` — docket scraping for kill signals + Ohio prayer amounts.
- Future: `core/excess_elite/` — CRM dedup integration.

Whenever you edit code in this project, READ THE RELEVANT KB FILE FIRST. Do not assume county behavior. Do not invent rules. If the KB doesn't cover a case, ask before deciding.
