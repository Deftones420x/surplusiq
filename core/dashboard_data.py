"""
SurplusIQ — Dashboard Data Exporter (v5 — bug fixes from live deploy)

v5 fixes:
  Bug 1 (KPI cards show apparent surplus, not refined):
    • summary_payload.total_surplus now reflects best_real_surplus (was: gross_surplus)
    • summary_payload.top_5_leads is now recomputed using best_real_surplus
    • Original apparent surplus preserved as total_apparent_surplus

  Bug 2 (Wilmington Trust mislabeled DOCKET despite Miami-Dade reCAPTCHA block):
    • _compute_best_real_surplus now requires classification ∈ {green, yellow, red, killed}
    • "unknown" classification no longer triggers docket source
      (it indicates the scrape ran but produced no data, not docket-verified)

Generates two JSON files that the dashboard HTML reads:
  docs/data/leads.json      — all qualifying leads, enriched with PR + docket data
  docs/data/summary.json    — county totals, score distribution, KPIs

Priority for best_real_surplus:
  1. Docket-verified (classification in {green/yellow/red/killed} AND true_surplus set)  → "docket"
  2. PropertyRadar enriched (pr_match=True AND real_surplus_estimate)                    → "propertyradar"
  3. Apparent surplus (auction-only fallback)                                            → "apparent"

Usage:
    python -m core.dashboard_data
"""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

from core.loader import load_all_leads, get_summary, PROJECT_ROOT


# Classifications that count as "docket-verified" — explicit allowlist.
# "unknown" is excluded because it means the scrape ran but produced no usable data.
DOCKET_VERIFIED_CLASSIFICATIONS = {"green", "yellow", "red", "killed"}


def _load_pr_enrichment() -> dict:
    """Load the most recent PropertyRadar enrichment file."""
    enriched_dir = PROJECT_ROOT / "data" / "enriched"
    if not enriched_dir.exists():
        return {}

    files = sorted(enriched_dir.glob("all_enriched_*.json"))
    if not files:
        return {}

    latest = files[-1]
    print(f"   📡 PropertyRadar enrichment: loading {latest.name}")

    try:
        with open(latest) as f:
            records = json.load(f)
    except Exception as e:
        print(f"   ⚠ Failed to load PR enrichment: {e}")
        return {}

    lookup = {}
    matched = 0
    for r in records:
        key = (r.get("county_id", ""), r.get("case_number", ""))
        lookup[key] = r
        if r.get("pr_match"):
            matched += 1

    print(f"   ✓ {len(lookup)} PR enrichment records ({matched} matched)")
    return lookup


def _apply_pr_to_payload(payload_lead: dict, pr_record: dict) -> dict:
    """Merge PropertyRadar enrichment fields onto a payload lead dict."""
    if not pr_record or not pr_record.get("pr_match"):
        return payload_lead

    pr_fields = [
        "pr_match", "pr_radar_id", "pr_owner_name",
        "pr_mailing_address", "pr_mailing_city", "pr_mailing_state", "pr_mailing_zip",
        "pr_estimated_value", "pr_total_loan_balance", "pr_available_equity",
        "pr_first_loan_amount", "pr_first_loan_type", "pr_second_loan_amount",
        "pr_years_owned", "pr_owner_occupied", "pr_in_tax_delinquency",
        "pr_involuntary_lien", "pr_property_type", "pr_year_built",
        "pr_sqft", "pr_bedrooms", "pr_bathrooms",
        "real_surplus_estimate", "debt_coverage_ratio", "is_clean_surplus",
        "enrichment_status",
    ]
    for field in pr_fields:
        if field in pr_record:
            payload_lead[field] = pr_record[field]

    return payload_lead


def _compute_best_real_surplus(payload_lead: dict) -> tuple:
    """
    Pick best available "real surplus" estimate and tag its source.

    v5: docket source requires classification ∈ {green, yellow, red, killed}.
    "unknown" classification is excluded — means scrape ran but no data extracted.
    """
    # Source 1: docket-verified — only if classification is in the explicit allowlist
    classification = (payload_lead.get("classification") or "").strip().lower()
    if classification in DOCKET_VERIFIED_CLASSIFICATIONS:
        docket_true_surplus = payload_lead.get("true_surplus", 0.0)
        if docket_true_surplus is not None:
            return (float(docket_true_surplus), "docket")

    # Source 2: PropertyRadar enrichment
    pr_real_surplus = payload_lead.get("real_surplus_estimate")
    if pr_real_surplus is not None and payload_lead.get("pr_match"):
        return (float(pr_real_surplus), "propertyradar")

    # Source 3: apparent surplus fallback
    apparent = payload_lead.get("gross_surplus", 0.0)
    return (float(apparent), "apparent")


