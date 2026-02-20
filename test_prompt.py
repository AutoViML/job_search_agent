#!/usr/bin/env python3
import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

CANDIDATE_PROFILE = """
Candidate: Purdue University, BS Mechanical Engineering + Manufacturing minor
GPA: 3.52 | Graduating: May 2026 (entry-level / new-graduate)
Total Experience: 0 years full-time.
"""

# Replicating the prompt from run_search.py for testing
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

Return a JSON object with:
{{
  "decision": "SELECTED" or "REJECTED",
  "reasoning": "Explain exactly why you made this choice based on the rules."
}}
"""

def test_job_file(file_path:str):
    path = Path(file_path)
    if not path.exists():
        print(f"Error: {file_path} not found. Please create {file_path} and paste the job description there.")
        return

    print(f"Reading {file_path}...")
    content = path.read_text(encoding="utf-8")
    
    job_summary = [{
        "id": "TEST_ID",
        "title": "Manufacturing Engineer, Product Quality (Semiconductor)",
        "company": "CyberCoders",
        "location": "New York, NY",
        "description_snippet": content[:2000] # simulating the extended snippet
    }]

    prompt = FILTER_PROMPT_TEMPLATE.format(
        profile=CANDIDATE_PROFILE,
        jobs_json=json.dumps(job_summary, indent=2)
    )

    print(f"Calling Gemini ({GEMINI_MODEL})...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        print("\n" + "="*50)
        print("GEMINI DECISION:")
        print("="*50)
        # Try to parse as JSON or just print text
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
        
        try:
            result = json.loads(text)
            print(f"STATUS    : {result.get('decision')}")
            print(f"REASONING : {result.get('reasoning')}")
        except:
            print(text)
        print("="*50)
    except Exception as e:
        print(f"API Error: {e}")

if __name__ == "__main__":
    target = "test_job.txt"
    if len(sys.argv) > 1:
        target = sys.argv[1]
    test_job_file(target)
