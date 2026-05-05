"""
SurplusIQ — Scraper Date Audit

Inspects the raw JSONL files from each county scrape and reports:
  • Sale date distribution (when did each lead actually sell?)
  • Case-number-year vs sale-date-year mismatches
  • Records with NO sale_date populated (scraper missed it)
  • Date range each county actually covers

This answers Eric's concern: "are these leads actually recent or are they old?"

Run after a fresh scrape:
    python -m core.audit_dates
"""

from __future__ import annotations
import json
import sys
import re
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import defaultdict, Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

COUNTIES = [
    "miami-dade-fl", "broward-fl", "duval-fl", "lee-fl", "orange-fl",
    "cuyahoga-oh", "franklin-oh", "montgomery-oh", "summit-oh", "hamilton-oh",
]

CUTOFF_DAYS = 14  # Eric wants leads from the last 14 days


def parse_sale_date(raw: dict) -> str | None:
    """
    Try every plausible field name for the sale date in the raw record.
    Returns ISO date string or None.
    """
    # Direct fields
    for key in ("sale_date", "sale_datetime", "auction_date", "soldDate", "AUCTIONDATE"):
        v = raw.get(key)
        if v:
            return str(v)[:10]

    # Pull from raw_text — most scrapers store the unparsed page text
    raw_text = raw.get("raw_text", "") or ""

    # Common patterns: "01/09/2026 09:03 AM ET", "Sold on 04/22/2026", "Sale Date: 4/22/2026"
    patterns = [
        r"(\d{1,2}/\d{1,2}/\d{4})\s+\d{1,2}:\d{2}",   # "04/22/2026 09:03"
        r"Sold on\s+(\d{1,2}/\d{1,2}/\d{4})",          # "Sold on 04/22/2026"
        r"Sale Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})",
        r"AUCTIONDATE[=:\s]+(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})",                    # last resort: any date
    ]
    for pat in patterns:
        m = re.search(pat, raw_text)
        if m:
            try:
                d = datetime.strptime(m.group(1), "%m/%d/%Y").date()
                return d.isoformat()
            except ValueError:
                continue
    return None


def parse_case_year(case_num: str) -> int | None:
    """Pull the year out of a case number. Different formats per state."""
    if not case_num:
        return None
    # Florida: "CACE-23-015282" or "2024-004878-CA-01" or "2025A00491"
    # Ohio: "2023 CV 02035" or "CV23976605"
    m = re.search(r"\b(20\d{2})\b", case_num)
    if m:
        return int(m.group(1))
    m = re.search(r"\b\d{2}\b", case_num)
    if m:
        yr = int(m.group(0))
        return 2000 + yr if yr < 80 else 1900 + yr
    return None


def audit_county(county_id: str) -> dict:
    """Run a full audit on one county's raw JSONL files."""
    files = sorted(RAW_DIR.glob(f"{county_id}_*.jsonl"))
    if not files:
        return {"county": county_id, "error": "no raw files found"}

    # Use the most recent file
    latest = files[-1]
    records = []
    with open(latest) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Filter to qualifying leads (3rd party, ≥$10K surplus)
    leads = [r for r in records if r.get("is_third_party") and r.get("gross_surplus", 0) >= 10000]

    today = date.today()
    cutoff = today - timedelta(days=CUTOFF_DAYS)

    sale_dates_found = []
    sale_dates_missing = []
    case_year_counter = Counter()
    sale_year_counter = Counter()
    out_of_window = []  # leads whose sale_date is older than cutoff
    in_window = []
    parser_misses = []  # records where we couldn't extract a date at all

    for lead in leads:
        sale_iso = parse_sale_date(lead)
        case_yr = parse_case_year(lead.get("case_number", ""))

        if case_yr:
            case_year_counter[case_yr] += 1

        if sale_iso:
            sale_dates_found.append(sale_iso)
            sale_year = int(sale_iso[:4])
            sale_year_counter[sale_year] += 1
            try:
                sale_d = date.fromisoformat(sale_iso)
                if sale_d < cutoff:
                    out_of_window.append((lead.get("case_number", "?"), sale_iso))
                else:
                    in_window.append((lead.get("case_number", "?"), sale_iso))
            except ValueError:
                pass
        else:
            sale_dates_missing.append(lead.get("case_number", "?"))
            parser_misses.append(lead)

    return {
        "county": county_id,
        "file": latest.name,
        "total_records": len(records),
        "qualifying_leads": len(leads),
        "sale_dates_extracted": len(sale_dates_found),
        "sale_dates_missing": len(sale_dates_missing),
        "in_14_day_window": len(in_window),
        "out_of_window": len(out_of_window),
        "case_year_distribution": dict(case_year_counter),
        "sale_year_distribution": dict(sale_year_counter),
        "out_of_window_examples": out_of_window[:5],
        "missing_date_examples": sale_dates_missing[:5],
        "earliest_sale_date": min(sale_dates_found) if sale_dates_found else None,
        "latest_sale_date": max(sale_dates_found) if sale_dates_found else None,
    }


