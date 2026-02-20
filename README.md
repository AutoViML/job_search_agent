# 🤖 Adzuna Gemini Job Search Agent

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/AI-Google_Gemini-4285F4?style=flat-square&logo=google-cloud&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/API-Adzuna-00A651?style=flat-square" alt="Adzuna">
  <img src="https://img.shields.io/badge/License-Apache_2.0-D22128?style=flat-square" alt="License">
</p>

---

### 🚀 Smart, Automated, and Deeply Personalized Job Hunting
**Adzuna Gemini Agent** is a high-performance career tool that bridges the gap between massive job databases and your specific career stage. By combining the **Adzuna API** with **Google's Gemini LLM**, it doesn't just find jobs—it *understands* them.

**Created by Ram Seshadri (2026)**

---

## ✨ How It Works

1.  **`init_search.py`** → Reads your `my_profile.pdf` and `search_objectives.txt`. It uses Gemini to generate optimized search parameters for `.env` and an AI-derived candidate profile (`_candidate_profile.txt`).
2.  **`run_search.py`** → The complete engine. It automatically detects your experience level using Gemini and applies one of three **STRICT FILTER** modes (NEW GRAD, MID-LEVEL, or SENIOR). It then fetches jobs from Adzuna and filters them in parallel.

---

## 🔑 Step 1 — Get Your API Keys

You need two free API keys: Google AI Studio (for Gemini) and Adzuna (for job search).

| Service | Where to get it | Notes |
|---------|-----------------|-------|
| **Gemini** | [aistudio.google.com](https://aistudio.google.com/) | Copy the key starting with `AIzaSy...` |
| **Adzuna** | [developer.adzuna.com](https://developer.adzuna.com/) | Get your **App ID** and **API Key** |

---

## ⚙️ Step 2 — Configure Your Search

### 2a. Install dependencies
```bash
uv sync   # Requires Python 3.10+ and uv
```

### 2b. Set up your `.env` file
Fill in your API keys. The search parameters below will be automatically populated by the initializer.

```bash
GEMINI_API_KEY=...
ADZUNA_APP_ID=...
ADZUNA_API_KEY=...

# Optional settings
TEST_RUN=True      # True = quick 5-job test | False = full run
SEARCH_QUERIES=...
SEARCH_LOCATIONS=...
```

### 2c. Add your resume and objectives

| File | What to do |
|------|-----------|
| `my_profile.pdf` | Drop your resume PDF here. |
| `search_objectives.txt` | Write your target roles, industries, and locations. |

---

## 🚀 Step 3 — Run It

### Initial Setup (or when objectives change):
```bash
uv run python init_search.py
```
This validates your configuration and creates your AI profile.

### Search & Filter:
```bash
uv run python run_search.py
```
*Note: The script automatically caches results. If you cancel and restart, it skips the fetching phase and resumes filtering from where you left off.*

---

## 📂 Project Structure & Privacy

```
├── run_search.py           # 🚀 Main engine (Fetching + Filtering)
├── init_search.py          # 🔧 Config initializer
├── _candidate_profile.txt   # 👤 AI-summarized profile (Private)
├── .env                    # 🔑 API Keys (Private)
├── outputs/                # 📄 CSV matches (Private)
```

**Privacy Note:** Your PDF resume, `.env` keys, `_candidate_profile.txt`, and the entire `outputs/` folder are automatically excluded from git via `.gitignore`. Your data stays local.

---

## 🎛️ Adjusting Your Search

Everything is controlled from `.env` and your source text files — no code changes needed.

| Want to... | Action |
|------------|--------|
| Change roles | Edit `search_objectives.txt` and run `init_search.py` |
| Switch to full run | Change `TEST_RUN=False` in `.env` |
| Widen the search radius | Change `DISTANCE_KM` in `.env` |
| Get more results per query | Change `ADZUNA_LIMIT_PER_SEARCH=50` (max 50) |
| Update your background | Edit `search_objectives.txt` or `my_profile.pdf` then run `init_search.py` |

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
This is not an endorsement of any company or organization. This is a tool created for educational purposes only. 