"""
Checks GHSA advisory JSONs for a "PACKAGE" reference.
Reads every *.json file in a directory and reports whether its "references"
list contains an entry with "type": "PACKAGE", along with the entry's URL.

Usage:
    python bin/check_package_refs.py tests/data/sample/first_20_samples
    python bin/check_package_refs.py tests/data/sample/second_20_samples --csv out.csv
"""
import argparse
import csv
import json
import sys

from pathlib import Path


def package_urls(advisory):
    """Returns the URLs of all references of type PACKAGE in an advisory"""
    return [
        ref.get("url", "")
        for ref in advisory.get("references", [])
        if ref.get("type") == "PACKAGE"
    ]


def check_directory(input_dir):
    """Returns a list of (ghsa_id, urls, error) for every JSON in input_dir"""
    results = []
    for path in sorted(input_dir.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                advisory = json.load(f)
            results.append((advisory.get("id", path.stem), package_urls(advisory), None))
        except (json.JSONDecodeError, OSError) as e:
            results.append((path.stem, [], str(e)))
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Check GHSA JSONs for a "type": "PACKAGE" reference'
    )
    parser.add_argument("input_dir", type=Path, help="Folder containing GHSA JSON files")
    parser.add_argument("--csv", type=Path, help="Optional path to write results as CSV")
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        sys.exit(f"{args.input_dir} is not a directory")

    results = check_directory(args.input_dir)
    if not results:
        sys.exit(f"No JSON files found in {args.input_dir}")

    for ghsa_id, urls, error in results:
        if error:
            print(f"{ghsa_id}: ERROR ({error})")
        elif urls:
            print(f"{ghsa_id}: PACKAGE  {', '.join(urls)}")
        else:
            print(f"{ghsa_id}: no PACKAGE reference")

    with_package = sum(1 for _, urls, err in results if urls and not err)
    errors = sum(1 for _, _, err in results if err)
    print(f"\n{with_package}/{len(results)} advisories have a PACKAGE reference"
          + (f" ({errors} unreadable)" if errors else ""))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ghsa_id", "has_package", "package_urls", "error"])
            for ghsa_id, urls, error in results:
                writer.writerow([ghsa_id, bool(urls), ";".join(urls), error or ""])


if __name__ == "__main__":
    main()
