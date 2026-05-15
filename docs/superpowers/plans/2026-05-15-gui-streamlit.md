# Streamlit GUI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit GUI with four tabs (Employees, Income, Preference Matrix, Generate) that edits the three input CSVs and runs the salary planning pipeline with a user-supplied seed.

**Architecture:** Single file `gui.py` at the project root plus a new `src/sanity.py` utility module for the testable sanity-check logic. Backend changes consolidate `exclusive_company` into `employee_data.csv` and add a dynamic output filename. No new directories.

**Tech Stack:** Python 3.11, Streamlit ≥1.35, pandas, openpyxl (existing).

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `data/employee_data.csv` | Add `exclusive_company` column |
| Modify | `src/config.py` | Remove `PREF_ALT_FILE` |
| Modify | `src/loaders/data_loader.py` | Read `exclusive_company` from employee CSV; remove `_load_exclusive_companies()` |
| Modify | `src/reports/excel_writer.py` | Accept `output_path` parameter |
| Modify | `main.py` | Build dynamic filename; pass `output_path` to `generate_report()` |
| Modify | `requirements.txt` | Add `streamlit>=1.35` |
| Create | `src/sanity.py` | Pure-Python sanity-check function (no Streamlit import) |
| Create | `tests/test_sanity.py` | Unit tests for `run_sanity_check` |
| Create | `tests/test_data_loader_excl.py` | Unit test: `exclusive_company` loaded from employee CSV |
| Create | `tests/test_excel_output_path.py` | Unit test: `generate_report` respects `output_path` |
| Create | `gui.py` | Streamlit app: 4 tabs |

---

## Task 1 — Add `exclusive_company` to `employee_data.csv`

**Files:**
- Modify: `data/employee_data.csv`

- [ ] **Step 1: Open `data/employee_data.csv` and add the new column**

Replace the file content with the following (Lin → Tianyuan, Zhong → Good Life, all others blank):

```csv
name,type,salary,exclusive_company
Jenny,Self-Employed,1800,
Ling,Self-Employed,2000,
Min,Self-Employed,1200,
Hou,Self-Employed,1100,
Elina,Self-Employed,1500,
Yang,Self-Employed,1200,
Rose,Self-Employed,1200,
Lily,Self-Employed,2000,
Amy,Self-Employed,1200,
Sunny,Self-Employed,1400,
Mango,Self-Employed,1150,
Kunsang,Self-Employed,1200,
Tenzin,Self-Employed,120,
Urai,Self-Employed,1500,
Linda,Self-Employed,900,
Nana,Self-Employed,900,
Sisi,Self-Employed,400,
Sherry,Self-Employed,900,
Zhong,Company-Employed,9210,Good Life
Yi,Company-Employed,12600,
Lin,Company-Employed,5670,Tianyuan
```

- [ ] **Step 2: Commit the CSV change alone**

```bash
git add data/employee_data.csv
git commit -m "data: add exclusive_company column to employee_data.csv"
```

---

## Task 2 — Update `data_loader.py` and `config.py`

**Files:**
- Modify: `src/config.py`
- Modify: `src/loaders/data_loader.py`
- Create: `tests/test_data_loader_excl.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_loader_excl.py`:

```python
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
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
pytest tests/test_data_loader_excl.py -v
```

Expected: FAIL — `_load_employees` does not yet read `exclusive_company`.

- [ ] **Step 3: Remove `PREF_ALT_FILE` from `src/config.py`**

Delete this line from `src/config.py`:

```python
PREF_ALT_FILE = f"{DATA_DIR}/preferences.csv"
```

- [ ] **Step 4: Update `_load_employees()` in `src/loaders/data_loader.py`**

Replace the existing `_load_employees` function with:

