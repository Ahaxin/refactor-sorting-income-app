"""Tests that exclusive_company is read from employee_data.csv."""
import src.loaders.data_loader as dl_mod
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
    # Patch the constant on the data_loader module itself; monkeypatch auto-restores
    # it after the test, so no global state leaks to later tests.
    monkeypatch.setattr(dl_mod, "EMPLOYEE_FILE", str(emp_csv))

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
    monkeypatch.setattr(dl_mod, "EMPLOYEE_FILE", str(emp_csv))

    se_workers, _ = dl_mod._load_employees()
    assert se_workers[0].exclusive_company is None
