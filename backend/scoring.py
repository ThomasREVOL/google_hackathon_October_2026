"""Edge risk scoring (owner: scoring teammate). See SPEC.md, Contract 2.

Each raw feature is converted into an interpretable factor risk in [0, 1].

contribution(factor) =
    w[factor] * RELIABILITY[factor] * factor_risk

Final risk is the reliability-weighted normalized mean of all
available factors.

IMPORTANT:
- risk is a relative routing cost, NOT a probability of harm.
- missing data is unknown, not unsafe.
- crime means reported incidents, which are subject to reporting
  and patrolling bias.
"""

import math


# ============================================================
# CONFIG
# ============================================================

RELIABILITY = {
    "light": 0.7,
    "outage": 0.6,
    "lively": 0.6,
    "help": 0.9,
    "park": 0.9,
    "crime": 0.4,
}


DEFAULT_WEIGHTS = {
    "light": 0.25,
    "outage": 0.10,
    "lively": 0.20,
    "help": 0.15,
    "park": 0.15,
    "crime": 0.15,
}


# ============================================================
# PARAMETERS
# ============================================================

# Saturation constants:
# risk/quality = 1 - exp(-count / K)

LAMP_K = 3.0
OUTAGE_K = 1.5
VENUE_K = 4.0

# Long segments amplify isolation-related signals slightly.
LONG_SEGMENT_START_M = 100.0
LONG_SEGMENT_FULL_M = 400.0


# ============================================================
# HELPERS
# ============================================================

def clamp(x: float) -> float:
    """Clamp a value to [0, 1]."""
    return max(0.0, min(1.0, x))


def saturation(count: float, k: float) -> float:
    """Smooth count -> [0,1] with diminishing returns."""
    count = max(0.0, float(count))
    return 1.0 - math.exp(-count / k)


def long_segment_factor(length: float | None) -> float:
    """
    0 for <=100 m, gradually increasing to 1 around 400 m.

    Used only to amplify isolation-related penalties.
    """
    if length is None:
        return 0.0

    return clamp(
        (float(length) - LONG_SEGMENT_START_M)
        / (LONG_SEGMENT_FULL_M - LONG_SEGMENT_START_M)
    )


# ============================================================
# INDIVIDUAL FACTORS
# ============================================================

def light_risk(f: dict, night: bool) -> float | None:
    """
    Lighting risk.

    Combines:
    - OSM lit tag if known
    - nearby lamp count

    Missing lit does NOT mean unlit.
    """

    # During the day, lighting is largely irrelevant.
    if not night:
        return 0.0

    lit = f.get("lit")
    lamps = f.get("lamps")

    evidence = []

    # OSM lit tag: direct evidence
    if lit is not None:
        evidence.append((1.0 - clamp(float(lit)), 0.65))

    # Nearby lamps: indirect evidence
    if lamps is not None:
        lamp_quality = saturation(lamps, LAMP_K)
        evidence.append((1.0 - lamp_quality, 0.35))

    if not evidence:
        return None

    numerator = sum(risk * weight for risk, weight in evidence)
    denominator = sum(weight for _, weight in evidence)

    return clamp(numerator / denominator)


def outage_risk(f: dict, night: bool) -> float | None:
    """
    Risk from reported streetlight outages.

    An outage matters mainly at night.
    """

    if not night:
        return 0.0

    outages = f.get("outages")

    if outages is None:
        return None

    return saturation(outages, OUTAGE_K)


def lively_risk(f: dict, night: bool) -> float | None:
    """
    Low late-night activity -> higher risk proxy.

    venues_late is the number of nearby venues expected
    to be open late.
    """

    venues = f.get("venues_late")

    if venues is None:
        return None

    quality = saturation(venues, VENUE_K)

    risk = 1.0 - quality

    # Liveliness matters more conceptually at night.
    # The factor remains valid during the day, but its risk
    # is softened.
    if not night:
        risk *= 0.5

    return clamp(risk)


def help_risk(f: dict, night: bool) -> float | None:
    """
    f["help"] is expected to be a normalized proximity score:

        0 = no nearby help
        1 = strong nearby help presence

    e.g. generated upstream as exp(-distance / 300).
    """

    help_score = f.get("help")

    if help_score is None:
        return None

    return 1.0 - clamp(float(help_score))