```python
def _load_employees() -> tuple[list[SelfEmployedEmployee], list[CompanyEmployedEmployee]]:
    df = pd.read_csv(EMPLOYEE_FILE)
    logger.info(f"Loaded {EMPLOYEE_FILE}: {len(df)} rows")

    se_workers: list[SelfEmployedEmployee] = []
    ce_workers: list[CompanyEmployedEmployee] = []
    has_excl_col = "exclusive_company" in df.columns

    for _, row in df.iterrows():
        name = str(row["name"]).strip()
        emp_type = str(row["type"]).strip()
        salary = int(row["salary"])

        if emp_type == TYPE_SELF_EMPLOYED:
            worker: SelfEmployedEmployee | CompanyEmployedEmployee = SelfEmployedEmployee(name, salary)
            se_workers.append(worker)
        elif emp_type == TYPE_COMPANY_EMPLOYED:
            worker = CompanyEmployedEmployee(name, salary)
            ce_workers.append(worker)
        else:
            logger.warning(f"  Unknown employee type '{emp_type}' for {name} — skipping")
            continue

        if has_excl_col:
            excl_raw = row["exclusive_company"]
            excl = (
                ""
                if (excl_raw is None or (isinstance(excl_raw, float) and math.isnan(excl_raw)))
                else str(excl_raw).strip()
            )
            if excl:
                if "good" in excl.lower():
                    worker.exclusive_company = GOOD_LIFE
                elif "tian" in excl.lower():
                    worker.exclusive_company = TIANYUAN
                else:
                    logger.warning(f"  exclusive_company: unrecognised value '{excl}' for {name}")
                if worker.exclusive_company:
                    logger.info(f"  {name} is exclusive to {worker.exclusive_company}")

    logger.info(
        f"  Self-employed:     {len(se_workers)} workers, "
        f"total monthly target = {sum(w.salary for w in se_workers):,}"
    )
    logger.info(
        f"  Company-employed:  {len(ce_workers)} workers, "
        f"total monthly cap    = {sum(w.salary for w in ce_workers):,}"
    )
    return se_workers, ce_workers
```

- [ ] **Step 5: Update `load_all()` — remove `_load_exclusive_companies` call**

In `src/loaders/data_loader.py`, replace the `load_all` function body:

```python
def load_all() -> tuple[
    list[SelfEmployedEmployee],
    list[CompanyEmployedEmployee],
    dict[str, Company],
]:
    logger.info("=" * 60)
    logger.info("DATA AUDIT — loading input files")
    logger.info("=" * 60)

    se_workers, ce_workers = _load_employees()
    companies = _load_income()
    _load_preferences(se_workers, ce_workers, companies)

    _log_summary(se_workers, ce_workers, companies)
    return se_workers, ce_workers, companies
```

- [ ] **Step 6: Delete `_load_exclusive_companies()` from `src/loaders/data_loader.py`**

Remove the entire function (lines ~165–219 in the original file). Also remove the `PREF_ALT_FILE` import at the top of the file:

```python
# Remove this import line:
from src.config import (
    EMPLOYEE_FILE, INCOME_FILE, PREFERENCE_FILE, PREF_ALT_FILE,
    ...
)

# Replace with:
from src.config import (
    EMPLOYEE_FILE, INCOME_FILE, PREFERENCE_FILE,
    GOOD_LIFE, TIANYUAN, COMPANY_NAMES,
    TYPE_SELF_EMPLOYED, TYPE_COMPANY_EMPLOYED,
)
```

- [ ] **Step 7: Run all tests**

```bash
pytest -v
```

Expected: all existing tests pass; both new tests in `test_data_loader_excl.py` pass.

- [ ] **Step 8: Commit**

```bash
git add src/config.py src/loaders/data_loader.py tests/test_data_loader_excl.py
git commit -m "refactor: fold exclusive_company into employee_data.csv; remove preferences.csv dependency"
```

---

## Task 3 — Dynamic output filename in `generate_report()` and `main.py`

**Files:**
- Modify: `src/reports/excel_writer.py`
- Modify: `main.py`
- Create: `tests/test_excel_output_path.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_excel_output_path.py`:

```python
"""Tests that generate_report writes to a caller-supplied path."""
import os
import random
import pytest
from src.reports.excel_writer import generate_report
from src.engine.feasibility import check_se_feasibility
from src.engine.ce_planner import plan_ce
from src.engine.se_scheduler import schedule_se
from src.engine.salary_solver import solve_salaries


def _run_and_report(scenario, seed, output_path):
    import copy
    s = copy.deepcopy(scenario)
    rng = random.Random(seed)
    check_se_feasibility(s["se_workers"], s["companies"])
    for company in s["companies"].values():
        for day in company.days:
            s["companies"][company.name].get_day(day).compute_se_target_from_ce(0)
    schedule_se(s["se_workers"], s["companies"], rng)
    solve_salaries(s["se_workers"], s["companies"], rng)
    plan_ce(s["ce_workers"], s["companies"], rng)
    generate_report(
        s["se_workers"], s["ce_workers"], s["companies"],
        seed=seed, output_path=output_path,
    )


def test_generate_report_writes_to_custom_path(tmp_path, simple_scenario):
    output_path = str(tmp_path / "report_seed42_20260515_120000.xlsx")
    _run_and_report(simple_scenario, seed=42, output_path=output_path)
    assert os.path.exists(output_path)


def test_generate_report_default_path_still_works(tmp_path, simple_scenario, monkeypatch):
    import src.config as cfg
    default_path = str(tmp_path / "output" / "report.xlsx")
    monkeypatch.setattr(cfg, "OUTPUT_FILE", default_path)
    import importlib, src.reports.excel_writer as ew
    importlib.reload(ew)
    _run_and_report(simple_scenario, seed=42, output_path=None)
    assert os.path.exists(default_path)
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
pytest tests/test_excel_output_path.py -v
```

Expected: FAIL — `generate_report` does not accept `output_path`.

- [ ] **Step 3: Update `generate_report()` in `src/reports/excel_writer.py`**

Replace the function signature and body opening:

```python
def generate_report(
    se_workers: list[SelfEmployedEmployee],
    ce_workers: list[CompanyEmployedEmployee],
    companies: dict[str, Company],
    seed: int = 0,
    output_path: str | None = None,
) -> None:
    path = output_path if output_path is not None else OUTPUT_FILE
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    wb = Workbook()
    default_sheet = wb.active
    if default_sheet is not None:
        wb.remove(default_sheet)

    _write_company_sheet(wb, GOOD_LIFE, "Good Life", se_workers, ce_workers, companies)
    _write_company_sheet(wb, TIANYUAN, "Tianyuan", se_workers, ce_workers, companies)
    _write_schedule_sheet(wb, se_workers, ce_workers, companies)
    _write_summary_sheet(wb, se_workers, ce_workers, companies, seed=seed)

    wb.save(path)
    logger.info(f"Report saved to: {path}")
```

- [ ] **Step 4: Update `main.py` to build the dynamic filename**

Replace the imports section at the top of `main.py` to add `datetime` and `OUTPUT_DIR`:

```python
import argparse
import logging
import os
import random
import sys
from datetime import datetime

from src.config import OUTPUT_DIR
from src.loaders.data_loader import load_all
from src.engine.feasibility import check_se_feasibility
from src.engine.ce_planner import plan_ce
from src.engine.se_scheduler import schedule_se
from src.engine.salary_solver import solve_salaries
from src.reports.excel_writer import generate_report
```

Replace the final two lines inside `main()`:

```python
    # 7. Generate report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"report_seed{seed}_{timestamp}.xlsx")
    generate_report(se_workers, ce_workers, companies, seed=seed, output_path=output_path)

    logger.info(f"Done. Output written to: {output_path}")
```

- [ ] **Step 5: Run all tests**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/reports/excel_writer.py main.py tests/test_excel_output_path.py
git commit -m "feat: dynamic output filename with seed and timestamp in generate_report"
```

---

## Task 4 — Sanity check utility and its tests

**Files:**
- Create: `src/sanity.py`
- Create: `tests/test_sanity.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sanity.py`:

```python
"""Unit tests for run_sanity_check."""
import pandas as pd
import pytest
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
    assert len(errors) >= 3  # bad type, zero salary, duplicate, missing from pref
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_sanity.py -v
```

Expected: FAIL — `src/sanity.py` does not exist yet.

- [ ] **Step 3: Create `src/sanity.py`**

```python
import math
import pandas as pd

_VALID_TYPES = {"Self-Employed", "Company-Employed"}


