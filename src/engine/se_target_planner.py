"""
SE Target Planner — sets per-day SE_day_target with CE capacity awareness.

For each (company, day):
  LB_d = RATIO * max(0, I_d - max_ce_excl_d)
    where max_ce_excl_d = #(exclusive CE workers with pref>0) * CE_MAX_PER_DAY,
    capped at I_d. This is the minimum SE needed so that the residual CE work
    fits within the EXCLUSIVE CE pool on this day — independent of how the
    flexible (any-company) CE workers are placed.
  UB_d = RATIO * I_d (formula upper bound: SE/RATIO + CE = I requires SE <= RATIO*I)

The total SE pool (sum of all SE worker monthly targets) is distributed across
days such that each day's target lies in [LB_d, UB_d]. Days where UB_d <
MIN_SALARY are marked CE-only (target = 0). Days where LB_d < MIN_SALARY but
UB_d >= MIN_SALARY are bumped up to MIN_SALARY so the SE scheduler does not
skip them.

Compared to a uniform 0.4*I_d target, this concentrates SE delivery on days
where CE has weaker coverage (e.g., only 1 exclusive worker eligible) and
relaxes SE on days where the CE pool can absorb the residual.
"""

import logging

from src.config import CE_MAX_PER_DAY, MIN_SALARY, RATIO, SE_SALARY_UNIT
from src.models.company import Company
from src.models.employee import CompanyEmployedEmployee, SelfEmployedEmployee

logger = logging.getLogger(__name__)


def plan_se_day_targets(
    companies: dict[str, Company],
    ce_workers: list[CompanyEmployedEmployee],
    se_workers: list[SelfEmployedEmployee],
) -> None:
    """Set per-day SE_day_target on every DayLedger, accounting for CE capacity."""
    logger.info("=" * 60)
    logger.info("SE DAY-TARGET PLANNING (CE-aware)")
    logger.info("=" * 60)

    total_se_pool = sum(w.salary for w in se_workers)

    day_info: list[tuple] = []
    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            n_excl = sum(
                1 for w in ce_workers
                if w.preferences.get(company.name, {}).get(day, 0) > 0
                and w.exclusive_company == company.name
            )
            max_ce_excl = min(dl.cleaned_income, n_excl * CE_MAX_PER_DAY)
            ub = round(RATIO * dl.cleaned_income)
            lb_raw = round(RATIO * max(0, dl.cleaned_income - max_ce_excl))
            if ub < MIN_SALARY:
                lb_eff, ub_eff = 0, 0
            else:
                lb_eff = max(lb_raw, MIN_SALARY)
                ub_eff = max(lb_eff, ub)
            day_info.append((dl, lb_eff, ub_eff))

    sum_lb = sum(info[1] for info in day_info)
    sum_ub = sum(info[2] for info in day_info)
    logger.info(f"  SE pool={total_se_pool}, sum_LB={sum_lb}, sum_UB={sum_ub}")

    if total_se_pool <= sum_lb:
        scale = total_se_pool / sum_lb if sum_lb > 0 else 0
        for dl, lb, _ in day_info:
            target = (round(lb * scale) // SE_SALARY_UNIT) * SE_SALARY_UNIT
            dl.set_se_day_target(target)
        if total_se_pool < sum_lb:
            logger.warning(
                f"  SE pool ({total_se_pool}) below required minimum ({sum_lb}) — "
                "expect formula deviation on tight days"
            )
        return

    if total_se_pool >= sum_ub:
        for dl, _, ub in day_info:
            dl.set_se_day_target(ub)
        logger.warning(
            f"  SE pool ({total_se_pool}) exceeds sum_UB ({sum_ub}) — "
            "SE will fully cover; CE work minimized"
        )
        return

    extra = total_se_pool - sum_lb
    sum_slack = sum(info[2] - info[1] for info in day_info)
    for dl, lb, ub in day_info:
        slack = ub - lb
        share = round((slack / sum_slack) * extra) if sum_slack > 0 else 0
        target = lb + share
        target = (target // SE_SALARY_UNIT) * SE_SALARY_UNIT
        target = max(lb, min(ub, target))
        dl.set_se_day_target(target)
