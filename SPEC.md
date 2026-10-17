# SPEC — Safe route home (Berkeley)

> Every coding agent (Claude Code, Codex, Gemini CLI) reads this file first.

## One-liner
"The fastest route is not the safest route." A mobile-first web app that computes a safety-aware walking route at night, explains why, and lets people walk home together.
**Our algorithm computes routes and scores. Gemini only translates (text → weights, comment → tags, facts → explanation). People decide what feels safe, report what data can't see, and look out for each other.**

## Demo story
A student gets off BART at Downtown Berkeley at 11 pm to walk back to the Unit 3 residence halls. The fastest route crosses the Grinnell Natural Area and campus woods in the dark. Our app proposes a route that stays on streets, explains why, and matches her with two other students going the same way, with a safe meeting point.

Demo zone: UC Berkeley campus, Downtown, Southside, Northside — 3 × 3 km box centered on (37.8705, -122.2600) → `data/graph_raw.pkl` (5,396 nodes, 14,452 edges, 2.5 MB).
**Demo route (verified on the graph):** Downtown Berkeley BART (37.8701, -122.2681) → Unit 3 (37.8669, -122.2560). Fastest = 1,495 m with ~420 m through the Grinnell Natural Area and an unnamed campus wood; avoiding parks/woods = 1,530 m (+2 %). Backup: Channing & Telegraph (37.8668, -122.2588) → Downtown BART, same crossing.

## Team split
- **Data**: download + clean Berkeley sources → `data/clean/`
- **Scoring**: `backend/scoring.py` (done, see Contract 2)
- **Implementation**: graph + A* (`backend/graph.py`, `backend/routing.py`, `scripts/`), API, Gemini (`backend/llm.py`), matching, frontend (`static/`), deploy (Render)

## Contract 1 — data/clean (Data → Implementation)
`data/clean/points.csv`
| column | type | notes |
|---|---|---|
| lat, lon | float | WGS84 |
| kind | str | `crime`, `light_outage`, `lamp`, `venue_late`, `help` |
| hour | int 0–23 | only for `crime` (empty otherwise) |
| source | str | dataset name, e.g. `berkeley_pd`, `osm` |

- `crime`: Berkeley open data found by the data teammate (document the exact dataset in README → Data sources). Last 12 months, **pedestrian-safety categories only** (assault, robbery, sex offense, weapons); exclude vehicle and property crimes, drugs.
- `light_outage`, `lamp`: Berkeley sources if available; `lamp` can also come from OSM `highway=street_lamp`.
- `venue_late`: OSM bars/restaurants/shops open at night (`opening_hours`; if missing, bars/pubs/nightclubs = open until 2 am, flagged as heuristic). `help`: OSM police, hospital, clinic, pharmacy, fire station, plus campus emergency phones if available.
- **If a source does not exist for Berkeley, leave that kind out of the file** — the implementation then sets the feature to `None` (unknown) instead of `0` (which would read as "no lamps = dark everywhere").

`data/clean/parks.geojson` (data teammate): OSM `leisure=park` polygons. `data/clean/woods.geojson` (downloaded by `scripts/attach_features.py`): OSM `natural=wood|scrub`, `landuse=forest`, `leisure=nature_reserve` — **campus groves (Grinnell Natural Area…) are `natural=wood`, not parks**, and they are what makes the demo route differ.

## Contract 2 — scoring (Scoring → Implementation)
`backend/scoring.py` (implemented): `RELIABILITY`, `DEFAULT_WEIGHTS`, `edge_risk(f, w, night) -> (risk, breakdown)`.
Edge features `f` (computed by `scripts/attach_features.py`):
| feature | value |
|---|---|
| `lit` | 1 / 0 / None from OSM. **None on ~92 % of Berkeley edges = unknown, not dark** |
| `lamps`, `outages`, `venues_late` | counts within 50 m, or None if the source is missing |
| `help` | **normalized proximity in [0, 1]**: `exp(-distance_to_nearest_help_m / 300)` |
| `in_park` | bool: at least half of the edge inside parks ∪ woods (not "within 30 m", which would penalize the lit streets along a park) |
| `crime` | **normalized in [0, 1]** upstream: `min(1, log(1+n) / log(1+P95))`, n = night-band incidents at the edge's 2 end nodes |
| `length` | meters |

**`scripts/attach_features.py` (done)** builds `data/graph.pkl` from `graph_raw.pkl` + the data layer, joined on `segment_id` (100 % match):
- `lamps` / `outages`: counts within 30 m / 50 m, **None when 0** (OSM maps few lamps; no outage report ≠ working light).
- `venues_late`: teammate's `n_lively_open_23h`. `help`: nearest help point **available at 23:00 whatever its hours** (emergency phones, police, fire stations, hospitals), `exp(-d/300)`.
- `crime`: **simulated** points, night hours, assault/robbery/harassment only, snapped to intersections, log-normalized.
- `seed_reports`: **simulated** past community reports per edge; the API turns each into a 0.1 penalty.
- `G.graph["meta"]["simulated_factors"] = ["crime", "outage"]`: the API flags them `simulated`, the UI shows a badge, Gemini says so.

