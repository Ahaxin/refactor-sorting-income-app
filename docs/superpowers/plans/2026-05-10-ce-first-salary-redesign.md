# CE-first Salary Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the salary scheduler so CE workers are planned first (income-weighted random day selection), the per-day formula `Σ SE = (I_clean − Σ CE) × 0.4` is an exact equality, and every SE worker hits their monthly target exactly.

**Architecture:** CE planner runs first using total CE budget derived from the formula identity; SE scheduler then fills the residual per-day budgets; a two-stage Sinkhorn + integer-repair solver hits exact SE monthly targets. Old `scheduler.py` is split into `ce_planner.py` + `se_scheduler.py`.

**Tech Stack:** Python 3.11+, pytest, openpyxl, pandas. No new external dependencies.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/config.py` | Split SALARY_UNIT → SE_SALARY_UNIT=2, CE_SALARY_UNIT=5; add MAX_PER_DAY; remove RANDOM_SEED |
| Modify | `src/models/company.py` | Replace compute_se_budget with compute_se_target_from_ce; remove is_infeasible/is_ce_only; add is_full_ce_absorption |
| Create | `src/engine/feasibility.py` | Pre-flight SE feasibility check |
| Create | `src/engine/ce_planner.py` | CE monthly budget allocation + income-weighted day assignment |
| Create | `src/engine/se_scheduler.py` | SE worker assignment within per-day SE budgets |
| Rewrite | `src/engine/salary_solver.py` | Two-stage Sinkhorn + integer-repair for exact SE targets |
| Delete | `src/engine/scheduler.py` | Replaced by ce_planner + se_scheduler |
| Modify | `main.py` | Seed resolution (--seed / env / auto), new pipeline order |
| Modify | `src/reports/excel_writer.py` | Remove is_infeasible/is_ce_only refs; add seed/phantom/shortfall to Summary |
| Create | `tests/conftest.py` | Shared fixtures (tiny synthetic companies + workers) |
| Create | `tests/test_config_models.py` | config constants + DayLedger.compute_se_target_from_ce |
| Create | `tests/test_feasibility.py` | Feasibility check logic |
| Create | `tests/test_ce_planner.py` | CE budget allocation + day selection |
| Create | `tests/test_se_scheduler.py` | SE worker assignment |
| Create | `tests/test_salary_solver.py` | Exact-target solver: row sums, col sums, cell bounds |
| Create | `tests/test_integration.py` | End-to-end: math invariants, determinism, infeasible fallback |

---

## Task 1: Update config.py

**Files:** Modify `src/config.py`

- [ ] **Step 1: Update constants**

Replace the existing file content:

```python
"""
Configuration constants for the monthly salary/schedule planner.
"""

# Salary granularity
SE_SALARY_UNIT = 2    # SE individual daily salary must be even integer
CE_SALARY_UNIT = 5    # CE individual daily salary must be multiple of 5
INCOME_UNIT = 5       # I_clean rounded to multiple of 5

# Salary bounds for SE workers (per day). CE has no per-day lower bound.
MIN_SALARY = 120
MAX_SALARY = 400
MAX_PER_DAY = 400     # upper bound for both SE and CE daily salary

# Used to estimate preferred number of working days per SE worker
PREDEFINED_DAILY = 180

# Sinkhorn solver settings
SOLVER_MAX_ITER = 3000
SOLVER_TOL = 1e-1

# The 40% profit-sharing ratio
RATIO = 0.40

# Data file paths
DATA_DIR = "data"
EMPLOYEE_FILE = f"{DATA_DIR}/employee_data.csv"
INCOME_FILE = f"{DATA_DIR}/income_data.csv"
PREFERENCE_FILE = f"{DATA_DIR}/updated_preference.csv"
PREF_ALT_FILE = f"{DATA_DIR}/preferences.csv"

# Output
OUTPUT_DIR = "output"
OUTPUT_FILE = f"{OUTPUT_DIR}/report.xlsx"

# Company name constants
GOOD_LIFE = "good_life"
TIANYUAN = "tianyuan"
COMPANY_NAMES = [GOOD_LIFE, TIANYUAN]

# Employee type constants
TYPE_SELF_EMPLOYED = "Self-Employed"
TYPE_COMPANY_EMPLOYED = "Company-Employed"
```

- [ ] **Step 2: Verify no import errors**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -c "from src.config import SE_SALARY_UNIT, CE_SALARY_UNIT, MAX_PER_DAY; print('OK')"
```
Expected: `OK`

---

## Task 2: Update DayLedger model

**Files:** Modify `src/models/company.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_config_models.py`:

