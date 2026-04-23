"""
SurplusIQ — Surplus Detection & Lead Scoring Pipeline
Analyzes enriched properties, calculates surplus, scores leads A+/A/B/C
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

# ── Scoring Thresholds ────────────────────────────────────────────────
MIN_SURPLUS_THRESHOLD = 1000   # Below this = not worth pursuing
SCORE_WEIGHTS = {
    "surplus_amount":      40,  # Biggest factor
    "no_secondary_liens":  25,  # Clean title = easier claim
    "claim_not_filed":     20,  # Nobody's touched it yet
    "doc_available":       10,  # Certificate of disbursement ready
    "enrichment_complete":  5,  # We have owner contact info
}

# Keywords in docket text indicating a claim has been filed
CLAIM_FILED_KEYWORDS = [
    "motion to disburse", "motion for disbursement",
    "claim to surplus", "claim surplus funds",
    "petition to determine", "petition for",
    "notice of claim", "competing claim",
    "disbursement of surplus", "order granting",
    "order disbursing",
]

# Keywords indicating funds already paid out
DISBURSED_KEYWORDS = [
    "order disbursing", "funds disbursed", "check issued",
    "payment issued", "surplus paid", "funds released",
    "disbursement complete",
]

# Partial claim keywords — claim filed but surplus may remain
PARTIAL_CLAIM_KEYWORDS = [
    "seeking additional advances", "additional attorney",
    "condominium association", "hoa claim", "partial",
    "only as to", "limited claim",
]

PLAINTIFF_KEYWORDS = [
    "plaintiff", "mortgagee", "bank", "n.a.", "trust",
    "llc", "financial", "federal", "national", "mortgage",
    "fannie", "freddie", "wells fargo", "chase", "citibank",
    "us bank", "u.s. bank", "pennymac", "newrez",
    "ocwen", "nationstar", "mr. cooper", "lakeview", "freedom",
    "no bid", "certificate to plaintiff",
]


def is_third_party_sale(prop: dict) -> bool:
    """Determine if the winning bidder is a genuine third party."""
    winner    = (prop.get("winner_name") or "").lower().strip()
    plaintiff = (prop.get("plaintiff") or "").lower().strip()

    if not winner:
        return False

    # If winner matches plaintiff — bank took it back
    if plaintiff and len(plaintiff) > 3:
        if plaintiff in winner or winner in plaintiff:
            return False

    # Check against known plaintiff patterns
    for kw in PLAINTIFF_KEYWORDS:
        if kw in winner:
            return False

    return True


def calculate_surplus(prop: dict) -> float:
    """
    Compute estimated net surplus.
    Surplus = Final Sale Price - Opening Bid (judgment amount)
    Then subtract known secondary liens.
    """
    final_price  = float(prop.get("final_sale_price", 0) or 0)
    opening_bid  = float(prop.get("opening_bid", 0) or 0)
    sec_liens    = float(prop.get("total_secondary_liens", 0) or 0)

    gross_surplus = final_price - opening_bid
    if gross_surplus <= 0:
        return 0.0

    # Net surplus after known secondary encumbrances
    net_surplus = gross_surplus - sec_liens
    return max(net_surplus, 0.0)


def detect_claim_status(docket_text: str) -> str:
    """
    Analyze docket text to determine claim status.
    Returns: 'none', 'partial', 'filed', 'disbursed'
    """
    if not docket_text:
        return "none"

    text = docket_text.lower()

    # Check if already disbursed (worst case)
    if any(kw in text for kw in DISBURSED_KEYWORDS):
        return "disbursed"

    # Check for partial claim (still pursuable)
    if any(kw in text for kw in PARTIAL_CLAIM_KEYWORDS):
        return "partial"

    # Check if any claim filed
    if any(kw in text for kw in CLAIM_FILED_KEYWORDS):
        return "filed"

    return "none"


def score_lead(prop: dict) -> tuple:
    """
    Score a lead from 0-100 and assign A+/A/B/C grade.
    Returns (score: int, grade: str, breakdown: dict)
    """
    score = 0
    breakdown = {}

    surplus = prop.get("net_surplus", 0) or 0

    # ── Surplus Amount (0-40 pts) ─────────────────────────────────────
    if surplus >= 50000:
        pts = 40
    elif surplus >= 25000:
        pts = 35
    elif surplus >= 10000:
        pts = 28
    elif surplus >= 5000:
        pts = 18
    elif surplus >= 1000:
        pts = 10
    else:
        pts = 0
    score += pts
    breakdown["surplus_score"] = pts

    # ── No Secondary Liens (0-25 pts) ────────────────────────────────
    if not prop.get("has_secondary_liens", True):
        pts = 25
    else:
        sec = prop.get("total_secondary_liens", 0) or 0
        if sec < 5000:
            pts = 15
        elif sec < 15000:
            pts = 8
        else:
            pts = 0
    score += pts
    breakdown["lien_score"] = pts

    # ── Claim Status (0-20 pts) ───────────────────────────────────────
    claim = prop.get("claim_status", "none")
    if claim == "none":
        pts = 20
    elif claim == "partial":
        pts = 12   # Still pursuable
    elif claim == "filed":
        pts = 3    # Someone's there — low priority
    else:  # disbursed
        pts = 0
    score += pts
    breakdown["claim_score"] = pts

    # ── Document Available (0-10 pts) ────────────────────────────────
    if prop.get("doc_available"):
        pts = 10
    elif prop.get("doc_status") == "pending":
        pts = 5
    else:
        pts = 0
    score += pts
    breakdown["doc_score"] = pts

    # ── Enrichment Complete (0-5 pts) ────────────────────────────────
    if prop.get("pr_enriched"):
        pts = 5
    else:
        pts = 0
    score += pts
    breakdown["enrichment_score"] = pts

    # ── Grade ─────────────────────────────────────────────────────────
    if score >= 85:
        grade = "A+"
    elif score >= 70:
        grade = "A"
    elif score >= 50:
        grade = "B"
    else:
        grade = "C"

    # Hard downgrade rules
    if claim == "disbursed":
        grade = "C"
        score = min(score, 20)
    if surplus < MIN_SURPLUS_THRESHOLD:
        grade = "C"
        score = min(score, 10)

    return score, grade, breakdown


def process_property(prop: dict) -> dict:
    """
    Full processing pipeline for one property.
    Adds: third_party flag, surplus calc, claim status, score, grade.
    """
    processed = prop.copy()

    # ── Step 1: Third-party check ─────────────────────────────────────
    processed["is_third_party"] = is_third_party_sale(prop)
    if not processed["is_third_party"]:
        processed["skip_reason"]  = "plaintiff_won"
        processed["score"]        = 0
        processed["grade"]        = "C"
        processed["net_surplus"]  = 0.0
        processed["claim_status"] = "n/a"
        return processed

    # ── Step 2: Surplus calculation ───────────────────────────────────
    gross_surplus = float(prop.get("final_sale_price", 0) or 0) - float(prop.get("opening_bid", 0) or 0)
    net_surplus   = calculate_surplus(prop)

    processed["gross_surplus"] = round(gross_surplus, 2)
    processed["net_surplus"]   = round(net_surplus, 2)

    # Skip if no surplus
    if net_surplus < MIN_SURPLUS_THRESHOLD:
        processed["skip_reason"] = f"surplus_below_threshold (${net_surplus:,.0f})"
        processed["score"]       = 0
        processed["grade"]       = "C"
        processed["claim_status"] = "n/a"
        return processed

    # ── Step 3: Claim status from docket ─────────────────────────────
    docket_text = prop.get("docket_text", "") or prop.get("clerk_text", "")
    claim_status = detect_claim_status(docket_text)
    processed["claim_status"] = claim_status

    # ── Step 4: Document status ───────────────────────────────────────
    if not prop.get("doc_status"):
        processed["doc_status"]    = "pending"
        processed["doc_available"] = False
    else:
        processed["doc_available"] = prop.get("doc_status") == "retrieved"

    # ── Step 5: Re-scan schedule ──────────────────────────────────────
    from counties import COUNTY_MAP  # noqa: allow local import
    county_config = COUNTY_MAP.get(prop.get("county_id", ""), {})
    doc_days = county_config.get("doc_timing_days", 10)

    sale_date_str = prop.get("sale_date", date.today().isoformat())
    try:
        sale_dt = datetime.fromisoformat(sale_date_str).date()
    except Exception:
        sale_dt = date.today()

    days_since_sale = (date.today() - sale_dt).days
    processed["days_since_sale"] = days_since_sale

    # Determine next checkpoint
    if days_since_sale < 3:
        processed["next_check"] = "day_3"
    elif days_since_sale < 7:
        processed["next_check"] = "day_7"
    elif days_since_sale < 14:
        processed["next_check"] = "day_14"
    else:
        processed["next_check"] = "overdue"

    # ── Step 6: Score ─────────────────────────────────────────────────
    score, grade, breakdown = score_lead(processed)
    processed["score"]           = score
    processed["grade"]           = grade
    processed["score_breakdown"] = breakdown

    # ── Step 7: Outreach flag ─────────────────────────────────────────
    processed["outreach_ready"] = (
        grade in ("A+", "A")
        and claim_status in ("none", "partial")
        and net_surplus >= 5000
    )

    return processed


def run_pipeline(raw_properties: list) -> list:
    """
    Process all raw scraped properties through the full pipeline.
    Returns only third-party surplus leads (filters out non-surplus).
    """
    print(f"\n⚙️  Running surplus detection pipeline on {len(raw_properties)} properties...")

    all_processed   = []
    third_party     = 0
    surplus_found   = 0
    skipped         = 0

    for prop in raw_properties:
        processed = process_property(prop)
        all_processed.append(processed)

        if processed.get("is_third_party"):
            third_party += 1
            if processed.get("net_surplus", 0) >= MIN_SURPLUS_THRESHOLD:
                surplus_found += 1
            else:
                skipped += 1
        else:
            skipped += 1

    # Sort by score descending, then surplus descending
    surplus_leads = [p for p in all_processed if p.get("is_third_party") and p.get("net_surplus", 0) >= MIN_SURPLUS_THRESHOLD]
    surplus_leads.sort(key=lambda x: (x.get("score", 0), x.get("net_surplus", 0)), reverse=True)

    # Grade summary
    grades = {"A+": 0, "A": 0, "B": 0, "C": 0}
    for lead in surplus_leads:
        g = lead.get("grade", "C")
        grades[g] = grades.get(g, 0) + 1

    print(f"  Total scraped:    {len(raw_properties)}")
    print(f"  Third-party:      {third_party}")
    print(f"  Surplus leads:    {surplus_found}")
    print(f"  Filtered out:     {skipped}")
    print(f"  Grade breakdown:  A+={grades['A+']} A={grades['A']} B={grades['B']} C={grades['C']}")

    total_surplus = sum(p.get("net_surplus", 0) for p in surplus_leads)
    print(f"  Total net surplus identified: ${total_surplus:,.0f}")

    return surplus_leads


def save_leads(leads: list, date_str: str = None):
    """Save processed leads to JSONL."""
    if not date_str:
        date_str = date.today().isoformat()
    filepath = DATA_DIR / f"leads_{date_str}.jsonl"
    with open(filepath, "w") as f:
        for lead in leads:
            f.write(json.dumps(lead) + "\n")
    print(f"💾 Leads saved: {filepath} ({len(leads)} records)")
    return filepath


def load_leads(date_str: str = None) -> list:
    """Load processed leads from JSONL."""
    if not date_str:
        date_str = date.today().isoformat()
    filepath = DATA_DIR / f"leads_{date_str}.jsonl"
    if not filepath.exists():
        return []
    with open(filepath) as f:
        return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    # Test with sample data
    test_prop = {
        "county_id":        "miami-dade-fl",
        "county_name":      "Miami-Dade",
        "state":            "FL",
        "case_number":      "2024-CA-048821",
        "address":          "4821 NW 7th Ave, Miami, FL 33127",
        "opening_bid":      263800,
        "final_sale_price": 312000,
        "winner_name":      "MDH Real Estate Partners LLC",
        "plaintiff":        "Wells Fargo Bank NA",
        "pr_enriched":      True,
        "has_secondary_liens": False,
        "total_secondary_liens": 0,
        "owner_name":       "Marcus T. Johnson",
        "sale_date":        date.today().isoformat(),
        "docket_text":      "",
    }

    result = process_property(test_prop)
    print(f"\nTest Result:")
    print(f"  Third party:  {result['is_third_party']}")
    print(f"  Gross surplus: ${result.get('gross_surplus', 0):,.0f}")
    print(f"  Net surplus:  ${result.get('net_surplus', 0):,.0f}")
    print(f"  Claim status: {result.get('claim_status')}")
    print(f"  Score:        {result.get('score')}/100")
    print(f"  Grade:        {result.get('grade')}")
    print(f"  Outreach:     {result.get('outreach_ready')}")
