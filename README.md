# Safe Route Home

Google DeepMind hackathon @ UC Berkeley, October 2026 — *"The Human Side of Building with AI"*

**"The fastest route is not the safest route."** A mobile-first web app that computes a safety-aware walking route at night in San Francisco, explains why, and lets people walk home together.

- **🎥 Demo video:** _coming soon_
- **🌐 Live app:** _coming soon (Render)_
- **📋 Team status:** [TODO.md](TODO.md) · **🧠 Judgment log:** [DECISIONS.md](DECISIONS.md) · **📐 Spec and contracts:** [SPEC.md](SPEC.md)

## The problem
A student leaves a bar on Valencia St at 11 pm to walk home to the Castro. A standard maps app sends her through Dolores Park in the dark because it is 3 minutes shorter.

## Why AI alone is not enough
- **Our algorithm** (A* on a weighted street graph) computes routes and scores. It is rule-based and explainable.
- **Gemini only translates**: free-text profile → factor weights, a user's comment → tags, computed facts → plain-language explanation. It never computes a route and never invents a safety fact.
- **People** decide what feels safe for them, report what data cannot see (a broken light, a street that felt isolated), and look out for each other by walking together.

## How it works
1. **Precompute** (local): OSMnx walking graph of Mission / Castro / Dolores Park, with public data attached to each street segment.
2. **Score**: each factor's contribution = importance (from the user's profile) × reliability of the data source × factor risk.
3. **Route**: A* for the fastest route (length) and the safest route (length × (1 + λ · risk)), with a maximum detour of 40 %.
4. **Explain**: score out of 10, breakdown per factor with its reliability, and a Gemini explanation grounded only in those facts.
5. **Human loop**: a report on a segment raises its penalty, and the route visibly changes.
6. **Walk together**: people going the same way at the same time are matched, with a lit, public meeting point.

## Data sources
| Factor | Source | Reliability |
|---|---|---|
| Reported incidents | DataSF SFPD Incident Reports 2018–present (`wg3w-h783`), pedestrian-safety categories only | 0.4 (reporting and patrolling bias) |
| Streetlight outages | DataSF SF311 Cases (`vw6y-z8j6`), streetlight category | 0.6 |
| Lighting | OpenStreetMap `lit` tag and street lamps | 0.7 |
| Lively streets | OpenStreetMap venues open late | 0.6 |
| Help points | OpenStreetMap police, hospitals, pharmacies, fire stations | 0.9 |
| Parks | OpenStreetMap | 0.9 |
| User reports | This app | grows with the number of reports |

## Judgment calls
See [DECISIONS.md](DECISIONS.md). The 3 strongest will be summarized here.

## Repository structure
```
backend/   api.py (FastAPI + serves static/), graph.py, routing.py (A*), scoring.py, llm.py (Gemini), matching.py
scripts/   build_graph.py, attach_features.py (run locally, need requirements-dev.txt)
data/      clean/ (processed sources), raw/ (not committed), mock_users.json, graph.pkl
static/    index.html, app.js, style.css (Leaflet map)
demo/      demo_script.md
```

## Run locally
Python 3.14 (same as Render, see `.python-version`).
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt   # app + local data scripts (OSMnx, pandas)
copy .env.example .env                # add your GEMINI_API_KEY from https://aistudio.google.com
uvicorn backend.api:app --reload
```
Open http://localhost:8000. To rebuild the data: run `scripts/build_graph.py` then `scripts/attach_features.py`.
If PowerShell blocks the activation script: `Set-ExecutionPolicy -Scope Process Bypass`.

## Deploy
Render → New → Blueprint → this repo (reads `render.yaml`) → set `GEMINI_API_KEY`. Render installs only `requirements.txt` (pinned versions, so `data/graph.pkl` loads with the same networkx/numpy it was built with).

## Limits and ethics
- The score is an estimate from partial data and user reports, **not a guarantee of safety**.
- Crime data reflects where incidents are reported and where police patrol, not actual risk. We use it filtered, aggregated and with low weight, and we **never label a neighborhood "dangerous"**.
- Meeting strangers is risky: verified university email, public meeting points, trip sharing with a trusted contact, SOS and block are part of the design (shown in the demo, not yet functional).
- Minimal personal data; location is shared only during a trip.

## Team
_names_
