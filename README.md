# Safe Route Home

Google DeepMind hackathon @ UC Berkeley, October 2026 — *"The Human Side of Building with AI"*

**"The fastest route is not the safest route."** A mobile-first web app that computes a safety-aware walking route at night around UC Berkeley, explains why, and lets people walk home together.

- **🎥 Demo video:** _coming soon_
- **🌐 Live app:** https://safe-route-home.onrender.com (free instance: first load can take ~1 min) · API docs: https://safe-route-home.onrender.com/docs
- **📋 Team status:** [TODO.md](TODO.md) · **🧠 Judgment log:** [DECISIONS.md](DECISIONS.md) · **📐 Spec and contracts:** [SPEC.md](SPEC.md)

## The problem
A student gets off BART at Downtown Berkeley at 11 pm to walk back to the Unit 3 residence halls. The fastest route (1,495 m) sends her 426 m through the Grinnell Natural Area and campus woods in the dark. Our safer route avoids them entirely for only 50 m more — and by day, the app happily takes the shortcut.

## Why AI alone is not enough
- **Our algorithm** (A* on a weighted street graph) computes routes and scores. It is rule-based and explainable.
- **Gemini only translates**: free-text profile → factor weights (and it restates what it understood, so the person can correct it), a user's comment → tags, computed facts → plain-language explanation. It never computes a route and never invents a safety fact: when data is missing, the explanation says so. Every call has a deterministic fallback and a cache, so the app keeps working if Gemini is unavailable.
- **People** decide what feels safe for them, report what data cannot see (a broken light, a street that felt isolated), and look out for each other by walking together.

## How it works
1. **Precompute** (local): OSMnx walking graph of a 3 × 3 km box around UC Berkeley (campus, Downtown, Southside, Northside), with public data attached to each street segment.
2. **Score**: each factor's contribution = importance (from the user's profile) × reliability of the data source × factor risk.
3. **Route**: A* for the fastest route (length) and the safest route (length × (1 + λ · risk)), with a maximum detour of 40 %.
4. **Explain**: score out of 10, breakdown per factor with its reliability, and a Gemini explanation grounded only in those facts.
5. **Human loop**: a report on a segment raises its penalty, and the route visibly changes.
6. **Walk together**: people going the same way at the same time are matched, with a lit, public meeting point.

**Interface** (`static/`, Leaflet, no build step): night basemap (Esri Dark Gray Canvas) with "Night (detailed)" (OpenStreetMap with a dark filter), Light (OpenStreetMap) and Satellite (Esri) options — all free without API key, animated glowing safe route vs dashed fastest route, score cards, factor bars with data coverage and reliability, "Gemini understood" box, report mode (tap a street → Gemini tags → reroute), walk-together panel, and toggleable data layers (lamps, broken lights, open venues, help points, parks). Crime is never drawn on the map.

## Data sources
| Factor | Source | Reliability |
|---|---|---|
| Reported incidents | **Simulated placeholder** (60 points, `source=simulated`). Real sources to integrate: City of Berkeley Open Data, UCPD daily crime log. Never presented as real data | 0.4 (reporting and patrolling bias) |
| Streetlight outages | **Simulated placeholder** (15 points, `source=simulated`) | 0.6 |
| Lighting | OpenStreetMap `lit` tag (7.5 % of segments) and 78 street lamps | 0.7 |
| Lively streets | OpenStreetMap venues open at 23:00 (`opening_hours` parsed) | 0.6 |
| Help points | OpenStreetMap police, hospitals, pharmacies, fire stations (156) | 0.9 |
| Parks and campus woods | OpenStreetMap `leisure=park` (57 polygons) + `natural=wood` and similar (75 polygons, incl. the Grinnell Natural Area) | 0.9 |
| User reports | This app; 150 **simulated** demo reports in `data/processed/user_reports.csv` | grows with the number of reports |

Full data-layer documentation: [data/clean/README.md](data/clean/README.md), [scripts/data_sources.md](scripts/data_sources.md).

## Judgment calls
See [DECISIONS.md](DECISIONS.md). The 3 strongest will be summarized here.

