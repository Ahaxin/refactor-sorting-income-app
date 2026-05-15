"""
Load and validate all input CSV files.  Logs a structured data audit on startup.
"""

import logging
import math
import pandas as pd

from src.config import (
    EMPLOYEE_FILE, INCOME_FILE, PREFERENCE_FILE,
    GOOD_LIFE, TIANYUAN, COMPANY_NAMES,
    TYPE_SELF_EMPLOYED, TYPE_COMPANY_EMPLOYED,
)
from src.models.employee import SelfEmployedEmployee, CompanyEmployedEmployee
from src.models.company import Company

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def load_all() -> tuple[
    list[SelfEmployedEmployee],
    list[CompanyEmployedEmployee],
    dict[str, Company],
]:
    """
    Load employees, income, and preferences.
    Returns (se_employees, ce_employees, companies).
    """
    logger.info("=" * 60)
    logger.info("DATA AUDIT — loading input files")
    logger.info("=" * 60)

    se_workers, ce_workers = _load_employees()
    companies = _load_income()
    _load_preferences(se_workers, ce_workers, companies)

    _log_summary(se_workers, ce_workers, companies)
    return se_workers, ce_workers, companies


# ---------------------------------------------------------------------------
# Employee loading
# ---------------------------------------------------------------------------

def _load_employees() -> tuple[list[SelfEmployedEmployee], list[CompanyEmployedEmployee]]:
    df = pd.read_csv(EMPLOYEE_FILE)
    logger.info(f"Loaded {EMPLOYEE_FILE}: {len(df)} rows")

    se_workers: list[SelfEmployedEmployee] = []
    ce_workers: list[CompanyEmployedEmployee] = []
    has_excl_col = "exclusive_company" in df.columns

    for _, row in df.iterrows():
        name = str(row["name"]).strip()
        emp_type = str(row["type"]).strip()
        salary = int(row["salary"])

        if emp_type == TYPE_SELF_EMPLOYED:
            worker: SelfEmployedEmployee | CompanyEmployedEmployee = SelfEmployedEmployee(name, salary)
            se_workers.append(worker)
        elif emp_type == TYPE_COMPANY_EMPLOYED:
            worker = CompanyEmployedEmployee(name, salary)
            ce_workers.append(worker)
        else:
            logger.warning(f"  Unknown employee type '{emp_type}' for {name} — skipping")
            continue

        if has_excl_col:
            excl_raw = row["exclusive_company"]
            excl = (
                ""
                if (excl_raw is None or (isinstance(excl_raw, float) and math.isnan(excl_raw)))
                else str(excl_raw).strip()
            )
            if excl:
                if "good" in excl.lower():
                    worker.exclusive_company = GOOD_LIFE
                elif "tian" in excl.lower():
                    worker.exclusive_company = TIANYUAN
                else:
                    logger.warning(f"  exclusive_company: unrecognised value '{excl}' for {name}")
                if worker.exclusive_company:
                    logger.info(f"  {name} is exclusive to {worker.exclusive_company}")

    logger.info(
        f"  Self-employed:     {len(se_workers)} workers, "
        f"total monthly target = {sum(w.salary for w in se_workers):,}"
    )
    logger.info(
        f"  Company-employed:  {len(ce_workers)} workers, "
        f"total monthly cap    = {sum(w.salary for w in ce_workers):,}"
    )
    return se_workers, ce_workers


# ---------------------------------------------------------------------------
# Income loading
# ---------------------------------------------------------------------------

def _load_income() -> dict[str, Company]:
    df = pd.read_csv(INCOME_FILE)
    logger.info(f"Loaded {INCOME_FILE}: {len(df)} rows (days {df['day'].min()}–{df['day'].max()})")

    companies: dict[str, Company] = {name: Company(name) for name in COMPANY_NAMES}

    for _, row in df.iterrows():
        day = int(row["day"])
        companies[GOOD_LIFE].add_day(day, int(row["good_life"]))
        companies[TIANYUAN].add_day(day, int(row["tianyuan"]))

    for cname, company in companies.items():
        incomes = [dl.raw_income for dl in company.ledger.values()]
        logger.info(f"  {cname}: income range [{min(incomes)}, {max(incomes)}], "
                    f"total cleaned = {company.total_cleaned_income:,}")

    return companies


# ---------------------------------------------------------------------------
# Preference loading
# ---------------------------------------------------------------------------

def _load_preferences(
    se_workers: list[SelfEmployedEmployee],
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
) -> None:
    """
    Parse updated_preference.csv and attach preference data to each worker.
    Stores preferences as a nested dict on each employee:
        employee.preferences[company][day] = 0 | 1 | 2
    """
    df = pd.read_csv(PREFERENCE_FILE)
    logger.info(f"Loaded {PREFERENCE_FILE}: {len(df)} rows")

    all_workers: dict[str, SelfEmployedEmployee | CompanyEmployedEmployee] = {
        w.name: w for w in [*se_workers, *ce_workers]
    }

    # Column headers after "Company" and "Day"
    pref_cols = [c for c in df.columns if c not in ("Company", "Day")]

    # Verify all preference columns have a matching employee
    unknown = [c for c in pref_cols if c not in all_workers]
    if unknown:
        logger.warning(f"  Preference columns with no matching employee: {unknown}")

    # Initialise preference dicts (base class already declares this field)
    for worker in all_workers.values():
        worker.preferences = {GOOD_LIFE: {}, TIANYUAN: {}}

    zero_days: dict[str, int] = {GOOD_LIFE: 0, TIANYUAN: 0}

    for _, row in df.iterrows():
        company = str(row["Company"]).strip().lower().replace(" ", "_")
        day = int(row["Day"])

        if company not in (GOOD_LIFE, TIANYUAN):
            # Normalise "tian yuan" / "tianyuan" variants
            if "tian" in company:
                company = TIANYUAN
            elif "good" in company:
                company = GOOD_LIFE
            else:
                logger.warning(f"  Unknown company '{company}' in preferences — skipping row")
                continue

        for col in pref_cols:
            if col not in all_workers:
                continue
            cell = row[col]
            val = 0 if (cell is None or (isinstance(cell, float) and math.isnan(cell))) else int(cell)
            all_workers[col].preferences[company][day] = val
            if val == 0:
                zero_days[company] += 1

    logger.info(f"  Preference zero-days: {GOOD_LIFE}={zero_days[GOOD_LIFE]}, "
                f"{TIANYUAN}={zero_days[TIANYUAN]}")


# ---------------------------------------------------------------------------
# Summary audit log
# ---------------------------------------------------------------------------

def _log_summary(
    se_workers: list[SelfEmployedEmployee],
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
) -> None:
    logger.info("-" * 60)
    logger.info("SE WORKERS — monthly target and estimated work days:")
    for w in se_workers:
        excl = f" [exclusive: {w.exclusive_company}]" if w.exclusive_company else ""
        logger.info(f"  {w.name:<12} target={w.salary:>5}  target_days={w.target_days}{excl}")

    logger.info("CE WORKERS:")
    for w in ce_workers:
        excl = f" [exclusive: {w.exclusive_company}]" if w.exclusive_company else ""
        logger.info(f"  {w.name:<12} cap={w.salary:>6}{excl}")

    logger.info("=" * 60)