def run_sanity_check(employees_df: pd.DataFrame, pref_df: pd.DataFrame) -> list[str]:
    """
    Returns a list of human-readable error strings.
    Empty list means all checks passed.
    """
    errors: list[str] = []

    for _, row in employees_df.iterrows():
        name = str(row["name"]).strip()
        if str(row["type"]).strip() not in _VALID_TYPES:
            errors.append(f"{name}: invalid type '{row['type']}' (must be Self-Employed or Company-Employed)")
        try:
            salary = int(row["salary"])
        except (ValueError, TypeError):
            salary = 0
        if salary <= 0:
            errors.append(f"{name}: salary must be a positive integer (got {row['salary']})")

    names = [str(r).strip() for r in employees_df["name"]]
    seen: set[str] = set()
    for n in names:
        if n in seen:
            errors.append(f"Duplicate employee name: '{n}'")
        seen.add(n)

    pref_cols = set(pref_df.columns) - {"Company", "Day"}
    missing = [n for n in names if n not in pref_cols]
    if missing:
        errors.append(f"Employees missing from preference matrix: {missing}")

    return errors
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_sanity.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/sanity.py tests/test_sanity.py
git commit -m "feat: add run_sanity_check utility with full test coverage"
```

---

## Task 5 — Add Streamlit to requirements and scaffold `gui.py`

**Files:**
- Modify: `requirements.txt`
- Create: `gui.py`

- [ ] **Step 1: Add Streamlit to `requirements.txt`**

```
openpyxl>=3.1.0
pandas>=2.0.0
numpy>=1.24.0
streamlit>=1.35
```

- [ ] **Step 2: Install it**

```bash
pip install streamlit>=1.35
```

- [ ] **Step 3: Create `gui.py` with the four-tab scaffold**

```python
"""Streamlit GUI for the monthly salary planner."""
import logging
import os
import random
from datetime import datetime
from io import StringIO

import pandas as pd
import streamlit as st

from src.sanity import run_sanity_check

EMPLOYEE_FILE = "data/employee_data.csv"
INCOME_FILE = "data/income_data.csv"
PREF_MATRIX_FILE = "data/updated_preference.csv"
OUTPUT_DIR = "output"

st.set_page_config(page_title="Salary Planner", layout="wide")
st.title("Monthly Salary Planner")

tab_employees, tab_income, tab_pref, tab_generate = st.tabs(
    ["Employees", "Income", "Preference Matrix", "Generate"]
)

with tab_employees:
    st.header("Employees")
    st.caption("Edit employee_data.csv. Save before switching tabs.")

with tab_income:
    st.header("Income")
    st.caption("Edit income_data.csv — 30 rows, one per working day.")

with tab_pref:
    st.header("Preference Matrix")
    st.caption("0 = unavailable · 1 = available · 2 = preferred. Edit updated_preference.csv.")

with tab_generate:
    st.header("Generate Report")
```

- [ ] **Step 4: Verify the scaffold runs without errors**

```bash
streamlit run gui.py
```

Open the URL shown in terminal (usually `http://localhost:8501`). Confirm four tabs appear with their headings and captions. Close the server with Ctrl+C.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt gui.py
git commit -m "feat: scaffold Streamlit GUI with four tabs"
```

---

## Task 6 — Employees tab

**Files:**
- Modify: `gui.py` (Employees tab section)

- [ ] **Step 1: Replace the `with tab_employees:` block**

```python
with tab_employees:
    st.header("Employees")
    st.caption("Edit employee_data.csv. Save before switching tabs.")

    _emp_df = pd.read_csv(EMPLOYEE_FILE)
    edited_emp = st.data_editor(
        _emp_df,
        num_rows="dynamic",
        column_config={
            "name": st.column_config.TextColumn("Name", required=True),
            "type": st.column_config.SelectboxColumn(
                "Type",
                options=["Self-Employed", "Company-Employed"],
                required=True,
            ),
            "salary": st.column_config.NumberColumn("Salary", min_value=1, step=1, required=True),
            "exclusive_company": st.column_config.SelectboxColumn(
                "Exclusive Company",
                options=["", "Good Life", "Tianyuan"],
            ),
        },
        use_container_width=True,
        key="employees_editor",
    )
    if st.button("Save Employees"):
        edited_emp.to_csv(EMPLOYEE_FILE, index=False)
        st.success("Saved employee_data.csv")
