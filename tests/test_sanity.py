"""Unit tests for run_sanity_check (split SE / CE availability matrices)."""
import pandas as pd
from src.sanity import run_sanity_check


def _emp(rows):
    return pd.DataFrame(rows, columns=["name", "type", "salary", "exclusive_company"])


def _se_pref(names):
    cols = {"Day": [1]}
    for n in names:
        cols[n] = [1]
    return pd.DataFrame(cols)


def _ce_pref(names):
    cols = {"Company": ["good_life"], "Day": [1]}
    for n in names:
        cols[n] = [1]
    return pd.DataFrame(cols)


def test_valid_data_returns_no_errors():
    emp = _emp([("Alice", "Self-Employed", 500, ""), ("Bob", "Company-Employed", 1000, "Tianyuan")])
    assert run_sanity_check(emp, _se_pref(["Alice"]), _ce_pref(["Bob"])) == []


def test_invalid_type_is_flagged():
    emp = _emp([("Alice", "Freelancer", 500, "")])
    errors = run_sanity_check(emp, _se_pref([]), _ce_pref([]))
    assert any("invalid type" in e for e in errors)


def test_zero_salary_is_flagged():
    emp = _emp([("Alice", "Self-Employed", 0, "")])
    errors = run_sanity_check(emp, _se_pref(["Alice"]), _ce_pref([]))
    assert any("salary" in e for e in errors)


def test_negative_salary_is_flagged():
    emp = _emp([("Alice", "Self-Employed", -100, "")])
    errors = run_sanity_check(emp, _se_pref(["Alice"]), _ce_pref([]))
    assert any("salary" in e for e in errors)


def test_duplicate_names_flagged():
    emp = _emp([("Alice", "Self-Employed", 500, ""), ("Alice", "Company-Employed", 1000, "")])
    errors = run_sanity_check(emp, _se_pref(["Alice"]), _ce_pref(["Alice"]))
    assert any("duplicate" in e.lower() for e in errors)


def test_se_employee_missing_from_matrix_flagged():
    emp = _emp([("Alice", "Self-Employed", 500, ""), ("Bob", "Self-Employed", 600, "")])
    errors = run_sanity_check(emp, _se_pref(["Alice"]), _ce_pref([]))  # Bob missing
    assert any("Bob" in e for e in errors)


def test_ce_employee_missing_from_matrix_flagged():
    emp = _emp([("Carol", "Company-Employed", 1000, "")])
    errors = run_sanity_check(emp, _se_pref([]), _ce_pref([]))  # Carol missing from CE matrix
    assert any("Carol" in e for e in errors)


def test_multiple_errors_all_reported():
    emp = _emp([("Alice", "BAD", 0, ""), ("Alice", "Self-Employed", 500, "")])
    errors = run_sanity_check(emp, _se_pref([]), _ce_pref([]))
    assert len(errors) >= 4  # bad type, zero salary, duplicate, missing from pref
