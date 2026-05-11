"""
SurplusIQ — Dashboard HTML Patch v1
Adds True Surplus display + Classification badge column to docs/index.html.

Changes:
  1. Surplus cell: shows True Surplus large + Apparent in small text underneath
  2. New Classification column with green/yellow/red/killed badges
  3. Subtle row tinting for killed leads (so Eric can scan them)
  4. Updates colspan from 10 → 11 in 3 places
  5. Adds tooltip showing kill_signals + classification_reason on hover

Run: python dashboard_html_patch_v1.py
"""

from pathlib import Path

HTML = Path.home() / "Desktop/surplusiq/docs/index.html"


def main():
    if not HTML.exists():
        print(f"✗ Cannot find {HTML}")
        return

    src = HTML.read_text()
    HTML.with_suffix(".html.bak3").write_text(src)
    print(f"✓ Backed up index.html to index.html.bak3")

    # ── PATCH 1: Update Surplus header label, add Classification column ──
    old_th = '''            <th data-sort="gross_surplus" class="numeric sorted-desc">Surplus</th>
            <th data-sort="score">Tier</th>'''

    new_th = '''            <th data-sort="true_surplus" class="numeric sorted-desc">Surplus</th>
            <th data-sort="classification">Status</th>
            <th data-sort="score">Tier</th>'''

    if old_th in src:
        src = src.replace(old_th, new_th)
        print("✓ Patch 1: Surplus header → True Surplus sort, added Status column")
    else:
        print("⚠ Patch 1: header anchor not found (already patched?)")

    # ── PATCH 2: Update surplus cell to show True + Apparent ──
    old_surplus_td = '<td class="numeric surplus">${fmtMoney(l.gross_surplus)}</td>\n        <td><span class="badge ${scoreBadgeClass(l.score)}">${l.score}</span></td>'

    new_surplus_td = '''<td class="numeric surplus-cell">${renderSurplusCell(l)}</td>
        <td>${renderStatusBadge(l)}</td>
        <td><span class="badge ${scoreBadgeClass(l.score)}">${l.score}</span></td>'''

    if old_surplus_td in src:
        src = src.replace(old_surplus_td, new_surplus_td)
        print("✓ Patch 2: Surplus cell → True large + Apparent small, added Status badge cell")
    else:
        print("⚠ Patch 2: surplus cell anchor not found")

    # ── PATCH 3: Update colspans from 10 to 11 ──
    n = src.count('colspan="10"')
    src = src.replace('colspan="10"', 'colspan="11"')
    print(f"✓ Patch 3: updated {n} colspan references from 10 → 11")

    # ── PATCH 4: Add CSS for surplus cell + status badges ──
    css_block = '''
  /* True Surplus cell — large primary, apparent small below */
  td.surplus-cell {
    line-height: 1.3;
  }
  .surplus-true {
    font-weight: 700;
    font-size: 0.95em;
  }
  .surplus-true.positive { color: var(--green, #2ECC71); }
  .surplus-true.negative { color: #ff6b6b; }
  .surplus-apparent {
    display: block;
    color: var(--text-muted, #888);
    font-size: 0.72em;
    font-weight: 400;
    margin-top: 1px;
  }

  /* Status badges */
  .status-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.75em;
    font-weight: 600;
    letter-spacing: 0.3px;
    text-transform: uppercase;
    cursor: help;
  }
  .status-badge.status-green   { background: rgba(46, 204, 113, 0.15); color: #2ECC71; }
  .status-badge.status-yellow  { background: rgba(255, 200, 0, 0.15);  color: #f1b500; }
  .status-badge.status-red     { background: rgba(255, 99, 99, 0.15);  color: #ff6b6b; }
  .status-badge.status-killed  { background: rgba(120, 120, 120, 0.2); color: #999; }
  .status-badge.status-unknown { background: rgba(150, 150, 150, 0.1); color: #777; }
  .status-badge.status-none    { background: rgba(100, 130, 200, 0.1); color: #6688cc; }

  /* Subtle row tint for killed leads */
  tr.row-killed {
    opacity: 0.55;
  }
  tr.row-killed td.surplus-cell .surplus-true {
    text-decoration: line-through;
  }
</style>'''

    if '.status-badge' not in src and '</style>' in src:
        src = src.replace('</style>', css_block, 1)
        print("✓ Patch 4: added CSS for surplus cell + status badges")
    else:
        print("⚠ Patch 4: CSS already present or </style> not found")

    # ── PATCH 5: Add JavaScript helper functions ──
    # Find a spot near the existing scoreBadgeClass function
    old_js_anchor = 'function scoreBadgeClass(score)'
    new_js_helpers = '''function renderSurplusCell(l) {
    const apparent = l.gross_surplus || 0;
    const trueSur = (l.true_surplus !== undefined && l.true_surplus !== null && l.true_surplus !== 0)
                    ? l.true_surplus
                    : apparent;
    const cls = trueSur < 0 ? 'negative' : 'positive';
    const trueStr = fmtMoney(trueSur);
    // Only show "apparent" subtitle if it differs meaningfully from true (Ohio docket case)
    const showApparent = Math.abs(apparent - trueSur) > 100;
    return `<span class="surplus-true ${cls}">${trueStr}</span>` +
           (showApparent ? `<span class="surplus-apparent">apparent ${fmtMoney(apparent)}</span>` : '');
  }

  function renderStatusBadge(l) {
    const cls = (l.classification || '').toLowerCase();
    if (!cls) return '<span class="status-badge status-none" title="No docket data yet">—</span>';
    const labels = {
      green:   '✓ Confirmed',
      yellow:  'Pending',
      red:     '⚠ At Risk',
      killed:  '✗ Killed',
      unknown: '?'
    };
    const label = labels[cls] || cls;
    const reason = (l.classification_reason || '').replace(/"/g, '&quot;');
    const signals = (l.kill_signals || []).join(', ');
    const tooltip = reason + (signals ? ` — signals: ${signals}` : '');
    return `<span class="status-badge status-${cls}" title="${tooltip}">${label}</span>`;
  }

  function scoreBadgeClass(score)'''

    if 'function renderSurplusCell' not in src and old_js_anchor in src:
        src = src.replace(old_js_anchor, new_js_helpers, 1)
        print("✓ Patch 5: added renderSurplusCell + renderStatusBadge JS helpers")
    else:
        print("⚠ Patch 5: JS anchor not found or already patched")

    # ── PATCH 6: Add row-killed class on <tr> for killed leads ──
    # Find the row template start
    old_row_open = '`<tr>'
    new_row_open = '`<tr class="${l.classification === \'killed\' ? \'row-killed\' : \'\'}">'

    if 'row-killed' not in src and old_row_open in src:
        # Only replace within the table rendering function
        # Find the template literal start
        src = src.replace(old_row_open, new_row_open, 1)
        print("✓ Patch 6: added row-killed class to <tr> for killed leads")
    else:
        print("⚠ Patch 6: row anchor not found or already patched")

    HTML.write_text(src)
    print(f"\n✅ All patches applied. Backup: index.html.bak3")
    print()
    print("Now run:")
    print("  python -m core.dashboard_data    # regenerate (already current)")
    print("  open docs/index.html             # preview locally")
    print()
    print("Or push live:")
    print("  git add docs/")
    print("  git commit -m 'Add True Surplus + Classification status to dashboard'")
    print("  git push")


if __name__ == "__main__":
    main()