```

- [ ] **Step 2: Verify in the browser**

```bash
streamlit run gui.py
```

Open `http://localhost:8501`. In the Employees tab:
- Confirm the table loads with all 21 employees.
- Edit a salary value and click **Save Employees** — verify the value persists after page refresh.
- Add a new row and save — verify it appears in `data/employee_data.csv`.
- Close with Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add gui.py
git commit -m "feat: Employees tab with editable data_editor and save"
```

---

## Task 7 — Income tab

**Files:**
- Modify: `gui.py` (Income tab section)

- [ ] **Step 1: Replace the `with tab_income:` block**

```python
with tab_income:
    st.header("Income")
    st.caption("Edit income_data.csv — 30 rows, one per working day.")

    _inc_df = pd.read_csv(INCOME_FILE)
    edited_inc = st.data_editor(
        _inc_df,
        num_rows="fixed",
        column_config={
            "day": st.column_config.NumberColumn("Day", disabled=True),
            "good_life": st.column_config.NumberColumn("Good Life Income", min_value=0, step=1),
            "tianyuan": st.column_config.NumberColumn("Tianyuan Income", min_value=0, step=1),
        },
        use_container_width=True,
        key="income_editor",
    )
    if st.button("Save Income"):
        edited_inc.to_csv(INCOME_FILE, index=False)
        st.success("Saved income_data.csv")
```

- [ ] **Step 2: Verify in the browser**

```bash
streamlit run gui.py
```

In the Income tab:
- Confirm 30 rows appear, `day` column is not editable.
- Edit a Good Life income value and save — verify it persists in `data/income_data.csv`.
- Close with Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add gui.py
git commit -m "feat: Income tab with editable data_editor and save"
```

---

## Task 8 — Preference Matrix tab

**Files:**
- Modify: `gui.py` (Preference Matrix tab section)

- [ ] **Step 1: Replace the `with tab_pref:` block**

```python
with tab_pref:
    st.header("Preference Matrix")
    st.caption("0 = unavailable · 1 = available · 2 = preferred. Edit updated_preference.csv.")

    _pref_df = pd.read_csv(PREF_MATRIX_FILE)
    _employee_cols = [c for c in _pref_df.columns if c not in ("Company", "Day")]

    _pref_col_config: dict = {
        "Company": st.column_config.TextColumn("Company", disabled=True),
        "Day": st.column_config.NumberColumn("Day", disabled=True),
    }
    for _col in _employee_cols:
        _pref_col_config[_col] = st.column_config.NumberColumn(
            _col, min_value=0, max_value=2, step=1
        )

    edited_pref = st.data_editor(
        _pref_df,
        num_rows="fixed",
        disabled=["Company", "Day"],
        column_config=_pref_col_config,
        use_container_width=True,
        key="pref_editor",
    )
    if st.button("Save Preference Matrix"):
        edited_pref.to_csv(PREF_MATRIX_FILE, index=False)
        st.success("Saved updated_preference.csv")
```

- [ ] **Step 2: Verify in the browser**

```bash
streamlit run gui.py
```

