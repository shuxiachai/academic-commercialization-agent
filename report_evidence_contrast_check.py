"""Print the bounded offline PCQ preparation or its allowlisted review view."""

import argparse
import json

from academic_agent.report_evidence_claim_contrast import load_draft, project_review_input, rehearse


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline scripted PCQ claim-contrast preparation.")
    parser.add_argument("--review-input", action="store_true", help="Print only the detached blind-review projection.")
    args = parser.parse_args()
    draft = load_draft()
    output = project_review_input(draft.cases) if args.review_input else rehearse(draft.cases)
    print(json.dumps(output, ensure_ascii=True, sort_keys=True))
    return 0 if args.review_input or output["mechanical_passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
