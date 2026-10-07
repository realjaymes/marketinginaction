#!/usr/bin/env python3
"""Fail the deploy on known template wording errors in the published pages.

Why this exists
---------------
Acquisition niche pages are cloned from one another by hand, and the clone step
pluralises the niche noun mechanically. That shipped "companys" and "businesss"
into body copy, meta descriptions and Service schema on nine pages, and gave 19
pages the title "More Booked Qualifieds", a placeholder noun that never got
replaced. An SEO audit found them, not a check. Any new niche cloned from one of
those pages would have copied the errors, so this blocks them at deploy.

What it checks
--------------
Every ``index.html`` in the repo for the patterns in ``BANNED``, case-insensitive.
Add a pattern here when a new template error is found, with the fix it needs.

Run it locally before pushing::

    python3 tools/check-wording.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

BANNED = {
    r"\bqualifieds\b": "placeholder title noun; name what gets booked (Estimates, Appointments, Jobs)",
    r"\b\w*companys\b": "plural of company is companies",
    r"\b\w*businesss\b": "plural of business is businesses",
    r"\b\w*agencys\b": "plural of agency is agencies",
}


def main() -> int:
    failures = []
    for page in sorted(ROOT.rglob("index.html")):
        if ".git" in page.parts or "node_modules" in page.parts:
            continue
        for lineno, line in enumerate(page.read_text(errors="ignore").splitlines(), 1):
            for pattern, fix in BANNED.items():
                for m in re.finditer(pattern, line, re.IGNORECASE):
                    failures.append(f"{page.relative_to(ROOT)}:{lineno}: '{m.group(0)}' ({fix})")
    if failures:
        print("Template wording errors found:\n" + "\n".join(failures))
        return 1
    print("Wording check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