## Repository structure
```
backend/   api.py (FastAPI + serves static/), graph.py, routing.py (A*), scoring.py, llm.py (Gemini), matching.py,
           data_loader.py (loads the data layer: graph, edges, POIs)
scripts/   data layer: config.py, build_graph.py, build_features.py, enrich_features.py, export_clean*.py,
           simulate_human_data.py, validate.py
           app: build_app_graph.py (light graph for the API), attach_features.py (run locally, need requirements-dev.txt)
data/      clean/ + clean_rich/ (simplified sources), processed/ (graph.graphml, edges/nodes/pois parquet, simulated reports),
           raw/ (not committed), mock_users.json, graph_raw.pkl (light OSM graph), graph.pkl (with features)
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
uvicorn backend.api:app --reload --reload-dir backend --reload-dir static
```
Open http://localhost:8000 (map) or http://localhost:8000/docs (try the API endpoints). To rebuild the data: run `scripts/build_graph.py` then `scripts/attach_features.py`.
If PowerShell blocks the activation script: `Set-ExecutionPolicy -Scope Process Bypass`.
If you get `SSL: CERTIFICATE_VERIFY_FAILED` (proxy or antivirus), add `import truststore; truststore.inject_into_ssl()` at the top of your script (already done in `backend/llm.py` and `scripts/build_graph.py`).

## Data pipeline (data layer, from repo root)
Needs `requirements-dev.txt`.
```bash
python -m scripts.build_graph        # street network -> data/processed/graph.graphml
python -m scripts.build_features     # POIs + edge features -> edges.parquet / .geojson
python -m scripts.enrich_features    # optional: slope, GTFS, incidents
python -m scripts.validate           # checks + debug map + data dictionary
```
Teammates load the data via `from backend.data_loader import load_graph, load_edges, load_pois, nearest_node`.
`edges` is indexed by `segment_id = f"{u}_{v}_{key}"`. Unknown values are NaN with a matching `*_known` flag — never zero.

The API itself only needs `data/graph_raw.pkl` / `data/graph.pkl` (built by `scripts/build_app_graph.py` and `scripts/attach_features.py`), so Render installs the light `requirements.txt`.

## Team git workflow
Everyone pushes to `main` (Render redeploys on every push), so:
1. `git pull --rebase` before starting and before every push.
2. Stage **only your own files**: `git add backend/scoring.py` — never `git add -A` / `git add .`.
3. `git commit -m "..."` then `git pull --rebase` then `git push`.
4. On a conflict in a shared file (README.md, TODO.md): keep both versions, then `git add <file>` and `git rebase --continue`.

## Deploy
**Option A — Blueprint:** Render → New → Blueprint → connect GitHub → this repo, branch `main` (reads `render.yaml`, free plan) → enter `GEMINI_API_KEY` → Deploy.
**Option B — manual Web Service** (if the Blueprint asks for a paid plan): Render → New → Web Service → this repo → Language Python 3, branch `main`, Build `pip install -r requirements.txt`, Start `uvicorn backend.api:app --host 0.0.0.0 --port $PORT`, Instance type Free, env var `GEMINI_API_KEY`, health check path `/health`.
Every push to `main` redeploys automatically. The free instance sleeps after 15 min idle (about 1 min to wake up) and has 512 MB RAM. Render installs only `requirements.txt` (pinned versions, so `data/graph.pkl` loads with the same networkx/numpy it was built with).

## Limits and ethics
- The score is an estimate from partial data and user reports, **not a guarantee of safety**.
- OpenStreetMap lighting data is very incomplete: only 7.5 % of street segments in our zone have a `lit` tag (88 % of those say "lit"). A missing tag means "unknown", never "dark".
- Sidewalks are mapped as separate unnamed footways (60 % of segments), so explanations name the nearest street rather than the footway.
- Each route shows a confidence level and a warning when a factor has little or no data on that route.
- Reported incidents, streetlight outages and the seeded user reports are **simulated** for the demo; they are labelled as such and never presented as real data.
- Crime data reflects where incidents are reported and where police patrol, not actual risk. We use it filtered, aggregated and with low weight, we **never label a neighborhood "dangerous"**, and we never draw incidents on the map.
- Meeting strangers is risky: verified university email, public meeting points, trip sharing with a trusted contact, SOS and block are part of the design (shown in the demo, not yet functional).
- Minimal personal data; location is shared only during a trip.

## Team
_names_
