"""FastAPI app: API endpoints + serves the frontend in static/. /route and /report use the real graph; /match and /trip/feedback are still mocks."""
import csv
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import graph, llm, matching, routing
from backend.scoring import DEFAULT_WEIGHTS

ROOT = Path(__file__).resolve().parent.parent

# Human penalties per street segment (routing.pair_key -> [0, 1]), raised by /report. In memory: reset on restart.
PENALTIES = {}
REPORT_STEP = 0.4  # penalty added per report, times severity
SEED_STEP = 0.1  # per SIMULATED past community report (data/processed/user_reports.csv, via graph.pkl)
_seeded = False


def get_graph():
    """Load the graph once and seed PENALTIES with the simulated past community reports."""
    global _seeded
    G = graph.load_graph()
    if not _seeded:
        for u, v, k, d in G.edges(keys=True, data=True):
            if d.get("seed_reports"):
                key = routing.pair_key(u, v)
                PENALTIES[key] = max(PENALTIES.get(key, 0.0), min(1.0, SEED_STEP * d["seed_reports"]))
        _seeded = True
    return G

app = FastAPI(title="Safe route home")


@app.middleware("http")
async def no_stale_frontend(request, call_next):
    """Browsers revalidate every file (cheap thanks to ETags), so a new deploy shows up on a normal refresh."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


class RouteRequest(BaseModel):
    origin: list[float]  # [lat, lon]
    dest: list[float]
    profile_text: str = ""
    time: str = "23:00"


class MatchRequest(BaseModel):
    user_id: str
    origin: list[float]
    dest: list[float]
    window: list[str]  # ["23:00", "23:20"]
    profile: dict = {}


class ReportRequest(BaseModel):
    lat: float
    lon: float
    comment: str


class FeedbackRequest(BaseModel):
    trip_id: str
    sliders: dict  # {"safe": 0-10, "alone": 0-10, "respected": 0-10}
    comment: str = ""


def route_facts(summary: dict) -> dict:
    """Compact facts sent to Gemini (small prompt, stable cache key)."""
    return {
        "length_m": summary["length_m"],
        "duration_min": summary["duration_min"],
        "score": summary["score"],
        "confidence": summary["confidence"],
        "meters_through_parks_or_woods": summary["park_m"],
        "factors": {f["name"]: {"risk": f["risk"], "coverage": f["coverage"], "simulated": f["simulated"]}
                    for f in summary["factors"]},
        "streets": summary["streets"][:6],
    }


@app.get("/health")
def health():
    return {"ok": True}


# Map overlays. Crime points are deliberately NOT exposed: we never show "dangerous spots" on a map.
LAYER_KINDS = ["lamp", "light_outage", "venue_late", "help"]
MAX_POINTS = 4000


@app.get("/layers")
def layers():
    out = {"points": {k: [] for k in LAYER_KINDS}, "parks": None, "reports": []}
    clean = ROOT / "data" / "clean"
    if (clean / "points.csv").exists():
        with open(clean / "points.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pts = out["points"].get(row.get("kind"))
                if pts is not None and len(pts) < MAX_POINTS:
                    try:
                        pts.append([round(float(row["lat"]), 6), round(float(row["lon"]), 6)])
                    except (KeyError, TypeError, ValueError):
                        pass
    # Parks (OSM leisure=park) + campus woods (OSM natural=wood...) in one overlay
    features = []
    for name in ("parks.geojson", "woods.geojson"):
        if (clean / name).exists():
            features += json.loads((clean / name).read_text(encoding="utf-8"))["features"]
    if features:
        out["parks"] = {"type": "FeatureCollection", "features": features}
    # Segments with SIMULATED past community reports (one per street, not per direction)
    G, seen = get_graph(), set()
    for u, v, k, d in G.edges(keys=True, data=True):
        if d.get("seed_reports") and routing.pair_key(u, v) not in seen:
            seen.add(routing.pair_key(u, v))
            out["reports"].append(d["geometry"])
    return out


@app.post("/route")
def route(req: RouteRequest):
    G = get_graph()
    source, target = graph.nearest_node(*req.origin), graph.nearest_node(*req.dest)
    night = routing.is_night(req.time)
    profile = llm.profile_to_weights(req.profile_text)  # Gemini translates text -> weights; routing stays ours
    r = routing.plan(G, source, target, profile["weights"], night, PENALTIES, profile["max_detour"])
    facts = {
        "night": night,
        "same_route": r["same_route"],
        "fast": route_facts(r["fast"]),
        "safe": route_facts(r["safe"]),
        "unsupported_needs": profile["unsupported_needs"],
        "profile_summary": profile["summary"],
    }
    r["explanation"], r["explanation_source"] = llm.explain_route(facts)
    r["profile"] = profile
    r["weights"] = profile["weights"] or DEFAULT_WEIGHTS
    r["coverage_warning"] = r["safe"]["coverage_warning"]
    return r


SAFEGUARDS = [
    "Verified @berkeley.edu email for everyone",
    "Public meeting point, chosen for light, open venues and help nearby",
    "Trip shared live with a trusted contact",
    "Report or block anyone, any time",
]
# Real campus service, shown when nobody is going your way (https://nightsafety.berkeley.edu)
SAFEWALK = {"label": "Request a free SafeWalk escort (UC Police, dusk to 3 am)", "phone": "510-642-9255"}


@app.post("/match")
def match(req: MatchRequest):
    G = get_graph()
    me = {"user_id": req.user_id, "origin": req.origin, "dest": req.dest, "window": req.window, "profile": req.profile}
    m = matching.find_group(G, me, routing.is_night(req.window[0]), PENALTIES)
    m["safeguards"] = SAFEGUARDS
    if not m["group"]:
        m["explanation"], m["explanation_source"] = (
            "Nobody is going your way at this time yet. You can still request a SafeWalk escort.", "fallback")
        m["safewalk"] = SAFEWALK
        return m
    facts = {
        "you_leave_between": req.window,
        "group": [{"name": p["name"], "leaves_between": p["window"], "pace": p["pace"],
                   "meters_of_tonights_route_in_common": p["shared_m"]} for p in m["group"]],
        "meeting_point": m["meeting_point"]["label"],
        "meeting_point_surroundings": m["meeting_point_facts"],
        "people_not_matched_because_of_their_group_preferences": m["excluded_for_preferences"],
    }
    m["explanation"], m["explanation_source"] = llm.explain_match(facts)
    return m


@app.post("/report")
def report(req: ReportRequest):
    G = get_graph()
    u, v, k = graph.nearest_edge(req.lat, req.lon)
    t = llm.comment_to_tags(req.comment)
    key = routing.pair_key(u, v)
    PENALTIES[key] = min(1.0, PENALTIES.get(key, 0.0) + REPORT_STEP * t["severity"])
    return {
        "segment": {"u": u, "v": v, "geometry": G.edges[u, v, k]["geometry"], "name": G.edges[u, v, k].get("name")},
        "tags": t["tags"],
        "severity": t["severity"],
        "source": t["source"],
        "updated_penalty": round(PENALTIES[key], 2),
    }


@app.post("/trip/feedback")
def trip_feedback(req: FeedbackRequest):
    # TODO: llm.comment_to_tags -> update penalties along the trip
    return {"tags": [], "updated_penalties": {}}


# Mounted last so API routes take precedence
app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
