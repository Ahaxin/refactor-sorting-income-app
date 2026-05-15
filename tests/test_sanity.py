"""Unit tests for run_sanity_check."""
import pandas as pd
from src.sanity import run_sanity_check


def _emp(rows):
    return pd.DataFrame(rows, columns=["name", "type", "salary", "exclusive_company"])


def _pref(names):
    cols = {"Company": ["good_life"], "Day": [1]}
    for n in names:
        cols[n] = [2]
    return pd.DataFrame(cols)


def test_valid_data_returns_no_errors():
    emp = _emp([("Alice", "Self-Employed", 500, ""), ("Bob", "Company-Employed", 1000, "Tianyuan")])
    pref = _pref(["Alice", "Bob"])
    assert run_sanity_check(emp, pref) == []


def test_invalid_type_is_flagged():
    emp = _emp([("Alice", "Freelancer", 500, "")])
    pref = _pref(["Alice"])
    errors = run_sanity_check(emp, pref)
    assert any("invalid type" in e for e in errors)


def test_zero_salary_is_flagged():
    emp = _emp([("Alice", "Self-Employed", 0, "")])
    pref = _pref(["Alice"])
    errors = run_sanity_check(emp, pref)
    assert any("salary" in e for e in errors)


def test_negative_salary_is_flagged():
    emp = _emp([("Alice", "Self-Employed", -100, "")])
    pref = _pref(["Alice"])
    errors = run_sanity_check(emp, pref)
    assert any("salary" in e for e in errors)


def test_duplicate_names_flagged():
    emp = _emp([("Alice", "Self-Employed", 500, ""), ("Alice", "Company-Employed", 1000, "")])
    pref = _pref(["Alice"])
    errors = run_sanity_check(emp, pref)
    assert any("duplicate" in e.lower() for e in errors)


def test_employee_missing_from_preference_matrix_flagged():
    emp = _emp([("Alice", "Self-Employed", 500, ""), ("Bob", "Self-Employed", 600, "")])
    pref = _pref(["Alice"])  # Bob is missing
    errors = run_sanity_check(emp, pref)
    assert any("Bob" in e for e in errors)


def test_multiple_errors_all_reported():
    emp = _emp([("Alice", "BAD", 0, ""), ("Alice", "Self-Employed", 500, "")])
    pref = _pref([])
    errors = run_sanity_check(emp, pref)
    assert len(errors) >= 4  # bad type, zero salary, duplicate, missing from pref
