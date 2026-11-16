"""Part S: hand one arm's collected registries to the benchmark as its frozen evidence.

    uv run python <this branch>/evals/market_issuer_share_v1/freeze.py --arm-dir <dir>/old [--only V06]
    uv run python <this branch>/evals/market_issuer_share_v1/freeze.py --arm-dir <dir>/new [--only V06]

Run from the root of the checkout whose ``benchmark.py --fixtures`` will run
that arm. Each scored case's ``validated_sources.json`` is stored, byte for
byte, as that checkout's fixture for the case. ``--only`` names the cases the
protocol admits to Part S: those whose two registries differ. The fixture
files and the manifest entry are local to the experiment: do not commit them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--arm-dir", type=Path, required=True)
    parser.add_argument("--only", help="comma-separated case ids")
    args = parser.parse_args(argv)
    sys.path[:0] = [str(Path.cwd())]
    import benchmark
    import benchmark_fixtures

    wanted = set(args.only.split(",")) if args.only else None
    cases = json.loads(Path(__file__).with_name("cases.json").read_text(encoding="utf-8"))["cases"]
    for case in cases:
        if not case["scored"] or (wanted is not None and case["id"] not in wanted):
            continue
        path = args.arm_dir / case["id"] / "validated_sources.json"
        if not path.exists():
            print(f"{case['id']}: no registry under {args.arm_dir}; nothing frozen for it")
            return 1
        entry = benchmark_fixtures.freeze(
            case["id"], benchmark._slug(case["topic"]), case["topic"],
            path.read_bytes().decode("utf-8"))
        print(f"{case['id']}: frozen {entry['file']} ({entry['sha256_16']}), {entry['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
