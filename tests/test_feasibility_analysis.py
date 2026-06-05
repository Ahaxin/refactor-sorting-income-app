"""Structural feasibility checks: pass on solvable data, fire precisely on broken data."""
import pandas as pd
from src.sanity import run_sanity_check

EMP = "data/employee_data.csv"
SE = "data/se_preference.csv"
CE = "data/ce_preference.csv"
INC = "data/income_data.csv"


def _load():
    return (pd.read_csv(EMP), pd.read_csv(SE), pd.read_csv(CE), pd.read_csv(INC))


def test_real_data_is_feasible():
    emp, se, ce, inc = _load()
    assert run_sanity_check(emp, se, ce, inc, lang="en") == []


def test_worker_with_too_few_days_flagged():
    emp, se, ce, inc = _load()
    emp.loc[emp["name"] == "Ling", "salary"] = 5000  # 3 eligible days * 400 = 1200 < 5000
    errors = run_sanity_check(emp, se, ce, inc, lang="en")
    assert any("Ling" in e for e in errors)


def test_aggregate_se_overflow_flagged():
    emp, se, ce, inc = _load()
    mask = emp["type"] == "Self-Employed"
    emp.loc[mask, "salary"] = emp.loc[mask, "salary"] * 3  # exceeds 40% of income
    errors = run_sanity_check(emp, se, ce, inc, lang="en")
    assert any("40%" in e or "exceeds" in e for e in errors)


def test_aggregate_ce_shortage_flagged():
    emp, se, ce, inc = _load()
    mask = emp["type"] == "Company-Employed"
    emp.loc[mask, "salary"] = 100  # nowhere near enough to absorb residual
    errors = run_sanity_check(emp, se, ce, inc, lang="en")
    assert any("CE capacity" in e or "absorb" in e for e in errors)
