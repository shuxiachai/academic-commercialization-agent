"""Verify RS identity by default; only the parent may acknowledge the live batch."""

import argparse
import json
from pathlib import Path

from academic_agent.report_evidence_real_saved_qwen_canary import (
    CanaryStopped, _encoded, _sha, run_canary, verify_identity,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "invalid_real_saved_canary_arguments\n")


def main(argv=None) -> int:
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--packet-dir", required=True)
    parser.add_argument("--authorize-paid", help="Exact new RS acknowledgement; not independent consent verification.")
    args = parser.parse_args(argv)
    try:
        if args.authorize_paid is None:
            identity = verify_identity(args.expected_commit, args.expected_manifest_sha256, Path(args.packet_dir))
            print(json.dumps({"mode": "identity_only", "identity_verified": True,
                              "live_authorized": False, "identity_sha256": _sha(_encoded(identity)),
                              "commit": identity["commit"],
                              "manifest_sha256": identity["packet"]["manifest_sha256"],
                              "configuration_sha256": identity["configuration_sha256"]}, ensure_ascii=True))
            return 0
        result = run_canary(expected_commit=args.expected_commit, expected_manifest_sha256=args.expected_manifest_sha256,
                            packet_dir=Path(args.packet_dir), authorize_paid=args.authorize_paid)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0 if result["passed"] else 1
    except CanaryStopped as exc:
        print(json.dumps({"passed": False, "error": str(exc)}))
    except Exception:  # noqa: BLE001 -- never echo a private argument, source or credential exception.
        print(json.dumps({"passed": False, "error": "real_saved_canary_setup_or_persistence_failed"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
