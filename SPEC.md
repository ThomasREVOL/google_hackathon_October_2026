# SPEC — Safe route home (San Francisco)

> Every coding agent (Claude Code, Codex, Gemini CLI) reads this file first.

## One-liner
"The fastest route is not the safest route." A mobile-first web app that computes a safety-aware walking route at night, explains why, and lets people walk home together.
**Our algorithm computes routes and scores. Gemini only translates (text → weights, comment → tags, facts → explanation). People decide what feels safe, report what data can't see, and look out for each other.**

## Demo story
A student leaves a bar on Valencia St at 11 pm to go home to the Castro. The fastest route crosses Dolores Park in the dark. Our app proposes a slightly longer route that is lit, lively and close to help points, explains why, and matches her with two other students going the same way, with a safe meeting point.

Demo zone: Mission / Castro / Dolores Park, ~2 km around (37.7600, -122.4269).

## Team split
- **Data** (teammate 2): download + clean sources → `data/clean/`
- **Scoring** (teammate 1): `backend/scoring.py`
- **Implementation**: graph + A* (`backend/graph.py`, `backend/routing.py`, `scripts/`), API, Gemini (`backend/llm.py`), matching, frontend (`static/`), deploy (Render)

## Contract 1 — data/clean (Data → Implementation)
`data/clean/points.csv`
| column | type | notes |
|---|---|---|
| lat, lon | float | WGS84 |
| kind | str | `crime`, `light_outage`, `lamp`, `venue_late`, `help` |
| hour | int 0–23 | only for `crime` (empty otherwise) |
| source | str | e.g. `sfpd`, `sf311`, `osm` |

- `crime`: SFPD Incident Reports 2018–present (DataSF `wg3w-h783`), last 12 months, **pedestrian-safety categories only** (assault, robbery, sex offense, weapons). Exclude vehicle break-ins, vehicle theft, drugs. Locations are snapped to the nearest intersection → attached to graph **nodes**.
- `light_outage`: SF311 cases (DataSF `vw6y-z8j6`), streetlight category, last 12 months.
- `lamp`: OSM `highway=street_lamp`. `venue_late`: OSM bars/restaurants/shops open at night (`opening_hours`; if missing, bars/pubs/nightclubs = open until 2 am, flagged as heuristic). `help`: OSM police, hospital, clinic, pharmacy, fire station.

`data/clean/parks.geojson`: park polygons (OSM `leisure=park`).

## Contract 2 — scoring (Scoring → Implementation)
`backend/scoring.py`
```python
RELIABILITY: dict[str, float]      # per factor, how much we trust the source (crime is low: reporting/patrolling bias)
DEFAULT_WEIGHTS: dict[str, float]  # per factor importance, overridden by the user profile (Gemini)
def edge_risk(f: dict, w: dict, night: bool) -> tuple[float, dict]: ...
```
Edge features `f`: `lit` (1/0/None), `lamps`, `outages`, `venues_late`, `help`, `in_park` (bool), `crime` (night-band count at the edge's 2 end nodes), `length` (m).
Returns `(risk, breakdown)` where breakdown is `{factor: contribution}`; contribution = `w[factor] * RELIABILITY[factor] * factor_risk` (each factor_risk in [0, 1]).

Routing cost (implementation): `cost = length * (1 + LAMBDA * (risk + human_penalty))`, LAMBDA = 3 at night, 0.5 by day. Safe route capped at 1.4 × fastest length (halve LAMBDA and retry).

## Contract 3 — API (backend ↔ frontend)
All coordinates are `[lat, lon]`.
- `POST /route {origin, dest, profile_text, time}` → `{fast_path, safe_path, fast, safe, explanation, weights, coverage_warning}` where `fast`/`safe` = `{length_m, duration_min, score, factors: [{name, value, reliability}]}`
- `POST /match {user_id, origin, dest, window, profile}` → `{group, meeting_point, shared_route, explanation, safeguards}`
- `POST /report {lat, lon, comment}` → `{segment, tags, severity, updated_penalty}`
- `POST /trip/feedback {trip_id, sliders: {safe, alone, respected}, comment}` → `{tags, updated_penalties}`

## Scope
- Tier 1 (must work by T+40): fast vs safe route, score /10, factor breakdown with reliability, Gemini explanation, profile → weights, deployed on Render.
- Tier 2 (T+40–T+60): report → penalty → route changes on screen; walk-together matching with `data/mock_users.json`; post-trip sliders.
- Tier 3 (roadmap only, shown in the video): accessibility/slopes, Muni Owl GTFS, weather, events, ML risk model, real SOS / trip sharing / email verification.

## Rules for coding agents
- Read this file before any task. Respect the 3 contracts exactly; never change them silently.
- Small, testable changes; run the app after each one. Do not refactor working code.
- Free tools only: Gemini API free tier (`google-genai`), key in env var `GEMINI_API_KEY`. No paid APIs. Never commit `.env`.
- Gemini never computes routes or scores and never invents safety/accessibility facts: explanations use only the facts JSON passed in, otherwise say "no information".
- Every Gemini call has a deterministic fallback (default weights, template explanation) so the demo never breaks.
- Production deps stay light (`requirements.txt`); OSMnx/pandas are only for local scripts (`requirements-dev.txt`).
- Never label a neighborhood "dangerous"; crime data is "reported incidents", low reliability.
- After finishing a task: tick it in `TODO.md` (your own section only, update "Dernière mise à jour"), and update `README.md` if setup, structure, data sources or the live URL changed.
