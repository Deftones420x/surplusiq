"""
SurplusIQ — Unified Data Loader (v2 — 14-day cutoff enforced)

Consolidates raw scraped data from all 10 counties into a single clean dataset
ready for Excel export, dashboard rendering, and PropertyRadar enrichment.

CHANGES IN v2:
  • Hard 14-day window: any lead with sale_date older than (today - 14 days)
    is dropped before reaching the dashboard / Excel / enrichment.
  • If sale_date can't be parsed, the lead is dropped as well.
  • Console output reports how many were dropped and why, so we can verify
    the filter is doing what we expect each time.

Usage:
    from core.loader import load_all_leads, get_summary

    leads = load_all_leads()                    # all qualifying leads (last 14 days)
    leads = load_all_leads(min_surplus=25000)   # higher surplus threshold
    leads = load_all_leads(window_days=7)       # tighter date window
    summary = get_summary(leads)                # county totals
"""

from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# Project paths
# ═══════════════════════════════════════════════════════════════════════
def _find_project_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "config" / "counties.py").exists():
            return parent
    return Path(__file__).resolve().parent.parent

PROJECT_ROOT = _find_project_root()
RAW_DIR      = PROJECT_ROOT / "data" / "raw"


# ═══════════════════════════════════════════════════════════════════════
# County metadata (ID → display info)
# ═══════════════════════════════════════════════════════════════════════
COUNTY_INFO = {
    "miami-dade-fl": {"name": "Miami-Dade", "state": "FL", "platform": "Florida — RealForeclose"},
    "broward-fl":    {"name": "Broward",    "state": "FL", "platform": "Florida — RealForeclose"},
    "duval-fl":      {"name": "Duval",      "state": "FL", "platform": "Florida — RealForeclose (Tax Deed)"},
    "lee-fl":        {"name": "Lee",        "state": "FL", "platform": "Florida — RealForeclose"},
    "orange-fl":     {"name": "Orange",     "state": "FL", "platform": "Florida — RealForeclose"},
    "cuyahoga-oh":   {"name": "Cuyahoga",   "state": "OH", "platform": "Ohio — SheriffSaleAuction"},
    "franklin-oh":   {"name": "Franklin",   "state": "OH", "platform": "Ohio — SheriffSaleAuction"},
    "montgomery-oh": {"name": "Montgomery", "state": "OH", "platform": "Ohio — SheriffSaleAuction"},
    "summit-oh":     {"name": "Summit",     "state": "OH", "platform": "Ohio — SheriffSaleAuction"},
    "hamilton-oh":   {"name": "Hamilton",   "state": "OH", "platform": "Ohio — SheriffSaleAuction"},
}


# ═══════════════════════════════════════════════════════════════════════
# Lead data structure
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class Lead:
    # Identity
    county_id:      str
    county_name:    str
    state:          str
    case_number:    str

    # Property
    address:        str
    parcel_id:      str
    auction_type:   str

    # Financials
    opening_bid:    float
    final_sale_price: float
    gross_surplus:  float
    assessed_value: float

    # Sale details
    sale_date:      str         # ISO format (YYYY-MM-DD) after normalization
    sale_datetime:  str         # Full readable timestamp e.g. "May 4, 2026 9:02 AM ET"
    sold_to:        str
    is_third_party: bool
    source_url:     str         # Direct link to the county auction page

    # Lead quality
    auction_status: str

    # Source
    scraped_at:     str
    source_file:    str

    # Lead score
    score:          str = ""
    score_reason:   str = ""

    # Enrichment placeholders
    enriched:           bool   = False
    estimated_value:    float  = 0.0
    mortgage_balance:   float  = 0.0
    secondary_liens:    float  = 0.0
    net_surplus:        float  = 0.0
    owner_name:         str    = ""
    owner_address:      str    = ""

    # Claim status
    claim_filed:        bool   = False
    claim_status:       str    = "Unknown"

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════
def _latest_jsonl_for_county(county_id: str) -> Optional[Path]:
    pattern = f"{county_id}_*.jsonl"
    files = sorted(RAW_DIR.glob(pattern))
    return files[-1] if files else None


