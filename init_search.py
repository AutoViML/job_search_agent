#!/usr/bin/env python3
"""
init_search.py — Preflight script for run_search.py

What this does:
  1. Reads search_objectives.txt (and optionally my_profile.pdf)
  2. Sends both to Gemini to intelligently extract search parameters
  3. Previews the suggested settings and validates your .env
  4. Asks for confirmation, then writes the settings to .env
  5. Updates the CANDIDATE_PROFILE inside run_search.py

Run this ONCE before any new job search campaign:
  uv run python init_search.py
Then run:
  uv run python run_search.py
"""

import json
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
OBJECTIVES_PATH = BASE_DIR / "search_objectives.txt"
PROFILE_PDF_PATH = BASE_DIR / "my_profile.pdf"
ENV_PATH = BASE_DIR / ".env"
RUN_SCRIPT_PATH = BASE_DIR / "run_search.py"
CANDIDATE_PROFILE_PATH = BASE_DIR / "_candidate_profile.txt"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


# ============================================================
# HELPERS
# ============================================================

def read_objectives() -> str:
    """Read search_objectives.txt."""
    if not OBJECTIVES_PATH.exists():
        print(f"⚠️  {OBJECTIVES_PATH.name} not found — skipping.")
        return ""
    text = OBJECTIVES_PATH.read_text(encoding="utf-8").strip()
    print(f"  ✓ Read {OBJECTIVES_PATH.name} ({len(text)} chars)")
    return text


def read_pdf_text() -> str:
    """Extract text from my_profile.pdf using PyMuPDF."""
    if not PROFILE_PDF_PATH.exists():
        print(f"  ⚠️  {PROFILE_PDF_PATH.name} not found — skipping PDF.")
        return ""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(PROFILE_PDF_PATH))
        pages = [page.get_text() for page in doc]
        text = "\n".join(pages).strip()
        print(f"  ✓ Read {PROFILE_PDF_PATH.name} ({len(text)} chars, {len(doc)} pages)")
        return text
    except Exception as e:
        print(f"  ⚠️  Could not read PDF: {e}")
        return ""


def call_gemini(prompt: str) -> str:
    """Call Gemini and return raw text response."""
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text.strip()


def parse_json_response(text: str) -> dict:
    """Strip markdown fences and parse JSON from LLM response."""
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]).rstrip("`").strip()
    return json.loads(text)


# ============================================================
# VALIDATION
# ============================================================

REQUIRED_ENV_VARS = {
    "GEMINI_API_KEY":        "Your Google Gemini API key",
    "ADZUNA_APP_ID":         "Adzuna App ID from developer.adzuna.com",
    "ADZUNA_API_KEY":        "Adzuna API key from developer.adzuna.com",
    "SEARCH_QUERIES":        "Comma-separated role search queries",
    "SEARCH_LOCATIONS":      "Comma-separated city/metro locations",
}

OPTIONAL_ENV_VARS = {
    "DISTANCE_KM":           ("40",  "Radius in km per location (~40 = 25 miles)"),
    "ADZUNA_LIMIT_PER_SEARCH": ("50", "Results per query (Adzuna max is 50)"),
    "TEST_RUN":              ("False","True = 5 jobs/query test; False = full run"),
    "TEST_LIMIT":            ("5",   "Jobs per query in test mode"),
    "GEMINI_MODEL":          ("gemini-2.5-flash-lite", "Gemini model for filtering"),
    "LLM_CHUNK_SIZE":        ("20",  "Jobs sent to Gemini per batch"),
}


def validate_env() -> tuple[bool, list[str], list[str]]:
    """
    Returns (all_ok, errors, warnings).
    errors   = missing required vars
    warnings = missing optional vars (using defaults)
    """
    errors = []
    warnings = []

    for var, desc in REQUIRED_ENV_VARS.items():
        val = os.getenv(var, "").strip()
        if not val:
            errors.append(f"  ❌ {var} — {desc}")

    for var, (default, desc) in OPTIONAL_ENV_VARS.items():
        val = os.getenv(var, "").strip()
        if not val:
            warnings.append(f"  ⚠️  {var} not set → will use default: {default!r}  ({desc})")

    return len(errors) == 0, errors, warnings


