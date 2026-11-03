"""Check the patent-applicant parser on saved Google Patents pages.

    python check.py <repo> <page cache dir>

The cache is the one evals/patent_family_v1/families.py fills (one HTML file
per publication number). For every readable page this parses the header block
with academic_agent.patent_applicants, using only the first MAX_BYTES as
production does, and compares the original assignees it finds with the page's
independent <meta name="DC.contributor" scheme="assignee"> tags, and the
inventors with the scheme="inventor" tags. It also reports how many pages
yield a company name, an inventor-owned patent, or nothing. No request is made.
"""
import html as html_lib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT / "src")]
from academic_agent import patent_applicants  # noqa: E402

_META = {scheme: re.compile(rf'<meta name="DC\.contributor" content="([^"]*)" scheme="{scheme}"')
         for scheme in ("assignee", "inventor")}

pages = [p.read_text(encoding="utf-8") for p in sorted(Path(sys.argv[2]).glob("*.html"))]
pages = [page for page in pages if not page.startswith("\0")]
statuses = Counter()
agreement = Counter()
inventor_agreement = Counter()
differs = []
current_differs = 0
for page in pages:
    head = page.encode("utf-8")[:patent_applicants.MAX_BYTES].decode("utf-8", errors="ignore")
    found = patent_applicants.assignees_from_html(head)
    names, status = patent_applicants.applicants(head)
    statuses[status] += 1
    meta = list(dict.fromkeys(" ".join(html_lib.unescape(m).split()) for m in _META["assignee"].findall(page)))
    inventors = list(dict.fromkeys(" ".join(html_lib.unescape(m).split()) for m in _META["inventor"].findall(page)))
    inventor_agreement["agree" if sorted(inventors) == sorted(found["inventors"]) else "differ"] += 1
    if not meta:
        agreement["no meta"] += 1
    elif sorted(meta) == sorted(found["original"]):
        agreement["agree"] += 1
    else:
        agreement["differ"] += 1
        differs.append({"meta": meta, "parsed": found["original"]})
    current_differs += bool(found["current"]) and sorted(found["current"]) != sorted(found["original"])

print(json.dumps({
    "pages": len(pages),
    "status": dict(statuses),
    "original_vs_meta": dict(agreement),
    "inventors_vs_meta": dict(inventor_agreement),
    "current_differs_from_original": current_differs,
    "differences": differs[:10],
}, ensure_ascii=False, indent=1))
