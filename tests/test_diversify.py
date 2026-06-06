"""Tests for the post-solve salary diversification (constraint-preserving
randomization). All tests use hand-built 'solved' schedules so they are fast and
deterministic — no MILP solve required."""
import copy
import math

import pytest

from src.models.company import Company
from src.models.employee import SelfEmployedEmployee, CompanyEmployedEmployee
from src.config import (
    GOOD_LIFE, TIANYUAN, MIN_SALARY, MAX_SALARY, CE_MAX_PER_DAY,
    SE_SALARY_UNIT, CE_SALARY_UNIT,
)
from src.engine.diversify import (
    diversify_schedule, verify_schedule, snapshot_schedules, restore_schedules,
)


def _set_se(company: Company, day: int, name: str, sal: int, worker) -> None:
    company.get_day(day).se_salaries[name] = sal
    worker.schedule[(company.name, day)] = sal


def _set_ce(company: Company, day: int, name: str, sal: int, worker) -> None:
    company.get_day(day).ce_salaries[name] = sal
    worker.schedule[(company.name, day)] = sal


@pytest.fixture
def se_dup_scenario():
    """2 SE workers, 2 days, all four daily salaries identical (100), with a clean
    4-cell cycle available. GL cleaned income = se_total/0.4 = 500 each day."""
    gl = Company(GOOD_LIFE)
    ty = Company(TIANYUAN)
    for d in (1, 2):
        gl.add_day(d, 500)
        ty.add_day(d, 0)
    companies = {GOOD_LIFE: gl, TIANYUAN: ty}

    alice = SelfEmployedEmployee("Alice", 200)
    bob = SelfEmployedEmployee("Bob", 200)
    for w in (alice, bob):
        w.preferences = {GOOD_LIFE: {1: 2, 2: 2}, TIANYUAN: {1: 0, 2: 0}}
        for d in (1, 2):
            _set_se(gl, d, w.name, 100, w)
    for d in (1, 2):
        gl.get_day(d).set_se_day_target(gl.get_day(d).se_total)

    return {"se_workers": [alice, bob], "ce_workers": [], "companies": companies}


@pytest.fixture
def ce_dup_scenario():
    """2 CE workers, 2 days, all four daily salaries identical (100). GL cleaned
    income = ce_total = 200 each day (no SE). Caps (300) are non-binding."""
    gl = Company(GOOD_LIFE)
    ty = Company(TIANYUAN)
    for d in (1, 2):
        gl.add_day(d, 200)
        ty.add_day(d, 0)
    companies = {GOOD_LIFE: gl, TIANYUAN: ty}

    x = CompanyEmployedEmployee("Xan", 300)
    y = CompanyEmployedEmployee("Yi", 300)
    for w in (x, y):
        w.exclusive_company = GOOD_LIFE
        w.preferences = {GOOD_LIFE: {1: 2, 2: 2}, TIANYUAN: {}}
        for d in (1, 2):
            _set_ce(gl, d, w.name, 100, w)
    for d in (1, 2):
        gl.get_day(d).set_se_day_target(0)

    return {"se_workers": [], "ce_workers": [x, y], "companies": companies}


def _per_day_totals(companies, attr):
    return {
        (c, d): sum(getattr(companies[c].get_day(d), attr).values())
        for c in companies for d in companies[c].days
    }


def _monthly(workers):
    return {w.name: w.actual_monthly_salary for w in workers}


def test_diversify_reduces_duplicate_values(se_dup_scenario):
    se = se_dup_scenario["se_workers"]
    companies = se_dup_scenario["companies"]
    before = sorted(s for w in se for s in w.schedule.values())
    assert len(set(before)) == 1  # sanity: fixture starts all-identical

    diversify_schedule(se, se_dup_scenario["ce_workers"], companies, pct=0.15, seed=0)

    after = sorted(s for w in se for s in w.schedule.values())
    assert len(set(after)) > len(set(before))


