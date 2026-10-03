#!/usr/bin/env python3
"""Verify every acquisition ROI calculator against the one pricing model.

Why this exists
---------------
The calculator on each ``/acquisition/[niche]/`` page is not generated. A new
niche page is cloned from an existing one by hand, so nothing connects a page's
numbers to the model they are supposed to come from. On 2026-10-03 that cost us
twice in one morning: ``TARGET_SHARE`` had to be corrected across 26 files, and
every page except home care turned out to be shipping an identical set of static
result values inherited from whatever page it was cloned from, so roofing and pet
waste removal both claimed a $150 fee and 10.3x ROI despite a $15,000 ticket
against a $180 one. Both were found by reading, not by any check.

This makes the model enforceable. It is the deploy-time guard for the invariant
documented in the vault at ``MIA/Website/Niche ROI Calculator - Live Model`` and
``MIA Acquisition/Strategy/09 - Niche Calculator Inputs & Model``.

What it checks
--------------
1. **Shared constants.** ``SAFETY`` is 0.75 and ``TARGET_SHARE`` is 0.22 on every
   page. The 22% share is what resolves home care to the $150 per qualified
   consultation actually contracted with Purecare LLC.
2. **The invariant.** Everything downstream of the guarantee runs on the
   guaranteed count: ``closed`` and ``totalFee`` must both read ``guaranteed``,
   never ``rawLeads``. This keeps the cost side and the revenue side of a page on
   one volume, and keeps every projection a prospect sees at or below the single
   number we put in writing.
3. **The cost-per-lead row** matches the page's own ``CPL`` constant.
4. **The static fallback values** in the result rows match what the page's own
   script computes at its own defaults. These are what ships in the HTML before
   JavaScript runs and what anyone reading the page source sees, and they are the
   values a clone silently inherits.

Usage
-----
    python3 tools/verify-calculators.py          # check, exit 1 on any failure
    python3 tools/verify-calculators.py --fix    # rewrite the stale fallbacks

Only the fallback values are auto-fixable. A wrong constant or a broken invariant
is a code change someone has to make deliberately, so ``--fix`` reports those and
still exits non-zero.
"""

import argparse
import glob
import math
import os
import re
import sys
from decimal import Decimal, ROUND_HALF_UP

EXPECTED_SAFETY = 0.75
EXPECTED_TARGET_SHARE = 0.22

# The niches index runs the same chain off a selector; it opens on roofing.
NICHES_INDEX = "acquisition/niches/index.html"
NICHES_INDEX_DEFAULTS = {"budget": 1500.0, "slug": "roofing"}

RE_DEFAULTS = re.compile(
    r"var DEFAULTS = \{ budget: ([\d.]+), ticket: ([\d.]+), close: ([\d.]+) \};")
RE_CONSTS = re.compile(
    r"var CPL = ([\d.]+), MARGIN = ([\d.]+), SAFETY = ([\d.]+), TARGET_SHARE = ([\d.]+);")
RE_INDEX_CONSTS = re.compile(r"var SAFETY = ([\d.]+), TARGET_SHARE = ([\d.]+);")
RE_CPL_ROW = re.compile(r"<span[^>]*>Cost per lead[^<]*</span><strong>\$(\d+)</strong>")


def js_round(n):
    """JavaScript Math.round: halves go up, toward positive infinity."""
    return math.floor(n + 0.5)


def money(n):
    return "$" + f"{js_round(n):,}"


