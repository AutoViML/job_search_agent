#!/usr/bin/env python3
"""
CONSOLIDATED Adzuna Job Search — High Performance Edition
Features:
  - Phase 1: Adzuna Fetching (Caching to raw_results.json)
  - Phase 2: Async Gemini Filtering (Rate-limited to 30 calls/min)
  - STRICT FILTER Mode logic matched from test_prompt.py
"""

import asyncio
import csv
import json
import os
import sys
import time
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from google import genai

load_dotenv()

# ============================================================
# CONFIG & PATHS
# ============================================================
ADZUNA_APP_ID  = os.getenv("ADZUNA_APP_ID")
ADZUNA_API_KEY = os.getenv("ADZUNA_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"

TEST_RUN   = os.getenv("TEST_RUN", "True").lower() == "true"
TEST_LIMIT = int(os.getenv("TEST_LIMIT", "5"))
FULL_LIMIT = int(os.getenv("ADZUNA_LIMIT_PER_SEARCH", "50"))
NUM_RESULTS = TEST_LIMIT if TEST_RUN else FULL_LIMIT
DISTANCE_KM = int(os.getenv("DISTANCE_KM", "40"))

_raw_queries = os.getenv("SEARCH_QUERIES", "entry level engineer")
SEARCH_QUERIES = [q.strip() for q in _raw_queries.split(",") if q.strip()]

_raw_locations = os.getenv("SEARCH_LOCATIONS", "New York")
SEARCH_LOCATIONS = [loc.strip() for loc in _raw_locations.split(",") if loc.strip()]

OUTPUT_DIR = Path(__file__).parent / "outputs"
_run_subdir = OUTPUT_DIR / ("test_results" if TEST_RUN else "search_results")
_run_subdir.mkdir(parents=True, exist_ok=True)

RAW_JSON_PATH = _run_subdir / "raw_results.json"
BAK_JSON_PATH = _run_subdir / "raw_results.bak"

_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
CSV_PATH = _run_subdir / f"curated_matches_{_timestamp}.csv"

# Load candidate profile
PROFILE_PATH = Path(__file__).parent / "_candidate_profile.txt"
if PROFILE_PATH.exists():
    CANDIDATE_PROFILE = PROFILE_PATH.read_text(encoding="utf-8").strip()
else:
    CANDIDATE_PROFILE = "Candidate: Purdue University, BS Mechanical Engineering\nGraduating: May 2026 (entry-level)\nExperience: 0 years."

async def detect_experience_level_async(client, profile: str) -> str:
    """Use Gemini to detect experience level (NEW_GRAD, MID_LEVEL, or SENIOR)."""
    PROMPT = f"""Below is a candidate's profile. Categorize their experience into exactly ONE of these tags:
- NEW_GRAD (0-2 years experience, entry-level, internship focus)
- MID_LEVEL (3-7 years experience, established professional)
- SENIOR (8+ years experience, leadership, staff, or advanced professional roles)

CANDIDATE PROFILE:
{profile}

Return ONLY the tag (NEW_GRAD, MID_LEVEL, or SENIOR). No punctuation or other text.
"""
    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=PROMPT)
        res = response.text.strip().upper()
        if "SENIOR" in res: return "SENIOR"
        if "MID_LEVEL" in res: return "MID_LEVEL"
        return "NEW_GRAD"
    except Exception as e:
        print(f"  ⚠️ Level detection failed ({e}), defaulting to NEW_GRAD.")
        return "NEW_GRAD"

# ============================================================
# FILTER RULES BY MODE
# ============================================================

RULES_MASTER = {
    "NEW_GRAD": {
        "label": "NEW GRADUATE (0-2 years)",
        "rules": """- Candidate has 0 years full-time experience.
- SCAN for: "3+", "5+", "10+". If found, REJECT.
- SCAN for: "Senior", "Lead", "Staff", "Manager", "Principal", "II", "III". If found, REJECT.
- If the description is a TRUNCATED SNIPPET (ends in '…') and doesn't mention "entry" or "graduate", REJECT it.
- We prefer to miss a good job than recommend a senior job.""",
        "exclusion_list": ["senior", "lead", "principal", "manager", "director", "architect", "vp", "head", "sr.", "staff"]
    },
    "MID_LEVEL": {
        "label": "MID-LEVEL PROFESSIONAL (3-7 years)",
        "rules": """- Candidate has ~5 years of experience.
- REJECT: "Entry Level", "Junior", "Graduate", "Intern". (Too junior)
- REJECT: "Principal", "Director", "VP", "Architect", "Staff", "Head". (Too senior)
- SELECT: Roles requiring 3-8 years, "Software Engineer II/III", "Senior" (if listing ~5yrs).
- If snippet is truncated and looks like a junior role, REJECT.""",
        "exclusion_list": ["junior", "intern", "graduate", "principal", "director", "vp", "architect", "staff", "head"]
    },
    "SENIOR": {
        "label": "SENIOR/EXECUTIVE (8+ years)",
        "rules": """- Candidate has 8+ years of experience.
- REJECT: "Junior", "Entry", "Associate", "II", "III". (Too junior)
- SELECT: "Staff", "Principal", "Director", "VP", "Architect", "Lead".
- SCAN for: "10+", "15+". These are target roles.""",
        "exclusion_list": ["junior", "entry", "intern", "associate", "graduate"]
    }
}

