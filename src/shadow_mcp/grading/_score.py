"""Validate external grading scores before using them in a report."""

import math


def risk_score(value: object) -> float | None:
    """Both providers define capability scores on the closed interval [0, 10]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        score = float(value)
    except OverflowError:
        return None
    return score if math.isfinite(score) and 0.0 <= score <= 10.0 else None