```python
"""Tests for config constants and DayLedger model."""
import pytest
from src.models.company import DayLedger, clean_income


def test_clean_income_multiple_of_5():
    assert clean_income(1007) == 1005
    assert clean_income(1000) == 1000
    assert clean_income(1004) == 1000


def test_compute_se_target_from_ce_exact():
    dl = DayLedger(day=1, raw_income=2005)
    # I_clean = 2005 (already multiple of 5)
    # CE_day = 200, SE_target = (2005 - 200) * 0.4 = 722.0
    result = dl.compute_se_target_from_ce(200)
    assert result == 722
    assert not dl.is_full_ce_absorption


def test_compute_se_target_full_ce_absorption():
    dl = DayLedger(day=1, raw_income=1000)
    result = dl.compute_se_target_from_ce(1000)
    assert result == 0
    assert dl.is_full_ce_absorption


def test_compute_se_target_zero_ce():
    dl = DayLedger(day=1, raw_income=1000)
    result = dl.compute_se_target_from_ce(0)
    assert result == 400  # 1000 * 0.4
    assert not dl.is_full_ce_absorption


def test_se_target_always_even_integer():
    # I_clean multiple of 5, CE multiple of 5 → result multiple of 2
    for raw_income in [1000, 1005, 1500, 2000, 3750]:
        for ce in range(0, raw_income, 5):
            dl = DayLedger(day=1, raw_income=raw_income)
            result = dl.compute_se_target_from_ce(ce)
            assert result % 2 == 0, f"raw={raw_income} ce={ce} result={result}"
            break  # just spot-check first value per income


def test_no_infeasible_or_ce_only_flags():
    dl = DayLedger(day=1, raw_income=1000)
    assert not hasattr(dl, 'is_infeasible') or dl.is_infeasible is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/test_config_models.py -v 2>&1 | head -30
```
Expected: ImportError or AttributeError (compute_se_target_from_ce doesn't exist yet)

- [ ] **Step 3: Rewrite company.py**

Replace `src/models/company.py`:

```python
"""
Company model holding daily income and the computed SE/CE ledger.
"""

from src.config import INCOME_UNIT, RATIO


def clean_income(raw: int) -> int:
    """Round income down to the nearest multiple of INCOME_UNIT."""
    return (raw // INCOME_UNIT) * INCOME_UNIT


class DayLedger:
    """Financial record for a single (company, day) pair."""

    def __init__(self, day: int, raw_income: int):
        self.day = day
        self.raw_income = raw_income
        self.cleaned_income: int = clean_income(raw_income)

        self.ce_salaries: dict[str, int] = {}
        self.se_salaries: dict[str, int] = {}
        self._se_day_target: int = 0
        self.is_full_ce_absorption: bool = False

    def compute_se_target_from_ce(self, ce_total: int) -> int:
        """
        SE_day_target = (I_clean - CE_total) * RATIO exactly.
        Sets is_full_ce_absorption when result is 0.
        Returns an even integer (guaranteed when I_clean and CE are multiples of 5).
        """
        net = self.cleaned_income - ce_total
        target = int(round(net * RATIO))
        self._se_day_target = target
        self.is_full_ce_absorption = (target == 0)
        return target

    @property
    def se_day_target(self) -> int:
        return self._se_day_target

    @property
    def se_budget(self) -> int:
        """Alias for backward-compat during transition."""
        return self._se_day_target

    @property
    def ce_total(self) -> int:
        return sum(self.ce_salaries.values())

    @property
    def se_total(self) -> int:
        return sum(self.se_salaries.values())

    @property
    def formula_check(self) -> float:
        """SE / RATIO + CE should equal I_clean."""
        if RATIO == 0:
            return 0.0
        return self.se_total / RATIO + self.ce_total


class Company:
    """Represents one company with daily income and the full monthly ledger."""

    def __init__(self, name: str):
        self.name = name
        self.ledger: dict[int, DayLedger] = {}

    def add_day(self, day: int, raw_income: int):
        self.ledger[day] = DayLedger(day, raw_income)

    def get_day(self, day: int) -> DayLedger:
        return self.ledger[day]

    @property
    def days(self) -> list[int]:
        return sorted(self.ledger.keys())

    @property
    def total_cleaned_income(self) -> int:
        return sum(dl.cleaned_income for dl in self.ledger.values())

    @property
    def total_se(self) -> int:
        return sum(dl.se_total for dl in self.ledger.values())

    @property
    def total_ce(self) -> int:
        return sum(dl.ce_total for dl in self.ledger.values())
```

- [ ] **Step 4: Run tests**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/test_config_models.py -v
```
Expected: all pass

---

## Task 3: Feasibility check module

**Files:** Create `src/engine/feasibility.py`, create `tests/test_feasibility.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_feasibility.py`:

```python
"""Tests for pre-flight SE feasibility check."""
import logging
import pytest
from src.models.company import Company
from src.models.employee import SelfEmployedEmployee


def _make_companies(gl_incomes: list[int], ty_incomes: list[int]) -> dict:
    from src.config import GOOD_LIFE, TIANYUAN
    companies = {GOOD_LIFE: Company(GOOD_LIFE), TIANYUAN: Company(TIANYUAN)}
    for day, inc in enumerate(gl_incomes, start=1):
        companies[GOOD_LIFE].add_day(day, inc)
    for day, inc in enumerate(ty_incomes, start=1):
        companies[TIANYUAN].add_day(day, inc)
    return companies


def test_feasible_returns_true(caplog):
    se = [SelfEmployedEmployee("A", 400), SelfEmployedEmployee("B", 400)]
    companies = _make_companies([5000], [5000])
    with caplog.at_level(logging.WARNING):
        from src.engine.feasibility import check_se_feasibility
        result = check_se_feasibility(se, companies)
    assert result is True
    assert "infeasible" not in caplog.text.lower()


def test_infeasible_returns_false_and_warns(caplog):
    # total I_clean = 1000, 0.4*1000 = 400, but SE targets = 500
    se = [SelfEmployedEmployee("A", 500)]
    companies = _make_companies([1000], [])
    with caplog.at_level(logging.WARNING):
        from src.engine.feasibility import check_se_feasibility
        result = check_se_feasibility(se, companies)
    assert result is False
    assert "infeasible" in caplog.text.lower()


def test_feasibility_returns_budget_info():
    se = [SelfEmployedEmployee("A", 200)]
    companies = _make_companies([1000], [1000])
    from src.engine.feasibility import check_se_feasibility, compute_totals
    total_clean, max_se, sum_targets = compute_totals(se, companies)
    assert total_clean == 2000
    assert max_se == 800   # 0.4 * 2000
    assert sum_targets == 200
```

- [ ] **Step 2: Confirm failure**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/test_feasibility.py -v 2>&1 | head -20
```

- [ ] **Step 3: Implement feasibility.py**

Create `src/engine/feasibility.py`:

```python
"""Pre-flight SE feasibility check."""
import logging
from src.config import RATIO
from src.models.company import Company
from src.models.employee import SelfEmployedEmployee

logger = logging.getLogger(__name__)


def compute_totals(
    se_workers: list[SelfEmployedEmployee],
    companies: dict[str, Company],
) -> tuple[int, float, int]:
    """Return (total_I_clean, max_SE_possible, sum_SE_targets)."""
    total_clean = sum(
        dl.cleaned_income
        for company in companies.values()
        for dl in company.ledger.values()
    )
    max_se = total_clean * RATIO
    sum_targets = sum(w.salary for w in se_workers)
    return total_clean, max_se, sum_targets


def check_se_feasibility(
    se_workers: list[SelfEmployedEmployee],
    companies: dict[str, Company],
) -> bool:
    """
    Returns True if SE targets are achievable (sum_targets <= 0.4 * total_I_clean).
    Logs a loud WARNING and returns False otherwise.
    """
    total_clean, max_se, sum_targets = compute_totals(se_workers, companies)
    if sum_targets > max_se:
        gap = sum_targets - max_se
        logger.warning("=" * 60)
        logger.warning("SE TARGETS INFEASIBLE — falling back to best-effort mode")
        logger.warning(f"  SE targets needed : {sum_targets:,.0f}")
        logger.warning(f"  Max SE possible   : {max_se:,.0f}  (0.4 × total I_clean {total_clean:,})")
        logger.warning(f"  Shortfall gap     : {gap:,.0f}")
        logger.warning("=" * 60)
        return False
    return True
```

- [ ] **Step 4: Run tests**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/test_feasibility.py -v
```
Expected: all pass

---

## Task 4: CE planner — budget allocation

**Files:** Create `src/engine/ce_planner.py`, create `tests/test_ce_planner.py` (budget portion)

- [ ] **Step 1: Write failing tests for budget allocation**

Create `tests/test_ce_planner.py`:

```python
"""Tests for CE planner."""
import math
import random
import pytest
from src.models.company import Company
from src.models.employee import CompanyEmployedEmployee, SelfEmployedEmployee
from src.config import GOOD_LIFE, TIANYUAN, CE_SALARY_UNIT


def _company(name, incomes):
    c = Company(name)
    for day, inc in enumerate(incomes, start=1):
        c.add_day(day, inc)
    return c


def _ce(name, cap, company_name):
    w = CompanyEmployedEmployee(name, cap)
    w.exclusive_company = company_name
    # preferences: P=2 on all days of that company
    w.preferences = {company_name: {d: 2 for d in range(1, len([]) + 1)}}
    return w


# ---- budget allocation tests ----

def test_compute_ce_budgets_full_cap():
    """When CE budget >= sum of caps, each worker gets their full cap."""
    from src.engine.ce_planner import compute_ce_worker_budgets
    se_targets_sum = 0
    total_clean = 10000
    caps = {"A": 1000, "B": 2000}
    # total_CE_budget = 10000 - 2.5*0 = 10000 >= 3000
    budgets, phantom = compute_ce_worker_budgets(caps, total_clean, se_targets_sum)
    assert budgets["A"] == 1000
    assert budgets["B"] == 2000
    assert phantom == 7000   # 10000 - 3000


def test_compute_ce_budgets_proportional_shortfall():
    """When CE budget < sum of caps, scale proportionally to cap."""
    from src.engine.ce_planner import compute_ce_worker_budgets
    # total_CE_budget = 5000 - 2.5*1000 = 2500
    # caps: A=1000, B=4000, sum=5000 > 2500 → shortfall
    caps = {"A": 1000, "B": 4000}
    total_clean = 5000
    se_targets_sum = 1000
    budgets, phantom = compute_ce_worker_budgets(caps, total_clean, se_targets_sum)
    # A gets floor(1000 * 2500/5000 / 5)*5 = floor(500/5)*5 = 500
    # B gets floor(4000 * 2500/5000 / 5)*5 = floor(2000/5)*5 = 2000
    assert budgets["A"] == 500
    assert budgets["B"] == 2000
    assert sum(budgets.values()) == 2500
    assert phantom == 0


def test_compute_ce_budgets_multiples_of_5():
    """All CE budgets are multiples of 5."""
    from src.engine.ce_planner import compute_ce_worker_budgets
    caps = {"A": 1234, "B": 5678}
    total_clean = 50000
    budgets, _ = compute_ce_worker_budgets(caps, total_clean, 0)
    for name, amount in budgets.items():
        assert amount % CE_SALARY_UNIT == 0, f"{name}: {amount} not multiple of {CE_SALARY_UNIT}"


def test_compute_ce_budgets_infeasible_se():
    """If total_CE_budget < 0 (infeasible SE), all workers get 0."""
    from src.engine.ce_planner import compute_ce_worker_budgets
    caps = {"A": 1000}
    # total_CE_budget = 1000 - 2.5*1000 = -1500 < 0
    budgets, phantom = compute_ce_worker_budgets(caps, 1000, 1000)
    assert budgets["A"] == 0
    assert phantom == 0
```

- [ ] **Step 2: Confirm failure**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/test_ce_planner.py::test_compute_ce_budgets_full_cap -v 2>&1 | head -20
```

- [ ] **Step 3: Implement compute_ce_worker_budgets in ce_planner.py**

Create `src/engine/ce_planner.py`:

```python
"""
CE Planner — Phase 2.

Computes each CE worker's monthly budget, then assigns shifts to
high-income eligible days using income-weighted random selection.
"""

import logging
import math
import random

from src.config import (
    RATIO, CE_SALARY_UNIT, MAX_PER_DAY, GOOD_LIFE, TIANYUAN, COMPANY_NAMES,
)
from src.models.employee import CompanyEmployedEmployee
from src.models.company import Company

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


def compute_ce_worker_budgets(
    caps: dict[str, int],
    total_clean: int,
    se_targets_sum: int,
) -> tuple[dict[str, int], int]:
    """
    Returns (worker_budgets, phantom_CE).

    worker_budgets: {name: monthly_amount} — each a multiple of CE_SALARY_UNIT.
    phantom_CE: unallocatable surplus when total_CE_budget > sum(caps).
    """
    total_ce_budget = int(round(total_clean - (se_targets_sum / RATIO)))
    if total_ce_budget <= 0:
        return {name: 0 for name in caps}, 0

    sum_caps = sum(caps.values())
    budgets: dict[str, int] = {}

    if total_ce_budget >= sum_caps:
        for name, cap in caps.items():
            budgets[name] = cap
        phantom = total_ce_budget - sum_caps
        return budgets, phantom

    # Proportional to cap, floored to CE_SALARY_UNIT
    raw_total = 0
    for name, cap in caps.items():
        amount = math.floor(cap * total_ce_budget / sum_caps / CE_SALARY_UNIT) * CE_SALARY_UNIT
        budgets[name] = amount
        raw_total += amount

    # Absorb rounding deficit: give +CE_SALARY_UNIT to largest-cap workers first
    deficit = total_ce_budget - raw_total
    for name in sorted(caps, key=lambda n: caps[n], reverse=True):
        if deficit <= 0:
            break
        budgets[name] += CE_SALARY_UNIT
        deficit -= CE_SALARY_UNIT

    return budgets, 0


def plan_ce(
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
    se_targets_sum: int,
    rng: random.Random,
) -> int:
    """
    Assigns CE shifts in-place to DayLedger.ce_salaries.
    Returns phantom_CE amount.
    """
    logger.info("=" * 60)
    logger.info("CE PLANNING PHASE")
    logger.info("=" * 60)

    total_clean = sum(
        dl.cleaned_income
        for company in companies.values()
        for dl in company.ledger.values()
    )

    caps = {w.name: w.salary for w in ce_workers}
    worker_budgets, phantom_ce = compute_ce_worker_budgets(caps, total_clean, se_targets_sum)

    total_ce_budget = int(round(total_clean - se_targets_sum / RATIO))
    logger.info(f"  total_I_clean       = {total_clean:,}")
    logger.info(f"  total_CE_budget     = {total_ce_budget:,}")
    logger.info(f"  phantom_CE          = {phantom_ce:,}")

    # Process CE workers in random order
    workers_shuffled = list(ce_workers)
    rng.shuffle(workers_shuffled)

    for worker in workers_shuffled:
        monthly_amount = worker_budgets[worker.name]
        if monthly_amount == 0:
            logger.info(f"  CE {worker.name}: budget=0, no shifts assigned")
            continue

        _assign_worker_shifts(worker, monthly_amount, companies, rng)

    _validate_ce_non_negative(ce_workers, companies)
    _log_ce_summary(ce_workers)

    return phantom_ce


def _get_company_for_worker(
    worker: CompanyEmployedEmployee,
    companies: dict[str, Company],
) -> Company | None:
    """Determine the single company this CE worker belongs to."""
    if worker.exclusive_company:
        return companies.get(worker.exclusive_company)
    if worker.preferred_company:
        return companies.get(worker.preferred_company)
    # Pick company with highest preference score
    best = max(
        COMPANY_NAMES,
        key=lambda c: sum(worker.preferences.get(c, {}).values()),
    )
    return companies.get(best)


def _assign_worker_shifts(
    worker: CompanyEmployedEmployee,
    monthly_amount: int,
    companies: dict[str, Company],
    rng: random.Random,
) -> None:
    company = _get_company_for_worker(worker, companies)
    if company is None:
        logger.warning(f"  CE {worker.name}: no company found — skipping")
        return

    # Eligible days: P > 0 at this company
    eligible = [
        d for d in company.days
        if worker.preferences.get(company.name, {}).get(d, 0) > 0
    ]
    if not eligible:
        logger.warning(f"  CE {worker.name}: no eligible days at {company.name}")
        return

    # Sort by income descending (high-income days preferred)
    eligible_sorted = sorted(eligible, key=lambda d: company.get_day(d).cleaned_income, reverse=True)

    # Compute k (number of working days)
    k_min = math.ceil(monthly_amount / MAX_PER_DAY)
    k_max = len(eligible_sorted)

    if k_min > k_max:
        actual_amount = MAX_PER_DAY * k_max
        logger.warning(
            f"  CE {worker.name}: can't reach budget {monthly_amount} in {k_max} days "
            f"— capping at {actual_amount}"
        )
        monthly_amount = actual_amount
        k_min = k_max

    k_upper = max(k_min, min(k_max, math.ceil(monthly_amount / 120)))
    k = rng.randint(k_min, k_upper)

    # Pick top k days (busiest first), with randomness in the tail
    if k == k_min:
        selected_days = eligible_sorted[:k]
    else:
        # Take top k_min deterministically, fill remainder by weighted sample
        head = eligible_sorted[:k_min]
        tail_pool = eligible_sorted[k_min:]
        weights = [company.get_day(d).cleaned_income for d in tail_pool]
        tail_needed = k - k_min
        tail_needed = min(tail_needed, len(tail_pool))
        if tail_pool and tail_needed > 0:
            tail = _weighted_sample_without_replacement(tail_pool, weights, tail_needed, rng)
        else:
            tail = []
        selected_days = head + tail

    # Split monthly_amount across selected_days as multiples of CE_SALARY_UNIT
    daily_amounts = _split_amount(monthly_amount, len(selected_days), rng)

    # Assign with SE-feasibility guard
    assigned_total = 0
    for day, amount in zip(selected_days, daily_amounts):
        dl = company.get_day(day)
        current_ce = dl.ce_total

        # SE-feasibility guard: ensure CE_day stays in safe zone
        max_safe = dl.cleaned_income - 300  # keeps (I_clean-CE)*0.4 >= 120
        headroom = max_safe - current_ce

        if amount > headroom:
            retries = 0
            placed = False
            while retries < MAX_RETRIES:
                # Try to reduce amount to fit headroom
                reduced = (headroom // CE_SALARY_UNIT) * CE_SALARY_UNIT
                if reduced >= CE_SALARY_UNIT:
                    amount = reduced
                    placed = True
                    break
                # No room — try next day in sorted list
                alt_days = [
                    d for d in eligible_sorted
                    if d not in [dd for dd in selected_days]
                    and not worker.is_working_on(d)
                ]
                if alt_days:
                    day = alt_days[0]
                    dl = company.get_day(day)
                    current_ce = dl.ce_total
                    headroom = (dl.cleaned_income - 300) - current_ce
                    selected_days.append(day)
                retries += 1

            if not placed and headroom < CE_SALARY_UNIT:
                logger.warning(
                    f"  CE {worker.name}: can't place {amount} on day {day} "
                    f"(headroom={headroom}) — partial shortfall"
                )
                continue

        dl.ce_salaries[worker.name] = amount
        worker.schedule[(company.name, day)] = amount
        assigned_total += amount

    if assigned_total != monthly_amount:
        logger.warning(
            f"  CE {worker.name}: assigned {assigned_total} vs target {monthly_amount} "
            f"(gap={monthly_amount - assigned_total})"
        )


def _weighted_sample_without_replacement(
    pool: list,
    weights: list[int],
    k: int,
    rng: random.Random,
) -> list:
    """Sample k items from pool without replacement, weighted by weights."""
    result = []
    pool = list(pool)
    weights = list(weights)
    for _ in range(k):
        if not pool:
            break
        total = sum(weights)
        r = rng.uniform(0, total)
        cumulative = 0
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                result.append(pool[i])
                pool.pop(i)
                weights.pop(i)
                break
    return result


def _split_amount(total: int, n: int, rng: random.Random) -> list[int]:
    """
    Split total into n parts, each a multiple of CE_SALARY_UNIT in [CE_SALARY_UNIT, MAX_PER_DAY].
    """
    if n == 0:
        return []
    if n == 1:
        return [total]

    props = [rng.randint(1, 10) for _ in range(n)]
    prop_sum = sum(props)
    raw = [p * total / prop_sum for p in props]
    parts = [
        max(CE_SALARY_UNIT, min(MAX_PER_DAY, round(r / CE_SALARY_UNIT) * CE_SALARY_UNIT))
        for r in raw
    ]

    diff = total - sum(parts)
    step = CE_SALARY_UNIT if diff > 0 else -CE_SALARY_UNIT
    for _ in range(abs(diff) // CE_SALARY_UNIT):
        for i in range(n):
            new_val = parts[i] + step
            if CE_SALARY_UNIT <= new_val <= MAX_PER_DAY:
                parts[i] = new_val
                break

    return parts


def _validate_ce_non_negative(
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
) -> None:
    """Warn loudly if any CE salary or CE_day total is negative."""
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
        gap = cap - actual
        status = "OK" if gap == 0 else f"SHORTFALL={gap}"
        logger.info(f"  {w.name:<12} cap={cap:>6} actual={actual:>6} [{status}]")
    logger.info("=" * 60)
```

- [ ] **Step 4: Run CE budget tests**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/test_ce_planner.py -v
```
Expected: all pass

---

## Task 5: SE scheduler

**Files:** Create `src/engine/se_scheduler.py`, create `tests/test_se_scheduler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_se_scheduler.py`:

```python
"""Tests for SE scheduler."""
import random
import pytest
from src.models.company import Company
from src.models.employee import SelfEmployedEmployee
from src.config import GOOD_LIFE, TIANYUAN


def _setup():
    rng = random.Random(42)
    gl = Company(GOOD_LIFE)
    ty = Company(TIANYUAN)
    # 5 days, varying income
    for d in range(1, 6):
        gl.add_day(d, 2000)
        ty.add_day(d, 1500)
    companies = {GOOD_LIFE: gl, TIANYUAN: ty}

    # Compute SE targets for each day (CE = 0 on all days for simplicity)
    for c in companies.values():
        for d in c.days:
            c.get_day(d).compute_se_target_from_ce(0)

    # 2 SE workers
    w1 = SelfEmployedEmployee("Alice", 400)
    w1.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {}}
    w2 = SelfEmployedEmployee("Bob", 400)
    w2.preferences = {GOOD_LIFE: {d: 1 for d in range(1, 6)}, TIANYUAN: {}}
    return [w1, w2], companies, rng


