"""
Exact joint SE+CE solver (replaces the greedy schedule → solve → CE-plan pipeline).

The whole month is modelled as ONE mixed-integer program and solved with HiGHS
(via scipy.optimize.milp). This is deterministic — a single solve replaces the
old random-retry loop.

Why one model works
-------------------
Per (company, day) the profit-sharing formula is  SE_total/0.4 + CE_total = I.
Writing SE_total = 2·A and CE_total = 5·B (SE pay is even, CE pay is a multiple
of 5, income is a multiple of 5) the formula collapses to the clean integer
identity

        A + B = I / 5

so the formula can ALWAYS be hit exactly as long as the per-day SE and CE totals
are realisable by the eligible workers. Shortfalls and deviations are therefore
purely capacity/eligibility effects, which a global optimiser handles directly —
something the old sequential heuristic could not, because each stage committed
locally without seeing the others.

Decision variables
-------------------
SE  a[w,c,d] = half the daily SE salary (salary = 2a, in [120,400] even
               ⇒ a ∈ [60,200] when the worker actually works that slot)
    y[w,c,d] binary "works this slot"; 60·y ≤ a ≤ 200·y
    one company per day:  Σ_c y[w,·,d] ≤ 1
    monthly exact:        Σ 2a = target_w   (soft, heavily penalised)
CE  b[w,c,d] = CE daily salary / 5  (salary = 5b ∈ [0,500] ⇒ b ∈ [0,100])
    flexible CE need z to pick one company per day; exclusive CE are single-company
    monthly cap:          Σ 5b ≤ cap_w
formula slack sp,sn ≥ 0 per (c,d), heavily penalised.
"""

import logging
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy import sparse

from src.config import MIN_SALARY, MAX_SALARY, CE_MAX_PER_DAY, SE_SALARY_UNIT, CE_SALARY_UNIT
from src.models.company import Company
from src.models.employee import SelfEmployedEmployee, CompanyEmployedEmployee

logger = logging.getLogger(__name__)

# Objective weights. Violations dominate (must be driven to zero first); the
# spread reward is a strictly smaller tie-break that, among all zero-violation
# schedules, prefers the one where the most SE workers work each day — i.e. each
# worker's fixed monthly target is split across as many days as possible, every
# active day still paying >= MIN_SALARY. Bound: (#SE slots) * W_SPREAD must stay
# below one deviation unit (W_DEVIATION) so spread can never buy a violation.
W_DEVIATION = 10_000      # per 5-currency unit of |formula - income|
W_SHORTFALL = 100_000     # per 2-currency unit of SE monthly miss
W_SPREAD = 1              # reward per active SE (worker, company, day) slot

# Phase 2 (spread maximisation) is a tie-break, not correctness — cap its time
# separately so phase 1 (which decides shortfalls/deviations) always gets the
# full budget. A good incumbent appears within a few seconds.
SPREAD_TIME_LIMIT = 10.0


@dataclass
class SolveReport:
    status: int
    feasible: bool
    solve_time: float
    deviations: list[tuple[str, int, int]] = field(default_factory=list)   # (company, day, signed dev)
    shortfalls: list[tuple[str, int]] = field(default_factory=list)        # (worker, signed gap)

    @property
    def perfect(self) -> bool:
        return self.feasible and not self.deviations and not self.shortfalls