`risk` = reliability-weighted mean of the known factors (0.5 if nothing is known); `breakdown["_meta"]` has `factor_risks`, `weights`, `confidence`, `safety_score`.

Routing cost (`backend/routing.py`): `cost = length * (1 + LAMBDA * (risk + human_penalty))`, LAMBDA = 3 at night (20:00–06:00), 0.5 by day. Safe route capped at 1.4 × fastest length (halve LAMBDA and retry).

## Contract 3 — API (backend ↔ frontend)
All coordinates are `[lat, lon]`.
- `POST /route {origin, dest, profile_text, time}` → `{fast_path, safe_path, fast, safe, options: [{id: fastest|balanced|lively|safest, label, recommended, path, summary}], same_route, lambda, explanation, weights, coverage_warning}` (`options` only lists genuinely different routes; all scored with the person's weights) where `fast`/`safe` = `{length_m, duration_min, score, confidence, factors: [{name, risk, coverage, reliability}], coverage_warning, streets}` (`risk` None when no data on the route; each factor also has `simulated`), `park_m` (meters through parks/woods), plus `profile: {weights, max_detour, unsupported_needs, summary, source}` (show `summary` so the user can correct it) and `explanation_source`. **Implemented with Gemini.**
- `POST /report {lat, lon, comment}` → `{segment: {u, v, geometry, name}, tags, severity, source, updated_penalty}`. **Implemented** (Gemini tags, keyword fallback); the frontend then calls `/route` again.
- `GET /layers` → `{points: {lamp, light_outage, venue_late, help: [[lat, lon], ...]}, parks: GeoJSON (parks + woods) | null, reports: [segment geometry, ...] (simulated)}` from `data/clean/` (max 4,000 points per kind). **Crime is never exposed as map points.** **Implemented.**
- `POST /match {user_id, origin, dest, window: [start, end], profile: {gender?, same_gender_only?}}` → `{group: [{user_id, name, origin, window, pace, languages, shared_m}], meeting_point: {lat, lon, label}, shared_route, shared_m, meeting_point_facts, excluded_for_preferences, explanation, explanation_source, safeguards}`; when nobody matches: `group: []` + `safewalk: {label, phone}` (real UCPD escort service). **Implemented** (`backend/matching.py` on `data/mock_users.json`): windows overlap ±15 min, starts within 400 m, everyone's group preferences respected, score = shared safe-route length 60 % + start proximity 25 % + pace 15 %, meeting point = safest node near the start that the whole group walks through.
- `POST /trip/feedback {trip_id, sliders: {safe, alone, respected}, comment}` → `{tags, updated_penalties}` (mock).

## Scope
- Tier 1 (must work by T+40): fast vs safe route, score /10, factor breakdown with reliability, Gemini explanation, profile → weights, deployed on Render.
- Tier 2 (T+40–T+60): report → penalty → route changes on screen; walk-together matching with `data/mock_users.json`; post-trip sliders.
- Tier 3 (roadmap only, shown in the video): accessibility/slopes, transit, weather, events, ML risk model, real SOS / trip sharing / email verification.

## Rules for coding agents
- Read this file before any task. Respect the 3 contracts exactly; never change them silently.
- Small, testable changes; run the app after each one. Do not refactor working code.
- Free tools only: Gemini API free tier (`google-genai`), key in env var `GEMINI_API_KEY`. No paid APIs. Never commit `.env`. Use `backend/llm.py`: models `gemini-flash-lite-latest` (~1 s) then `gemini-3.1-flash-lite`; `gemini-flash-latest` was overloaded (503/504). Answers are cached in `data/llm_cache.json`.
- Any script that downloads data starts with `import truststore; truststore.inject_into_ssl()` (otherwise SSL CERTIFICATE_VERIFY_FAILED on this network).
- Gemini never computes routes or scores and never invents safety/accessibility facts: explanations use only the facts JSON passed in, otherwise say "no information".
- Every Gemini call has a deterministic fallback (default weights, template explanation) so the demo never breaks.
- Production deps stay light and pinned (`requirements.txt`: what Render installs). Data-pipeline libraries (OSMnx, geopandas, pandas, pyarrow…) go in `requirements-dev.txt` only — never replace `requirements.txt`.
- `.gitignore` must keep ignoring `.env`.
- Never label a neighborhood "dangerous"; crime data is "reported incidents", low reliability.
- Git: never `git add -A` / `git add .`; stage only the files you changed; `git pull --rebase` before pushing (teammates push to the same `main`).
- After finishing a task: tick it in `TODO.md` (your own section only, update "Dernière mise à jour"), and update `README.md` if setup, structure, data sources or the live URL changed.
