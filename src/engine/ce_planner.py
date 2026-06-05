"""
CE Planner — Phase 3 (runs after SE salary solving).

Distributes the formula residual on each day to eligible CE workers.
  CE_day_residual = max(0, I_clean - round(SE_day_total / RATIO))
CE workers earn at most CE_MAX_PER_DAY per day and at most their monthly cap.

Allocation strategy (max-flow):
  - Flexible (any-company) CE workers are pre-assigned to ONE company per day
    based on which side has the larger residual / deficit. This avoids the
    physical impossibility of a single worker contributing to both companies
    on the same calendar day.
  - All remaining CE-workers-per-(company, day) cells are modeled as a max-flow
    network with monthly cap, per-day cap, and per-(company,day) residual as
    edge capacities. networkx.maximum_flow finds the globally optimal
    distribution.
"""

import logging
import random

import networkx as nx

from src.config import CE_MAX_PER_DAY, CE_SALARY_UNIT, RATIO
from src.models.employee import CompanyEmployedEmployee
from src.models.company import Company

logger = logging.getLogger(__name__)


def plan_ce(
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
    rng: random.Random,  # kept for signature compatibility; allocation is deterministic
) -> None:
    """Distribute formula residuals to CE workers via max-flow."""
    logger.info("=" * 60)
    logger.info("CE PLANNING PHASE (max-flow)")
    logger.info("=" * 60)

    if not ce_workers:
        logger.info("  No CE workers — skipping")
        return

    residuals = _compute_residuals(companies)
    if not residuals:
        logger.info("  All days have zero CE residual — nothing to assign")
        return

    fw_assignment = _assign_flexible_workers(ce_workers, companies, residuals)
    _apply_flow(ce_workers, companies, residuals, fw_assignment)

    _validate_ce_non_negative(ce_workers, companies)
    _log_unabsorbed_residual(residuals, companies)
    _log_ce_summary(ce_workers)


def _compute_residuals(
    companies: dict[str, Company],
) -> dict[tuple[str, int], int]:
    """Return {(company_name, day): residual} for days with positive residual."""
    residuals: dict[tuple[str, int], int] = {}
    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            se_implied = round(dl.se_total / RATIO) if dl.se_total > 0 else 0
            residual = dl.cleaned_income - se_implied
            if residual > 0:
                residuals[(company.name, day)] = residual
    return residuals


def _assign_flexible_workers(
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
    residuals: dict[tuple[str, int], int],
) -> dict[tuple[str, int], str]:
    """Pre-assign each flexible (any-company) CE worker to one company per day.

    For each day, the worker is placed on the company with the largest
    (deficit, residual) — deficit being the residual after exclusive workers
    fully absorb their day-cap. This concentrates the flexible worker where
    they can do real work.
    """
    flexible = [w for w in ce_workers if w.exclusive_company is None]
    all_days = sorted(set(d for c in companies.values() for d in c.days))
    fw_assignment: dict[tuple[str, int], str] = {}
    for fw in flexible:
        for day in all_days:
            options = []
            for company in companies.values():
                if (company.name, day) not in residuals:
                    continue
                if fw.preferences.get(company.name, {}).get(day, 0) <= 0:
                    continue
                excl_cap = sum(
                    CE_MAX_PER_DAY for ew in ce_workers
                    if ew.exclusive_company == company.name
                    and ew.preferences.get(company.name, {}).get(day, 0) > 0
                )
                deficit = max(0, residuals[(company.name, day)] - excl_cap)
                options.append((deficit, residuals[(company.name, day)], company.name))
            if not options:
                continue
            options.sort(reverse=True)
            fw_assignment[(fw.name, day)] = options[0][2]
    return fw_assignment


def _apply_flow(
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
    residuals: dict[tuple[str, int], int],
    fw_assignment: dict[tuple[str, int], str],
) -> None:
    """Build the max-flow network, solve it, and write allocations to ledgers."""
    G = nx.DiGraph()
    unit = CE_SALARY_UNIT
    day_cap = CE_MAX_PER_DAY // unit

    for w in ce_workers:
        cap_units = w.salary // unit
        if cap_units > 0:
            G.add_edge("SRC", w.name, capacity=cap_units)

    for w in ce_workers:
        for company in companies.values():
            for day in company.days:
                if (company.name, day) not in residuals:
                    continue
                if w.preferences.get(company.name, {}).get(day, 0) <= 0:
                    continue
                if w.exclusive_company and w.exclusive_company != company.name:
                    continue
                if w.exclusive_company is None:
                    assigned = fw_assignment.get((w.name, day))
                    if assigned and assigned != company.name:
                        continue
                wd = f"wd|{w.name}|{day}"
                cell = f"cell|{w.name}|{day}|{company.name}"
                cd = f"cd|{company.name}|{day}"
                G.add_edge(w.name, wd, capacity=day_cap)
                G.add_edge(wd, cell, capacity=day_cap)
                G.add_edge(cell, cd, capacity=day_cap)

    for (cname, day), residual in residuals.items():
        cap_units = residual // unit
        if cap_units > 0:
            G.add_edge(f"cd|{cname}|{day}", "SNK", capacity=cap_units)

    if "SRC" not in G or "SNK" not in G:
        return

    _, flow_dict = nx.maximum_flow(G, "SRC", "SNK")

    for w in ce_workers:
        for company in companies.values():
            for day in company.days:
                cell = f"cell|{w.name}|{day}|{company.name}"
                cd = f"cd|{company.name}|{day}"
                if cell not in flow_dict:
                    continue
                amount = flow_dict[cell].get(cd, 0) * unit
                if amount > 0:
                    dl = company.get_day(day)
                    dl.ce_salaries[w.name] = dl.ce_salaries.get(w.name, 0) + amount
                    w.schedule[(company.name, day)] = w.schedule.get((company.name, day), 0) + amount


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


def _log_unabsorbed_residual(
    residuals: dict[tuple[str, int], int],
    companies: dict[str, Company],
) -> None:
    """Warn about days where max-flow could not fully cover the formula residual."""
    unabsorbed = []
    for (cname, day), residual in residuals.items():
        dl = companies[cname].get_day(day)
        leftover = residual - dl.ce_total
        if leftover >= CE_SALARY_UNIT:
            unabsorbed.append((cname, day, residual, leftover))
    if not unabsorbed:
        return
    total_lost = sum(leftover for _, _, _, leftover in unabsorbed)
    logger.warning("-" * 60)
    logger.warning(
        f"UNABSORBED CE RESIDUAL: {len(unabsorbed)} day(s), "
        f"{total_lost} total left unassigned"
    )
    logger.warning(
        "  (formula SE/RATIO + CE = I_clean will deviate on these days — "
        "CE pool insufficient given per-day cap, monthly caps, or eligibility)"
    )
    for company_name, day, residual, leftover in sorted(unabsorbed):
        logger.warning(
            f"  {company_name} day {day}: residual={residual}, "
            f"unabsorbed={leftover}"
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