def test_se_workers_assigned_enough_days():
    """Each SE worker gets at least min_days = ceil(target/400) days."""
    from src.engine.se_scheduler import schedule_se
    import math
    workers, companies, rng = _setup()
    schedule_se(workers, companies, rng)
    for w in workers:
        min_days = math.ceil(w.salary / 400)
        assert w.assigned_days >= min_days, f"{w.name}: {w.assigned_days} < {min_days}"


def test_no_double_booking():
    """No worker appears at two companies on the same day."""
    from src.engine.se_scheduler import schedule_se
    workers, companies, rng = _setup()
    schedule_se(workers, companies, rng)
    for w in workers:
        days_worked = [d for (_, d) in w.schedule]
        assert len(days_worked) == len(set(days_worked)), f"{w.name} double-booked"


def test_workers_respect_preferences():
    """Workers only appear on days where P > 0."""
    from src.engine.se_scheduler import schedule_se
    workers, companies, rng = _setup()
    schedule_se(workers, companies, rng)
    for w in workers:
        for (company, day) in w.schedule:
            pref = w.preferences.get(company, {}).get(day, 0)
            assert pref > 0, f"{w.name} assigned to {company} day {day} with P=0"
```

- [ ] **Step 2: Confirm failure**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/test_se_scheduler.py -v 2>&1 | head -20
```