def test_se_per_day_totals_preserved(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    before = _per_day_totals(companies, "se_salaries")
    diversify_schedule(se, ce, companies, pct=0.15, seed=0)
    assert _per_day_totals(companies, "se_salaries") == before


def test_se_monthly_targets_preserved(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    before = _monthly(se)
    diversify_schedule(se, ce, companies, pct=0.15, seed=0)
    assert _monthly(se) == before
    for w in se:
        assert w.actual_monthly_salary == w.salary


def test_se_values_even_and_in_bounds(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    diversify_schedule(se, ce, companies, pct=0.15, seed=0)
    for w in se:
        for sal in w.schedule.values():
            assert sal % SE_SALARY_UNIT == 0
            assert MIN_SALARY <= sal <= MAX_SALARY


def test_se_values_within_band(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    before = {(w.name, col): sal for w in se for col, sal in w.schedule.items()}
    pct = 0.15
    diversify_schedule(se, ce, companies, pct=pct, seed=0)
    for w in se:
        for col, sal in w.schedule.items():
            orig = before[(w.name, col)]
            assert abs(sal - orig) <= math.ceil(orig * pct)


def test_ce_invariants_preserved(ce_dup_scenario):
    se, ce = ce_dup_scenario["se_workers"], ce_dup_scenario["ce_workers"]
    companies = ce_dup_scenario["companies"]
    totals_before = _per_day_totals(companies, "ce_salaries")
    monthly_before = _monthly(ce)
    diversify_schedule(se, ce, companies, pct=0.15, seed=0)
    assert _per_day_totals(companies, "ce_salaries") == totals_before
    assert _monthly(ce) == monthly_before
    for w in ce:
        assert w.actual_monthly_salary <= w.salary
        for sal in w.schedule.values():
            assert sal % CE_SALARY_UNIT == 0
            assert 0 <= sal <= CE_MAX_PER_DAY


def test_ce_reduces_duplicates(ce_dup_scenario):
    se, ce = ce_dup_scenario["se_workers"], ce_dup_scenario["ce_workers"]
    companies = ce_dup_scenario["companies"]
    before = sorted(s for w in ce for s in w.schedule.values())
    diversify_schedule(se, ce, companies, pct=0.15, seed=0)
    after = sorted(s for w in ce for s in w.schedule.values())
    assert len(set(after)) > len(set(before))


def test_pct_zero_is_noop(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    before = {w.name: dict(w.schedule) for w in se}
    diversify_schedule(se, ce, companies, pct=0, seed=0)
    after = {w.name: dict(w.schedule) for w in se}
    assert after == before


def test_deterministic_same_seed(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    snap = copy.deepcopy((se, ce, companies))
    diversify_schedule(se, ce, companies, pct=0.15, seed=42)
    first = {w.name: dict(w.schedule) for w in se}

    se2, ce2, companies2 = snap
    diversify_schedule(se2, ce2, companies2, pct=0.15, seed=42)
    second = {w.name: dict(w.schedule) for w in se2}
    assert first == second


def test_schedule_and_ledger_consistent(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    diversify_schedule(se, ce, companies, pct=0.15, seed=0)
    for w in se:
        for (c, d), sal in w.schedule.items():
            assert companies[c].get_day(d).se_salaries[w.name] == sal


# --- snapshot / restore ---

def test_snapshot_restore_roundtrip(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    snap = snapshot_schedules(se, ce, companies)
    before = {w.name: dict(w.schedule) for w in se}

    diversify_schedule(se, ce, companies, pct=0.15, seed=0)
    assert {w.name: dict(w.schedule) for w in se} != before  # tuning changed it

    restore_schedules(snap, se, ce, companies)
    assert {w.name: dict(w.schedule) for w in se} == before
    for w in se:
        for (c, d), sal in w.schedule.items():
            assert companies[c].get_day(d).se_salaries[w.name] == sal


# --- verify_schedule ---

def test_verify_clean_schedule_ok(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    r = verify_schedule(se, ce, companies)
    assert r.ok
    assert r.deviations == []
    assert r.shortfalls == []
    assert r.cap_violations == []
    assert r.bound_violations == []


def test_verify_ok_after_diversify(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    diversify_schedule(se, ce, companies, pct=0.15, seed=0)
    assert verify_schedule(se, ce, companies).ok


def test_verify_detects_shortfall(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    alice = se[0]
    alice.schedule[(GOOD_LIFE, 1)] = 80  # was 100 -> monthly 180 != target 200
    companies[GOOD_LIFE].get_day(1).se_salaries["Alice"] = 80
    r = verify_schedule(se, ce, companies)
    assert any(name == "Alice" for name, _ in r.shortfalls)
    assert not r.ok


def test_verify_detects_bound_violation(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    alice = se[0]
    alice.schedule[(GOOD_LIFE, 1)] = 101  # odd -> not a multiple of SE unit
    companies[GOOD_LIFE].get_day(1).se_salaries["Alice"] = 101
    r = verify_schedule(se, ce, companies)
    assert r.bound_violations
    assert not r.ok


def test_verify_detects_cap_violation(ce_dup_scenario):
    se, ce = ce_dup_scenario["se_workers"], ce_dup_scenario["ce_workers"]
    companies = ce_dup_scenario["companies"]
    xan = ce[0]
    # Push Xan well over the 300 cap.
    xan.schedule[(GOOD_LIFE, 1)] = 250
    companies[GOOD_LIFE].get_day(1).ce_salaries["Xan"] = 250
    r = verify_schedule(se, ce, companies)
    assert any(name == "Xan" for name, _ in r.cap_violations)
    assert not r.ok


def test_regressed_from_false_when_clean(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    diversify_schedule(se, ce, companies, pct=0.15, seed=0)
    r = verify_schedule(se, ce, companies)
    assert not r.regressed_from([], [])


def test_regressed_from_true_on_new_shortfall(se_dup_scenario):
    se, ce = se_dup_scenario["se_workers"], se_dup_scenario["ce_workers"]
    companies = se_dup_scenario["companies"]
    alice = se[0]
    alice.schedule[(GOOD_LIFE, 1)] = 80
    companies[GOOD_LIFE].get_day(1).se_salaries["Alice"] = 80
    r = verify_schedule(se, ce, companies)
    assert r.regressed_from([], [])