# These will be set dynamically in main()
EXPERIENCE_LEVEL = "NEW_GRAD"
ACTIVE_MODE      = RULES_MASTER["NEW_GRAD"]

FILTER_PROMPT_TEMPLATE = """You are an ELITE career advisor. Your reputation is built on high PRECISION.
You are filtering jobs for a {level_label}.

CANDIDATE PROFILE:
{profile}

JOBS TO EVALUATE (JSON list):
{jobs_json}

FEW-SHOT EXAMPLES:

Example 1 (REJECT): 
  Title: "Job title that doesn't fit seniority"
  Snippet: "...requires 10+ years of experience in leadership..."
  Reason: Seniority mismatch. REJECT.

Example 2 (REJECT):
  Title: "Job title that is too junior"
  Snippet: "...seeking a fresh graduate for our internship program..."
  Reason: Seniority mismatch. REJECT.

Example 3 (SELECT):
  Title: "Correct Level Role"
  Snippet: "...seeking a professional with relevant skills and experience in this field..."
  Reason: Good alignment with profile and seniority. SELECT.

CRITICAL FILTERING RULES:
1. EXPERIENCE LEVEL (STRICT FILTER Mode - {experience_level}):
{mode_rules}

2. INDUSTRY RELEVANCE:
   - Match industry keywords from the profile (e.g., Mechanical/Finance/Software).

3. DOUBT = REJECTION:
   - High precision only. If seniority or alignment is unclear, REJECT.

Return a JSON object with:
{{
  "decision": "SELECTED" or "REJECTED",
  "reasoning": "Explain exactly why you made this choice based on the rules."
}}
"""

# ============================================================
# PHASE 1: FETCHING
# ============================================================

def fetch_adzuna_jobs(role: str, location: str, num_results: int, distance_km: int) -> list[dict]:
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
        return data.get("results", [])
    except Exception as e:
        print(f"  ✗ '{role}' → Error: {e}")
        return []