- [ ] **Step 3: Implement se_scheduler.py**

Create `src/engine/se_scheduler.py`:

```python
"""
SE Scheduler — Phase 3.

Assigns SE workers to (company, day) slots using per-day SE_day_target
already set by the CE planner. Salaries are left at 0 (filled by solver).
"""

import logging
import math
import random

from src.config import MIN_SALARY, MAX_SALARY, COMPANY_NAMES
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
        w.min_days = math.ceil(w.salary / MAX_SALARY)
        w.max_days = math.floor(w.salary / MIN_SALARY)
        w.target_days = math.ceil(w.salary / 180)  # preferred count

    # Build active slots: those with SE_day_target >= MIN_SALARY
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

        n = rng.randint(n_min, min(n_max, len(pool)))
        pool.sort(key=lambda w: (
            -w.preferences.get(company_name, {}).get(day, 0),
            -(w.target_days - w.assigned_days),
        ))
        for worker in pool[:n]:
            worker.add_shift(company_name, day, salary=0)

    _fill_under_scheduled(se_workers, companies, rng)
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
            current = sum(
                1 for w in se_workers if (company_name, day) in w.schedule
            )
            n_max = math.floor(dl.se_day_target / MIN_SALARY)
            if current >= n_max:
                continue
            worker.add_shift(company_name, day, salary=0)

        if worker.assigned_days < worker.min_days:
            logger.warning(
                f"  SE {worker.name}: only {worker.assigned_days}/{worker.min_days} days "
                f"assigned — shortfall likely"
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
```

