"""Verify committed CQ identity by default; the explicit live path is parent-only."""

import argparse
import json
from pathlib import Path

from academic_agent.report_evidence_catalog_qwen_canary import (
    CanaryStopped, PROTOCOL_IDENTITY, run_canary, verify_identity,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Do not echo unsupported arguments that might contain credentials.
        self.exit(2, "invalid_catalog_canary_arguments\n")


def main(argv=None) -> int:
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-fixture-sha256", required=True)
    parser.add_argument("--authorize-paid", help="Exact CQ acknowledgement; not independently verified consent.")
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)
    try:
        if args.authorize_paid is None:
            if args.output_dir is not None:
                raise CanaryStopped("output_requires_paid_mode")
            identity = verify_identity(args.expected_commit, args.expected_fixture_sha256)
            print(json.dumps({"mode": "identity_only", "identity_verified": True,
                              "live_authorized": False, "identity": identity}, ensure_ascii=True))
            return 0
        if args.authorize_paid != PROTOCOL_IDENTITY or args.output_dir is None:
            raise CanaryStopped("fresh_protocol_acknowledgement_and_output_required")
        result = run_canary(expected_commit=args.expected_commit,
                            expected_fixture_sha256=args.expected_fixture_sha256,
                            authorize_paid=args.authorize_paid, output_dir=Path(args.output_dir))
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0 if result["passed"] else 1
    except CanaryStopped as exc:
        print(json.dumps({"passed": False, "error": str(exc)}))
    except Exception:  # noqa: BLE001 -- raw setup/path/credential diagnostics must not escape.
        print(json.dumps({"passed": False, "error": "catalog_canary_setup_or_persistence_failed"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