def print_validation_report() -> bool:
    ok, errors, warnings = validate_env()

    print("\n📋 Environment Validation")
    print("─" * 50)

    if errors:
        print("\n🚫 Missing required settings:")
        for e in errors: print(e)
    else:
        print("  ✅ All required settings present")

    if warnings:
        print("\n📌 Optional (using defaults):")
        for w in warnings: print(w)

    # Print current search config summary
    queries   = [q.strip() for q in os.getenv("SEARCH_QUERIES", "").split(",") if q.strip()]
    locations = [l.strip() for l in os.getenv("SEARCH_LOCATIONS", "").split(",") if l.strip()]
    limit     = int(os.getenv("ADZUNA_LIMIT_PER_SEARCH", "50"))
    test_run  = os.getenv("TEST_RUN", "False").lower() == "true"
    dist      = os.getenv("DISTANCE_KM", "40")

    total_searches = len(queries) * len(locations)
    total_jobs_est = total_searches * min(limit, 50)

    print(f"""
📊 Search Plan Summary
─────────────────────────────────────
  Mode        : {"🧪 TEST" if test_run else "🚀 FULL RUN"}
  Queries     : {len(queries)}  →  {', '.join(queries) or '(none)'}
  Locations   : {len(locations)}  →  {', '.join(locations) or '(none)'}
  Radius      : {dist} km (~{round(int(dist)*0.621)} miles)
  Per query   : {limit if not test_run else os.getenv("TEST_LIMIT", "5")} jobs/search
─────────────────────────────────────
  Total API calls : {total_searches}
  Max jobs to fetch: ~{total_jobs_est:,}
  (Adzuna free tier: 250 calls/month)
─────────────────────────────────────""")

    return ok


# ============================================================
# GEMINI EXTRACTION
# ============================================================

EXTRACTION_PROMPT = """You are a career search assistant. Below is a job seeker's profile and search objectives.

Extract structured information and return it as a single JSON object — no markdown, no extra text.

RESUME / PROFILE:
{resume}

SEARCH OBJECTIVES:
{objectives}

Return this exact JSON structure:
{{
  "candidate_profile": "A concise summary of the candidate (no name) covering: degree, graduation date (essential for entry-level status), GPA, total full-time experience (state '0' or 'Entry-Level' clearly), key skills, and target industries. This profile will be used to filter jobs, so be precise about seniority.",
  "search_queries": ["list", "of", "4-6", "adzuna", "search", "query", "strings"],
  "search_locations": ["City1", "City2", "City3"],
  "distance_km": 40
}}

BROADENING STRATEGY (CRITICAL):
For entry-level candidates or new grads, do NOT use overly specific queries like "entry level mechanical engineer in semiconductors" as they return very few results on job boards. 
Instead, generate broad, high-recall keyword phrases. The goal is to cast a wide net (return 100s of jobs) and let the Gemini filter in the next step do the heavy lifting of finding the specific gems.

FEW-SHOT EXAMPLES:

Example 1 (New Grad Mechanical Engineer):
  Search Objectives: "Looking for entry level mechanical engineering roles in robotics."
  Good Queries: ["entry level engineer", "new grad engineer", "junior engineer", "mechanical engineer junior", "robotics engineer entry"]
  Bad Queries: ["entry level mechanical engineer robotics"]

Example 2 (Packaging Engineer):
  Search Objectives: "I want to be a package engineer in semiconductors."
  Good Queries: ["packaging engineer", "semiconductor engineer", "hardware engineer", "package design", "manufacturing engineer"]
  Bad Queries: ["new grad packaging engineer in semiconductors"]

Rules:
- search_queries: 2-4 word keyword phrases. For entry-level candidates, ensure at least 3 queries are broad (e.g., "entry level engineer", "junior engineer").
- search_locations: city names only (e.g. "New York", "Dallas", "San Jose") — no states.
- candidate_profile: used internally as context for the LLM filter. Focus on degree and skills.
- distance_km: integer, ~40 for 25-mile radius.
"""


