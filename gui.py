"""Streamlit GUI for the monthly salary planner."""
import streamlit as st
import pandas as pd

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
        edited_emp.to_csv(EMPLOYEE_FILE, index=False)
        st.success("Saved employee_data.csv")

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

with tab_generate:
    st.header("Generate Report")
    st.caption("Run sanity check, then generate the Excel report with your chosen seed.")
