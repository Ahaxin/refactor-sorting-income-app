"""Tests for CE planner (residual-based: runs after SE salary solving)."""
import random
import pytest
from src.models.company import Company
from src.models.employee import CompanyEmployedEmployee
from src.config import GOOD_LIFE, TIANYUAN


def _company(name, incomes):
    c = Company(name)
    for day, inc in enumerate(incomes, start=1):
        c.add_day(day, inc)
    return c


def test_ce_earns_nothing_when_formula_has_no_residual():
    """When SE fully covers the 40% share, CE residual is zero and CE earns nothing."""
    from src.engine.ce_planner import plan_ce
    gl = _company(GOOD_LIFE, [1000])
    companies = {GOOD_LIFE: gl, TIANYUAN: _company(TIANYUAN, [])}

    # SE earns 400 = 1000 * 0.4 → residual = 1000 - 400/0.4 = 0
    gl.get_day(1).se_salaries["Alice"] = 400

    ce = CompanyEmployedEmployee("Zhong", 500)
    ce.exclusive_company = GOOD_LIFE
    ce.preferences = {GOOD_LIFE: {1: 2}, TIANYUAN: {}}

    rng = random.Random(42)
    plan_ce([ce], companies, rng)

    assert ce.actual_monthly_salary == 0, \
        f"Expected CE to earn 0 when SE residual is 0, got {ce.actual_monthly_salary}"


def test_ce_worker_does_not_exceed_cap():
    """CE worker earns at most their monthly cap from formula residuals."""
    from src.engine.ce_planner import plan_ce
    gl = _company(GOOD_LIFE, [3000] * 5)
    companies = {GOOD_LIFE: gl, TIANYUAN: _company(TIANYUAN, [])}

    # SE earns 500/day → residual per day = 3000 - 500/0.4 = 3000 - 1250 = 1750
    for day in gl.days:
        gl.get_day(day).se_salaries["Alice"] = 500

    ce = CompanyEmployedEmployee("Zhong", 1000)
    ce.exclusive_company = GOOD_LIFE
    ce.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {}}

    rng = random.Random(42)
    plan_ce([ce], companies, rng)

    assert ce.actual_monthly_salary <= ce.salary


def test_plan_ce_assigns_shifts():
    """plan_ce assigns CE earnings when formula residual is positive."""
    from src.engine.ce_planner import plan_ce
    gl = _company(GOOD_LIFE, [3000] * 5)
    companies = {GOOD_LIFE: gl, TIANYUAN: _company(TIANYUAN, [])}

    # SE earns 500/day → residual = 3000 - 1250 = 1750 per day
    for day in gl.days:
        gl.get_day(day).se_salaries["Alice"] = 500

    ce = CompanyEmployedEmployee("Zhong", 1000)
    ce.exclusive_company = GOOD_LIFE
    ce.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {}}

    rng = random.Random(42)
    plan_ce([ce], companies, rng)

    assert ce.actual_monthly_salary > 0
    assert ce.actual_monthly_salary <= ce.salary


def test_plan_ce_no_negative_salaries():
    """No CE salary recorded in any DayLedger is negative."""
    from src.engine.ce_planner import plan_ce
    gl = _company(GOOD_LIFE, [2000] * 5)
    companies = {GOOD_LIFE: gl, TIANYUAN: _company(TIANYUAN, [])}

    # SE earns 300/day → residual = 2000 - 300/0.4 = 2000 - 750 = 1250
    for day in gl.days:
        gl.get_day(day).se_salaries["Alice"] = 300

    ce = CompanyEmployedEmployee("Lin", 500)
    ce.exclusive_company = GOOD_LIFE
    ce.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {}}

    rng = random.Random(7)
    plan_ce([ce], companies, rng)

    for day in gl.days:
        dl = gl.get_day(day)
        assert dl.ce_total >= 0
        for amt in dl.ce_salaries.values():
            assert amt >= 0


def test_validate_ce_non_negative_warns_on_injected_negative(caplog):
    """Validator emits WARNING when a DayLedger contains a negative CE salary."""
    import logging
    from src.engine.ce_planner import _validate_ce_non_negative
    gl = _company(GOOD_LIFE, [2000])
    companies = {GOOD_LIFE: gl, TIANYUAN: _company(TIANYUAN, [])}

    gl.get_day(1).ce_salaries["BadWorker"] = -50

    ce = CompanyEmployedEmployee("BadWorker", 500)
    ce.exclusive_company = GOOD_LIFE

    with caplog.at_level(logging.WARNING):
        _validate_ce_non_negative([ce], companies)

    assert any("negative" in msg.lower() or "validation error" in msg.lower()
               for msg in caplog.messages)
