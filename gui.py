"""Streamlit GUI for the monthly salary planner."""
import streamlit as st

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
    st.caption("Run sanity check, then generate the Excel report with your chosen seed.")
