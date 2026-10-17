"""A* routing on the walking graph.

fastest: weight = length
safest:  weight = length * (1 + LAMBDA * (risk + human_penalty)), LAMBDA = 3 at night, 0.5 by day
Heuristic = haversine distance to target, admissible because cost >= length on every edge.
"""

LAMBDA_NIGHT = 3.0
LAMBDA_DAY = 0.5
MAX_DETOUR = 1.4  # safe route length <= 1.4 x fastest, otherwise halve LAMBDA and retry


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    raise NotImplementedError


def fastest_route(G, source, target) -> list:
    raise NotImplementedError


def safest_route(G, source, target, night: bool, penalties: dict) -> list:
    raise NotImplementedError


def route_summary(G, path) -> dict:
    """{length_m, duration_min, score (0-10), factors: [{name, value, reliability}], coverage_warning}"""
    raise NotImplementedError
