"""Post-solve salary diversification (constraint-preserving randomization).

The solver tends to assign many identical daily salaries. This module shuffles
those values *without* changing any solved guarantee, using 4-cell cycle moves on
the (worker x (company, day)) matrix:

    w1@k1 += d   w1@k2 -= d
    w2@k1 -= d   w2@k2 += d

Each move preserves every per-(company, day) column total (so the 40% formula
stays exact) and every per-worker row total (so monthly targets / caps stay
exact). ``d`` is a multiple of the salary unit, bounded so every touched cell
stays inside its legal range and within +/-pct of its original solved value.
"""

import math
import random
from dataclasses import dataclass, field

from src.config import (
    MIN_SALARY, MAX_SALARY, CE_MAX_PER_DAY, SE_SALARY_UNIT, CE_SALARY_UNIT,
)

# Number of cycle attempts = ITER_FACTOR * (#active cells). Cheap; well above
# the point where extra attempts stop adding variety on typical datasets.
ITER_FACTOR = 8


def _band(pct, value_range, unit):
    """Drift band derived from the input scale: the largest multiple of ``unit``
    that does not exceed ``pct`` of the legal value range (cap - floor)."""
    return (int(pct * value_range) // unit) * unit


def diversify_schedule(se_workers, ce_workers, companies, pct=0.15, seed=0,
                       se_max=None, ce_max=None, se_min=None):
    """Diversify SE and CE daily salaries in place. ``pct <= 0`` is a no-op.

    The drift band is NOT a per-cell percentage; it is one absolute band per
    worker-type, ``pct`` of that type's legal range (so floor/cap cells get real
    room): SE range is [se_min, se_max], CE range is [0, ce_max]. ``se_min`` must
    match the solver's ``se_min_per_day`` so tuning never pushes a concentrated
    value back below the floor it was solved against."""
    if not pct or pct <= 0:
        return
    se_hi = se_max if se_max is not None else MAX_SALARY
    ce_hi = ce_max if ce_max is not None else CE_MAX_PER_DAY
    se_lo = se_min if se_min is not None else MIN_SALARY
    rng = random.Random(seed)
    se_band = _band(pct, se_hi - se_lo, SE_SALARY_UNIT)
    ce_band = _band(pct, ce_hi - 0, CE_SALARY_UNIT)
    _diversify_matrix(se_workers, companies, "se_salaries",
                      SE_SALARY_UNIT, se_lo, se_hi, se_band, rng)
    _diversify_matrix(ce_workers, companies, "ce_salaries",
                      CE_SALARY_UNIT, CE_SALARY_UNIT, ce_hi, ce_band, rng)


def _diversify_matrix(workers, companies, attr, unit, lo, hi, band, rng):
    """Run cycle moves over one worker-type matrix, then write values back.

    ``band`` is the absolute max drift allowed for every cell of this type."""
    if band < unit:
        return
    value: dict = {}                 # (wi, col) -> current salary
    original: dict = {}              # (wi, col) -> solved salary
    cols_of: dict = {}               # wi -> [col, ...]
    workers_at: dict = {}            # col -> set(wi)
    for wi, w in enumerate(workers):
        for col, sal in w.schedule.items():
            if sal <= 0:
                continue
            value[(wi, col)] = sal
            original[(wi, col)] = sal
            cols_of.setdefault(wi, []).append(col)
            workers_at.setdefault(col, set()).add(wi)

    movable = [wi for wi, cols in cols_of.items() if len(cols) >= 2]
    if not movable:
        return

    attempts = ITER_FACTOR * len(value)
    for _ in range(attempts):
        wi1 = rng.choice(movable)
        k1, k2 = rng.sample(cols_of[wi1], 2)
        common = sorted((workers_at[k1] & workers_at[k2]) - {wi1})
        if not common:
            continue
        wi2 = rng.choice(common)

        c11, c12 = (wi1, k1), (wi1, k2)
        c21, c22 = (wi2, k1), (wi2, k2)
        dlo, dhi = _feasible_delta(
            [(value[c11], original[c11], band, +1),
             (value[c12], original[c12], band, -1),
             (value[c21], original[c21], band, -1),
             (value[c22], original[c22], band, +1)],
            lo, hi)
        d = _pick_delta(dlo, dhi, unit, rng)
        if d == 0:
            continue
        value[c11] += d
        value[c12] -= d
        value[c21] -= d
        value[c22] += d

    for (wi, col), sal in value.items():
        w = workers[wi]
        w.schedule[col] = sal
        c, day = col
        getattr(companies[c].get_day(day), attr)[w.name] = sal


def _feasible_delta(cells, lo, hi):
    """Intersect the per-cell legal+band ranges into one [dlo, dhi] for delta."""
    dlo, dhi = -math.inf, math.inf
    for v, o, b, s in cells:
        # new = v + s*d must satisfy lo<=new<=hi and o-b<=new<=o+b, i.e.
        # s*d in [L, U].
        low = max(lo - v, o - b - v)
        high = min(hi - v, o + b - v)
        cl, cu = (low, high) if s == 1 else (-high, -low)
        dlo = max(dlo, cl)
        dhi = min(dhi, cu)
    return dlo, dhi


def _pick_delta(dlo, dhi, unit, rng):
    """Random nonzero multiple of ``unit`` in [dlo, dhi]; 0 if none exists."""
    lo_m = math.ceil(dlo / unit) * unit
    hi_m = math.floor(dhi / unit) * unit
    if hi_m < lo_m:
        return 0
    candidates = [m for m in range(int(lo_m), int(hi_m) + 1, unit) if m != 0]
    if not candidates:
        return 0
    return rng.choice(candidates)


@dataclass
class VerifyReport:
    """Result of re-checking a (possibly tuned) schedule against the guarantees."""
    deviations: list = field(default_factory=list)        # (company, day, signed dev)
    shortfalls: list = field(default_factory=list)         # (se worker, signed gap)
    cap_violations: list = field(default_factory=list)     # (ce worker, overage)
    bound_violations: list = field(default_factory=list)   # human-readable strings

    @property
    def ok(self) -> bool:
        return not (self.deviations or self.shortfalls
                    or self.cap_violations or self.bound_violations)

    def regressed_from(self, baseline_deviations, baseline_shortfalls) -> bool:
        """True if this state is worse than the solver baseline — more formula
        deviations or shortfalls than the solver produced, or any cap/bound
        violation (which the solver never produces)."""
        return (len(self.deviations) > len(baseline_deviations)
                or len(self.shortfalls) > len(baseline_shortfalls)
                or bool(self.cap_violations)
                or bool(self.bound_violations))


def verify_schedule(se_workers, ce_workers, companies, se_max=None, ce_max=None,
                    se_min=None):
    """Recompute deviations / shortfalls / cap+bound violations from the live
    model state. Read-only. ``se_max``/``ce_max``/``se_min`` None -> config
    defaults (``se_min`` must match the solver's floor)."""
    se_hi = se_max if se_max is not None else MAX_SALARY
    ce_hi = ce_max if ce_max is not None else CE_MAX_PER_DAY
    se_lo = se_min if se_min is not None else MIN_SALARY

    deviations = []
    for c in companies:
        comp = companies[c]
        for d in comp.days:
            dl = comp.get_day(d)
            if dl.is_full_ce_absorption:
                continue
            dev = round(dl.formula_check) - dl.cleaned_income
            if dev != 0:
                deviations.append((c, d, dev))

    shortfalls = []
    for w in se_workers:
        gap = w.actual_monthly_salary - w.salary
        if gap != 0:
            shortfalls.append((w.name, gap))

    cap_violations = []
    for w in ce_workers:
        over = w.actual_monthly_salary - w.salary
        if over > 0:
            cap_violations.append((w.name, over))

    bound_violations = []
    for w in se_workers:
        for (c, d), sal in w.schedule.items():
            if sal % SE_SALARY_UNIT != 0 or not (se_lo <= sal <= se_hi):
                bound_violations.append(f"SE {w.name} @ {c} day {d}: {sal}")
    for w in ce_workers:
        for (c, d), sal in w.schedule.items():
            if sal % CE_SALARY_UNIT != 0 or not (0 <= sal <= ce_hi):
                bound_violations.append(f"CE {w.name} @ {c} day {d}: {sal}")

    return VerifyReport(deviations, shortfalls, cap_violations, bound_violations)


def snapshot_schedules(se_workers, ce_workers, companies) -> dict:
    """Capture schedules and day ledgers so tuning can be rolled back exactly."""
    return {
        "schedules": {w.name: dict(w.schedule) for w in (*se_workers, *ce_workers)},
        "se": {(c, d): dict(companies[c].get_day(d).se_salaries)
               for c in companies for d in companies[c].days},
        "ce": {(c, d): dict(companies[c].get_day(d).ce_salaries)
               for c in companies for d in companies[c].days},
    }


def restore_schedules(snapshot, se_workers, ce_workers, companies) -> None:
    """Restore a snapshot produced by :func:`snapshot_schedules`."""
    for w in (*se_workers, *ce_workers):
        w.schedule.clear()
        w.schedule.update(snapshot["schedules"][w.name])
    for c in companies:
        for d in companies[c].days:
            dl = companies[c].get_day(d)
            dl.se_salaries.clear()
            dl.se_salaries.update(snapshot["se"][(c, d)])
            dl.ce_salaries.clear()
            dl.ce_salaries.update(snapshot["ce"][(c, d)])