def main():
    print()
    print("=" * 78)
    print("  SurplusIQ — Scraper Date Audit")
    print(f"  Today: {date.today().isoformat()}  |  Cutoff: last {CUTOFF_DAYS} days")
    print("=" * 78)
    print()

    grand_total = {
        "total": 0, "leads": 0, "in_window": 0, "out_of_window": 0,
        "missing_dates": 0,
    }

    for county_id in COUNTIES:
        result = audit_county(county_id)

        if "error" in result:
            print(f"❌ {county_id:<18}  {result['error']}")
            continue

        total = result["qualifying_leads"]
        in_w = result["in_14_day_window"]
        out_w = result["out_of_window"]
        miss = result["sale_dates_missing"]

        grand_total["total"] += result["total_records"]
        grand_total["leads"] += total
        grand_total["in_window"] += in_w
        grand_total["out_of_window"] += out_w
        grand_total["missing_dates"] += miss

        # Status flag
        if miss > 0 and total > 0 and miss / total > 0.5:
            flag = "🚨"  # more than half of leads have no parsed date
        elif out_w > 0:
            flag = "⚠️ "  # some leads outside 14-day window
        else:
            flag = "✅"

        print(f"{flag} {county_id:<18}  {total:>3} leads  |  in-window: {in_w:>3}  |  out-of-window: {out_w:>3}  |  no date: {miss:>3}")

        if result["earliest_sale_date"]:
            print(f"    Sale date range: {result['earliest_sale_date']} → {result['latest_sale_date']}")

        if result["case_year_distribution"]:
            cy = result["case_year_distribution"]
            cy_str = ", ".join(f"{y}: {n}" for y, n in sorted(cy.items()))
            print(f"    Case # year:     {cy_str}")

        if result["sale_year_distribution"]:
            sy = result["sale_year_distribution"]
            sy_str = ", ".join(f"{y}: {n}" for y, n in sorted(sy.items()))
            print(f"    Sale year:       {sy_str}")

        if result["out_of_window_examples"]:
            print(f"    ⚠ Out-of-window examples:")
            for case, date_str in result["out_of_window_examples"]:
                print(f"      • {case}  sold {date_str}")

        if result["missing_date_examples"]:
            print(f"    ⚠ Cases with no parseable sale_date:")
            for case in result["missing_date_examples"][:3]:
                print(f"      • {case}")
        print()

    print("=" * 78)
    print(f"  GRAND TOTAL: {grand_total['leads']} leads  |  in-window: {grand_total['in_window']}  |  "
          f"out-of-window: {grand_total['out_of_window']}  |  no date: {grand_total['missing_dates']}")
    print("=" * 78)
    print()
    print("INTERPRETATION:")
    print("  ✅ Green: scraper is working, sale dates extracted, all within window")
    print("  ⚠️  Yellow: some leads from outside the 14-day window (Orange County")
    print("              shows ALL historical sales, this is expected behavior)")
    print("  🚨 Red: scraper is failing to extract sale dates from raw text")
    print("              — needs a parser fix before we trust the date column")
    print()


if __name__ == "__main__":
    main()
