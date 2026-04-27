#!/usr/bin/env python3
"""
extract_fresh_jobs.py — Identify New Jobs to Apply For
======================================================
Compares the most recent job search results against previous ones
to extract only the "fresh" jobs that haven't appeared before.

Matching logic (same as dedupe_results.py):
  1. Adzuna Job ID (extracted from URL)
  2. Normalized Company + Role

Saves the result as 'fresh_jobs.tsv' (tab-separated) in the test_results folder.
"""

import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "outputs" / "test_results"
OUTPUT_NAME = "fresh_jobs.tsv"

EXPECTED_HEADERS = ["Company", "Role", "Location", "Salary", "Link"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def normalise(text: str) -> str:
    if not text: return ""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_job_id(url: str) -> str | None:
    if not url: return None
    m = re.search(r"/(\d{7,})", url)
    return m.group(1) if m else None

def get_row_fingerprints(row: dict) -> tuple[str | None, tuple[str, str]]:
    url = row.get("Link", "").strip()
    jid = extract_job_id(url)
    co_role = (normalise(row.get("Company", "")), normalise(row.get("Role", "")))
    return jid or url, co_role

def load_csv(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if any(v.strip() for v in row.values()):
                    rows.append(dict(row))
    except Exception as e:
        print(f"  ✗  Error reading {path.name}: {e}")
    return rows

# ── Main Logic ────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"  Fresh Jobs Extractor")
    print(f"{'='*60}")

    # Find all curated matches files
    all_files = sorted(RESULTS_DIR.glob("curated_matches_*.csv"))
    
    if len(all_files) < 2:
        print("❌ Need at least two 'curated_matches_*.csv' files to compare.")
        print(f"   Found: {[f.name for f in all_files]}")
        return

    # Assuming sorted order (by timestamp in filename), last is newest, second to last is old.
    old_file = all_files[-2]
    new_file = all_files[-1]

    print(f"📂 Comparing:")
    print(f"   OLD (Applied) : {old_file.name}")
    print(f"   NEW (Current) : {new_file.name}")

    old_rows = load_csv(old_file)
    new_rows = load_csv(new_file)

    # Build "Already Seen" set from old file
    seen_ids = set()
    seen_co_role = set()

    for row in old_rows:
        jid, co_role = get_row_fingerprints(row)
        if jid: seen_ids.add(jid)
        if co_role[0] and co_role[1]: seen_co_role.add(co_role)

    # Filter new rows
    fresh_rows = []
    for row in new_rows:
        jid, co_role = get_row_fingerprints(row)
        
        is_duplicate = False
        if jid and jid in seen_ids:
            is_duplicate = True
        elif co_role[0] and co_role[1] and co_role in seen_co_role:
            is_duplicate = True
            
        if not is_duplicate:
            fresh_rows.append(row)

    print(f"\n📊 Results:")
    print(f"   Total in new file : {len(new_rows)}")
    print(f"   Duplicates found  : {len(new_rows) - len(fresh_rows)}")
    print(f"   ✅ Fresh jobs     : {len(fresh_rows)}")

    # Save output
    output_path = RESULTS_DIR / OUTPUT_NAME
    try:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=EXPECTED_HEADERS, extrasaction="ignore", delimiter="\t")
            writer.writeheader()
            writer.writerows(fresh_rows)
        print(f"\n💾 Saved {len(fresh_rows)} fresh jobs to:\n   {output_path}")
    except Exception as e:
        print(f"\n❌ Failed to write output: {e}")

    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
