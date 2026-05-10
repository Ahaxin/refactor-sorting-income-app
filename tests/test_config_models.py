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
        dl = DayLedger(day=1, raw_income=raw_income)
        result = dl.compute_se_target_from_ce(0)
        assert result % 2 == 0, f"raw={raw_income} result={result}"


def test_no_is_infeasible_flag():
    dl = DayLedger(day=1, raw_income=1000)
    assert not hasattr(dl, 'is_infeasible')
