"""
SurplusIQ — County Configuration
All 10 Phase 1 counties with auction + clerk portal URLs
"""

COUNTIES = [

    # ─── FLORIDA ───────────────────────────────────────────────────
    {
        "id":           "miami-dade-fl",
        "name":         "Miami-Dade",
        "state":        "FL",
        "state_full":   "Florida",
        "auction_url":  "https://miami-dade.realforeclose.com",
        "auction_results_path": "/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID=",
        "clerk_url":    "https://www2.miami-dadeclerk.com/ocs",
        "clerk_search": "https://www2.miami-dadeclerk.com/ocs/Search.aspx",
        "clerk_type":   "oscar",          # Miami-Dade uses OSCAR system
        "tax_deed_url": "https://www.miamidade.gov/taxcollector/",
        "doc_timing_days": 14,            # Miami-Dade can take 10-14 days
        "has_captcha":  False,
        "lead_types":   ["Mortgage Foreclosure", "Tax Deed"],
        "notes":        "High volume. OSCAR docket system for case search.",
    },
    {
        "id":           "broward-fl",
        "name":         "Broward",
        "state":        "FL",
        "state_full":   "Florida",
        "auction_url":  "https://broward.realforeclose.com",
        "auction_results_path": "/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID=",
        "clerk_url":    "https://www.browardclerk.org/Web2",
        "clerk_search": "https://www.browardclerk.org/Web2/CaseSearchECA/Search",
        "clerk_type":   "broward_portal",
        "tax_deed_url": "https://www.broward.org/RecordsTaxesTreasury/TaxDeeds",
        "doc_timing_days": 7,
        "has_captcha":  False,
        "lead_types":   ["Mortgage Foreclosure", "Tax Deed"],
        "notes":        "Broward Clerk Web2 portal for docket search.",
    },
    {
        "id":           "duval-fl",
        "name":         "Duval",
        "state":        "FL",
        "state_full":   "Florida",
        "auction_url":  "https://duval.realforeclose.com",
        "auction_results_path": "/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID=",
        "clerk_url":    "https://core.duvalclerk.com",
        "clerk_search": "https://core.duvalclerk.com/CoreCivil/CaseSearch",
        "clerk_type":   "core_duval",     # CORE portal
        "tax_deed_url": "https://core.duvalclerk.com/CoreCivil/CaseSearch",
        "doc_timing_days": 5,
        "has_captcha":  False,
        "lead_types":   ["Mortgage Foreclosure", "Tax Deed"],
        "notes":        "Uses CORE portal. duval.realforeclose.com confirmed by clerk site.",
    },
    {
        "id":           "lee-fl",
        "name":         "Lee",
        "state":        "FL",
        "state_full":   "Florida",
        "auction_url":  "https://lee.realforeclose.com",
        "auction_results_path": "/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID=",
        "clerk_url":    "https://www.leeclerk.org/courts/civil-courts/civil-case-search",
        "clerk_search": "https://efiling.leeclerk.org/CourtRecords/Search",
        "clerk_type":   "lee_portal",
        "tax_deed_url": "https://www.leepa.org/",
        "doc_timing_days": 7,
        "has_captcha":  True,             # Eric flagged 2-3 counties with CAPTCHA
        "lead_types":   ["Mortgage Foreclosure", "Tax Deed"],
        "notes":        "May have CAPTCHA on clerk search. Use Playwright pause loop.",
    },
    {
        "id":           "orange-fl",
        "name":         "Orange",
        "state":        "FL",
        "state_full":   "Florida",
        "auction_url":  "https://orange.realforeclose.com",
        "auction_results_path": "/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID=",
        "clerk_url":    "https://myeclerk.myorangeclerk.com",
        "clerk_search": "https://myeclerk.myorangeclerk.com/Cases/Search",
        "clerk_type":   "orange_eclerk",
        "tax_deed_url": "https://www.occompt.com/taxdeeds",
        "doc_timing_days": 2,             # Orange posts within 2 days per Eric
        "has_captcha":  False,
        "lead_types":   ["Mortgage Foreclosure", "Tax Deed"],
        "notes":        "Orange County posts docs fast — 2 days. High priority for doc checks.",
    },

    # ─── OHIO ───────────────────────────────────────────────────────
    {
        "id":           "cuyahoga-oh",
        "name":         "Cuyahoga",
        "state":        "OH",
        "state_full":   "Ohio",
        "auction_url":  "https://cuyahoga.realforeclose.com",
        "auction_results_path": "/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID=",
        "clerk_url":    "https://cpdocket.cp.cuyahogacounty.us",
        "clerk_search": "https://cpdocket.cp.cuyahogacounty.us/Search.aspx",
        "clerk_type":   "cuyahoga_docket",
        "tax_deed_url": "https://fiscalofficer.cuyahogacounty.gov/en-US/FiscalOfficer/TaxForeclosure",
        "doc_timing_days": 10,
        "has_captcha":  True,             # Eric flagged some OH counties with CAPTCHA
        "lead_types":   ["Mortgage Foreclosure"],
        "notes":        "Cuyahoga CP docket system. Born there — great county for surplus.",
    },
    {
        "id":           "franklin-oh",
        "name":         "Franklin",
        "state":        "OH",
        "state_full":   "Ohio",
        "auction_url":  "https://franklin.realforeclose.com",
        "auction_results_path": "/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID=",
        "clerk_url":    "https://fcdcfcjs.co.franklin.oh.us/CaseInformationOnline",
        "clerk_search": "https://fcdcfcjs.co.franklin.oh.us/CaseInformationOnline/caseSearch",
        "clerk_type":   "franklin_fcjs",
        "tax_deed_url": "https://www.franklincountyauditor.com",
        "doc_timing_days": 10,
        "has_captcha":  False,
        "lead_types":   ["Mortgage Foreclosure"],
        "notes":        "Franklin County Clerk FCJS system. Columbus area — high volume.",
    },
    {
        "id":           "montgomery-oh",
        "name":         "Montgomery",
        "state":        "OH",
        "state_full":   "Ohio",
        "auction_url":  "https://montgomery.realforeclose.com",
        "auction_results_path": "/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID=",
        "clerk_url":    "https://www.mcohio.org/government/elected_officials/clerk_of_courts/civil_division/case_search.php",
        "clerk_search": "https://www.mcohio.org/government/elected_officials/clerk_of_courts/civil_division/case_search.php",
        "clerk_type":   "montgomery_clerk",
        "tax_deed_url": "https://www.mcohio.org",
        "doc_timing_days": 10,
        "has_captcha":  False,
        "lead_types":   ["Mortgage Foreclosure"],
        "notes":        "Dayton area. Montgomery County Clerk civil division.",
    },
    {
        "id":           "summit-oh",
        "name":         "Summit",
        "state":        "OH",
        "state_full":   "Ohio",
        "auction_url":  "https://summit.realforeclose.com",
        "auction_results_path": "/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID=",
        "clerk_url":    "https://www.summitcountyclerk.com",
        "clerk_search": "https://www.summitcountyclerk.com/civil-case-search",
        "clerk_type":   "summit_clerk",
        "tax_deed_url": "https://www.summitcountyohio.us/fiscal",
        "doc_timing_days": 10,
        "has_captcha":  False,
        "lead_types":   ["Mortgage Foreclosure"],
        "notes":        "Akron area. Summit County Clerk portal.",
    },
    {
        "id":           "hamilton-oh",
        "name":         "Hamilton",
        "state":        "OH",
        "state_full":   "Ohio",
        "auction_url":  "https://hamilton.realforeclose.com",
        "auction_results_path": "/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDAYID=",
        "clerk_url":    "https://courtclerk.org",
        "clerk_search": "https://courtclerk.org/records-search",
        "clerk_type":   "hamilton_clerk",
        "tax_deed_url": "https://www.hamiltoncountyauditor.org",
        "doc_timing_days": 10,
        "has_captcha":  True,             # Eric flagged 2-3 OH counties
        "lead_types":   ["Mortgage Foreclosure"],
        "notes":        "Cincinnati area. courtclerk.org — may have CAPTCHA.",
    },
]

# Quick lookup by ID
COUNTY_MAP = {c["id"]: c for c in COUNTIES}

# FL only
FL_COUNTIES = [c for c in COUNTIES if c["state"] == "FL"]

# OH only
OH_COUNTIES = [c for c in COUNTIES if c["state"] == "OH"]

# Counties with CAPTCHA (need Playwright pause loop)
CAPTCHA_COUNTIES = [c["id"] for c in COUNTIES if c["has_captcha"]]

if __name__ == "__main__":
    print(f"Total counties: {len(COUNTIES)}")
    print(f"Florida: {len(FL_COUNTIES)}")
    print(f"Ohio: {len(OH_COUNTIES)}")
    print(f"CAPTCHA counties: {CAPTCHA_COUNTIES}")
    for c in COUNTIES:
        print(f"  [{c['state']}] {c['name']:15} auction: {c['auction_url']}")
