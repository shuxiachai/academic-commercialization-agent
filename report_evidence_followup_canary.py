"""Explicitly authorized synthetic-only canary CLI; never a production endpoint."""

import argparse
import json
import os
from pathlib import Path

from academic_agent.report_evidence_qwen_canary import CanaryStopped, ROOT, run_canary, verify_identity
from academic_agent.report_evidence_qwen_transport import validate_key


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "invalid_canary_arguments\n")


def main(argv=None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--key-from-dotenv", action="store_true", help="Explicitly read only DASHSCOPE_API_KEY from .env.")
    args = parser.parse_args(argv)
    try:
        manifest = verify_identity(args.expected_commit)
        output = Path(args.output_dir).resolve()
        output.relative_to((ROOT / "outputs").resolve())
        key = os.environ.get("DASHSCOPE_API_KEY")
        if args.key_from_dotenv:
            from dotenv import dotenv_values

            key = dotenv_values(ROOT / ".env", interpolate=False).get("DASHSCOPE_API_KEY")
        validate_key(key)
        result = run_canary(api_key=key, output_dir=output, manifest=manifest)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0 if result["passed"] else 1
    except CanaryStopped as exc:
        print(json.dumps({"passed": False, "error": str(exc)}))
    except Exception:  # noqa: BLE001 -- CLI failures must not print paths, credentials or exception chains.
        print(json.dumps({"passed": False, "error": "canary_setup_or_persistence_failed"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
