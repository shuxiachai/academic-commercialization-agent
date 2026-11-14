"""Part R: collect each case's sources under one arm's code, over shared recorded responses.

    python evals/market_selection_v1/collect.py --src <checkout>/src --arm old|new \\
        --cache <file outside the repo> --out <dir> --accessed YYYY-MM-DD --env <.env> [--only V01,N03]

``--src`` chooses whose pipeline runs: a checkout of ``main`` before the
change for the ``old`` arm, this branch for the ``new`` arm. Everything the
pipeline asks of the outside world goes through one recorder, keyed by the
call and its arguments and kept in ``--cache``:

- web search (the default client, and the native-language client by its locale);
- the topic planner and the heading translator (the only model calls);
- OpenAlex, Semantic Scholar, PubMed, arXiv, Crossref and Lens;
- the URL check, the page-date reader and the patent-page reader.

The arm that runs first makes each request once; the other arm is answered
from the record, so the two registries differ only where the code does. A
request only one arm makes (a query the other never reached, a page only one
arm listed) is made live for that arm and recorded. Errors are recorded and
replayed like answers. ``calls.json`` counts, per case, the requests answered
live and from the record: the new arm's live count is what the change adds.

The cache holds third-party text and must stay outside the repository.
No crew is run and no report is written.
"""

from __future__ import annotations

import argparse
import json
import pickle
import subprocess
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

CASES = Path(__file__).with_name("cases.json")


class Recorder:
    """Answers each distinct call once, from the record when it has one."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.record: dict[tuple, tuple[str, object]] = (
            pickle.loads(path.read_bytes()) if path.exists() else {}
        )
        self.calls: Counter[str] = Counter()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_suffix(self.path.suffix + ".partial")
        partial.write_bytes(pickle.dumps(self.record))
        partial.replace(self.path)

    def function(self, name: str, target):
        def call(*args, **kwargs):
            key = (name, repr(args), repr(sorted(kwargs.items())))
            if key in self.record:
                self.calls[f"{name}: from the record"] += 1
            else:
                self.calls[f"{name}: live"] += 1
                try:
                    self.record[key] = ("ok", target(*args, **kwargs))
                except Exception as exc:  # noqa: BLE001 - replayed to the other arm unchanged
                    self.record[key] = ("error", exc)
            kind, value = self.record[key]
            if kind == "error":
                raise value
            return pickle.loads(pickle.dumps(value))

        return call

    def client(self, name: str, client):
        recorder = self

        class Recorded:
            def __getattr__(self, attribute):
                target = getattr(client, attribute)
                if not callable(target):
                    return target
                return recorder.function(f"{name}.{attribute}", target)

        return Recorded()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--arm", choices=("old", "new"), required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--accessed", type=date.fromisoformat, required=True)
    parser.add_argument("--env", type=Path, help="dotenv file with the search and model keys; read, never printed")
    parser.add_argument("--only", help="comma-separated case ids")
    args = parser.parse_args(argv)

    src = args.src.resolve()
    sys.path[:0] = [str(src)]
    if args.env:
        from dotenv import load_dotenv

        load_dotenv(args.env)
    from academic_agent import language, source_clients
    from academic_agent import source_pipeline as sp
    from academic_agent.evidence import check_public_url
    from academic_agent.page_dates import page_publication_date
    from academic_agent.patent_applicants import patent_page_facts

    recorder = Recorder(args.cache)
    make_web_client = sp.default_web_search_client
    sp.default_web_search_client = lambda **locale: recorder.client(
        f"web{sorted(locale.items())}", make_web_client(**locale))
    language.plan_topic_search = recorder.function("plan_topic_search", language.plan_topic_search)
    language.translate_headings = recorder.function("translate_headings", language.translate_headings)

    revision = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=False).stdout.strip()
    wanted = set(args.only.split(",")) if args.only else None
    cases = [case for case in json.loads(CASES.read_text(encoding="utf-8"))["cases"]
             if wanted is None or case["id"] in wanted]
    failures = 0
    for case in cases:
        run_dir = args.out / args.arm / case["id"]
        if (run_dir / "meta.json").exists():
            print(f"{case['id']}: already collected for the {args.arm} arm, left as it is")
            continue
        run_dir.mkdir(parents=True, exist_ok=True)
        recorder.calls.clear()
        started = time.monotonic()
        meta = {"case": case["id"], "topic": case["topic"], "arm": args.arm,
                "src": str(src), "revision": revision, "accessed": args.accessed.isoformat()}
        try:
            collection = sp.collect_source_collection(
                case["topic"],
                crossref=recorder.client("crossref", source_clients.CrossrefClient()),
                openalex=recorder.client("openalex", source_clients.OpenAlexClient()),
                s2=recorder.client("s2", source_clients.SemanticScholarClient()),
                pubmed=recorder.client("pubmed", source_clients.PubMedClient()),
                arxiv=recorder.client("arxiv", source_clients.ArxivClient()),
                lens=recorder.client("lens", source_clients.LensPatentClient()),
                url_checker=recorder.function("url_check", check_public_url),
                page_dater=recorder.function("page_date", page_publication_date),
                patent_applicant_lookup=recorder.function("patent_page", patent_page_facts),
                accessed_date=args.accessed,
            )
        except Exception as exc:  # noqa: BLE001 - a failed case is a reading, recorded and counted
            failures += 1
            meta["error"] = f"{type(exc).__name__}: {exc}"[:500]
            print(f"{case['id']}: FAILED {meta['error'][:120]}")
        else:
            (run_dir / "validated_sources.json").write_text(
                collection.model_dump_json(indent=2), encoding="utf-8", newline="")
            print(f"{case['id']}: {len(collection.academic_sources)} academic, "
                  f"{len(collection.patent_sources)} patent, {len(collection.market_sources)} market")
        meta["seconds"] = round(time.monotonic() - started, 1)
        (run_dir / "calls.json").write_text(
            json.dumps(dict(sorted(recorder.calls.items())), indent=2) + "\n", encoding="utf-8")
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        recorder.save()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
