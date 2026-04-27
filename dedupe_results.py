#!/usr/bin/env python3
"""
dedupe_results.py — Job Search Results De-Duplicator
=====================================================
Scans all curated_matches_*.csv files inside outputs/test_results/,
strips duplicates, and writes a single consolidated CSV back to that folder.

De-dupe priority:
  1. Exact URL match (most reliable — Adzuna job IDs are embedded in URLs)
  2. Normalised Company + Role pair (catches same job posted on different URLs)

Usage:
    python dedupe_results.py
    python dedupe_results.py --dry-run   # show stats without writing file
"""

import argparse
import sys

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError with emoji)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import csv
import os
import re
from datetime import datetime
from pathlib import Path


# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "outputs" / "test_results"
OUTPUT_NAME = "consolidated_matches.csv"

EXPECTED_HEADERS = {"Company", "Role", "Location", "Salary", "Link"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalise(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for fuzzy matching."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_job_id(url: str) -> str | None:
    """
    Pull the Adzuna numeric job-ID out of the URL so we can match even
    when the URL query-string differs (utm params, se=…, v=… tokens).

    Examples handled:
      https://www.adzuna.com/details/5461711099?utm_medium=api&...
      https://www.adzuna.com/land/ad/5461711099?se=…&utm_medium=api&…
    """
    if not url:
        return None
    m = re.search(r"/(\d{7,})", url)
    return m.group(1) if m else None


def load_csv(path: Path) -> list[dict]:
    """Load a CSV file and return rows as list-of-dicts (skips blank rows)."""
    rows = []
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                print(f"  ⚠️  Skipping {path.name}: no headers found.")
                return rows
            missing = EXPECTED_HEADERS - set(reader.fieldnames)
            if missing:
                print(f"  ⚠️  Skipping {path.name}: missing columns {missing}.")
                return rows
            for row in reader:
                # Skip completely blank rows
                if any(v.strip() for v in row.values()):
                    rows.append(dict(row))
    except Exception as e:
        print(f"  ✗  Could not read {path.name}: {e}")
    return rows


# ── Core logic ────────────────────────────────────────────────────────────────

def dedupe(all_rows: list[dict]) -> tuple[list[dict], int]:
    """
    Return (deduplicated_rows, duplicate_count).

    Two rows are considered duplicates if they share:
      - the same extracted Adzuna job-ID from their URL, OR
      - the same normalised (company, role) pair
    """
    seen_job_ids: set[str]  = set()
    seen_co_role: set[tuple] = set()
    unique: list[dict]       = []
    dup_count                = 0

    for row in all_rows:
        url    = row.get("Link", "").strip()
        job_id = extract_job_id(url)
        co_role = (normalise(row.get("Company", "")), normalise(row.get("Role", "")))

        is_dup = False

        # 1️⃣  URL / job-ID check
        if job_id:
            if job_id in seen_job_ids:
                is_dup = True
            else:
                seen_job_ids.add(job_id)
        elif url:
            # No numeric ID found — fall back to exact URL match
            if url in seen_job_ids:
                is_dup = True
            else:
                seen_job_ids.add(url)

        # 2️⃣  Company + Role check (catches cross-URL duplicates)
        if not is_dup:
            if co_role[0] and co_role[1]:   # only when both fields are non-empty
                if co_role in seen_co_role:
                    is_dup = True
                else:
                    seen_co_role.add(co_role)

        if is_dup:
            dup_count += 1
        else:
            unique.append(row)

    return unique, dup_count


def find_source_files() -> list[Path]:
    """Return all curated_matches_*.csv files, sorted oldest-first."""
    files = sorted(RESULTS_DIR.glob("curated_matches_*.csv"))
    return files


# ── Main ──────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"  Job Search Results De-Duplicator")
    print(f"{'='*60}")
    print(f"📂 Scanning: {RESULTS_DIR}\n")

    source_files = find_source_files()

    if not source_files:
        print("❌  No curated_matches_*.csv files found. Nothing to do.")
        sys.exit(0)

    print(f"📄 Found {len(source_files)} source file(s):")
    all_rows: list[dict] = []
    for p in source_files:
        rows = load_csv(p)
        print(f"   • {p.name:45s}  →  {len(rows):>4} rows")
        all_rows.extend(rows)

    total_in = len(all_rows)
    print(f"\n📊 Total rows loaded   : {total_in}")

    unique_rows, dup_count = dedupe(all_rows)
    total_out = len(unique_rows)

    print(f"🔁 Duplicates removed  : {dup_count}")
    print(f"✅ Unique jobs retained: {total_out}")

    output_path = RESULTS_DIR / OUTPUT_NAME

    if dry_run:
        print(f"\n🏁 [DRY RUN] Would write {total_out} rows to:\n   {output_path}")
        return

    # Write consolidated file
    fieldnames = ["Company", "Role", "Location", "Salary", "Link"]
    try:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(unique_rows)
        print(f"\n💾 Consolidated file saved to:\n   {output_path}")
    except Exception as e:
        print(f"\n❌ Failed to write output: {e}")
        sys.exit(1)

    print(f"\n⏱  Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="De-duplicate job search CSVs and write a consolidated file."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stats without writing any file.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
