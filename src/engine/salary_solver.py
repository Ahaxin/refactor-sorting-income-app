"""
SE Salary Solver — Phase 4.

Two-stage approach:
  Stage A: Sinkhorn biproportional fitting (continuous).
  Stage B: Round to even integers, then swap-repair to hit exact sums.
"""

import logging
import random

from src.config import MIN_SALARY, MAX_SALARY, SE_SALARY_UNIT, SOLVER_MAX_ITER, SOLVER_TOL, RATIO
from src.models.employee import SelfEmployedEmployee
from src.models.company import Company

logger = logging.getLogger(__name__)


def solve_salaries(
    se_workers: list[SelfEmployedEmployee],
    companies: dict[str, Company],
    rng: random.Random,
) -> None:
    """Assign exact daily SE salaries in-place."""
    logger.info("=" * 60)
    logger.info("SE SALARY SOLVER")
    logger.info("=" * 60)

    # Build slot → worker list index
    slots: dict[tuple[str, int], list[SelfEmployedEmployee]] = {}
    for w in se_workers:
        for (company_name, day) in w.schedule:
            slots.setdefault((company_name, day), []).append(w)

    if not slots:
        logger.warning("  No SE assignments — nothing to solve")
        return

    # Initialise matrix uniformly within [MIN_SALARY, MAX_SALARY]
    matrix: dict[tuple[str, str, int], float] = {}
    for (c, d), workers in slots.items():
        budget = companies[c].get_day(d).se_day_target
        n = len(workers)
        share = max(MIN_SALARY, min(MAX_SALARY, budget / n if n else MIN_SALARY))
        for w in workers:
            matrix[(w.name, c, d)] = share

    # Stage A: Sinkhorn
    _sinkhorn(matrix, se_workers, slots, companies)

    # Stage B: Round to even integers then repair
    int_matrix: dict[tuple[str, str, int], int] = {
        k: _round_even(v) for k, v in matrix.items()
    }
    _repair(int_matrix, se_workers, slots, companies)

    # Write back
    for (c, d), workers in slots.items():
        dl = companies[c].get_day(d)
        for w in workers:
            sal = int_matrix[(w.name, c, d)]
            w.schedule[(c, d)] = sal
            dl.se_salaries[w.name] = sal

    _log_results(se_workers, companies)


def _sinkhorn(
    matrix: dict[tuple[str, str, int], float],
    se_workers: list[SelfEmployedEmployee],
    slots: dict[tuple[str, int], list[SelfEmployedEmployee]],
    companies: dict[str, Company],
) -> None:
    for iteration in range(SOLVER_MAX_ITER):
        max_err = 0.0

        # Row normalisation: scale each worker's entries to their target
        for w in se_workers:
            worker_keys = [k for k in matrix if k[0] == w.name]
            if not worker_keys:
                continue
            row_sum = sum(matrix[k] for k in worker_keys)
            if row_sum == 0:
                continue
            scale = w.salary / row_sum
            for k in worker_keys:
                matrix[k] = max(MIN_SALARY, min(MAX_SALARY, matrix[k] * scale))
            max_err = max(max_err, abs(row_sum - w.salary))

        # Column normalisation: scale each slot to SE_day_target
        for (c, d), workers in slots.items():
            col_keys = [(w.name, c, d) for w in workers]
            col_sum = sum(matrix[k] for k in col_keys)
            target = companies[c].get_day(d).se_day_target
            if col_sum == 0 or target == 0:
                continue
            scale = target / col_sum
            for k in col_keys:
                matrix[k] = max(MIN_SALARY, min(MAX_SALARY, matrix[k] * scale))
            max_err = max(max_err, abs(col_sum - target))

        if max_err < SOLVER_TOL:
            logger.debug(f"  Sinkhorn converged at iteration {iteration}")
            break


def _round_even(v: float) -> int:
    """Round to nearest even integer in [MIN_SALARY, MAX_SALARY]."""
    r = round(v / SE_SALARY_UNIT) * SE_SALARY_UNIT
    return max(MIN_SALARY, min(MAX_SALARY, r))


