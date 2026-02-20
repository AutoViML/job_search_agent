# 🤖 Adzuna Gemini Job Search Agent
-- created by Ram Seshadri (2026)

> **Find the best-matched job listings from Adzuna — automatically.**
>
> Searches multiple roles and locations, uses Gemini AI to cut through the noise, and delivers a clean CSV file you can click through in seconds.

---

## ✨ How It Works

```
1. init_search.py  →  Reads your resume (should be named my_profile.pdf file) + objectives (should be named search_objectives.txt file), generates smart search params, validates config
2. run_search.py   →  Fetches jobs from Adzuna, filters with Gemini AI, writes curated_matches.csv
```

That's it. Two scripts. One CSV with only the jobs worth your time.

---

## 🔑 Step 1 — Get Your API Keys

You need two free API keys before anything else.

### Gemini API Key (Google AI Studio)
1. Go to **[aistudio.google.com](https://aistudio.google.com/)**
2. Sign in with your Google account
3. Click **"Get API key"** → **"Create API key"**
4. Copy the key — it starts with `AIzaSy...`

### Adzuna API Key (Job Search)
1. Go to **[developer.adzuna.com](https://developer.adzuna.com/)**
2. Click **"Register"** and create a free account
3. After signup, go to **Dashboard → My Apps → Create App**
4. Copy both your **App ID** (numbers) and **API Key** (long string)
5. Free tier: **250 API calls/month** — enough for ~12 full runs

---

## ⚙️ Step 2 — Configure Your Search

### 2a. Install dependencies
```bash
# Requires Python 3.10+ and uv
uv sync
```

### 2b. Set up your `.env` file
Create a `.env` file in the project root (copy from `.env.example` if it exists):

```bash
# ── API Keys ─────────────────────────────────────
GEMINI_API_KEY=your-gemini-key-here
ADZUNA_APP_ID=your-adzuna-app-id
ADZUNA_API_KEY=your-adzuna-api-key

# ── Run Mode ──────────────────────────────────────
TEST_RUN=True      # True = quick 5-job test | False = full run
TEST_LIMIT=5       # Jobs per query in test mode

# ── Adzuna Limits ─────────────────────────────────
ADZUNA_LIMIT_PER_SEARCH=50    # Max 50 per search (Adzuna hard cap)
ADZUNA_MONTHLY_CALLS_LIMIT=250

# ── Search Parameters (auto-filled by init_search.py) ──
SEARCH_QUERIES=entry level engineer,new graduate engineer,product design engineer,packaging engineer
SEARCH_LOCATIONS=New York,New Jersey,Dallas,Austin,San Jose
DISTANCE_KM=40     # ~25 miles radius per location

# ── Gemini Settings ───────────────────────────────
GEMINI_MODEL=gemini-2.5-flash-lite
LLM_CHUNK_SIZE=20  # Jobs reviewed per Gemini batch (keep ≤ 20)
```

> **Never commit your `.env` file** — it's already in `.gitignore`.

### 2c. Add your resume and objectives

| File | What to do |
|------|-----------|
| `my_profile.pdf` | Drop your resume PDF here (stays private — excluded from git) |
| `search_objectives.txt` | Write in plain English: your target roles, industries, and preferred locations |

**Example `search_objectives.txt`:**
```
I'm a blah blah blah graduating in May 2026.
Looking for entry-level roles in:
- software industry
- Robotics and automation
- Product management

Preferred locations (in order):
1. New York / New Jersey metro
2. Dallas / Austin, Texas
3. Silicon Valley, California
```

---

## 🚀 Step 3 — Run It

### First time (or when objectives change):
```bash
uv run python init_search.py
```
This reads your resume + objectives, asks Gemini to generate smart search queries, validates your config, and gives you a full search plan preview. Type **Y** to apply it.

### Every search run:
```bash
# Quick test (5 jobs/query, ~4 seconds)
# Make sure TEST_RUN=True in .env
uv run python run_search.py

# Full search (~1,000 candidates, Gemini-filtered to best matches)
# Set TEST_RUN=False in .env
uv run python run_search.py
```

### Output files:
```
outputs/
  test_results/   curated_matches_YYYYMMDD_HHMMSS.csv   ← test runs
  search_results/ curated_matches_YYYYMMDD_HHMMSS.csv   ← full runs
```

Each CSV has exactly 5 columns: **Company | Role | Location | Salary | Link**

---

## 📁 Project Structure

```
job-search-agent/
├── init_search.py          # 🔧 Run first — reads your resume + objectives, validates configuration using Gemini AI
├── run_search.py           # 🚀 Run this to search and filter jobs using Adzuna API
├── search_objectives.txt   # ✏️  Edit this with your target roles and locations
├── my_profile.pdf          # 📄 Your resume (private — not committed to git)
├── .env                    # 🔑 Your API keys and search settings (private)
│
├── outputs/
│   ├── test_results/       # Test run CSVs
│   └── search_results/     # Full run CSVs
│
└── src/                    # Supporting modules (Adzuna tools, config, etc.)
```

---

## 🎛️ Adjusting Your Search

Everything is controlled from `.env` — no code changes needed.

| Want to... | Change this in `.env` |
|------------|----------------------|
| Search different roles | `SEARCH_QUERIES=role1,role2,role3` |
| Add a new city | Add it to `SEARCH_LOCATIONS` |
| Widen the radius | Increase `DISTANCE_KM` (80 = ~50 miles) |
| Get more results per query | `ADZUNA_LIMIT_PER_SEARCH=50` (max 50) |
| Switch to test mode | `TEST_RUN=True` |
| Use a different Gemini model | `GEMINI_MODEL=gemini-2.0-flash` |

---

## 🐛 Quick Troubleshooting

| Error | Fix |
|-------|-----|
| `GEMINI_API_KEY missing` | Add it to `.env` |
| `HTTP 401` from Adzuna | Double-check `ADZUNA_APP_ID` and `ADZUNA_API_KEY` |
| `0 jobs found` for a query | Query too specific — broaden it (e.g. `"mechanical engineer"` not `"mechanical engineer semiconductor NJ"`) |
| CSV has 0 rows | Gemini filtered everything out — widen your objectives in `search_objectives.txt` |
| `Module not found` | Run `uv sync` to install dependencies |

---

## 📊 API Usage Reference

| Config | API calls used | Est. unique jobs |
|--------|---------------|-----------------|
| 4 queries × 1 location | 4 calls | ~200 |
| 4 queries × 5 locations | 20 calls | ~700 |
| Free tier limit | 250 calls/month | ~12 full runs/month |

## New User's workflow
```bash
git clone <your-repo>
cp .env.example .env   # fill in your API keys
uv sync
uv run python init_search.py
uv run python run_search.py
```
---

*Built with Gemini AI + Adzuna Job Search API.*
