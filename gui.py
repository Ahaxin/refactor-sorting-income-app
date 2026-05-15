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
        if edited_emp.empty:
            st.error("Cannot save: employee list is empty.")
        elif edited_emp[["name", "type", "salary"]].isnull().any(axis=None):
            st.error("All rows must have Name, Type, and Salary filled in.")
        else:
            edited_emp["salary"] = edited_emp["salary"].astype("Int64")
            edited_emp.to_csv(EMPLOYEE_FILE, index=False)
            st.success("Saved employee_data.csv")
            st.session_state["sanity_passed"] = False

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
        edited_inc[["good_life", "tianyuan"]] = edited_inc[["good_life", "tianyuan"]].astype("Int64")
        edited_inc.to_csv(INCOME_FILE, index=False)
        st.success("Saved income_data.csv")
        st.session_state["sanity_passed"] = False

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
        column_config=_pref_col_config,
        use_container_width=True,
        key="pref_editor",
    )
    if st.button("Save Preference Matrix"):
        edited_pref.to_csv(PREF_MATRIX_FILE, index=False)
        st.success("Saved updated_preference.csv")
        st.session_state["sanity_passed"] = False

with tab_generate:
    st.header("Generate Report")
    st.caption("Run sanity check, then generate the Excel report with your chosen seed.")

    if "seed" not in st.session_state:
        st.session_state["seed"] = random.SystemRandom().randrange(2**32)
    if "sanity_passed" not in st.session_state:
        st.session_state["sanity_passed"] = False
    if "last_output_path" not in st.session_state:
        st.session_state["last_output_path"] = None
    if "last_log" not in st.session_state:
        st.session_state["last_log"] = ""

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
        _seed = 0
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
        _handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s", "%H:%M:%S"
        ))
        _root = logging.getLogger()
        _root.addHandler(_handler)
        _prior_level = _root.level
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
            st.session_state["last_output_path"] = _output_path
            st.session_state["last_log"] = _log_buffer.getvalue()
        except Exception as _exc:
            st.error(f"Pipeline error: {_exc}")
        finally:
            _root.removeHandler(_handler)
            _root.setLevel(_prior_level)

    if st.session_state.get("last_log"):
        st.text_area("Pipeline Log", st.session_state["last_log"], height=300)
    _last_path = st.session_state.get("last_output_path")
    if _last_path and os.path.exists(_last_path):
        with open(_last_path, "rb") as _f:
            st.download_button(
                label="Download Report",
                data=_f.read(),
                file_name=os.path.basename(_last_path),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