- [ ] **Step 4: Run SE scheduler tests**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/test_se_scheduler.py -v
```
Expected: all pass

---

## Task 6: SE salary solver (rewrite)

**Files:** Rewrite `src/engine/salary_solver.py`, create `tests/test_salary_solver.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_salary_solver.py`:

```python
"""Tests for the SE salary solver — exact monthly targets."""
import math
import random
import pytest
from src.models.company import Company
from src.models.employee import SelfEmployedEmployee
from src.config import GOOD_LIFE, TIANYUAN, MIN_SALARY, MAX_SALARY, SE_SALARY_UNIT


def _make_scenario(n_workers, n_days, incomes_gl, se_targets):
    """Build companies + workers with pre-set CE=0 day targets."""
    rng = random.Random(99)
    gl = Company(GOOD_LIFE)
    for d, inc in enumerate(incomes_gl, start=1):
        gl.add_day(d, inc)
        gl.get_day(d).compute_se_target_from_ce(0)
    companies = {GOOD_LIFE: gl, TIANYUAN: Company(TIANYUAN)}
    workers = []
    for i, tgt in enumerate(se_targets):
        w = SelfEmployedEmployee(f"W{i}", tgt)
        w.preferences = {GOOD_LIFE: {d: 2 for d in range(1, n_days+1)}, TIANYUAN: {}}
        workers.append(w)
    return workers, companies, rng


def test_solver_hits_exact_monthly_targets():
    """Each worker's actual monthly == their target."""
    from src.engine.se_scheduler import schedule_se
    from src.engine.salary_solver import solve_salaries
    # 2 workers, 5 days, I_clean=2000 each day → SE_target=800/day
    workers, companies, rng = _make_scenario(2, 5, [2000]*5, [800, 800])
    schedule_se(workers, companies, rng)
    solve_salaries(workers, companies, rng)
    for w in workers:
        assert w.actual_monthly_salary == w.salary, \
            f"{w.name}: actual={w.actual_monthly_salary} target={w.salary}"


def test_solver_satisfies_daily_column_sums():
    """Sum of SE salaries on each (c, d) == SE_day_target."""
    from src.engine.se_scheduler import schedule_se
    from src.engine.salary_solver import solve_salaries
    workers, companies, rng = _make_scenario(2, 5, [2000]*5, [800, 800])
    schedule_se(workers, companies, rng)
    solve_salaries(workers, companies, rng)
    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            if dl.se_day_target > 0:
                assert dl.se_total == dl.se_day_target, \
                    f"{company.name} day {day}: se_total={dl.se_total} target={dl.se_day_target}"


def test_solver_individual_salaries_in_bounds():
    """All individual SE salaries are even integers in [120, 400]."""
    from src.engine.se_scheduler import schedule_se
    from src.engine.salary_solver import solve_salaries
    workers, companies, rng = _make_scenario(2, 5, [2000]*5, [800, 800])
    schedule_se(workers, companies, rng)
    solve_salaries(workers, companies, rng)
    for w in workers:
        for (c, d), sal in w.schedule.items():
            assert MIN_SALARY <= sal <= MAX_SALARY, f"{w.name} day {d}: {sal} out of [120,400]"
            assert sal % SE_SALARY_UNIT == 0, f"{w.name} day {d}: {sal} not even"


def test_solver_deterministic():
    """Same seed → identical salaries."""
    from src.engine.se_scheduler import schedule_se
    from src.engine.salary_solver import solve_salaries
    workers1, companies1, rng1 = _make_scenario(2, 5, [2000]*5, [800, 800])
    workers2, companies2, rng2 = _make_scenario(2, 5, [2000]*5, [800, 800])
    schedule_se(workers1, companies1, rng1)
    schedule_se(workers2, companies2, rng2)
    solve_salaries(workers1, companies1, rng1)
    solve_salaries(workers2, companies2, rng2)
    for w1, w2 in zip(workers1, workers2):
        assert w1.schedule == w2.schedule
```

- [ ] **Step 2: Confirm failure**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/test_salary_solver.py -v 2>&1 | head -30
```

- [ ] **Step 3: Rewrite salary_solver.py**

Overwrite `src/engine/salary_solver.py`:

```python
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

    # Build assignment index: slot → list of workers
    slots: dict[tuple[str, int], list[SelfEmployedEmployee]] = {}
    for w in se_workers:
        for (company_name, day) in w.schedule:
            slots.setdefault((company_name, day), []).append(w)

    if not slots:
        logger.warning("  No SE assignments — nothing to solve")
        return

    # Build the salary matrix as {(w.name, c, d): float}
    # Initialise uniformly within [MIN_SALARY, MAX_SALARY]
    matrix: dict[tuple[str, str, int], float] = {}
    for (c, d), workers in slots.items():
        n = len(workers)
        budget = companies[c].get_day(d).se_day_target
        share = budget / n
        share = max(MIN_SALARY, min(MAX_SALARY, share))
        for w in workers:
            matrix[(w.name, c, d)] = share

    # Stage A: Sinkhorn iterations
    _sinkhorn(matrix, se_workers, slots, companies)

    # Stage B: Round to even integers and repair
    int_matrix: dict[tuple[str, str, int], int] = {
        k: _round_even(v) for k, v in matrix.items()
    }
    _repair(int_matrix, se_workers, slots, companies)

    # Write results back
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

        # Row normalisation: scale each worker's row to their target
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

        # Column normalisation: scale each slot to its SE_day_target
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
    """Round to nearest even integer, clamped to [MIN_SALARY, MAX_SALARY]."""
    r = round(v / SE_SALARY_UNIT) * SE_SALARY_UNIT
    return max(MIN_SALARY, min(MAX_SALARY, r))


def _repair(
    matrix: dict[tuple[str, str, int], int],
    se_workers: list[SelfEmployedEmployee],
    slots: dict[tuple[str, int], list[SelfEmployedEmployee]],
    companies: dict[str, Company],
) -> None:
    """Swap ±SE_SALARY_UNIT between cells to fix row and column sum violations."""
    for iteration in range(SOLVER_MAX_ITER):
        all_ok = True

        # Fix row violations (worker monthly sum)
        for w in se_workers:
            worker_keys = [(w.name, c, d) for (c, d) in w.schedule]
            row_sum = sum(matrix[k] for k in worker_keys)
            diff = w.salary - row_sum
            if diff == 0:
                continue
            all_ok = False
            step = SE_SALARY_UNIT if diff > 0 else -SE_SALARY_UNIT
            steps_needed = abs(diff) // SE_SALARY_UNIT
            for _ in range(steps_needed):
                for k in worker_keys:
                    new_val = matrix[k] + step
                    if MIN_SALARY <= new_val <= MAX_SALARY:
                        matrix[k] = new_val
                        break

        # Fix column violations (per-day sum)
        for (c, d), workers in slots.items():
            col_keys = [(w.name, c, d) for w in workers]
            col_sum = sum(matrix[k] for k in col_keys)
            target = companies[c].get_day(d).se_day_target
            diff = target - col_sum
            if diff == 0:
                continue
            all_ok = False
            step = SE_SALARY_UNIT if diff > 0 else -SE_SALARY_UNIT
            steps_needed = abs(diff) // SE_SALARY_UNIT
            for _ in range(steps_needed):
                for k in col_keys:
                    new_val = matrix[k] + step
                    if MIN_SALARY <= new_val <= MAX_SALARY:
                        matrix[k] = new_val
                        break

        if all_ok:
            logger.debug(f"  Repair converged at iteration {iteration}")
            return

    logger.warning("  Repair loop hit max iterations — some sums may not be exact")


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
    logger.info("PER-DAY FORMULA VERIFICATION:")
    violations = 0
    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            if dl.se_day_target == 0:
                continue
            if dl.se_total != dl.se_day_target:
                logger.warning(
                    f"  VIOLATION {company.name} day {day:02d}: "
                    f"SE_total={dl.se_total} target={dl.se_day_target}"
                )
                violations += 1
    if violations == 0:
        logger.info("  All days match SE_day_target exactly.")
    logger.info("=" * 60)
```