In the Preference Matrix tab:
- Confirm 60 rows, Company and Day columns are read-only.
- Change a cell value (0→2) and save — verify it persists in `data/updated_preference.csv`.
- Close with Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add gui.py
git commit -m "feat: Preference Matrix tab with editable data_editor and save"
```

---

## Task 9 — Generate tab

**Files:**
- Modify: `gui.py` (Generate tab section)

- [ ] **Step 1: Replace the `with tab_generate:` block**

```python
with tab_generate:
    st.header("Generate Report")

    if "seed" not in st.session_state:
        st.session_state["seed"] = random.SystemRandom().randrange(2**32)
    if "sanity_passed" not in st.session_state:
        st.session_state["sanity_passed"] = False

    seed_input = st.text_input(
        "Seed (integer)",
        value=str(st.session_state["seed"]),
        key="seed_input",
    )

    if st.button("Run Sanity Check"):
        try:
            st.session_state["seed"] = int(seed_input)
        except ValueError:
            st.error("Seed must be an integer.")
            st.stop()

        _emp_check = pd.read_csv(EMPLOYEE_FILE)
        _pref_check = pd.read_csv(PREF_MATRIX_FILE)
        _errors = run_sanity_check(_emp_check, _pref_check)

        if _errors:
            st.session_state["sanity_passed"] = False
            st.error("Sanity check failed:\n\n" + "\n".join(f"• {e}" for e in _errors))
        else:
            st.session_state["sanity_passed"] = True
            st.success("All checks passed — ready to generate.")

    if st.button("Generate", disabled=not st.session_state["sanity_passed"]):
        try:
            _seed = int(seed_input)
        except ValueError:
            st.error("Seed must be an integer.")
            st.stop()

        from src.loaders.data_loader import load_all
        from src.engine.feasibility import check_se_feasibility
        from src.engine.ce_planner import plan_ce
        from src.engine.se_scheduler import schedule_se
        from src.engine.salary_solver import solve_salaries
        from src.reports.excel_writer import generate_report
        import random as _rnd

        _log_buffer = StringIO()
        _handler = logging.StreamHandler(_log_buffer)
        _handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s — %(message)s", "%H:%M:%S"))
        _root = logging.getLogger()
        _root.addHandler(_handler)
        _root.setLevel(logging.INFO)

        _output_path = None
        try:
            _rng = _rnd.Random(_seed)
            _se, _ce, _companies = load_all()
            check_se_feasibility(_se, _companies)
            for _company in _companies.values():
                for _day in _company.days:
                    _company.get_day(_day).compute_se_target_from_ce(0)
            schedule_se(_se, _companies, _rng)
            solve_salaries(_se, _companies, _rng)
            plan_ce(_ce, _companies, _rng)

            _ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            _output_path = os.path.join(OUTPUT_DIR, f"report_seed{_seed}_{_ts}.xlsx")
            generate_report(_se, _ce, _companies, seed=_seed, output_path=_output_path)
            st.success(f"Report generated: `{_output_path}`")
        except Exception as _exc:
            st.error(f"Pipeline error: {_exc}")
        finally:
            _root.removeHandler(_handler)

        st.text_area("Pipeline Log", _log_buffer.getvalue(), height=300)

        if _output_path and os.path.exists(_output_path):
            with open(_output_path, "rb") as _f:
                st.download_button(
                    label="Download Report",
                    data=_f.read(),
                    file_name=os.path.basename(_output_path),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
```

- [ ] **Step 2: Verify in the browser — happy path**

```bash
streamlit run gui.py
```

In the Generate tab:
1. Note the random seed pre-filled in the text box.
2. Click **Run Sanity Check** — should show "All checks passed".
3. Click **Generate** — should show "Report generated: output/report_seed…xlsx", display the pipeline log, and show a **Download Report** button.
4. Verify the `.xlsx` file exists in `output/` with seed and timestamp in the filename.

- [ ] **Step 3: Verify in the browser — sanity failure path**

1. Go to Employees tab, change one employee's type to `InvalidType` and save.
2. Return to Generate tab and click **Run Sanity Check** — should show a bullet-list error about invalid type.
3. Confirm the **Generate** button is greyed out.
4. Fix the employee type and re-run sanity check — Generate should become active again.

- [ ] **Step 4: Verify seed is editable**

1. Clear the seed field and type `12345`.
2. Click **Run Sanity Check** (this persists the seed).
3. Click **Generate** — the output filename should contain `seed12345`.

- [ ] **Step 5: Run full test suite one final time**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add gui.py
git commit -m "feat: Generate tab with seed input, sanity check, pipeline run, and download"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Streamlit, 4 tabs — Tasks 5-9
- ✅ Edit employee_data.csv (name/type/salary/exclusive_company) — Task 6
- ✅ Edit income_data.csv (30 locked rows) — Task 7
- ✅ Edit updated_preference.csv (60-row matrix, 0/1/2) — Task 8
- ✅ Save button per tab — Tasks 6-8
- ✅ Seed textbox with random default — Task 9
- ✅ Sanity check: employee completeness + preference coverage — Tasks 4, 9
- ✅ Generate button disabled until sanity passes — Task 9
- ✅ Output filename: seed + datetime — Tasks 3, 9
- ✅ Pipeline log in text area — Task 9
- ✅ Download button — Task 9
- ✅ exclusive_company consolidated from preferences.csv into employee_data.csv — Tasks 1-2
- ✅ preferences.csv no longer read — Task 2

**No placeholders found.**

**Type consistency:** `run_sanity_check(employees_df, pref_df)` used consistently in `src/sanity.py`, `tests/test_sanity.py`, and `gui.py`. `generate_report(..., output_path=...)` consistent across `excel_writer.py`, `main.py`, `tests/test_excel_output_path.py`, and `gui.py`.
