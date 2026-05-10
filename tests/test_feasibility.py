"""Tests for pre-flight SE feasibility check."""
import logging
import pytest
from src.models.company import Company
from src.models.employee import SelfEmployedEmployee
from src.config import GOOD_LIFE, TIANYUAN


def _make_companies(gl_incomes: list[int], ty_incomes: list[int]) -> dict:
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


def test_feasibility_compute_totals():
    se = [SelfEmployedEmployee("A", 200)]
    companies = _make_companies([1000], [1000])
    from src.engine.feasibility import compute_totals
    total_clean, max_se, sum_targets = compute_totals(se, companies)
    assert total_clean == 2000
    assert max_se == 800   # 0.4 * 2000
    assert sum_targets == 200
