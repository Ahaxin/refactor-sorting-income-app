"""
SE Scheduler — Phase 3.

Assigns SE workers to (company, day) slots using per-day SE_day_target
already set by the CE planner. Salaries are left at 0 (filled by solver).
"""

import logging
import math
import random

from src.config import MIN_SALARY, MAX_SALARY, PREDEFINED_DAILY, COMPANY_NAMES
from src.models.employee import SelfEmployedEmployee
from src.models.company import Company

logger = logging.getLogger(__name__)


def schedule_se(
    se_workers: list[SelfEmployedEmployee],
    companies: dict[str, Company],
    rng: random.Random,
) -> None:
    """Assign SE workers to slots in-place. Salaries remain 0."""
    logger.info("=" * 60)
    logger.info("SE SCHEDULING PHASE")
    logger.info("=" * 60)

    # Compute per-worker day envelopes
    for w in se_workers:
        w.min_days = math.ceil(w.salary / PREDEFINED_DAILY)
        w.max_days = math.floor(w.salary / MIN_SALARY)
        w.target_days = math.ceil(w.salary / 180)

    # Build active slots
    all_slots = [
        (company.name, day)
        for company in companies.values()
        for day in company.days
        if company.get_day(day).se_day_target >= MIN_SALARY
    ]
    rng.shuffle(all_slots)

    for company_name, day in all_slots:
        dl = companies[company_name].get_day(day)
        budget = dl.se_day_target
        n_min = math.ceil(budget / MAX_SALARY)
        n_max = math.floor(budget / MIN_SALARY)

        pool = _eligible_workers(se_workers, company_name, day)
        if not pool:
            continue

        n_cap = min(n_max, len(pool))
        if n_cap < n_min:
            # Not enough eligible workers to satisfy minimum — take as many as available
            n = n_cap
        else:
            n = rng.randint(n_min, n_cap)
        pool.sort(key=lambda w: (
            -w.preferences.get(company_name, {}).get(day, 0),
            -(w.target_days - w.assigned_days),
        ))
        for worker in pool[:n]:
            worker.add_shift(company_name, day, salary=0)

    _fill_under_scheduled(se_workers, companies, rng)
    _fill_budget_deficient(se_workers, companies, rng, se_workers)
    _log_summary(se_workers)


def _eligible_workers(
    se_workers: list[SelfEmployedEmployee],
    company_name: str,
    day: int,
) -> list[SelfEmployedEmployee]:
    result = []
    for w in se_workers:
        if w.preferences.get(company_name, {}).get(day, 0) == 0:
            continue
        if w.exclusive_company and w.exclusive_company != company_name:
            continue
        if w.is_working_on(day):
            continue
        if w.assigned_days >= w.max_days:
            continue
        result.append(w)
    return result


def _fill_under_scheduled(
    se_workers: list[SelfEmployedEmployee],
    companies: dict[str, Company],
    rng: random.Random,
) -> None:
    under = [w for w in se_workers if w.assigned_days < w.min_days]
    if not under:
        return
    logger.info(f"  Post-sweep: {len(under)} SE workers under min_days")

    se_slots = [
        (company.name, day)
        for company in companies.values()
        for day in company.days
        if company.get_day(day).se_day_target >= MIN_SALARY
    ]
    rng.shuffle(se_slots)

    for worker in under:
        for company_name, day in se_slots:
            if worker.assigned_days >= worker.min_days:
                break
            if worker.preferences.get(company_name, {}).get(day, 0) == 0:
                continue
            if worker.exclusive_company and worker.exclusive_company != company_name:
                continue
            if worker.is_working_on(day):
                continue
            dl = companies[company_name].get_day(day)
            current = sum(1 for w in se_workers if (company_name, day) in w.schedule)
            n_max = math.floor(dl.se_day_target / MIN_SALARY)
            if current >= n_max:
                continue
            worker.add_shift(company_name, day, salary=0)

        if worker.assigned_days < worker.min_days:
            logger.warning(
                f"  SE {worker.name}: only {worker.assigned_days}/{worker.min_days} days "
                f"assigned — shortfall likely"
            )


def _fill_budget_deficient(
    se_workers: list[SelfEmployedEmployee],
    companies: dict[str, Company],
    rng: random.Random,
    all_workers: list[SelfEmployedEmployee],
) -> None:
    """Add extra slots for workers whose scheduled days can't cover their monthly target."""
    se_slots = [
        (company.name, day)
        for company in companies.values()
        for day in company.days
        if company.get_day(day).se_day_target >= MIN_SALARY
    ]
    rng.shuffle(se_slots)

    for worker in se_workers:
        if worker.assigned_days >= worker.max_days:
            continue
        max_achievable = sum(
            companies[c].get_day(d).se_day_target
            - sum(1 for w in all_workers if (c, d) in w.schedule and w.name != worker.name)
            * MIN_SALARY
            for (c, d) in worker.schedule
        )
        if max_achievable >= worker.salary:
            continue

        logger.info(
            f"  Budget-deficient: {worker.name} max_achievable={max_achievable} "
            f"< target={worker.salary}. Seeking extra slot."
        )
        for company_name, day in se_slots:
            if worker.assigned_days >= worker.max_days:
                break
            if max_achievable >= worker.salary:
                break
            if worker.preferences.get(company_name, {}).get(day, 0) == 0:
                continue
            if worker.exclusive_company and worker.exclusive_company != company_name:
                continue
            if worker.is_working_on(day):
                continue
            dl = companies[company_name].get_day(day)
            current = sum(1 for w in all_workers if (company_name, day) in w.schedule)
            n_max = math.floor(dl.se_day_target / MIN_SALARY)
            if current >= n_max:
                continue
            extra = dl.se_day_target - current * MIN_SALARY
            if extra <= 0:
                continue
            worker.add_shift(company_name, day, salary=0)
            max_achievable += extra
            logger.info(
                f"    Added {company_name} day {day} "
                f"(extra_budget={extra}, new_max={max_achievable})"
            )

        if max_achievable < worker.salary:
            logger.warning(
                f"  SE {worker.name}: budget-deficient even after extra slots "
                f"(max_achievable={max_achievable} < target={worker.salary})"
            )


def _log_summary(se_workers: list[SelfEmployedEmployee]) -> None:
    logger.info("-" * 60)
    logger.info("SE SCHEDULE SUMMARY:")
    for w in se_workers:
        by_company = {c: [] for c in COMPANY_NAMES}
        for (c, d) in w.schedule:
            by_company[c].append(d)
        status = "OK" if w.assigned_days >= w.min_days else f"SHORT({w.assigned_days}/{w.min_days})"
        logger.info(f"  {w.name:<12} [{status}] days={w.assigned_days}")
    logger.info("=" * 60)
