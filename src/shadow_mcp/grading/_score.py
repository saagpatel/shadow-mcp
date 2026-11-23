"""Validate external grading scores before using them in a report."""

import math


def finite_score(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        score = float(value)
    except OverflowError:
        return None
    return score if math.isfinite(score) else None
