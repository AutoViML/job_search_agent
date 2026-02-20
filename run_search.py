#!/usr/bin/env python3
"""
Streamlined Adzuna Job Search — Direct Script (no CrewAI overhead)

Steps:
  1. Fetch jobs from Adzuna for multiple search queries
  2. Use Gemini to filter and select best matches for the candidate profile
  3. Write clean CSV: Company, Role, Location, Salary, Link

Usage:
  python run_search.py             # TEST mode (5 jobs/query from .env)
  TEST_RUN=False python run_search.py  # Full run (20 jobs/query)
"""

import csv
import json
import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIG
# ============================================================
ADZUNA_APP_ID  = os.getenv("ADZUNA_APP_ID")
ADZUNA_API_KEY = os.getenv("ADZUNA_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"

TEST_RUN   = os.getenv("TEST_RUN", "True").lower() == "true"
TEST_LIMIT = int(os.getenv("TEST_LIMIT", "5"))
FULL_LIMIT = int(os.getenv("ADZUNA_LIMIT_PER_SEARCH", "50"))
NUM_RESULTS = TEST_LIMIT if TEST_RUN else FULL_LIMIT
DISTANCE_KM = int(os.getenv("DISTANCE_KM", "40"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
LLM_CHUNK_SIZE = int(os.getenv("LLM_CHUNK_SIZE", "20"))

# Search queries — read from .env as comma-separated list
_raw_queries = os.getenv("SEARCH_QUERIES", "entry level engineer,new graduate engineer,product design engineer,packaging engineer")
SEARCH_QUERIES = [q.strip() for q in _raw_queries.split(",") if q.strip()]

# Locations — read from .env as comma-separated list
_raw_locations = os.getenv("SEARCH_LOCATIONS", "New York")
SEARCH_LOCATIONS = [loc.strip() for loc in _raw_locations.split(",") if loc.strip()]

OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# Route to test_results/ or search_results/ based on mode
_run_subdir = OUTPUT_DIR / ("test_results" if TEST_RUN else "search_results")
_run_subdir.mkdir(exist_ok=True)

from datetime import datetime
_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
CSV_PATH = _run_subdir / f"curated_matches_{_timestamp}.csv"

CANDIDATE_PROFILE = """
Candidate: Purdue University, BS Mechanical Engineering + Manufacturing minor
GPA: 3.52 | Graduating: May 2026 (entry-level / new-graduate)

Internship: Tokyo Electron Limited (TEL) — Mechanical Engineering Intern (wafer handling robot, 3D printing)
Research: STARS Fellowship (semiconductor chip design), Neural Network Research in Engineering
Skills: SolidWorks, NX, Fusion 360, Creo, Python, SystemVerilog
Target Industries: Semiconductor manufacturing, semiconductor equipment, robotics, big tech, hardware, manufacturing
Target Locations: NY/NJ/CT metro → Dallas/Austin TX → Silicon Valley CA
"""

FILTER_PROMPT_TEMPLATE = """You are a career advisor filtering Adzuna job listings for a specific candidate.

CANDIDATE PROFILE:
{profile}

JOBS TO EVALUATE (JSON list):
{jobs_json}

TASK:
Review each job. Return a JSON array of the IDs of ONLY the jobs that are a good match:
- Entry-level, junior, or new-graduate friendly (NOT requiring 3+ years experience)
- Relevant to: mechanical engineering, product design, semiconductor, robotics, manufacturing, hardware
- Located in NY/NJ/CT metro, Dallas/Austin TX, Silicon Valley, OR explicitly remote
- REJECT: senior/staff/lead roles, software-only, unrelated industries, 5+ year requirements

Return ONLY a raw JSON array of ID strings. No explanation, no markdown, no extra text.
Example output: ["5461711151", "5375386397"]
If no jobs match, return: []
"""

# ============================================================
# ADZUNA FETCH
# ============================================================

def fetch_jobs(role: str, location: str, num_results: int, distance_km: int) -> list[dict]:
    """Fetch raw job listings from Adzuna API."""
    url = (
        f"{ADZUNA_BASE_URL}/us/search/1"
        f"?app_id={ADZUNA_APP_ID}"
        f"&app_key={ADZUNA_API_KEY}"
        f"&results_per_page={num_results}"
        f"&what={role.replace(' ', '+')}"
        f"&where={location.replace(' ', '+')}"
        f"&distance={distance_km}"
        f"&content-type=application/json"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        print(f"  ✓ '{role}' → {len(results)} jobs found")
        return results
    except Exception as e:
        print(f"  ✗ '{role}' → Error: {e}")
        return []


# ============================================================
# GEMINI LLM FILTER
# ============================================================

def gemini_filter(jobs: list[dict], chunk_size: int = LLM_CHUNK_SIZE) -> list[str]:
    """Ask Gemini to select the best-matching job IDs."""
    if not jobs:
        return []

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    selected_ids = []

    # Process in chunks to avoid token limits
    for i in range(0, len(jobs), chunk_size):
        chunk = jobs[i:i + chunk_size]
        # Build minimal job summaries for the LLM (reduce tokens)
        job_summaries = []
        for job in chunk:
            co = job.get("company", {}).get("display_name", "N/A") if isinstance(job.get("company"), dict) else "N/A"
            loc = job.get("location", {}).get("display_name", "N/A") if isinstance(job.get("location"), dict) else "N/A"
            job_summaries.append({
                "id": job.get("id"),
                "title": job.get("title"),
                "company": co,
                "location": loc,
                "description_snippet": (job.get("description", "") or "")[:300],
                "salary_min": job.get("salary_min"),
                "salary_max": job.get("salary_max"),
            })

        prompt = FILTER_PROMPT_TEMPLATE.format(
            profile=CANDIDATE_PROFILE,
            jobs_json=json.dumps(job_summaries, indent=2)
        )

        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            text = response.text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:]).rstrip("`").strip()
            ids = json.loads(text)
            if isinstance(ids, list):
                selected_ids.extend([str(id_) for id_ in ids])
                print(f"  🤖 chunk {i//chunk_size + 1}: selected {len(ids)} of {len(chunk)} jobs")
        except Exception as e:
            print(f"  ⚠️  LLM filter error on chunk {i//chunk_size + 1}: {e} — keeping all in chunk")
            selected_ids.extend([str(job.get("id")) for job in chunk if job.get("id")])

    return selected_ids


# ============================================================
# CSV WRITE
# ============================================================

def write_csv(jobs: list[dict], selected_ids: list[str], path: Path) -> int:
    """Write the selected jobs to CSV."""
    id_set = set(selected_ids)
    job_index = {str(j.get("id")): j for j in jobs if j.get("id")}

    rows = []
    for jid in selected_ids:
        job = job_index.get(jid)
        if not job:
            continue
        co = job.get("company", {}).get("display_name", "N/A") if isinstance(job.get("company"), dict) else "N/A"
        role = job.get("title", "N/A")
        loc = job.get("location", {}).get("display_name", "N/A") if isinstance(job.get("location"), dict) else "N/A"
        s_min = job.get("salary_min")
        s_max = job.get("salary_max")
        if s_min and s_max:
            salary = f"${s_min:,.0f} - ${s_max:,.0f}"
        elif s_min:
            salary = f"${s_min:,.0f}+"
        elif s_max:
            salary = f"up to ${s_max:,.0f}"
        else:
            salary = "N/A"
        link = job.get("redirect_url", "N/A")
        rows.append([co, role, loc, salary, link])

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Company", "Role", "Location", "Salary", "Link"])
        writer.writerows(rows)

    return len(rows)


# ============================================================
# MAIN
# ============================================================

def main():
    mode = "🧪 TEST" if TEST_RUN else "🚀 FULL"
    print(f"""
{'='*60}
  Adzuna Job Search {mode} ({NUM_RESULTS} jobs/query, {DISTANCE_KM}km radius)
  Locations : {', '.join(SEARCH_LOCATIONS)}
  Queries   : {len(SEARCH_QUERIES)}
  Total searches: {len(SEARCH_LOCATIONS) * len(SEARCH_QUERIES)}
  Output    : {CSV_PATH}
{'='*60}
""")

    if not ADZUNA_APP_ID or not ADZUNA_API_KEY:
        print("❌ Missing ADZUNA_APP_ID or ADZUNA_API_KEY in .env")
        sys.exit(1)
    if not GEMINI_API_KEY:
        print("❌ Missing GEMINI_API_KEY in .env")
        sys.exit(1)

    # Step 1: Fetch jobs across all locations and queries
    print("📡 STEP 1: Fetching jobs from Adzuna...")
    all_jobs = []
    seen_ids = set()
    for location in SEARCH_LOCATIONS:
        print(f"  📍 {location}")
        for query in SEARCH_QUERIES:
            jobs = fetch_jobs(query, location, NUM_RESULTS, DISTANCE_KM)
            for job in jobs:
                jid = str(job.get("id", ""))
                if jid and jid not in seen_ids:
                    seen_ids.add(jid)
                    all_jobs.append(job)
            time.sleep(0.3)  # be polite to the API

    print(f"\n  📦 Total unique jobs fetched: {len(all_jobs)}")

    if not all_jobs:
        print("⚠️  No jobs found. Check your API credentials or search queries.")
        sys.exit(0)

    # Save raw dump for inspection
    raw_path = _run_subdir / "raw_results.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({"total": len(all_jobs), "jobs": all_jobs}, f, indent=2)
    print(f"  💾 Raw results saved to {raw_path}")

    # Step 2: LLM filter
    print(f"\n🤖 STEP 2: Filtering with Gemini LLM...")
    selected_ids = gemini_filter(all_jobs)
    print(f"\n  ✅ {len(selected_ids)} jobs selected from {len(all_jobs)} total")

    # Step 3: Write CSV
    print(f"\n📄 STEP 3: Writing CSV...")
    count = write_csv(all_jobs, selected_ids, CSV_PATH)
    print(f"  ✅ Saved {count} rows to {CSV_PATH}")

    print(f"""
{'='*60}
  ✅ DONE! Open {CSV_PATH} to see your curated job matches.
{'='*60}
""")


if __name__ == "__main__":
    start = time.time()
    main()
    print(f"⏱  Total time: {time.time() - start:.1f}s")
