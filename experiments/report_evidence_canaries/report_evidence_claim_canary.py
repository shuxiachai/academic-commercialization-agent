"""Verify committed CLQ identity by default; only the parent may dispatch live."""

import argparse
import json

from academic_agent.report_evidence_claim_qwen_canary import (
    CanaryStopped, PROTOCOL_IDENTITY, run_canary, verify_identity,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's original message can contain a credential supplied by mistake.
        self.exit(2, "invalid_claim_canary_arguments\n")


def main(argv=None) -> int:
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-fixture-sha256", required=True)
    parser.add_argument("--authorize-paid", help="Exact CLQ acknowledgement; not independent consent verification.")
    args = parser.parse_args(argv)
    try:
        if args.authorize_paid is None:
            identity = verify_identity(args.expected_commit, args.expected_fixture_sha256)
            print(json.dumps({"mode": "identity_only", "identity_verified": True,
                              "live_authorized": False, "identity": identity}, ensure_ascii=True))
            return 0
        if args.authorize_paid != PROTOCOL_IDENTITY:
            raise CanaryStopped("fresh_protocol_acknowledgement_required")
        result = run_canary(expected_commit=args.expected_commit,
                            expected_fixture_sha256=args.expected_fixture_sha256,
                            authorize_paid=args.authorize_paid)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0 if (result["mechanical_passed"] and result["label_match_passed"] is True
                     and result["summary_persisted"]) else 1
    except CanaryStopped:
        # Even a nominally code-owned exception may originate in an imported
        # dependency. Do not print exception strings or arbitrary argv values.
        error = "claim_canary_admission_or_persistence_failed"
    except Exception:  # noqa: BLE001 -- setup/path/provider diagnostics must never expose credentials.
        error = "claim_canary_setup_failed"
    print(json.dumps({"mechanical_passed": False, "label_match_passed": None,
                      "semantic_review": "not_reviewable", "error": error}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