def _extract_sale_datetime(record: dict) -> str:
    """
    Extract a human-readable timestamp like "May 4, 2026 9:02 AM ET" from the raw_text.
    Returns empty string if not parseable.
    """
    raw = record.get("raw_text", "") or ""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}:\d{2})\s*(AM|PM)?\s*ET", raw, re.IGNORECASE)
    if not m:
        return ""
    try:
        mm, dd, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        time_str = m.group(4)
        ampm = (m.group(5) or "").upper()
        d = date(yyyy, mm, dd)
        return f"{d.strftime('%b %-d, %Y')} {time_str} {ampm} ET".strip()
    except (ValueError, AttributeError):
        return ""


def _normalize_address(raw: str) -> str:
    if not raw:
        return ""
    return raw.replace("Property Address:", "").strip()


def _extract_sale_date(record: dict) -> Optional[date]:
    """
    Try every plausible source for the sale date and return a date object.
    Returns None if no parseable date is found.
    """
    # Direct fields first
    for key in ("sale_date", "sale_datetime", "auction_date", "soldDate", "AUCTIONDATE"):
        v = record.get(key)
        if v:
            iso = str(v)[:10]
            try:
                return date.fromisoformat(iso)
            except ValueError:
                pass

    # Pull from raw_text — most scrapers store the unparsed page text
    raw_text = record.get("raw_text", "") or ""

    patterns = [
        r"(\d{1,2}/\d{1,2}/\d{4})\s+\d{1,2}:\d{2}",
        r"Sold on\s+(\d{1,2}/\d{1,2}/\d{4})",
        r"Sale Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})",
        r"AUCTIONDATE[=:\s]+(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, raw_text)
        if m:
            try:
                return datetime.strptime(m.group(1), "%m/%d/%Y").date()
            except ValueError:
                continue
    return None


def _parse_lead(record: dict, county_id: str, source_file: str) -> Optional[Lead]:
    """Convert a raw scraper record into a Lead dataclass."""
    info = COUNTY_INFO.get(county_id, {})

    try:
        opening   = float(record.get("opening_bid") or 0)
        final     = float(record.get("final_sale_price") or 0)
        assessed  = float(record.get("assessed_value") or 0)
        surplus   = final - opening if final and opening else 0
    except (ValueError, TypeError):
        return None

    # Normalize sale_date to ISO format if we can extract one
    parsed_date = _extract_sale_date(record)
    sale_date_iso = parsed_date.isoformat() if parsed_date else (record.get("sale_date") or "").strip()

    return Lead(
        county_id     = county_id,
        county_name   = info.get("name", county_id),
        state         = info.get("state", ""),
        case_number   = (record.get("case_number") or "").strip(),
        address       = _normalize_address(record.get("address") or ""),
        parcel_id     = (record.get("parcel_id") or "").strip(),
        auction_type  = (record.get("auction_type") or "").strip(),
        opening_bid   = opening,
        final_sale_price = final,
        gross_surplus = surplus,
        assessed_value   = assessed,
        sale_date     = sale_date_iso,
        sale_datetime = _extract_sale_datetime(record),
        sold_to       = (record.get("sold_to") or "").strip(),
        source_url    = (record.get("source_url") or "").strip(),
        is_third_party = bool(record.get("is_third_party", False)),
        auction_status = (record.get("auction_status") or "").strip(),
        scraped_at    = datetime.now().isoformat(timespec="seconds"),
        source_file   = source_file,
    )


def _score_lead(lead: Lead) -> tuple[str, str]:
    s = lead.gross_surplus
    reasons = []

    if s >= 100_000:
        score = "A+"
        reasons.append(f"${s:,.0f} surplus ≥ $100K")
    elif s >= 50_000:
        score = "A"
        reasons.append(f"${s:,.0f} surplus ≥ $50K")
    elif s >= 25_000:
        score = "B"
        reasons.append(f"${s:,.0f} surplus ≥ $25K")
    elif s >= 10_000:
        score = "C"
        reasons.append(f"${s:,.0f} surplus ≥ $10K")
    else:
        score = "—"
        reasons.append("below threshold")

    if lead.is_third_party:
        reasons.append("3rd party bidder ✓")
    if lead.address:
        reasons.append("address known")
    if lead.parcel_id:
        reasons.append("parcel ID known")

    return score, " | ".join(reasons)


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════
def load_all_leads(
    min_surplus: float = 10_000,
    require_third_party: bool = True,
    counties: Optional[list[str]] = None,
    window_days: int = 14,
    verbose: bool = True,
) -> list[Lead]:
    """
    Load all qualifying leads from raw JSONL files across all counties.

    Filters applied (in order):
      1. is_third_party (must be True if require_third_party)
      2. gross_surplus >= min_surplus
      3. sale_date must be parseable
      4. sale_date >= (today - window_days)  ← NEW in v2

    Args:
        min_surplus: Minimum gross surplus required to qualify (default $10K)
        require_third_party: Only include 3rd party bidder wins (default True)
        counties: Optional list of county_ids to include (default: all 10)
        window_days: Maximum age of sale_date in days (default 14)
        verbose: Print summary of what was filtered out

    Returns:
        List of Lead objects, sorted by gross_surplus descending.
    """
    target_counties = counties or list(COUNTY_INFO.keys())
    today = date.today()
    cutoff = today - timedelta(days=window_days)
    leads: list[Lead] = []

    # Track what got filtered out, per county
    stats = {
        cid: {"raw": 0, "kept": 0, "not_3rd_party": 0, "below_min": 0,
              "no_date": 0, "out_of_window": 0}
        for cid in target_counties
    }

    for county_id in target_counties:
        jsonl_path = _latest_jsonl_for_county(county_id)
        if not jsonl_path:
            if verbose:
                print(f"⚠ No data file found for {county_id}")
            continue

        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                stats[county_id]["raw"] += 1

                lead = _parse_lead(record, county_id, str(jsonl_path.name))
                if not lead:
                    continue

                # Filter 1: 3rd party
                if require_third_party and not lead.is_third_party:
                    stats[county_id]["not_3rd_party"] += 1
                    continue

                # Filter 2: minimum surplus
                if lead.gross_surplus < min_surplus:
                    stats[county_id]["below_min"] += 1
                    continue

                # Filter 3: sale_date must be parseable
                parsed_date = _extract_sale_date(record)
                if not parsed_date:
                    stats[county_id]["no_date"] += 1
                    continue

                # Filter 4: sale_date within window_days of today
                if parsed_date < cutoff:
                    stats[county_id]["out_of_window"] += 1
                    continue

                # Score and keep
                lead.score, lead.score_reason = _score_lead(lead)
                stats[county_id]["kept"] += 1
                leads.append(lead)

    leads.sort(key=lambda x: x.gross_surplus, reverse=True)

    # Print filter audit if verbose
    if verbose:
        total_raw = sum(s["raw"] for s in stats.values())
        total_kept = sum(s["kept"] for s in stats.values())
        total_dropped_window = sum(s["out_of_window"] for s in stats.values())
        total_dropped_date = sum(s["no_date"] for s in stats.values())

        print(f"\n  Date filter: keeping leads sold on or after {cutoff.isoformat()} (last {window_days} days)")
        print(f"  Loaded {total_kept} qualifying leads from {total_raw} raw records.")
        if total_dropped_window or total_dropped_date:
            print(f"  Dropped {total_dropped_window} as out-of-window, {total_dropped_date} with no parseable date.")

        # Show per-county breakdown if anything was dropped for date reasons
        if total_dropped_window or total_dropped_date:
            print("\n  Per-county date-filter impact:")
            for cid in target_counties:
                s = stats[cid]
                if s["out_of_window"] > 0 or s["no_date"] > 0:
                    print(f"    {cid:<18}: kept {s['kept']:>2}, "
                          f"dropped {s['out_of_window']:>2} out-of-window, "
                          f"{s['no_date']:>2} no-date")

    return leads


def get_summary(leads: list[Lead]) -> dict:
    by_county: dict[str, dict] = {}
    by_state: dict[str, dict] = {"FL": {"leads": 0, "surplus": 0.0},
                                  "OH": {"leads": 0, "surplus": 0.0}}
    by_score = {"A+": 0, "A": 0, "B": 0, "C": 0}

    for lead in leads:
        cid = lead.county_id
        if cid not in by_county:
            by_county[cid] = {
                "county_id":   cid,
                "county_name": lead.county_name,
                "state":       lead.state,
                "leads":       0,
                "surplus":     0.0,
                "top_lead":    0.0,
            }
        by_county[cid]["leads"] += 1
        by_county[cid]["surplus"] += lead.gross_surplus
        by_county[cid]["top_lead"] = max(by_county[cid]["top_lead"], lead.gross_surplus)

        if lead.state in by_state:
            by_state[lead.state]["leads"] += 1
            by_state[lead.state]["surplus"] += lead.gross_surplus

        if lead.score in by_score:
            by_score[lead.score] += 1

    return {
        "generated_at":    datetime.now().isoformat(timespec="seconds"),
        "total_leads":     len(leads),
        "total_surplus":   sum(l.gross_surplus for l in leads),
        "by_county":       sorted(by_county.values(), key=lambda x: x["surplus"], reverse=True),
        "by_state":        by_state,
        "by_score":        by_score,
        "top_5_leads":     [
            {
                "county":      l.county_name,
                "state":       l.state,
                "case_number": l.case_number,
                "address":     l.address,
                "surplus":     l.gross_surplus,
                "sale_price":  l.final_sale_price,
                "sale_date":   l.sale_date,
                "score":       l.score,
            }
            for l in leads[:5]
        ],
    }


# ═══════════════════════════════════════════════════════════════════════
# CLI for quick verification
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SurplusIQ — Data Loader Verification (v2 with 14-day cutoff)")
    print("=" * 70)
    print(f"\n📂 Reading from: {RAW_DIR}\n")

    leads = load_all_leads()
    summary = get_summary(leads)

    print(f"\n✓ Total surplus identified: ${summary['total_surplus']:,.0f}\n")

    print("─" * 70)
    print("  BY STATE")
    print("─" * 70)
    for state, data in summary["by_state"].items():
        print(f"  {state}: {data['leads']:>3} leads | ${data['surplus']:>14,.0f}")

    print("\n" + "─" * 70)
    print("  BY COUNTY (sorted by surplus)")
    print("─" * 70)
    for c in summary["by_county"]:
        print(f"  {c['county_name']:<14} ({c['state']}): {c['leads']:>3} leads | "
              f"${c['surplus']:>14,.0f} | top: ${c['top_lead']:>11,.0f}")

    print("\n" + "─" * 70)
    print("  BY SCORE")
    print("─" * 70)
    for score, count in summary["by_score"].items():
        bar = "█" * count
        print(f"  {score:<3}: {count:>3}  {bar}")

    print("\n" + "─" * 70)
    print("  TOP 5 LEADS")
    print("─" * 70)
    for i, l in enumerate(summary["top_5_leads"], 1):
        print(f"  #{i}  ${l['surplus']:>11,.0f} | {l['score']:<3} | "
              f"{l['county']}, {l['state']} | sold {l['sale_date']} | {l['case_number']}")
        if l['address']:
            print(f"       {l['address'][:60]}")

    print("\n" + "=" * 70)
    print("  ✓ Data loader v2 operational. 14-day cutoff enforced.")
    print("=" * 70)