def solve_exact(
    se_workers: list[SelfEmployedEmployee],
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
    time_limit: float = 60.0,
    se_max_per_day: int | None = None,
    ce_max_per_day: int | None = None,
) -> SolveReport:
    """Solve the month exactly and write salaries back into the model in-place.

    Parameters
    ----------
    se_max_per_day : int or None
        Max daily salary for SE workers (default: MAX_SALARY from config).
    ce_max_per_day : int or None
        Max daily salary for CE workers (default: CE_MAX_PER_DAY from config).
    """
    import time
    logger.info("=" * 60)
    logger.info("EXACT SOLVER (MILP / HiGHS)")
    logger.info("=" * 60)

    # --- resolve configurable bounds ---
    _se_max = se_max_per_day if se_max_per_day is not None else MAX_SALARY
    _ce_max = ce_max_per_day if ce_max_per_day is not None else CE_MAX_PER_DAY
    _a_max = _se_max // SE_SALARY_UNIT
    _a_min = MIN_SALARY // SE_SALARY_UNIT
    _b_max = _ce_max // CE_SALARY_UNIT
    logger.info(f"  SE bounds: [{MIN_SALARY}, {_se_max}]  CE max: {_ce_max}")

    comp_names = list(companies.keys())
    days = sorted(next(iter(companies.values())).days)
    i5 = {
        (c, d): companies[c].get_day(d).cleaned_income // 5
        for c in comp_names for d in days
    }

    idx: dict[str, int] = {}
    lb: list[float] = []
    ub: list[float] = []

    def add(name: str, lo: float, hi: float) -> int:
        idx[name] = len(lb)
        lb.append(lo)
        ub.append(hi)
        return idx[name]

    def se_elig_c(w: SelfEmployedEmployee, c: str, d: int) -> bool:
        if w.preferences.get(c, {}).get(d, 0) <= 0:
            return False
        if w.exclusive_company and w.exclusive_company != c:
            return False
        return True

    def ce_elig(w: CompanyEmployedEmployee, c: str, d: int) -> bool:
        if w.preferences.get(c, {}).get(d, 0) <= 0:
            return False
        if w.exclusive_company and w.exclusive_company != c:
            return False
        return True

    # --- variables ---
    for w in se_workers:
        for d in days:
            for c in comp_names:
                if not se_elig_c(w, c, d):
                    continue
                add(f"a|{w.name}|{c}|{d}", 0, _a_max)
                add(f"y|{w.name}|{c}|{d}", 0, 1)
        add(f"sf+|{w.name}", 0, w.salary)   # under-delivery, currency
        add(f"sf-|{w.name}", 0, w.salary)   # over-delivery, currency
    for w in ce_workers:
        for d in days:
            for c in comp_names:
                if not ce_elig(w, c, d):
                    continue
                add(f"b|{w.name}|{c}|{d}", 0, _b_max)
                if w.exclusive_company is None:
                    add(f"z|{w.name}|{c}|{d}", 0, 1)
    for c in comp_names:
        for d in days:
            add(f"sp|{c}|{d}", 0, i5[(c, d)])
            add(f"sn|{c}|{d}", 0, i5[(c, d)])

    n = len(lb)
    integrality = np.ones(n)   # every variable is integer
    rows: list[tuple[dict[int, float], float | None, float | None]] = []

    def con(coefs: dict[int, float], lo: float | None, hi: float | None) -> None:
        rows.append((coefs, lo, hi))

    # SE semicontinuity + one-company-per-day
    for w in se_workers:
        for d in days:
            ys = []
            for c in comp_names:
                if not se_elig_c(w, c, d):
                    continue
                a = idx[f"a|{w.name}|{c}|{d}"]
                y = idx[f"y|{w.name}|{c}|{d}"]
                con({a: 1, y: -_a_min}, 0, None)   # a >= A_MIN·y
                con({a: 1, y: -_a_max}, None, 0)   # a <= A_MAX·y
                ys.append(y)
            if len(ys) > 1:
                con({yi: 1 for yi in ys}, None, 1)

    # SE monthly: Σ 2a + sf+ - sf- = target
    for w in se_workers:
        coefs: dict[int, float] = {}
        for d in days:
            for c in comp_names:
                if se_elig_c(w, c, d):
                    coefs[idx[f"a|{w.name}|{c}|{d}"]] = 2
        coefs[idx[f"sf+|{w.name}"]] = 1
        coefs[idx[f"sf-|{w.name}"]] = -1
        con(coefs, w.salary, w.salary)

    # CE monthly cap + flexible one-company-per-day
    for w in ce_workers:
        flex = w.exclusive_company is None
        cap_coefs: dict[int, float] = {}
        for d in days:
            zs = []
            for c in comp_names:
                if not ce_elig(w, c, d):
                    continue
                b = idx[f"b|{w.name}|{c}|{d}"]
                cap_coefs[b] = 5
                if flex:
                    z = idx[f"z|{w.name}|{c}|{d}"]
                    con({b: 1, z: -_b_max}, None, 0)   # b <= B_MAX·z
                    zs.append(z)
            if flex and len(zs) > 1:
                con({zz: 1 for zz in zs}, None, 1)
        if cap_coefs:
            con(cap_coefs, 0, w.salary)

    # Formula per (c,d): Σ a + Σ b + sp - sn = I/5
    for c in comp_names:
        for d in days:
            coefs = {}
            for w in se_workers:
                if se_elig_c(w, c, d):
                    coefs[idx[f"a|{w.name}|{c}|{d}"]] = 1
            for w in ce_workers:
                if ce_elig(w, c, d):
                    coefs[idx[f"b|{w.name}|{c}|{d}"]] = 1
            coefs[idx[f"sp|{c}|{d}"]] = 1
            coefs[idx[f"sn|{c}|{d}"]] = -1
            con(coefs, i5[(c, d)], i5[(c, d)])

    # --- assemble sparse model ---
    data, ri, ci, clo, chi = [], [], [], [], []
    for r, (coefs, lo, hi) in enumerate(rows):
        for j, coef in coefs.items():
            data.append(coef)
            ri.append(r)
            ci.append(j)
        clo.append(-np.inf if lo is None else lo)
        chi.append(np.inf if hi is None else hi)
    A = sparse.csr_matrix((data, (ri, ci)), shape=(len(rows), n))

    lb_arr = np.array(lb, float)
    ub_arr = np.array(ub, float)
    constraints = LinearConstraint(A, clo, chi)
    viol_idx = [j for nm, j in idx.items() if nm.startswith(("sp|", "sn|", "sf+|", "sf-|"))]
    y_idx = [j for nm, j in idx.items() if nm.startswith("y|")]

    logger.info(f"  variables={n}  constraints={len(rows)}")
    t0 = time.time()

    # Phase 1 — minimise violations exactly (deterministic, ~10s). This decides
    # feasibility and the best achievable shortfall/deviation level.
    c1 = np.zeros(n)
    for nm, j in idx.items():
        if nm.startswith(("sp|", "sn|")):
            c1[j] = W_DEVIATION
        elif nm.startswith(("sf+|", "sf-|")):
            c1[j] = W_SHORTFALL
    res = milp(c=c1, constraints=constraints, integrality=integrality,
               bounds=Bounds(lb_arr, ub_arr),
               options={"time_limit": time_limit, "mip_rel_gap": 0.0})
    if res.x is None:
        dt = time.time() - t0
        logger.error("  Solver returned no solution — model infeasible/unbounded.")
        return SolveReport(status=res.status, feasible=False, solve_time=dt)
    best_x = res.x
    logger.info(f"  phase 1 (violations) status={res.status} time={time.time()-t0:.1f}s")

    # Phase 2 — among schedules with that minimal violation level, put as many SE
    # workers as possible on each day: pin the violation variables and maximise
    # the count of active SE slots (each still paying >= MIN_SALARY). Pinning
    # means this tie-break can never reintroduce a shortfall or deviation.
    if y_idx:
        lb2, ub2 = lb_arr.copy(), ub_arr.copy()
        for j in viol_idx:
            lb2[j] = ub2[j] = round(res.x[j])
        c2 = np.zeros(n)
        for j in y_idx:
            c2[j] = -W_SPREAD
        res2 = milp(c=c2, constraints=constraints, integrality=integrality,
                    bounds=Bounds(lb2, ub2),
                    options={"time_limit": SPREAD_TIME_LIMIT, "mip_rel_gap": 1e-2})
        if res2.x is not None:
            best_x = res2.x
            logger.info(f"  phase 2 (max SE/day) slots={int(round(sum(res2.x[j] for j in y_idx)))} "
                        f"total_time={time.time()-t0:.1f}s")

    dt = time.time() - t0
    x = best_x
    _write_back(x, idx, se_workers, ce_workers, companies, comp_names, days,
                se_elig_c, ce_elig)

    deviations: list[tuple[str, int, int]] = []
    for c in comp_names:
        for d in days:
            dev = round(x[idx[f"sp|{c}|{d}"]] - x[idx[f"sn|{c}|{d}"]]) * 5
            if dev != 0:
                deviations.append((c, d, dev))
    shortfalls: list[tuple[str, int]] = []
    for w in se_workers:
        gap = round(x[idx[f"sf-|{w.name}"]] - x[idx[f"sf+|{w.name}"]])
        if gap != 0:
            shortfalls.append((w.name, gap))

    report = SolveReport(
        status=res.status, feasible=True, solve_time=dt,
        deviations=deviations, shortfalls=shortfalls,
    )
    if report.perfect:
        logger.info("  PERFECT: 0 shortfalls, 0 deviations.")
    else:
        logger.warning(f"  Residual: {len(shortfalls)} shortfall(s), {len(deviations)} deviation(s).")
    logger.info("=" * 60)
    return report


