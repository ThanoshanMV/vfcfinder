"""
Batch runner: runs VFCFinder on the advisories listed in an annotation file
Each annotation entry gives a GHSA ID and the fixed version to process, the
advisory JSON is looked up by GHSA ID in the advisory directory.

Per advisory outputs (under --output_dir):
    logs/<ghsa>.log, logs/<ghsa>.console.txt, results/ranked_<ghsa>.csv
The CSV is the one VFCFinder writes itself.
"""
import argparse
import json
import sys

from pathlib import Path

from vfcfinder import vfc_ranker

REPO_ROOT = Path(__file__).resolve().parent.parent


class Tee:
    """Writes to the terminal and to a file, so progress can be watched live"""

    def __init__(self, stream, file):
        self.stream = stream
        self.file = file

    def write(self, text):
        self.stream.write(text)
        self.stream.flush()
        # progress bars redraw with carriage returns, one line each in the file
        self.file.write(text.replace("\r", "\n"))
        self.file.flush()

    def flush(self):
        self.stream.flush()
        self.file.flush()

    def isatty(self):
        return False


def run_one(entry, advisory_dir, clone_path, output_dir):
    """Runs VFCFinder for one annotation entry, returns (status, error)"""
    ghsa_id = entry["ghsa_id"]
    fixed_version = entry["fixed_version"]

    advisory_path = advisory_dir / f"{ghsa_id}.json"
    log_path = output_dir / "logs" / f"{ghsa_id}.log"
    console_path = output_dir / "logs" / f"{ghsa_id}.console.txt"
    csv_path = output_dir / "results" / f"ranked_{ghsa_id}.csv"

    if not advisory_path.exists():
        return "missing_advisory", f"{advisory_path} not found"

    stdout, stderr = sys.stdout, sys.stderr
    with open(console_path, "w", encoding="utf-8") as console:
        sys.stdout, sys.stderr = Tee(stdout, console), Tee(stderr, console)
        try:
            vfc_ranker.rank(
                advisory_path=str(advisory_path),
                clone_path=str(clone_path),
                output_path=str(csv_path),
                log_path=str(log_path),
                fixed_version=fixed_version,
            )
            return "ok", None
        except Exception as e:
            # already in the advisory log, keep going with the next advisory
            error = f"{type(e).__name__}: {e}"
            print(f"FAILED {ghsa_id}: {error}")
            return "failed", error
        finally:
            sys.stdout, sys.stderr = stdout, stderr


def main():
    parser = argparse.ArgumentParser(
        description="Run VFCFinder on the advisories listed in an annotation file.",
    )
    parser.add_argument(
        "--annotation",
        type=Path,
        default=REPO_ROOT / "tests/data/sample/ghsa_annotation_sample.json",
        help="JSON list of {ghsa_id, fixed_version, ...}",
    )
    parser.add_argument(
        "--advisory_dir",
        type=Path,
        default=None,
        help="Folder with <ghsa_id>.json advisories (default: the annotation file's folder)",
    )
    parser.add_argument(
        "--clone_path",
        type=Path,
        default=REPO_ROOT / "output/clones",
        help="Local path to clone the GitHub Repositories",
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=REPO_ROOT / "output",
        help="Folder for logs/ and results/",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="GHSA_ID",
        help="Only run these GHSA IDs",
    )
    parser.add_argument(
        "--skip_done",
        action="store_true",
        help="Skip advisories that already have a result CSV",
    )
    args = parser.parse_args()

    advisory_dir = args.advisory_dir or args.annotation.parent

    with open(args.annotation, "r") as f:
        entries = json.load(f)

    if args.only:
        unknown = set(args.only) - {e["ghsa_id"] for e in entries}
        if unknown:
            parser.error(f"not in the annotation file: {sorted(unknown)}")
        entries = [e for e in entries if e["ghsa_id"] in args.only]

    (args.output_dir / "logs").mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results").mkdir(parents=True, exist_ok=True)
    args.clone_path.mkdir(parents=True, exist_ok=True)

    # the clone path is joined with plain string concatenation downstream
    clone_path = f"{args.clone_path}/"

    outcomes = []
    for i, entry in enumerate(entries, start=1):
        ghsa_id = entry["ghsa_id"]
        print(
            f"\n===== [{i}/{len(entries)}] {ghsa_id} "
            f"fixed_version={entry['fixed_version']} ====="
        )
        csv_path = args.output_dir / "results" / f"ranked_{ghsa_id}.csv"
        if args.skip_done and csv_path.exists():
            print("Result exists, skipping")
            outcomes.append((ghsa_id, "skipped_done", None))
        else:
            status, error = run_one(entry, advisory_dir, clone_path, args.output_dir)
            outcomes.append((ghsa_id, status, error))

    print(f"\n===== Done: {len(outcomes)} advisories =====")
    for status in sorted({o[1] for o in outcomes}):
        print(f"{status}: {sum(1 for o in outcomes if o[1] == status)}")

    not_processed = [o for o in outcomes if o[1] in ("failed", "missing_advisory")]
    if not_processed:
        print("\nNot processed:")
        for ghsa_id, status, error in not_processed:
            print(f"{ghsa_id}  {status}  {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