def park_risk(f: dict, night: bool) -> float | None:
    """
    Park presence is treated as an isolation/environment proxy,
    not as a claim that parks are inherently unsafe.
    """

    in_park = f.get("in_park")

    if in_park is None:
        return None

    if not bool(in_park):
        return 0.0

    # Stronger penalty at night.
    base = 1.0 if night else 0.20

    # Long park segments increase the isolation proxy.
    length_factor = long_segment_factor(f.get("length"))

    return clamp(
        base * (0.80 + 0.20 * length_factor)
    )


def crime_risk(f: dict, night: bool) -> float | None:
    """
    f["crime"] must already be normalized to [0,1] upstream.

    It represents aggregated REPORTED INCIDENTS, not a
    probability of crime or a label that an area is dangerous.

    It deliberately receives low reliability.
    """

    crime = f.get("crime")

    if crime is None:
        return None

    return clamp(float(crime))


# ============================================================
# FACTOR COMPUTATION
# ============================================================

FACTOR_FUNCTIONS = {
    "light": light_risk,
    "outage": outage_risk,
    "lively": lively_risk,
    "help": help_risk,
    "park": park_risk,
    "crime": crime_risk,
}


# ============================================================
# PUBLIC API
# ============================================================

def edge_risk(
    f: dict,
    w: dict,
    night: bool,
) -> tuple[float, dict]:
    """
    Compute the explainable risk score for one graph edge.

    Parameters
    ----------
    f:
        Edge features:

        {
            "lit": 1 | 0 | None,
            "lamps": int | None,
            "outages": int | None,
            "venues_late": int | None,
            "help": float | None,       # normalized [0,1]
            "in_park": bool | None,
            "crime": float | None,      # normalized [0,1]
            "length": float | None,
        }

    w:
        Optional user-specific factor weights.
        Missing weights use DEFAULT_WEIGHTS.

    night:
        Whether routing occurs at night.

    Returns
    -------
    risk:
        Relative edge risk in [0,1].

    breakdown:
        {factor: contribution}

        plus metadata under "_meta".
    """

    # --------------------------------------------------------
    # 1. Build profile weights
    # --------------------------------------------------------

    weights = DEFAULT_WEIGHTS.copy()

    if w:
        for factor, value in w.items():
            if factor in weights:
                try:
                    weights[factor] = max(0.0, float(value))
                except (TypeError, ValueError):
                    pass

    # Normalize user weights.
    total_weight = sum(weights.values())

    if total_weight > 0:
        weights = {
            factor: weight / total_weight
            for factor, weight in weights.items()
        }

    # --------------------------------------------------------
    # 2. Compute factor risks
    # --------------------------------------------------------

    factor_risks = {
        factor: fn(f, night)
        for factor, fn in FACTOR_FUNCTIONS.items()
    }

    # --------------------------------------------------------
    # 3. Contributions
    # --------------------------------------------------------

    breakdown = {}

    numerator = 0.0
    denominator = 0.0

    # Maximum evidence we could have with this profile.
    total_possible_evidence = sum(
        weights[factor] * RELIABILITY[factor]
        for factor in RELIABILITY
    )

    for factor, risk in factor_risks.items():

        weight = weights[factor]
        reliability = RELIABILITY[factor]

        if risk is None:
            # Missing = unknown.
            # Do NOT turn missing information into risk.
            breakdown[factor] = 0.0
            continue

        effective_weight = weight * reliability

        contribution = (
            effective_weight
            * risk
        )

        breakdown[factor] = round(
            contribution,
            4,
        )

        numerator += contribution
        denominator += effective_weight

    # --------------------------------------------------------
    # 4. Final normalized risk
    # --------------------------------------------------------

    if denominator == 0:
        # No usable information.
        risk = 0.5
    else:
        risk = numerator / denominator

    risk = clamp(risk)

    # --------------------------------------------------------
    # 5. Confidence
    # --------------------------------------------------------

    if total_possible_evidence > 0:
        confidence = denominator / total_possible_evidence
    else:
        confidence = 0.0

    confidence = clamp(confidence)

    # --------------------------------------------------------
    # 6. Explainability metadata
    # --------------------------------------------------------

    breakdown["_meta"] = {
        "factor_risks": {
            factor: (
                None
                if value is None
                else round(value, 4)
            )
            for factor, value in factor_risks.items()
        },

        "weights": {
            factor: round(weight, 4)
            for factor, weight in weights.items()
        },

        "reliability": RELIABILITY.copy(),

        "risk": round(risk, 4),

        "safety_score": round(
            10 * (1 - risk),
            1,
        ),

        "confidence": round(
            confidence,
            4,
        ),
    }

    return risk, breakdown
