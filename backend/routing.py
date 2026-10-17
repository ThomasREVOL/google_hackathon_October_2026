"""A* routing on the walking graph.

fastest: weight = length
safest:  weight = length * (1 + LAMBDA * (risk + human_penalty)), LAMBDA = 3 at night, 0.5 by day
risk comes from backend.scoring.edge_risk (in [0, 1]); human_penalty comes from /report (in [0, 1]).
Heuristic = haversine distance to the target, admissible because cost >= length on every edge.
"""
import math

import networkx as nx

from backend.scoring import RELIABILITY, edge_risk

LAMBDA_NIGHT = 3.0
LAMBDA_DAY = 0.5
MAX_DETOUR = 1.4  # safe route length <= 1.4 x fastest, otherwise halve LAMBDA and retry
WALK_M_PER_MIN = 80  # ~4.8 km/h
LOW_COVERAGE = 0.3  # warn when a factor is known on less than 30 % of the route

_risk_cache = {}  # (graph id, weights, night) -> {(u, v, k): (risk, breakdown)}


def is_night(time_str: str) -> bool:
    """'23:00' -> True. Night = 20:00-06:00."""
    hour = int(time_str.split(":")[0])
    return hour >= 20 or hour < 6


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def pair_key(u, v):
    """Penalties apply to the street segment in both walking directions."""
    return (u, v) if u <= v else (v, u)


def edge_features(d: dict) -> dict:
    """Features expected by scoring.edge_risk; missing ones stay None (= unknown, not unsafe)."""
    f = dict(d.get("features") or {})
    f.setdefault("lit", d.get("lit"))
    f.setdefault("length", d["length"])
    return f


def compute_risks(G, weights: dict, night: bool) -> dict:
    """Risk + breakdown for every edge, cached per (weights, night) since the graph never changes."""
    key = (id(G), tuple(sorted((weights or {}).items())), night)
    if key not in _risk_cache:
        _risk_cache[key] = {
            (u, v, k): edge_risk(edge_features(d), weights, night)
            for u, v, k, d in G.edges(keys=True, data=True)
        }
    return _risk_cache[key]


def _heuristic(G):
    def h(a, b):
        na, nb = G.nodes[a], G.nodes[b]
        return haversine_m(na["y"], na["x"], nb["y"], nb["x"])
    return h


def _cost(risks: dict, penalties: dict, lam: float):
    def cost(u, v, d):
        pen = penalties.get(pair_key(u, v), 0.0)
        return min(e["length"] * (1 + lam * (risks[(u, v, k)][0] + pen)) for k, e in d.items())
    return cost


def path_length(G, path) -> float:
    return sum(min(e["length"] for e in G[u][v].values()) for u, v in zip(path, path[1:]))


def fastest_route(G, source, target) -> list:
    return nx.astar_path(G, source, target, heuristic=_heuristic(G), weight="length")


def safest_route(G, source, target, weights: dict, night: bool, penalties: dict) -> tuple[list, float]:
    """-> (path, lambda used). Lambda is halved until the detour is acceptable."""
    risks = compute_risks(G, weights, night)
    max_len = MAX_DETOUR * path_length(G, fastest_route(G, source, target))
    lam = LAMBDA_NIGHT if night else LAMBDA_DAY
    for _ in range(4):
        path = nx.astar_path(G, source, target, heuristic=_heuristic(G), weight=_cost(risks, penalties, lam))
        if path_length(G, path) <= max_len:
            return path, lam
        lam /= 2
    return fastest_route(G, source, target), 0.0


def _chosen_edges(G, path, risks, penalties, lam):
    """For each step, the parallel edge A* actually used (lowest cost), as (u, v, k, data)."""
    cost = _cost(risks, penalties, lam)
    for u, v in zip(path, path[1:]):
        k = min(G[u][v], key=lambda k: cost(u, v, {k: G[u][v][k]}))
        yield u, v, k, G[u][v][k]


def path_coords(G, path, risks=None, penalties=None, lam=0.0) -> list:
    """[[lat, lon], ...] along the real street geometry, for Leaflet."""
    risks = risks or compute_risks(G, {}, False)
    coords = []
    for u, v, k, d in _chosen_edges(G, path, risks, penalties or {}, lam):
        geom = d["geometry"]
        start = (G.nodes[u]["y"], G.nodes[u]["x"])
        # Make sure the geometry runs from u to v
        if haversine_m(*start, *geom[0]) > haversine_m(*start, *geom[-1]):
            geom = geom[::-1]
        coords.extend(geom if not coords else geom[1:])
    return coords


def route_summary(G, path, weights: dict, night: bool, penalties: dict, lam: float = 0.0) -> dict:
    """{length_m, duration_min, score (0-10), confidence, factors: [{name, risk, coverage, reliability}],
    coverage_warning, streets}. Scores are length-weighted over the edges of the route."""
    risks = compute_risks(G, weights, night)
    total = risk_sum = conf_sum = 0.0
    known_len = {f: 0.0 for f in RELIABILITY}
    factor_sum = {f: 0.0 for f in RELIABILITY}
    streets = []
    for u, v, k, d in _chosen_edges(G, path, risks, penalties, lam):
        length = d["length"]
        risk, breakdown = risks[(u, v, k)]
        meta = breakdown["_meta"]
        total += length
        risk_sum += length * min(1.0, risk + penalties.get(pair_key(u, v), 0.0))
        conf_sum += length * meta["confidence"]
        for f, r in meta["factor_risks"].items():
            if r is not None:
                known_len[f] += length
                factor_sum[f] += length * r
        if d.get("name") and (not streets or streets[-1] != d["name"]):
            streets.append(d["name"])

    total = max(total, 1e-9)
    factors = [
        {
            "name": f,
            "risk": round(factor_sum[f] / known_len[f], 2) if known_len[f] else None,
            "coverage": round(known_len[f] / total, 2),
            "reliability": RELIABILITY[f],
        }
        for f in RELIABILITY
    ]
    missing = [f["name"] for f in factors if f["coverage"] < LOW_COVERAGE]
    return {
        "length_m": round(total),
        "duration_min": round(total / WALK_M_PER_MIN),
        "score": round(10 * (1 - risk_sum / total), 1),
        "confidence": round(conf_sum / total, 2),
        "factors": factors,
        "coverage_warning": f"Little or no data on this route for: {', '.join(missing)}" if missing else None,
        "streets": streets,
    }


def plan(G, source, target, weights: dict, night: bool, penalties: dict) -> dict:
    """Fastest vs safest, ready for the /route response (explanation added by the API)."""
    fast = fastest_route(G, source, target)
    safe, lam = safest_route(G, source, target, weights, night, penalties)
    risks = compute_risks(G, weights, night)
    return {
        "fast_path": path_coords(G, fast, risks, penalties, 0.0),
        "safe_path": path_coords(G, safe, risks, penalties, lam),
        "fast": route_summary(G, fast, weights, night, penalties, 0.0),
        "safe": route_summary(G, safe, weights, night, penalties, lam),
        "lambda": lam,
        "same_route": fast == safe,
    }