def to_fixed_1(n):
    """JavaScript Number.toFixed(1)."""
    return str(Decimal(repr(n)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def project(budget, ticket, close_rate, cpl, margin, safety, target_share):
    """The unified formula chain from 09, in the order the page runs it."""
    raw_leads = budget / cpl
    guaranteed = max(0, math.floor(raw_leads * safety))
    closed = guaranteed * close_rate
    ppa = math.ceil(ticket * margin * close_rate * target_share / 5) * 5
    total_monthly = budget + ppa * guaranteed
    annual_cost = total_monthly * 12
    annual_revenue = closed * 12 * ticket
    net_profit = annual_revenue - annual_cost
    return {
        "calcRawLeads": str(math.floor(raw_leads)),
        "calcClosed": to_fixed_1(closed),
        "calcCAC": money(total_monthly / closed) if closed > 0 else "—",
        "calcRevenue": money(annual_revenue),
        "calcFee": money(ppa),
        "calcTotalCost": money(total_monthly),
        "calcProfit": money(net_profit),
        "calcROI": to_fixed_1(net_profit / annual_cost if annual_cost > 0 else 0) + "x",
        "calcGuarantee": str(guaranteed),
    }


def read_element(html, element_id):
    m = re.search(r'id="' + element_id + r'"[^>]*>([^<]*)<', html)
    return m.group(1) if m else None


def write_element(html, element_id, value):
    pattern = re.compile(r'(id="' + element_id + r'"[^>]*>)([^<]*)(</)')
    return pattern.sub(lambda m: m.group(1) + value + m.group(3), html, count=1)


def roofing_inputs(html):
    """Pull the niches index's opening selection out of its NICHES array."""
    m = re.search(r'\{ slug: "' + NICHES_INDEX_DEFAULTS["slug"] + r'",[^}]*\}', html)
    if not m:
        return None
    entry = m.group(0)
    def field(name):
        f = re.search(name + r": ([\d.]+)", entry)
        return float(f.group(1)) if f else None
    return field("ticket"), field("cpl"), field("margin"), field("close")


def check_page(path, html):
    """Return (failures, fixes) for one page. A fix is (element_id, found, want)."""
    failures, fixes = [], []
    is_index = path.endswith(NICHES_INDEX)

    if is_index:
        consts = RE_INDEX_CONSTS.search(html)
        if not consts:
            return ["cannot read SAFETY / TARGET_SHARE"], []
        safety, target_share = float(consts.group(1)), float(consts.group(2))
        inputs = roofing_inputs(html)
        if not inputs:
            return ["cannot read the roofing entry from the NICHES array"], []
        ticket, cpl, margin, close = inputs
        budget, close_rate = NICHES_INDEX_DEFAULTS["budget"], close / 100
    else:
        defaults, consts = RE_DEFAULTS.search(html), RE_CONSTS.search(html)
        if not (defaults and consts):
            return ["cannot read DEFAULTS / constants"], []
        budget, ticket = float(defaults.group(1)), float(defaults.group(2))
        close_rate = float(defaults.group(3)) / 100
        cpl, margin = float(consts.group(1)), float(consts.group(2))
        safety, target_share = float(consts.group(3)), float(consts.group(4))

        cpl_row = RE_CPL_ROW.search(html)
        if not cpl_row:
            failures.append("no cost-per-lead row")
        elif int(cpl_row.group(1)) != int(cpl):
            failures.append(
                f"cost-per-lead row says ${cpl_row.group(1)}, CPL is ${int(cpl)}")

    if safety != EXPECTED_SAFETY:
        failures.append(f"SAFETY is {safety}, expected {EXPECTED_SAFETY}")
    if target_share != EXPECTED_TARGET_SHARE:
        failures.append(
            f"TARGET_SHARE is {target_share}, expected {EXPECTED_TARGET_SHARE}")

    if "var closed = guaranteed * closeRate;" not in html:
        failures.append("invariant: closed does not run off guaranteed")
    if "var totalFee = ppa * guaranteed;" not in html:
        failures.append("invariant: totalFee does not run off guaranteed")

    for element_id, want in project(
            budget, ticket, close_rate, cpl, margin, safety, target_share).items():
        found = read_element(html, element_id)
        if found is None:
            failures.append(f"missing element {element_id}")
        elif found != want:
            fixes.append((element_id, found, want))

    return failures, fixes


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--fix", action="store_true",
                        help="rewrite stale fallback values in place")
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)

    pages = sorted(p for p in glob.glob("acquisition/*/index.html")
                   if "TARGET_SHARE" in open(p).read())
    if not pages:
        print("no calculator pages found", file=sys.stderr)
        return 1

    broken, stale, fixed = 0, 0, 0
    for path in pages:
        html = open(path).read()
        failures, fixes = check_page(path, html)
        name = path.split("/")[1]

        for failure in failures:
            print(f"FAIL  {name}: {failure}")
        if failures:
            broken += 1

        if fixes:
            verb = "fixed" if args.fix else "STALE"
            for element_id, found, want in fixes:
                print(f"{verb} {name}: {element_id} {found} -> {want}")
            if args.fix:
                for element_id, _, want in fixes:
                    html = write_element(html, element_id, want)
                open(path, "w").write(html)
                fixed += 1
            else:
                stale += 1

    print(f"\n{len(pages)} calculators checked, {broken} with errors, "
          f"{fixed if args.fix else stale} with stale fallback values"
          f"{' (rewritten)' if args.fix else ''}")

    if broken:
        return 1
    if stale and not args.fix:
        print("run with --fix to recompute the stale values")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
