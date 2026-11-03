"""Verify committed RP identity by default; native dispatch belongs to the parent."""

import argparse
import json

from academic_agent.report_evidence_relation_policy_qwen_canary import (
    CanaryStopped, PROTOCOL_IDENTITY, run_canary, verify_identity,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Never echo a mistaken credential or arbitrary argument in diagnostics.
        self.exit(2, "invalid_relation_policy_canary_arguments\n")


def main(argv=None) -> int:
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-fixture-sha256", required=True)
    parser.add_argument("--authorize-paid", help="Exact RP protocol acknowledgement, not consent or CI verification.")
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
        return 0 if result["batch_passed"] is True and result["summary_persisted"] is True else 1
    except CanaryStopped:
        error = "relation_policy_canary_admission_or_persistence_failed"
    except Exception:  # noqa: BLE001 -- arbitrary setup/provider details must not escape through the CLI.
        error = "relation_policy_canary_setup_failed"
    print(json.dumps({"batch_passed": False, "mechanical_passed": False, "label_match_passed": None,
                      "semantic_review": "not_reviewable", "error": error}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
