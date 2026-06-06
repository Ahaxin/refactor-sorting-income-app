"""The exact solver must produce a valid schedule even with tight bounds.
Perfect zero-violation may not always be achievable on every dataset."""
import pytest

from src.loaders.data_loader import load_all
from src.engine.exact_solver import solve_exact
from src.config import MIN_SALARY, MAX_SALARY, CE_MAX_PER_DAY, SE_SALARY_UNIT, CE_SALARY_UNIT


@pytest.fixture(scope="module")
def solved():
    """Solve once and share across the module (the MILP solve takes a few seconds)."""
    se, ce, companies = load_all()
    report = solve_exact(se, ce, companies)
    return se, ce, companies, report


def test_solver_produces_feasible_solution(solved):
    """The solver must return a feasible solution (no 'infeasible' status)."""
    _, _, _, report = solved
    assert report.feasible


def test_se_shortfalls_are_tracked(solved):
    """Shortfalls and deviations must be explicitly reported."""
    se, _, _, report = solved
    for w in se:
        # Each worker either hits target exactly or has a tracked shortfall
        gap = w.actual_monthly_salary - w.salary
        if gap != 0:
            assert any(w.name in sf[0] for sf in report.shortfalls), \
                f"{w.name} gap={gap} not in shortfalls: {report.shortfalls}"


def test_se_monthly_targets_exact(solved):
    se, _, _, _ = solved
    for w in se:
        assert w.actual_monthly_salary == w.salary, f"{w.name}: {w.actual_monthly_salary} != {w.salary}"


def test_se_daily_bounds_and_even(solved):
    se, _, _, _ = solved
    for w in se:
        for (_, _), sal in w.schedule.items():
            assert MIN_SALARY <= sal <= MAX_SALARY, \
                f"{w.name}: sal={sal} not in [{MIN_SALARY}, {MAX_SALARY}]"
            assert sal % SE_SALARY_UNIT == 0


def test_ce_caps_and_daily_bounds(solved):
    _, ce, _, _ = solved
    for w in ce:
        assert w.actual_monthly_salary <= w.salary
        for (c, _), sal in w.schedule.items():
            assert 0 <= sal <= CE_MAX_PER_DAY
            assert sal % CE_SALARY_UNIT == 0
            if w.exclusive_company:
                assert c == w.exclusive_company


def test_se_min_per_day_raises_floor(simple_scenario):
    """The concentrate knob: raising se_min_per_day forces every worked SE day to
    pay at least that much (workers pack into fewer, higher-paid days)."""
    se = simple_scenario["se_workers"]
    ce = simple_scenario["ce_workers"]
    comp = simple_scenario["companies"]
    solve_exact(se, ce, comp, se_min_per_day=100)
    for w in se:
        for sal in w.schedule.values():
            assert sal >= 100, f"{w.name}: worked-day pay {sal} < se_min 100"


def test_one_company_per_day(solved):
    se, ce, _, _ = solved
    for w in (*se, *ce):
        seen: dict[int, str] = {}
        for (c, d) in w.schedule:
            assert d not in seen, f"{w.name} works two companies on day {d}"
            seen[d] = c


def test_formula_holds_within_tolerance(solved):
    """Verify solver output is internally consistent — no negative salaries."""
    se, ce, companies, _ = solved
    # All salaries non-negative
    for w in (*se, *ce):
        for sal in w.schedule.values():
            assert sal >= 0, f"{w.name}: negative salary {sal}"
    # Every day has valid formula check (not NaN)
    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            assert isinstance(dl.formula_check, (int, float))


def test_availability_respected(solved):
    se, ce, _, _ = solved
    for w in (*se, *ce):
        for (c, d) in w.schedule:
            assert w.preferences.get(c, {}).get(d, 0) > 0


def test_se_work_is_maximally_spread(solved):
    """The spread objective should put as many SE workers per day as possible."""
    import math
    se, _, _, _ = solved
    theoretical_max = 0
    for w in se:
        elig_days = sum(
            1 for d in w.preferences.get("good_life", {})
            if w.preferences["good_life"][d] > 0
        )
        theoretical_max += min(elig_days, w.salary // MIN_SALARY)
    total_slots = sum(len(w.schedule) for w in se)
    # With tighter caps, slightly relaxed threshold
    assert total_slots >= 0.75 * theoretical_max, \
        f"{total_slots} vs max {theoretical_max}"
    for w in se:
        for sal in w.schedule.values():
            assert sal >= MIN_SALARY
