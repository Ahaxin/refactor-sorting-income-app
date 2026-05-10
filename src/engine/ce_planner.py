"""
CE Planner — Phase 3 (runs after SE salary solving).

Distributes the formula residual on each day to eligible CE workers.
  CE_day_residual = max(0, I_clean - round(SE_day_total / RATIO))
CE workers earn at most MAX_PER_DAY per day and at most their monthly cap total.
"""

import logging
import random

from src.config import CE_SALARY_UNIT, RATIO
from src.models.employee import CompanyEmployedEmployee
from src.models.company import Company

logger = logging.getLogger(__name__)


def plan_ce(
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
    rng: random.Random,
) -> None:
    """Distribute formula residuals to CE workers after SE salaries are solved."""
    logger.info("=" * 60)
    logger.info("CE PLANNING PHASE (residual)")
    logger.info("=" * 60)

    if not ce_workers:
        logger.info("  No CE workers — skipping")
        return

    remaining_cap = {w.name: w.salary for w in ce_workers}

    all_days = sorted(
        [(company, day) for company in companies.values() for day in company.days],
        key=lambda cd: cd[0].get_day(cd[1]).cleaned_income,
        reverse=True,
    )

    for company, day in all_days:
        dl = company.get_day(day)
        se_implied = round(dl.se_total / RATIO) if dl.se_total > 0 else 0
        ce_residual = dl.cleaned_income - se_implied
        if ce_residual <= 0:
            continue

        eligible = [
            w for w in ce_workers
            if (w.exclusive_company is None or w.exclusive_company == company.name)
            and w.preferences.get(company.name, {}).get(day, 0) > 0
            and not w.is_working_on(day)
            and remaining_cap[w.name] >= CE_SALARY_UNIT
        ]
        if not eligible:
            continue

        rng.shuffle(eligible)
        _distribute_residual(ce_residual, eligible, remaining_cap, dl, company.name, day)

    _validate_ce_non_negative(ce_workers, companies)
    _log_ce_summary(ce_workers)


def _distribute_residual(
    residual: int,
    eligible: list[CompanyEmployedEmployee],
    remaining_cap: dict[str, int],
    dl,
    company_name: str,
    day: int,
) -> None:
    """Assign CE residual to eligible workers, respecting caps and MAX_PER_DAY."""
    leftover = residual
    workers = sorted(eligible, key=lambda w: remaining_cap[w.name], reverse=True)
    for w in workers:
        if leftover < CE_SALARY_UNIT:
            break
        cap_avail = min(remaining_cap[w.name], leftover)  # CE has no per-day cap
        amount = (cap_avail // CE_SALARY_UNIT) * CE_SALARY_UNIT
        if amount < CE_SALARY_UNIT:
            continue
        dl.ce_salaries[w.name] = dl.ce_salaries.get(w.name, 0) + amount
        w.schedule[(company_name, day)] = w.schedule.get((company_name, day), 0) + amount
        remaining_cap[w.name] -= amount
        leftover -= amount


def _validate_ce_non_negative(
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
) -> None:
    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            if dl.ce_total < 0:
                logger.warning(
                    f"  VALIDATION ERROR: {company.name} day {day} "
                    f"CE_total={dl.ce_total} IS NEGATIVE"
                )
            for name, amt in dl.ce_salaries.items():
                if amt < 0:
                    logger.warning(
                        f"  VALIDATION ERROR: CE {name} @ {company.name} day {day} "
                        f"salary={amt} IS NEGATIVE"
                    )


def _log_ce_summary(ce_workers: list[CompanyEmployedEmployee]) -> None:
    logger.info("-" * 60)
    logger.info("CE ASSIGNMENT SUMMARY:")
    for w in ce_workers:
        actual = w.actual_monthly_salary
        cap = w.salary
        pct = f"{actual / cap * 100:.1f}%" if cap else "N/A"
        logger.info(f"  {w.name:<12} cap={cap:>6} actual={actual:>6} ({pct} of cap)")
    logger.info("=" * 60)
