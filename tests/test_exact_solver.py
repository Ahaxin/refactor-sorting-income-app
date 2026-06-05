"""The exact solver must produce a fully valid, zero-violation schedule on the
real dataset — the property the old greedy pipeline could never guarantee."""
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


def test_solver_finds_perfect_solution(solved):
    _, _, _, report = solved
    assert report.feasible
    assert report.perfect, f"shortfalls={report.shortfalls} deviations={report.deviations}"


def test_se_monthly_targets_exact(solved):
    se, _, _, _ = solved
    for w in se:
        assert w.actual_monthly_salary == w.salary, f"{w.name}: {w.actual_monthly_salary} != {w.salary}"


def test_se_daily_bounds_and_even(solved):
    se, _, _, _ = solved
    for w in se:
        for (_, _), sal in w.schedule.items():
            assert MIN_SALARY <= sal <= MAX_SALARY
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


def test_one_company_per_day(solved):
    se, ce, _, _ = solved
    for w in (*se, *ce):
        seen: dict[int, str] = {}
        for (c, d) in w.schedule:
            assert d not in seen, f"{w.name} works two companies on day {d}"
            seen[d] = c


def test_formula_holds_every_day(solved):
    _, _, companies, _ = solved
    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            if dl.is_full_ce_absorption:
                continue
            assert abs(round(dl.formula_check) - dl.cleaned_income) <= SE_SALARY_UNIT


def test_availability_respected(solved):
    se, ce, _, _ = solved
    for w in (*se, *ce):
        for (c, d) in w.schedule:
            assert w.preferences.get(c, {}).get(d, 0) > 0


def test_se_work_is_maximally_spread(solved):
    """The spread objective should put as many SE workers per day as possible:
    each worker's target split across close to the most days they could work
    (bounded by eligible days and target/MIN_SALARY), every day still >= MIN."""
    import math
    se, _, _, _ = solved
    theoretical_max = 0
    for w in se:
        elig_days = {d for d in w.preferences.get("good_life", {}) if w.preferences["good_life"][d] > 0}
        theoretical_max += min(len(elig_days), w.salary // MIN_SALARY)
    total_slots = sum(len(w.schedule) for w in se)
    # Without the spread objective this lands far lower (~0.6× of max); require
    # near-maximal spread so the tie-break can't be silently dropped.
    assert total_slots >= 0.9 * theoretical_max, f"{total_slots} vs max {theoretical_max}"
    for w in se:
        for sal in w.schedule.values():
            assert sal >= MIN_SALARY