def _repair(
    matrix: dict[tuple[str, str, int], int],
    se_workers: list[SelfEmployedEmployee],
    slots: dict[tuple[str, int], list[SelfEmployedEmployee]],
    companies: dict[str, Company],
) -> None:
    """Fix salaries so that:
    • each day's SE column sum ≤ SE_day_target  (Phase A — column upper bound)
    • each worker's monthly row sum == target     (Phase B — row equality)
    Phase B never increases a column sum past SE_day_target, so CE can always
    absorb the exact formula residual on every day."""
    for _ in range(SOLVER_MAX_ITER):
        all_ok = True

        # Phase A: reduce any column sums that exceed se_day_target
        for (c, d), workers in slots.items():
            col_target = companies[c].get_day(d).se_day_target
            col_keys = [(w.name, c, d) for w in workers]
            col_sum = sum(matrix[k] for k in col_keys)
            if col_sum <= col_target:
                continue
            all_ok = False
            for k in sorted(col_keys, key=lambda k: matrix[k], reverse=True):
                while matrix[k] > MIN_SALARY and col_sum > col_target:
                    matrix[k] -= SE_SALARY_UNIT
                    col_sum -= SE_SALARY_UNIT

        # Phase B: fix row sums (monthly targets), never pushing a column over its target
        for w in se_workers:
            worker_keys = [(w.name, c, d) for (c, d) in w.schedule]
            if not worker_keys:
                continue
            row_sum = sum(matrix[k] for k in worker_keys)
            diff = w.salary - row_sum
            if diff == 0:
                continue
            all_ok = False
            step = SE_SALARY_UNIT if diff > 0 else -SE_SALARY_UNIT
            for _ in range(abs(diff) // SE_SALARY_UNIT):
                placed = False
                for k in worker_keys:
                    new_val = matrix[k] + step
                    if MIN_SALARY <= new_val <= MAX_SALARY:
                        if step > 0:
                            cname, day = k[1], k[2]
                            col_sum = sum(
                                matrix[(ww.name, cname, day)]
                                for ww in slots[(cname, day)]
                            )
                            if col_sum + step > companies[cname].get_day(day).se_day_target:
                                continue
                        matrix[k] = new_val
                        placed = True
                        break
                if not placed and step > 0:
                    # Direct increase blocked on all days — try swapping with a co-worker
                    # who earns above MIN_SALARY on a shared column-capped day.
                    for k in worker_keys:
                        cname, day = k[1], k[2]
                        col_target = companies[cname].get_day(day).se_day_target
                        col_sum = sum(
                            matrix[(ww.name, cname, day)]
                            for ww in slots[(cname, day)]
                        )
                        if col_sum + step > col_target:
                            for other_w in slots[(cname, day)]:
                                if other_w.name == w.name:
                                    continue
                                other_k = (other_w.name, cname, day)
                                if matrix[other_k] - SE_SALARY_UNIT >= MIN_SALARY:
                                    matrix[other_k] -= SE_SALARY_UNIT
                                    matrix[k] += SE_SALARY_UNIT
                                    placed = True
                                    break
                        if placed:
                            break

        if all_ok:
            return

    logger.warning("  Repair loop hit max iterations — some worker monthly targets may not be exact")


def _log_results(
    se_workers: list[SelfEmployedEmployee],
    companies: dict[str, Company],
) -> None:
    logger.info("-" * 60)
    logger.info("SE MONTHLY SALARY RESULTS:")
    shortfall_count = 0
    for w in se_workers:
        actual = w.actual_monthly_salary
        target = w.salary
        gap = actual - target
        status = "OK" if gap == 0 else f"GAP={gap:+d}"
        if gap != 0:
            shortfall_count += 1
        logger.info(f"  {w.name:<12} target={target:>5} actual={actual:>5} [{status}]")

    if shortfall_count:
        logger.warning(f"  {shortfall_count} SE worker(s) did not hit their target")

    logger.info("-" * 60)
    logger.info("PER-DAY COLUMN BOUND CHECK (SE_total <= SE_day_target):")
    violations = 0
    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            if dl.se_day_target == 0:
                continue
            if dl.se_total > dl.se_day_target:
                logger.warning(
                    f"  OVERSHOOT {company.name} day {day:02d}: "
                    f"SE_total={dl.se_total} > target={dl.se_day_target}"
                )
                violations += 1
    if violations == 0:
        logger.info("  All days satisfy SE_total <= SE_day_target.")
    logger.info("=" * 60)
