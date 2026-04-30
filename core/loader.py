"""
SurplusIQ — Unified Data Loader

Consolidates raw scraped data from all 10 counties into a single clean dataset
ready for Excel export, dashboard rendering, and PropertyRadar enrichment.

Usage:
    from core.loader import load_all_leads, get_summary

    leads = load_all_leads()                    # all qualifying leads
    leads = load_all_leads(min_surplus=25000)   # higher threshold
    summary = get_summary(leads)                # county totals
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, date
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
    auction_type:   str        # FORECLOSURE / TAX DEED / etc.

    # Financials
    opening_bid:    float
    final_sale_price: float
    gross_surplus:  float       # final_sale - opening_bid
    assessed_value: float

    # Sale details
    sale_date:      str
    sold_to:        str         # "3rd Party Bidder" / "Plaintiff"
    is_third_party: bool

    # Lead quality
    auction_status: str         # "Sold" / "Redeemed"

    # Source
    scraped_at:     str         # ISO timestamp of scrape
    source_file:    str

    # Lead score (computed)
    score:          str = ""    # "A+" / "A" / "B" / "C"
    score_reason:   str = ""

    # Enrichment placeholders (filled later by PropertyRadar)
    enriched:           bool   = False
    estimated_value:    float  = 0.0
    mortgage_balance:   float  = 0.0
    secondary_liens:    float  = 0.0
    net_surplus:        float  = 0.0    # gross_surplus - liens
    owner_name:         str    = ""
    owner_address:      str    = ""

    # Claim status (filled later by clerk scraper)
    claim_filed:        bool   = False
    claim_status:       str    = "Unknown"  # Not Filed / Filed / Funds Disbursed

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════
# Loaders
# ═══════════════════════════════════════════════════════════════════════
def _latest_jsonl_for_county(county_id: str) -> Optional[Path]:
    """Find the most recent JSONL file for a given county."""
    pattern = f"{county_id}_*.jsonl"
    files = sorted(RAW_DIR.glob(pattern))
    return files[-1] if files else None


def _normalize_address(raw: str) -> str:
    """Strip 'Property Address:' prefix and trim."""
    if not raw:
        return ""
    return raw.replace("Property Address:", "").strip()


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
        sale_date     = (record.get("sale_date") or "").strip(),
        sold_to       = (record.get("sold_to") or "").strip(),
        is_third_party = bool(record.get("is_third_party", False)),
        auction_status = (record.get("auction_status") or "").strip(),
        scraped_at    = datetime.now().isoformat(timespec="seconds"),
        source_file   = source_file,
    )


def _score_lead(lead: Lead) -> tuple[str, str]:
    """
    Score a lead A+ / A / B / C based on surplus size and quality signals.
    Returns (score, reason).

    Tiers:
      A+   : surplus ≥ $100K — top priority
      A    : surplus ≥ $50K
      B    : surplus ≥ $25K
      C    : surplus ≥ $10K (minimum threshold)
    """
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

    # Bonus signals
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
) -> list[Lead]:
    """
    Load all qualifying leads from raw JSONL files across all counties.

    Args:
        min_surplus: Minimum gross surplus required to qualify (default $10K)
        require_third_party: Only include 3rd party bidder wins (default True)
        counties: Optional list of county_ids to include (default: all 10)

    Returns:
        List of Lead objects, sorted by gross_surplus descending.
    """
    target_counties = counties or list(COUNTY_INFO.keys())
    leads: list[Lead] = []

    for county_id in target_counties:
        jsonl_path = _latest_jsonl_for_county(county_id)
        if not jsonl_path:
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

                lead = _parse_lead(record, county_id, str(jsonl_path.name))
                if not lead:
                    continue

                # Apply qualifying filters
                if require_third_party and not lead.is_third_party:
                    continue
                if lead.gross_surplus < min_surplus:
                    continue

                # Score the lead
                lead.score, lead.score_reason = _score_lead(lead)
                leads.append(lead)

    # Sort by surplus descending
    leads.sort(key=lambda x: x.gross_surplus, reverse=True)
    return leads


def get_summary(leads: list[Lead]) -> dict:
    """
    Generate a summary breakdown of leads:
      - Per-county counts and totals
      - Per-state totals
      - Score distribution
      - Grand totals
    """
    by_county: dict[str, dict] = {}
    by_state: dict[str, dict] = {"FL": {"leads": 0, "surplus": 0.0},
                                  "OH": {"leads": 0, "surplus": 0.0}}
    by_score = {"A+": 0, "A": 0, "B": 0, "C": 0}

    for lead in leads:
        # County aggregation
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

        # State aggregation
        if lead.state in by_state:
            by_state[lead.state]["leads"] += 1
            by_state[lead.state]["surplus"] += lead.gross_surplus

        # Score aggregation
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
    print("  SurplusIQ — Data Loader Verification")
    print("=" * 70)
    print(f"\n📂 Reading from: {RAW_DIR}\n")

    leads = load_all_leads()
    summary = get_summary(leads)

    print(f"✓ Loaded {summary['total_leads']} qualifying leads")
    print(f"✓ Total surplus identified: ${summary['total_surplus']:,.0f}\n")

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
              f"{l['county']}, {l['state']} | {l['case_number']}")
        if l['address']:
            print(f"       {l['address'][:60]}")

    print("\n" + "=" * 70)
    print("  ✓ Data loader operational. Ready for Excel + dashboard build.")
    print("=" * 70)
