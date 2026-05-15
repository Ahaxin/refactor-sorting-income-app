"""Tests that exclusive_company is read from employee_data.csv."""
import math
import pytest
import pandas as pd
from src.config import GOOD_LIFE, TIANYUAN


def test_exclusive_company_loaded_from_employee_csv(tmp_path, monkeypatch):
    emp_csv = tmp_path / "employee_data.csv"
    emp_csv.write_text(
        "name,type,salary,exclusive_company\n"
        "Lin,Company-Employed,5670,Tianyuan\n"
        "Zhong,Company-Employed,9210,Good Life\n"
        "Jenny,Self-Employed,1800,\n",
        encoding="utf-8",
    )
    import src.config as cfg
    monkeypatch.setattr(cfg, "EMPLOYEE_FILE", str(emp_csv))

    # Re-import to pick up monkeypatched constant
    import importlib
    import src.loaders.data_loader as dl_mod
    importlib.reload(dl_mod)

    se_workers, ce_workers = dl_mod._load_employees()

    lin = next(w for w in ce_workers if w.name == "Lin")
    zhong = next(w for w in ce_workers if w.name == "Zhong")
    jenny = next(w for w in se_workers if w.name == "Jenny")

    assert lin.exclusive_company == TIANYUAN
    assert zhong.exclusive_company == GOOD_LIFE
    assert jenny.exclusive_company is None


def test_missing_exclusive_company_column_is_tolerated(tmp_path, monkeypatch):
    emp_csv = tmp_path / "employee_data.csv"
    emp_csv.write_text(
        "name,type,salary\nJenny,Self-Employed,1800\n",
        encoding="utf-8",
    )
    import src.config as cfg
    monkeypatch.setattr(cfg, "EMPLOYEE_FILE", str(emp_csv))

    import importlib
    import src.loaders.data_loader as dl_mod
    importlib.reload(dl_mod)

    se_workers, _ = dl_mod._load_employees()
    assert se_workers[0].exclusive_company is None
