"""Edge risk scoring (owner: scoring teammate). See SPEC.md, Contract 2.

contribution(factor) = w[factor] * RELIABILITY[factor] * factor_risk, each factor_risk in [0, 1]
"""

# How much we trust each source (crime is low: reporting and patrolling bias)
RELIABILITY = {
    "light": 0.7,    # OSM lit tag + street lamps, incomplete coverage
    "outage": 0.6,   # SF311 streetlight reports
    "lively": 0.6,   # OSM venues open late, opening_hours often missing
    "help": 0.9,     # OSM police / hospital / pharmacy
    "park": 0.9,     # OSM park polygons
    "crime": 0.4,    # SFPD reported incidents
}

# Factor importance, overridden by the user profile (llm.profile_to_weights)
DEFAULT_WEIGHTS = {
    "light": 0.25,
    "outage": 0.10,
    "lively": 0.20,
    "help": 0.15,
    "park": 0.15,
    "crime": 0.15,
}


def edge_risk(f: dict, w: dict, night: bool) -> tuple[float, dict]:
    """f: lit (1/0/None), lamps, outages, venues_late, help, in_park, crime, length.
    Returns (risk, breakdown) with breakdown = {factor: contribution}."""
    raise NotImplementedError