- [ ] **Step 4: Run solver tests**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/test_salary_solver.py -v
```
Expected: all pass

---

## Task 7: Update main.py

**Files:** Modify `main.py`

- [ ] **Step 1: Rewrite main.py**

```python
"""
Monthly Work/Salary Plan Generator
"""

import argparse
import logging
import os
import random
import sys

from src.config import OUTPUT_FILE
from src.loaders.data_loader import load_all
from src.engine.feasibility import check_se_feasibility
from src.engine.ce_planner import plan_ce
from src.engine.se_scheduler import schedule_se
from src.engine.salary_solver import solve_salaries
from src.reports.excel_writer import generate_report


def _resolve_seed(args) -> tuple[int, str]:
    if args.seed is not None:
        return args.seed, "from --seed"
    env_val = os.environ.get("SALARY_SEED")
    if env_val is not None:
        return int(env_val), "from SALARY_SEED env var"
    seed = random.SystemRandom().randrange(2 ** 32)
    return seed, "auto-generated"


def setup_logging() -> None:
    os.makedirs("output", exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("output/run.log", mode="w", encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Monthly salary plan generator")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Monthly Work/Salary Plan Generator — starting")

    seed, provenance = _resolve_seed(args)
    logger.info(f"Random seed: {seed} ({provenance})")
    rng = random.Random(seed)

    # 1. Load data
    se_workers, ce_workers, companies = load_all()

    # 2. Pre-flight feasibility check
    feasible = check_se_feasibility(se_workers, companies)

    se_targets_sum = sum(w.salary for w in se_workers)

    # 3. CE plan
    phantom_ce = plan_ce(ce_workers, companies, se_targets_sum, rng)

    # 4. Compute SE day targets from CE
    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            dl.compute_se_target_from_ce(dl.ce_total)

    # 5. SE schedule
    schedule_se(se_workers, companies, rng)

    # 6. SE salary solver
    solve_salaries(se_workers, companies, rng)

    # 7. Generate report
    generate_report(se_workers, ce_workers, companies, seed=seed, phantom_ce=phantom_ce)

    logger.info(f"Done. Output written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify import chain**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -c "import main; print('imports OK')"
```
Expected: `imports OK`

---

## Task 8: Update excel_writer.py

**Files:** Modify `src/reports/excel_writer.py`

- [ ] **Step 1: Update generate_report signature and remove old flag references**

Replace the relevant parts of `excel_writer.py` — update imports, `generate_report` signature, and fix all `dl.is_infeasible` / `dl.is_ce_only` / `dl.se_budget` / `SALARY_UNIT` references:

Key changes:
1. `generate_report` gains `seed: int` and `phantom_ce: int` params.
2. Replace `dl.is_infeasible` → `False`, `dl.is_ce_only` → `dl.is_full_ce_absorption`.
3. Replace `dl.se_budget` → `dl.se_day_target`.
4. Replace `SALARY_UNIT` import → `SE_SALARY_UNIT`.
5. In `_write_summary_sheet`, add seed row, phantom_CE row, and update shortfall tolerance to 0.

The full replacement is in step 2.

- [ ] **Step 2: Write the full updated excel_writer.py**

```python
"""
Generates a 4-sheet Excel workbook.
"""

import logging
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from src.config import GOOD_LIFE, TIANYUAN, OUTPUT_FILE, SE_SALARY_UNIT
from src.models.employee import SelfEmployedEmployee, CompanyEmployedEmployee
from src.models.company import Company

logger = logging.getLogger(__name__)

CLR_HEADER = "4472C4"
CLR_TOTAL_ROW = "D9E1F2"
CLR_GL = "E2EFDA"
CLR_TY = "FFF2CC"
CLR_CE_ONLY = "FFFFD7"
CLR_WARN = "FF0000"


def generate_report(
    se_workers: list[SelfEmployedEmployee],
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
    seed: int = 0,
    phantom_ce: int = 0,
) -> None:
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    wb = Workbook()
    default_sheet = wb.active
    if default_sheet is not None:
        wb.remove(default_sheet)

    _write_company_sheet(wb, GOOD_LIFE, "Good Life", se_workers, ce_workers, companies)
    _write_company_sheet(wb, TIANYUAN, "Tianyuan", se_workers, ce_workers, companies)
    _write_schedule_sheet(wb, se_workers, ce_workers, companies)
    _write_summary_sheet(wb, se_workers, ce_workers, companies, seed=seed, phantom_ce=phantom_ce)

    wb.save(OUTPUT_FILE)
    logger.info(f"Report saved to: {OUTPUT_FILE}")


def _header_font() -> Font:
    return Font(bold=True, color="FFFFFF")


def _header_fill(colour: str = CLR_HEADER) -> PatternFill:
    return PatternFill("solid", fgColor=colour)


def _thin_border() -> Border:
    thin = Side(style="thin")
    return Border(left=thin, right=thin, top=thin, bottom=thin)


def _apply_header(cell, label: str, colour: str = CLR_HEADER):
    cell.value = label
    cell.font = _header_font()
    cell.fill = _header_fill(colour)
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = _thin_border()


def _apply_cell(cell, value, fill_colour: str | None = None, bold: bool = False, red: bool = False):
    cell.value = value
    cell.alignment = Alignment(horizontal="center", vertical="center")
    cell.border = _thin_border()
    if fill_colour:
        cell.fill = PatternFill("solid", fgColor=fill_colour)
    if bold:
        cell.font = Font(bold=True)
    if red:
        cell.font = Font(color=CLR_WARN, bold=True)


def _write_company_sheet(
    wb: Workbook,
    company_key: str,
    sheet_title: str,
    se_workers: list[SelfEmployedEmployee],
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
) -> None:
    company = companies[company_key]
    ws = wb.create_sheet(title=sheet_title)

    ce_here = [w for w in ce_workers if any(c == company_key for (c, _) in w.schedule)]
    se_here = [w for w in se_workers if any(c == company_key for (c, _) in w.schedule)]

    headers = ["Day", "Income", "Cleaned Income"]
    headers += [f"CE: {w.name}" for w in ce_here]
    headers += ["CE Total", "SE Target"]
    headers += [f"SE: {w.name}" for w in se_here]
    headers += ["SE Total", "Formula Check\n(SE/0.4+CE)"]

    for col_idx, h in enumerate(headers, start=1):
        _apply_header(ws.cell(row=1, column=col_idx), h)
    ws.freeze_panes = "A2"

    monthly_ce: dict[str, int] = {w.name: 0 for w in ce_here}
    monthly_se: dict[str, int] = {w.name: 0 for w in se_here}
    monthly_income = 0
    monthly_cleaned = 0
    monthly_se_total = 0
    monthly_ce_total = 0

    for row_idx, day in enumerate(company.days, start=2):
        dl = company.get_day(day)
        row_colour = CLR_CE_ONLY if dl.is_full_ce_absorption else None

        col = 1
        _apply_cell(ws.cell(row=row_idx, column=col), day, fill_colour=row_colour)
        col += 1
        _apply_cell(ws.cell(row=row_idx, column=col), dl.raw_income, fill_colour=row_colour)
        col += 1
        _apply_cell(ws.cell(row=row_idx, column=col), dl.cleaned_income, fill_colour=row_colour)
        col += 1

        for w in ce_here:
            val = dl.ce_salaries.get(w.name, 0)
            _apply_cell(ws.cell(row=row_idx, column=col), val if val else "", fill_colour=row_colour)
            monthly_ce[w.name] += val
            col += 1

        ce_total = dl.ce_total
        _apply_cell(ws.cell(row=row_idx, column=col), ce_total, fill_colour=row_colour, bold=True)
        monthly_ce_total += ce_total
        col += 1

        _apply_cell(ws.cell(row=row_idx, column=col), dl.se_day_target, fill_colour=row_colour)
        col += 1

        for w in se_here:
            val = dl.se_salaries.get(w.name, 0)
            _apply_cell(ws.cell(row=row_idx, column=col), val if val else "", fill_colour=row_colour)
            monthly_se[w.name] += val
            col += 1

        se_total = dl.se_total
        _apply_cell(ws.cell(row=row_idx, column=col), se_total, fill_colour=row_colour, bold=True)
        monthly_se_total += se_total
        col += 1

        if dl.is_full_ce_absorption:
            _apply_cell(ws.cell(row=row_idx, column=col), "CE-FULL", fill_colour=CLR_CE_ONLY)
        else:
            fval = round(dl.formula_check)
            deviation = abs(fval - dl.cleaned_income)
            cell = ws.cell(row=row_idx, column=col)
            _apply_cell(cell, fval, fill_colour=row_colour)
            if deviation > SE_SALARY_UNIT:
                cell.font = Font(color=CLR_WARN, bold=True)

        monthly_income += dl.raw_income
        monthly_cleaned += dl.cleaned_income

    total_row = len(company.days) + 2
    _apply_cell(ws.cell(row=total_row, column=1), "MONTHLY TOTAL", fill_colour="D9E1F2", bold=True)
    ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=3)
    col = 4
    for w in ce_here:
        _apply_cell(ws.cell(row=total_row, column=col), monthly_ce[w.name], fill_colour="D9E1F2", bold=True)
        col += 1
    _apply_cell(ws.cell(row=total_row, column=col), monthly_ce_total, fill_colour="D9E1F2", bold=True)
    col += 2
    for w in se_here:
        actual = monthly_se[w.name]
        target = w.salary
        is_short = actual != target
        _apply_cell(ws.cell(row=total_row, column=col), actual, fill_colour="D9E1F2", bold=True, red=is_short)
        col += 1
    _apply_cell(ws.cell(row=total_row, column=col), monthly_se_total, fill_colour="D9E1F2", bold=True)

    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 13
    ws.row_dimensions[1].height = 40


def _write_schedule_sheet(
    wb: Workbook,
    se_workers: list[SelfEmployedEmployee],
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
) -> None:
    ws = wb.create_sheet(title="Schedule")
    all_days = sorted(next(iter(companies.values())).days)
    all_workers = [*se_workers, *ce_workers]

    _apply_header(ws.cell(row=1, column=1), "Employee")
    for col_idx, day in enumerate(all_days, start=2):
        _apply_header(ws.cell(row=1, column=col_idx), str(day))
    ws.freeze_panes = "B2"

    for row_idx, worker in enumerate(all_workers, start=2):
        name_cell = ws.cell(row=row_idx, column=1)
        name_cell.value = worker.name
        name_cell.font = Font(bold=True)
        name_cell.border = _thin_border()
        name_cell.alignment = Alignment(horizontal="left", vertical="center")
        for col_idx, day in enumerate(all_days, start=2):
            company_on_day = worker.company_on_day(day)
            cell = ws.cell(row=row_idx, column=col_idx)
            if company_on_day == GOOD_LIFE:
                _apply_cell(cell, "GL", fill_colour=CLR_GL)
            elif company_on_day == TIANYUAN:
                _apply_cell(cell, "TY", fill_colour=CLR_TY)
            else:
                _apply_cell(cell, "")

    ws.column_dimensions["A"].width = 14
    for col_idx in range(2, len(all_days) + 2):
        ws.column_dimensions[get_column_letter(col_idx)].width = 5
    ws.row_dimensions[1].height = 25


def _write_summary_sheet(
    wb: Workbook,
    se_workers: list[SelfEmployedEmployee],
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
    seed: int = 0,
    phantom_ce: int = 0,
) -> None:
    ws = wb.create_sheet(title="Summary")
    row = 1

    # Run metadata
    _apply_header(ws.cell(row=row, column=1), "Run Metadata", "1F497D")
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    row += 1
    for label, val in [("Random Seed", seed), ("Phantom CE (unallocated)", phantom_ce)]:
        _apply_cell(ws.cell(row=row, column=1), label, bold=True)
        _apply_cell(ws.cell(row=row, column=2), val)
        row += 1
    row += 1

    # SE/CE salary table
    headers = ["Name", "Type", "Monthly Target / Cap", "Actual Earned", "Gap", "Status"]
    for col_idx, h in enumerate(headers, start=1):
        _apply_header(ws.cell(row=row, column=col_idx), h)
    row += 1

    for worker in se_workers:
        target = worker.salary
        actual = worker.actual_monthly_salary
        gap = actual - target
        status = "OK" if gap == 0 else "SHORTFALL"
        is_short = status == "SHORTFALL"
        for col_idx, val in enumerate([worker.name, "SE", target, actual, gap, status], start=1):
            _apply_cell(ws.cell(row=row, column=col_idx), val, red=is_short)
        row += 1

    for worker in ce_workers:
        cap = worker.salary
        actual = worker.actual_monthly_salary
        gap = actual - cap
        status = "OK" if actual <= cap else "OVER CAP"
        for col_idx, val in enumerate([worker.name, "CE", cap, actual, gap, status], start=1):
            _apply_cell(ws.cell(row=row, column=col_idx), val)
        row += 1

    row += 1

    # Per-day formula verification
    _apply_header(ws.cell(row=row, column=1), "Formula Verification per Day (SE/0.4 + CE = I_clean)", "1F497D")
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
    row += 1

    day_headers = ["Company", "Day", "I_clean", "SE Target", "SE Total", "CE Total", "Formula\n(SE/0.4+CE)", "Status"]
    for col_idx, h in enumerate(day_headers, start=1):
        _apply_header(ws.cell(row=row, column=col_idx), h)
    row += 1

    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            if dl.is_full_ce_absorption:
                vals = [company.name, day, dl.cleaned_income, 0, 0, dl.ce_total, "—", "CE-FULL"]
                is_bad = False
            else:
                fval = round(dl.formula_check)
                dev = fval - dl.cleaned_income
                status = "OK" if abs(dev) <= SE_SALARY_UNIT else f"DEVIATION {dev:+d}"
                vals = [company.name, day, dl.cleaned_income, dl.se_day_target,
                        dl.se_total, dl.ce_total, fval, status]
                is_bad = abs(dev) > SE_SALARY_UNIT
            for col_idx, v in enumerate(vals, start=1):
                _apply_cell(ws.cell(row=row, column=col_idx), v, red=is_bad)
            row += 1

    for col_idx, width in enumerate([14, 5, 12, 10, 10, 10, 14, 14], start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.freeze_panes = "A2"
```

- [ ] **Step 3: Verify imports**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -c "from src.reports.excel_writer import generate_report; print('OK')"
```

---

## Task 9: Integration tests

**Files:** Create `tests/conftest.py`, create `tests/test_integration.py`

- [ ] **Step 1: Create conftest.py**

```python
"""Shared test fixtures."""
import random
import pytest
from src.models.company import Company
from src.models.employee import SelfEmployedEmployee, CompanyEmployedEmployee
from src.config import GOOD_LIFE, TIANYUAN


@pytest.fixture
def simple_scenario():
    """
    2 SE workers, 1 CE worker, 5-day month.
    GL income: 2000/day. TY income: 1500/day.
    CE cap: 500 (Zhong → Good Life).
    SE targets: 400+400 = 800. total_clean = 5*(2000+1500) = 17500.
    max_SE = 0.4*17500 = 7000 >> 800. Feasible.
    """
    gl = Company(GOOD_LIFE)
    ty = Company(TIANYUAN)
    for d in range(1, 6):
        gl.add_day(d, 2000)
        ty.add_day(d, 1500)
    companies = {GOOD_LIFE: gl, TIANYUAN: ty}

    se1 = SelfEmployedEmployee("Alice", 400)
    se1.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {d: 1 for d in range(1, 6)}}

    se2 = SelfEmployedEmployee("Bob", 400)
    se2.preferences = {GOOD_LIFE: {d: 1 for d in range(1, 6)}, TIANYUAN: {d: 2 for d in range(1, 6)}}

    ce1 = CompanyEmployedEmployee("Zhong", 500)
    ce1.exclusive_company = GOOD_LIFE
    ce1.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {}}

    return {
        "se_workers": [se1, se2],
        "ce_workers": [ce1],
        "companies": companies,
    }
```

- [ ] **Step 2: Create test_integration.py**

```python
"""Integration tests: math invariants, determinism, infeasible fallback."""
import random
import pytest
from src.engine.feasibility import check_se_feasibility
from src.engine.ce_planner import plan_ce
from src.engine.se_scheduler import schedule_se
from src.engine.salary_solver import solve_salaries
from src.models.employee import SelfEmployedEmployee
from src.models.company import Company
from src.config import GOOD_LIFE, TIANYUAN


def _run_pipeline(scenario, seed):
    import copy
    s = copy.deepcopy(scenario)
    rng = random.Random(seed)
    se_targets_sum = sum(w.salary for w in s["se_workers"])
    check_se_feasibility(s["se_workers"], s["companies"])
    plan_ce(s["ce_workers"], s["companies"], se_targets_sum, rng)
    for company in s["companies"].values():
        for day in company.days:
            dl = company.get_day(day)
            dl.compute_se_target_from_ce(dl.ce_total)
    schedule_se(s["se_workers"], s["companies"], rng)
    solve_salaries(s["se_workers"], s["companies"], rng)
    return s


def test_se_no_shortfall(simple_scenario):
    """Every SE worker hits their monthly target exactly."""
    s = _run_pipeline(simple_scenario, seed=42)
    for w in s["se_workers"]:
        assert w.actual_monthly_salary == w.salary, \
            f"{w.name}: actual={w.actual_monthly_salary} target={w.salary}"


def test_per_day_formula_exact(simple_scenario):
    """Σ SE_day == (I_clean − Σ CE_day) × 0.4 for every active day."""
    s = _run_pipeline(simple_scenario, seed=42)
    for company in s["companies"].values():
        for day in company.days:
            dl = company.get_day(day)
            if dl.is_full_ce_absorption:
                assert dl.se_total == 0
                continue
            expected = round((dl.cleaned_income - dl.ce_total) * 0.4)
            assert dl.se_total == expected, \
                f"{company.name} day {day}: se={dl.se_total} expected={expected}"


def test_determinism(simple_scenario):
    """Same seed → identical results."""
    s1 = _run_pipeline(simple_scenario, seed=777)
    s2 = _run_pipeline(simple_scenario, seed=777)
    for w1, w2 in zip(s1["se_workers"], s2["se_workers"]):
        assert w1.schedule == w2.schedule, f"{w1.name} schedule differs"
    for w1, w2 in zip(s1["ce_workers"], s2["ce_workers"]):
        assert w1.schedule == w2.schedule, f"{w1.name} schedule differs"


def test_different_seeds_produce_different_schedules(simple_scenario):
    """Different seeds produce different SE assignments (not just same result)."""
    results = set()
    for seed in range(10):
        s = _run_pipeline(simple_scenario, seed=seed)
        key = tuple(sorted(s["se_workers"][0].schedule.items()))
        results.add(key)
    assert len(results) > 1, "All seeds produced identical schedules"


def test_infeasible_se_fallback(caplog):
    """When SE targets > 0.4 * total_I_clean, warns loudly and continues."""
    import logging
    gl = Company(GOOD_LIFE)
    gl.add_day(1, 500)
    companies = {GOOD_LIFE: gl, TIANYUAN: Company(TIANYUAN)}
    # SE target = 500 > 0.4*500 = 200
    se = [SelfEmployedEmployee("X", 500)]
    se[0].preferences = {GOOD_LIFE: {1: 2}, TIANYUAN: {}}
    with caplog.at_level(logging.WARNING):
        result = check_se_feasibility(se, companies)
    assert result is False
    assert "infeasible" in caplog.text.lower()


def test_ce_non_negativity(simple_scenario):
    """No CE salary is negative."""
    s = _run_pipeline(simple_scenario, seed=42)
    for company in s["companies"].values():
        for day in company.days:
            dl = company.get_day(day)
            assert dl.ce_total >= 0
            for amt in dl.ce_salaries.values():
                assert amt >= 0


def test_no_bare_random_calls():
    """All randomness in engine files goes through a named rng instance, not bare random.*."""
    import pathlib, re
    bare_pattern = re.compile(r'\brandom\.(random|randint|shuffle|choice|sample|uniform|seed)\s*\(')
    engine_dir = pathlib.Path("src/engine")
    violations = []
    for py_file in engine_dir.glob("*.py"):
        for lineno, line in enumerate(py_file.read_text().splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            m = bare_pattern.search(line)
            if m:
                # OK if it's accessed on an object like rng.randint — check there's a dot before
                before = line[:m.start()].rstrip()
                if not before.endswith("."):
                    violations.append(f"{py_file}:{lineno}: {stripped}")
    assert not violations, "Bare random.* calls found:\n" + "\n".join(violations)
```

- [ ] **Step 3: Run integration tests**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/test_integration.py -v
```

---

## Task 10: Delete old scheduler.py, run full suite

- [ ] **Step 1: Delete old scheduler**

```bash
rm "F:/PROJECTS/refactor_sorting_income_app/src/engine/scheduler.py"
```

- [ ] **Step 2: Install pytest if needed**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && pip install pytest -q
```

- [ ] **Step 3: Run full test suite**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python -m pytest tests/ -v
```
Expected: all tests pass

- [ ] **Step 4: Run the full pipeline end-to-end**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && python main.py --seed 42
```
Expected: run completes, `output/report.xlsx` created, no ERROR lines in output

- [ ] **Step 5: Check no bare random module calls**

```bash
cd F:/PROJECTS/refactor_sorting_income_app && grep -rn "random\.seed\|import random$" src/engine/
```
Expected: only `import random` at module level (for type hints), no `random.seed()` calls