def export_dashboard_data():
    docs_data = PROJECT_ROOT / "docs" / "data"
    docs_data.mkdir(parents=True, exist_ok=True)

    print("📊 Loading leads...")
    leads = load_all_leads()
    summary = get_summary(leads)
    print(f"   ✓ {len(leads)} leads loaded")
    print(f"   ✓ ${summary['total_surplus']:,.0f} apparent surplus (pre-enrichment)")

    pr_lookup = _load_pr_enrichment()

    leads_payload = []
    pr_matches = 0
    docket_matches = 0
    total_real_surplus = 0.0

    for l in leads:
        payload = {
            "county_id":        l.county_id,
            "county_name":      l.county_name,
            "state":            l.state,
            "case_number":      l.case_number,
            "address":          l.address,
            "parcel_id":        l.parcel_id,
            "auction_type":     l.auction_type,
            "opening_bid":      l.opening_bid,
            "final_sale_price": l.final_sale_price,
            "gross_surplus":    l.gross_surplus,
            "assessed_value":   l.assessed_value,
            "sale_date":        l.sale_date,
            "sale_datetime":    getattr(l, "sale_datetime", ""),
            "sold_to":          l.sold_to,
            "auction_status":   l.auction_status,
            "score":            l.score,
            "source_url":       getattr(l, "source_url", ""),

            # Docket-enrichment fields
            "classification":         getattr(l, "classification", ""),
            "classification_reason":  getattr(l, "classification_reason", ""),
            "prayer_amount":          getattr(l, "prayer_amount", 0.0),
            "true_surplus":           getattr(l, "true_surplus", 0.0),
            "kill_signals":           getattr(l, "kill_signals", []),
            "proof_of_surplus":       getattr(l, "proof_of_surplus", ""),
            "competing_filers":       getattr(l, "competing_filers", []),
            "additional_parties":     getattr(l, "additional_parties", []),
            "docket_url":             getattr(l, "docket_url", ""),

            "pr_match": False,
        }

        pr_record = pr_lookup.get((l.county_id, l.case_number))
        if pr_record:
            _apply_pr_to_payload(payload, pr_record)
            if payload.get("pr_match"):
                pr_matches += 1

        # v5: only count as docket match if classification is in the allowlist
        if (payload.get("classification") or "").strip().lower() in DOCKET_VERIFIED_CLASSIFICATIONS:
            docket_matches += 1

        best_real, source = _compute_best_real_surplus(payload)
        payload["best_real_surplus"]  = best_real
        payload["real_surplus_source"] = source
        total_real_surplus += best_real

        leads_payload.append(payload)

    leads_file = docs_data / "leads.json"
    with open(leads_file, "w") as f:
        json.dump(leads_payload, f, indent=2)
    print(f"   ✓ Wrote {leads_file.relative_to(PROJECT_ROOT)}")
    print(f"   ✓ Enrichment coverage: {pr_matches} PR / {docket_matches} docket / {len(leads_payload)} total")
    print(f"   ✓ Total real surplus (best available): ${total_real_surplus:,.0f}")

    # v5 Bug 1 fix: rebuild top_5_leads using best_real_surplus, not gross_surplus
    sorted_by_real = sorted(
        leads_payload,
        key=lambda p: p.get("best_real_surplus", 0),
        reverse=True,
    )
    top_5_leads_real = []
    for p in sorted_by_real[:5]:
        top_5_leads_real.append({
            "county":      p.get("county_name", ""),
            "state":       p.get("state", ""),
            "case_number": p.get("case_number", ""),
            "address":     p.get("address", ""),
            "surplus":     p.get("best_real_surplus", 0),
            "apparent":    p.get("gross_surplus", 0),
            "source":      p.get("real_surplus_source", "apparent"),
        })

    summary_file = docs_data / "summary.json"
    summary_payload = {
        "generated_at":           summary["generated_at"],
        "total_leads":            summary["total_leads"],

        # v5 Bug 1 fix: total_surplus headline number is now refined, not apparent
        "total_surplus":          total_real_surplus,
        "total_apparent_surplus": summary["total_surplus"],

        "total_real_surplus":     total_real_surplus,
        "pr_matched_count":       pr_matches,
        "docket_matched_count":   docket_matches,

        "by_state":  summary["by_state"],
        "by_county": summary["by_county"],
        "by_score":  summary["by_score"],

        # v5 Bug 1 fix: top_5_leads now sorted by best_real_surplus
        "top_5_leads": top_5_leads_real,

        "coverage": {
            "states":   ["FL", "OH"],
            "counties": [
                {"id": "miami-dade-fl", "name": "Miami-Dade", "state": "FL"},
                {"id": "broward-fl",    "name": "Broward",    "state": "FL"},
                {"id": "duval-fl",      "name": "Duval",      "state": "FL"},
                {"id": "lee-fl",        "name": "Lee",        "state": "FL"},
                {"id": "orange-fl",     "name": "Orange",     "state": "FL"},
                {"id": "cuyahoga-oh",   "name": "Cuyahoga",   "state": "OH"},
                {"id": "franklin-oh",   "name": "Franklin",   "state": "OH"},
                {"id": "montgomery-oh", "name": "Montgomery", "state": "OH"},
                {"id": "summit-oh",     "name": "Summit",     "state": "OH"},
                {"id": "hamilton-oh",   "name": "Hamilton",   "state": "OH"},
            ],
        },
    }

    with open(summary_file, "w") as f:
        json.dump(summary_payload, f, indent=2)
    print(f"   ✓ Wrote {summary_file.relative_to(PROJECT_ROOT)}")
    print(f"   ✓ Headline KPI total_surplus = ${total_real_surplus:,.0f} (was apparent ${summary['total_surplus']:,.0f})")
    if top_5_leads_real:
        top = top_5_leads_real[0]
        print(f"   ✓ Top lead = ${top['surplus']:,.0f} | {top['county']}, {top['state']} | {top['case_number']}")

    return leads_file, summary_file


if __name__ == "__main__":
    leads_file, summary_file = export_dashboard_data()
    print()
    print("=" * 70)
    print("  ✓ Dashboard data export complete")
    print(f"  📁 {leads_file}")
    print(f"  📁 {summary_file}")
    print("=" * 70)
