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
Mechanical Engineering graduate (May 2026) with a 3.52 GPA, seeking entry-level roles. Key skills include CAD (Solidworks, NX, Fusion, Creo), System Verilog, and mechanical design. Target industries: Semiconductor manufacturing, Semiconductor Equipment, Robotics, Big Tech, and Manufacturing. Experience includes internships in semiconductor equipment and robotics, along with research applying neural networks and leadership roles in engineering consulting.
"""

FILTER_PROMPT_TEMPLATE = """You are an ELITE career advisor. Your reputation is built on high PRECISION.
You are filtering jobs for a NEW GRADUATE with ZERO years of experience.

CANDIDATE PROFILE:
{profile}

JOBS TO EVALUATE (JSON list):
{jobs_json}

FEW-SHOT EXAMPLES:

Example 1 (REJECT): 
  Title: "Manufacturing Engineer"
  Snippet: "...responsible for optimizing production for our power line products..."
  Reason: Too generic. If it's a high-paying role ($100k+) and the snippet doesn't explicitly say "junior" or "entry", be suspicious and REJECT.

Example 2 (REJECT):
  Title: "Characterization Engineer"
  Snippet: "...NY CREATES is seeking a highly skilled individual..."
  Reason: "Highly skilled" and "leads projects" are keywords for senior roles. REJECT.

Example 3 (SELECT):
  Title: "Entry Level Designer"
  Snippet: "Seeking university graduates for our 2026 rotational program..."
  Reason: Explicitly mentions "university graduates" and "entry level". SELECT.

CRITICAL FILTERING RULES:
1. EXPERIENCE LEVEL (STRICT FILTER Mode):
   - Candidate has 0 years full-time experience.
   - SCAN for: "3+", "5+", "10+". If found, REJECT.
   - SCAN for: "Senior", "Lead", "Staff", "Manager", "Principal", "II", "III". If found, REJECT.
   - If the description is a TRUNCATED SNIPPET (ends in '…') and doesn't mention "entry" or "graduate", REJECT it. 
   - We prefer to miss a good job than recommend a senior job.

2. INDUSTRY RELEVANCE:
   - Mechanical, Product Design, Semiconductor, Robotics, Manufacturing.

3. DOUBT = REJECTION:
   - This prevents the "sneaky" senior roles that use generic titles from slipping through.

Return ONLY a raw JSON array of ID strings.
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
        
        # Heuristic filter: Still skip obvious Senior/Lead roles to save tokens.
        # But we remove more moderate terms like "II" or "Staff" from the hard blacklist 
        # to let the LLM decide, while keeping "Senior", "Lead", "Director" etc.
        filtered_chunk = []
        hard_blacklist = ["senior", "lead", "principal", "manager", "director", "architect", "vp", "head", "sr."]
        for job in chunk:
            title_lower = (job.get("title") or "").lower()
            if any(word in title_lower for word in hard_blacklist):
                continue
            filtered_chunk.append(job)

        if not filtered_chunk:
            print(f"  🤖 chunk {i//chunk_size + 1}: skipped all {len(chunk)} (senior/lead titles)")
            continue

        # Build minimal job summaries for the LLM
        job_summaries = []
        for job in filtered_chunk:
            co = job.get("company", {}).get("display_name", "N/A") if isinstance(job.get("company"), dict) else "N/A"
            loc = job.get("location", {}).get("display_name", "N/A") if isinstance(job.get("location"), dict) else "N/A"
            # EXTEND SNIPPET to 2000 characters to catch "Requirements" sections
            job_summaries.append({
                "id": job.get("id"),
                "title": job.get("title"),
                "company": co,
                "location": loc,
                "description_snippet": (job.get("description", "") or "")[:2000],
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
                print(f"  🤖 chunk {i//chunk_size + 1}: selected {len(ids)} of {len(filtered_chunk)} candidates")
        except Exception as e:
            print(f"  ⚠️  LLM filter error on chunk {i//chunk_size + 1}: {e}")
            # In case of error, we now safely return nothing for this chunk instead of everything
    
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