def run_phase_1():
    print(f"📡 Phase 1: Fetching jobs across {len(SEARCH_LOCATIONS)} locations...")
    all_jobs = []
    seen_ids = set()
    
    for location in SEARCH_LOCATIONS:
        print(f"  📍 {location}")
        for query in SEARCH_QUERIES:
            jobs = fetch_adzuna_jobs(query, location, NUM_RESULTS, DISTANCE_KM)
            for job in jobs:
                jid = str(job.get("id", ""))
                if jid and jid not in seen_ids:
                    seen_ids.add(jid)
                    all_jobs.append(job)
            print(f"    ✓ '{query}' → {len(jobs)} jobs found")
            time.sleep(0.3)

    print(f"\n📦 Total unique jobs fetched: {len(all_jobs)}")
    with open(RAW_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump({"total": len(all_jobs), "jobs": all_jobs}, f, indent=2)
    print(f"✅ Raw results cached to {RAW_JSON_PATH}")

# ============================================================
# PHASE 2: FILTERING (ASYNC)
# ============================================================

def clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text

async def filter_job_async(client, job: dict, idx: int, total: int) -> str:
    co = job.get("company", {}).get("display_name", "N/A") if isinstance(job.get("company"), dict) else "N/A"
    loc = job.get("location", {}).get("display_name", "N/A") if isinstance(job.get("location"), dict) else "N/A"
    
    summary = [{
        "id": job.get("id"),
        "title": job.get("title"),
        "company": co,
        "location": loc,
        "description_snippet": (job.get("description", "") or "")[:2000],
    }]

    prompt = FILTER_PROMPT_TEMPLATE.format(
        profile=CANDIDATE_PROFILE, 
        jobs_json=json.dumps(summary, indent=2),
        level_label=ACTIVE_MODE["label"],
        experience_level=EXPERIENCE_LEVEL,
        mode_rules=ACTIVE_MODE["rules"]
    )
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            text = clean_json_response(response.text)
            if not text:
                raise ValueError("Empty response")
            result = json.loads(text)
            if result.get("decision") == "SELECTED":
                return str(job.get("id"))
            return None
        except Exception:
            if attempt == max_retries - 1:
                return None
            await asyncio.sleep((attempt + 1) * 3)
    return None

async def run_phase_2():
    if not RAW_JSON_PATH.exists():
        print("❌ No raw data found. This shouldn't happen.")
        return

    with open(RAW_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        all_jobs = data.get("jobs", [])

    print(f"🤖 Phase 2: Filtering {len(all_jobs)} jobs using {GEMINI_MODEL}...")
    
    # Heuristic pre-filter using mode-specific exclusion list
    exclusion_list = ACTIVE_MODE["exclusion_list"]
    candidates = []
    for j in all_jobs:
        title = (j.get("title") or "").lower()
        if not any(word in title for word in exclusion_list):
            candidates.append(j)

    print(f"  Heuristic: {len(candidates)} candidates remain after title filtering.")
    print(f"  Parallel Evaluation (30 jobs/min rate limit)...")

    client = genai.Client(api_key=GEMINI_API_KEY)
    semaphore = asyncio.Semaphore(5)
    call_times = []
    
    async def rate_limited_filter(job, idx):
        nonlocal call_times
        async with semaphore:
            while len(call_times) >= 30:
                elapsed = time.time() - call_times[0]
                if elapsed < 60:
                    await asyncio.sleep(60 - elapsed + 0.1)
                now = time.time()
                call_times = [t for t in call_times if now - t < 60]
            
            call_times.append(time.time())
            jid = await filter_job_async(client, job, idx, len(candidates))
            if (idx + 1) % 10 == 0 or idx == len(candidates) - 1:
                print(f"    Progress: {idx + 1}/{len(candidates)}...")
            return jid

    tasks = [rate_limited_filter(job, i) for i, job in enumerate(candidates)]
    results = await asyncio.gather(*tasks)
    selected_ids = [jid for jid in results if jid]

    # Write CSV
    print(f"\n📄 Phase 3: Writing {len(selected_ids)} curated matches to CSV...")
    job_map = {str(j.get("id")): j for j in all_jobs}
    
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Company", "Role", "Location", "Salary", "Link"])
        for jid in selected_ids:
            j = job_map.get(jid)
            if not j: continue
            co = j.get("company", {}).get("display_name", "N/A") if isinstance(j.get("company"), dict) else "N/A"
            loc = j.get("location", {}).get("display_name", "N/A") if isinstance(j.get("location"), dict) else "N/A"
            s_min, s_max = j.get("salary_min"), j.get("salary_max")
            salary = f"${s_min:,.0f} - ${s_max:,.0f}" if s_min and s_max else "N/A"
            writer.writerow([co, j.get("title"), loc, salary, j.get("redirect_url")])

    print(f"✅ DONE! Saved results to {CSV_PATH}")

async def main():
    if not ADZUNA_APP_ID or not ADZUNA_API_KEY or not GEMINI_API_KEY:
        print("❌ Missing API keys in .env")
        sys.exit(1)

    print(f"{'='*60}\n  Adzuna Job Search: Consolidated Workflow\n{'='*60}")

    global EXPERIENCE_LEVEL, ACTIVE_MODE
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    print("🧠 Analyzing candidate seniority...")
    EXPERIENCE_LEVEL = await detect_experience_level_async(client, CANDIDATE_PROFILE)
    ACTIVE_MODE = RULES_MASTER.get(EXPERIENCE_LEVEL, RULES_MASTER["NEW_GRAD"])
    print(f"🎯 Detected Experience Level: {EXPERIENCE_LEVEL} ({ACTIVE_MODE['label']})")

    if RAW_JSON_PATH.exists():
        print(f"♻️  Found existing {RAW_JSON_PATH.name}. Skipping Adzuna fetch phase.")
    else:
        run_phase_1()

    await run_phase_2()

    # Cleanup or Rename as per user request
    if RAW_JSON_PATH.exists():
        if BAK_JSON_PATH.exists():
            BAK_JSON_PATH.unlink()
        RAW_JSON_PATH.rename(BAK_JSON_PATH)
        print(f"💾 Renamed {RAW_JSON_PATH.name} to {BAK_JSON_PATH.name} for cleanup.")

if __name__ == "__main__":
    start_time = time.time()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled by user.")
    print(f"⏱  Total run time: {time.time() - start_time:.1f}s")