def extract_parameters_with_gemini(resume_text: str, objectives_text: str) -> dict:
    """Ask Gemini to extract structured search params from objectives + resume."""
    prompt = EXTRACTION_PROMPT.format(
        resume=resume_text or "(not provided)",
        objectives=objectives_text or "(not provided)"
    )
    print("\n🤖 Asking Gemini to analyze your objectives and resume...")
    raw = call_gemini(prompt)
    try:
        result = parse_json_response(raw)
        print("  ✓ Gemini extraction successful")
        return result
    except Exception as e:
        print(f"  ❌ Failed to parse Gemini response: {e}")
        print(f"  Raw response:\n{raw[:500]}")
        return {}


# ============================================================
# WRITE BACK
# ============================================================

def update_env(extracted: dict) -> None:
    """Write extracted search params back into .env."""
    env_text = ENV_PATH.read_text(encoding="utf-8")

    updates = {
        "SEARCH_QUERIES":   ",".join(extracted.get("search_queries", [])),
        "SEARCH_LOCATIONS": ",".join(extracted.get("search_locations", [])),
        "DISTANCE_KM":      str(extracted.get("distance_km", 40)),
    }

    for key, value in updates.items():
        pattern = rf"^({re.escape(key)}\s*=).*$"
        replacement = rf"\g<1>{value}"
        new_text, n = re.subn(pattern, replacement, env_text, flags=re.MULTILINE)
        if n:
            env_text = new_text
        else:
            # Key not found — append it
            env_text += f"\n{key}={value}\n"

    ENV_PATH.write_text(env_text, encoding="utf-8")
    print(f"  ✓ .env updated with new search parameters")


def update_candidate_profile(profile_text: str) -> None:
    """Save the candidate profile to a dedicated text file."""
    CANDIDATE_PROFILE_PATH.write_text(profile_text, encoding="utf-8")
    print(f"  ✓ Candidate profile saved to {CANDIDATE_PROFILE_PATH.name}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║          🔧  JOB SEARCH INITIALIZER                      ║
║     Reads your objectives → Generates search params      ║
╚══════════════════════════════════════════════════════════╝
""")

    # ── 1. Check Gemini key exists first (need it for extraction)
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY is missing from .env — cannot continue.")
        sys.exit(1)

    # ── 2. Read source files
    print("📄 Reading your profile and objectives...")
    objectives_text = read_objectives()
    resume_text     = read_pdf_text()

    if not objectives_text and not resume_text:
        print("❌ Neither search_objectives.txt nor my_profile.pdf could be read.")
        sys.exit(1)

    # ── 3. Gemini extraction
    extracted = extract_parameters_with_gemini(resume_text, objectives_text)

    if not extracted:
        print("\n⚠️  Gemini extraction failed. Skipping parameter update.")
        print("    Proceeding to validation with your current .env settings.\n")
    else:
        # ── 4. Preview extracted parameters
        print(f"""
📌 Gemini Suggested Parameters
─────────────────────────────────────────────────
  Search queries   : {', '.join(extracted.get('search_queries', []))}
  Locations        : {', '.join(extracted.get('search_locations', []))}
  Distance (km)    : {extracted.get('distance_km', 40)}
  
  Candidate profile preview:
    {chr(10).join('    ' + line for line in extracted.get('candidate_profile', '').splitlines()[:5])}
    ...
─────────────────────────────────────────────────""")

        # ── 5. Confirm before writing
        print(f"\nDo you want to apply these to .env and {CANDIDATE_PROFILE_PATH.name}?")
        print(f"  [Y] Yes — update .env + {CANDIDATE_PROFILE_PATH.name}")
        print("  [N] No  — keep current settings")
        choice = input("  Your choice [Y/n]: ").strip().lower()

        if choice in ("y", "yes", ""):
            print("\n✏️  Applying updates...")
            update_env(extracted)
            if extracted.get("candidate_profile"):
                update_candidate_profile(extracted["candidate_profile"])
            # Reload env so validation sees the new values
            load_dotenv(override=True)
            print()
        else:
            print("\n  Skipped — keeping current .env values.\n")

    # ── 6. Validate final state
    env_ok = print_validation_report()

    if env_ok:
        print("""
✅ All checks passed! You're ready to run:

    uv run python run_search.py

""")
    else:
        print("""
❌ Fix the errors above in your .env before running run_search.py.
""")
        sys.exit(1)


if __name__ == "__main__":
    main()