def _write_back(x, idx, se_workers, ce_workers, companies, comp_names, days,
                se_elig_c, ce_elig) -> None:
    """Clear and repopulate schedules, ledgers, and per-day targets from the solution."""
    for w in se_workers:
        w.schedule.clear()
    for w in ce_workers:
        w.schedule.clear()
    for c in comp_names:
        for d in days:
            dl = companies[c].get_day(d)
            dl.se_salaries.clear()
            dl.ce_salaries.clear()

    for w in se_workers:
        for d in days:
            for c in comp_names:
                if not se_elig_c(w, c, d):
                    continue
                sal = round(x[idx[f"a|{w.name}|{c}|{d}"]]) * 2
                if sal > 0:
                    w.schedule[(c, d)] = sal
                    companies[c].get_day(d).se_salaries[w.name] = sal
    for w in ce_workers:
        for d in days:
            for c in comp_names:
                if not ce_elig(w, c, d):
                    continue
                sal = round(x[idx[f"b|{w.name}|{c}|{d}"]]) * 5
                if sal > 0:
                    w.schedule[(c, d)] = sal
                    companies[c].get_day(d).ce_salaries[w.name] = sal

    for c in comp_names:
        for d in days:
            dl = companies[c].get_day(d)
            dl.set_se_day_target(dl.se_total)
