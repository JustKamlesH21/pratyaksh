"""Small-sample statistics for Eval Runs: Wilson intervals, rule of three, latency percentiles.

An Eval Run has 10-20 Calls per label, so a rate alone says little. Every rate is reported as
x/n with a Wilson 95% interval (never the Wald interval, which collapses to [1, 1] at 10/10).
"""

from __future__ import annotations

import math

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials; None when n is 0."""
    if n <= 0:
        return None
    if not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n, got {k}/{n}")
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    lo, hi = max(0.0, centre - half), min(1.0, centre + half)
    # At k == 0 or k == n the interval touches the bound exactly; keep float noise out of it.
    return (0.0 if k == 0 else lo, 1.0 if k == n else hi)


def rate(k: int, n: int) -> dict:
    """{"k", "n", "rate", "ci95": [lo, hi]} with 3-decimal rounding; rate and ci95 are None when n is 0."""
    ci = wilson(k, n)
    return {
        "k": k,
        "n": n,
        "rate": round(k / n, 3) if n else None,
        "ci95": None if ci is None else [round(ci[0], 3), round(ci[1], 3)],
    }


def format_rate(r: dict | None) -> str:
    """'18/20 = 90% (95% CI 70-97%)', or '-' when nothing was measured."""
    if not r or not r.get("n"):
        return "-"
    lo, hi = r["ci95"]
    return f"{r['k']}/{r['n']} = {_pct(r['rate'])} (95% CI {_pct(lo)}-{_pct(hi)})"


def rule_of_three(n: int) -> float | None:
    """95% upper bound on an error rate when 0 errors were seen in n trials (3/n, capped at 1)."""
    return None if n <= 0 else min(1.0, 3.0 / n)


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile (an observed value, no interpolation): honest with few samples."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def median(values: list[float]) -> float | None:
    if not values:
        return None
    s, m = sorted(values), len(values) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def spread(values: list[float], digits: int = 1) -> dict:
    """{"n", "median", "p95", "max", "mean"} of a list of numbers (None fields when empty)."""
    r = lambda v: None if v is None else round(v, digits)  # noqa: E731
    return {
        "n": len(values),
        "median": r(median(values)),
        "p95": r(percentile(values, 0.95)),
        "max": r(max(values) if values else None),
        "mean": r(sum(values) / len(values) if values else None),
    }


def _pct(v: float) -> str:
    return f"{v * 100:.0f}%"
