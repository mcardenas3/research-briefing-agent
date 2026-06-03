"""
filter_seen_papers.py
Manages persistent memory of seen papers across automated runs.

Modes:
  filter — Reads seen_papers.json and papers_raw.json, removes already-seen
           papers, overwrites the input file with the filtered list.
           Writes new_count to GITHUB_OUTPUT when running in CI.
           Also saves the list of new paper IDs to <run-dir>/new_paper_ids.json
           so the update step can read them after a successful pipeline run.

  update — Appends new paper IDs from <run-dir>/new_paper_ids.json into
           seen_papers.json, committing the memory for future runs.
"""

import argparse
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def write_github_output(key: str, value: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def load_seen(seen_path: Path) -> set:
    if not seen_path.exists():
        print(f"  seen_papers.json not found at {seen_path} — starting fresh.")
        return set()
    data = json.loads(seen_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print(f"  WARNING: {seen_path} has unexpected format; treating as empty.")
        return set()
    return set(data)


def main():
    parser = argparse.ArgumentParser(description="Filter and track seen papers across runs")
    parser.add_argument("--mode", choices=["filter", "update"], required=True,
                        help="filter: remove seen papers from raw list; update: persist new IDs")
    parser.add_argument("--input", default=".tmp/papers_raw.json",
                        help="Path to papers_raw.json (filter mode)")
    parser.add_argument("--output", default=None,
                        help="Output path for filtered papers (defaults to --input, i.e. overwrites)")
    parser.add_argument("--seen", default="seen_papers.json",
                        help="Path to the persistent seen_papers.json file (repo root)")
    parser.add_argument("--run-dir", default=None,
                        help="Run folder for reading/writing new_paper_ids.json")
    args = parser.parse_args()

    seen_path = Path(args.seen)
    run_dir = Path(args.run_dir) if args.run_dir else None

    # ── filter mode ───────────────────────────────────────────────────────────
    if args.mode == "filter":
        input_path = Path(args.input)
        output_path = Path(args.output) if args.output else input_path

        if not input_path.exists():
            print(f"ERROR: input file not found: {input_path}")
            sys.exit(1)

        seen_ids = load_seen(seen_path)
        papers = json.loads(input_path.read_text(encoding="utf-8"))

        new_papers = [p for p in papers if p.get("paperId") not in seen_ids]
        new_count = len(new_papers)
        already_seen = len(papers) - new_count

        print(f"Papers from search:  {len(papers)}")
        print(f"Already seen:        {already_seen}")
        print(f"New (to process):    {new_count}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(new_papers, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Filtered list written to {output_path}")

        # Save new paper IDs so the update step can persist them after a successful run
        if run_dir:
            run_dir.mkdir(parents=True, exist_ok=True)
            new_ids = [p["paperId"] for p in new_papers if p.get("paperId")]
            (run_dir / "new_paper_ids.json").write_text(
                json.dumps(new_ids, indent=2), encoding="utf-8"
            )
            print(f"New paper IDs saved to {run_dir}/new_paper_ids.json")

        write_github_output("new_count", str(new_count))

        if new_count == 0:
            print("\nNo new papers found today — pipeline will send a notification and stop.")

    # ── update mode ───────────────────────────────────────────────────────────
    elif args.mode == "update":
        if not run_dir:
            print("ERROR: --run-dir is required for update mode")
            sys.exit(1)

        ids_path = run_dir / "new_paper_ids.json"
        if not ids_path.exists():
            print(f"No new_paper_ids.json found at {ids_path} — nothing to update.")
            return

        new_ids: list = json.loads(ids_path.read_text(encoding="utf-8"))

        existing: list = []
        if seen_path.exists():
            existing = json.loads(seen_path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []

        combined = list(set(existing) | set(new_ids))
        seen_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
        print(f"seen_papers.json updated: {len(existing)} → {len(combined)} total entries")


if __name__ == "__main__":
    main()
