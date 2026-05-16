"""Streamlit GUI for the monthly salary planner."""
import logging
import os
import random
from datetime import datetime
from io import StringIO

import pandas as pd
import streamlit as st

from src.sanity import run_sanity_check
from src.i18n import I18N

# File Paths
EMPLOYEE_FILE = "data/employee_data.csv"
INCOME_FILE = "data/income_data.csv"
PREF_MATRIX_FILE = "data/updated_preference.csv"
OUTPUT_DIR = "output"

# 1. Page Config
st.set_page_config(page_title="Salary Planner", layout="wide")

# 2. Language settings
if "lang" not in st.session_state:
    st.session_state["lang"] = "zh"

# 3. Custom CSS
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap');
    
    html, body, .stApp {
        font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif !important;
        background-color: #f8f9fc;
    }
    
    /* Target only the main container for background */
    [data-testid="stAppViewContainer"] {
        background-color: #f8f9fc;
    }

    .block-container {
        padding-top: 2rem;
    }

    /* Metric Styling */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
        color: #4e73df;
    }
    
    /* Ensure button text is always visible */
    .stButton > button {
        color: inherit !important;
    }
    </style>
    """, unsafe_allow_html=True)

# 4. Header with Title and Language Toggle
col_title, col_lang = st.columns([6, 1])

lang = st.session_state["lang"]
t = I18N[lang]

with col_lang:
    toggle_text = "English" if lang == "zh" else "中文"
    is_eng_active = st.toggle(toggle_text, value=(lang == "en"), key="lang_toggle")
    
    desired_lang = "en" if is_eng_active else "zh"
    if desired_lang != lang:
        st.session_state["lang"] = desired_lang
        st.rerun()

with col_title:
    st.title(t["title"])

# 5. Shared logic and State Management
def reset_all_editors():
    st.session_state["employees_version"] = st.session_state.get("employees_version", 0) + 1
    st.session_state["income_version"] = st.session_state.get("income_version", 0) + 1
    st.session_state["pref_version"] = st.session_state.get("pref_version", 0) + 1
    st.rerun()

def get_unsaved_changes():
    unsaved = []
    emp_key = f"employees_editor_{st.session_state.get('employees_version', 0)}_{lang}"
    if emp_key in st.session_state:
        s = st.session_state[emp_key]
        if s.get("edited_rows") or s.get("added_rows") or s.get("deleted_rows"):
            unsaved.append("employees")
    
    inc_key = f"income_editor_{st.session_state.get('income_version', 0)}_{lang}"
    if inc_key in st.session_state:
        s = st.session_state[inc_key]
        if s.get("edited_rows") or s.get("added_rows") or s.get("deleted_rows"):
            unsaved.append("income")
            
    pref_key = f"pref_editor_{st.session_state.get('pref_version', 0)}_{lang}"
    if pref_key in st.session_state:
        s = st.session_state[pref_key]
        if s.get("edited_rows") or s.get("added_rows") or s.get("deleted_rows"):
            unsaved.append("pref")
    return unsaved

def get_type_maps(t):
    type_map = {"Self-Employed": t["type_se"], "Company-Employed": t["type_ce"]}
    rev_type_map = {v: k for k, v in type_map.items()}
    return type_map, rev_type_map

def get_company_maps(t):
    company_map = {"": "", "Good Life": t["company_gl"], "Tianyuan": t["company_ty"]}
    rev_company_map = {v: k for k, v in company_map.items()}
    return company_map, rev_company_map

type_map, rev_type_map = get_type_maps(t)
comp_map, rev_comp_map = get_company_maps(t)

# 6. Global Prompt Bar
unsaved_tabs = get_unsaved_changes()
if unsaved_tabs:
    st.warning(t["warn_unsaved"])
    c_s, c_d, _ = st.columns([1, 1, 4])
    if c_s.button(t["btn_save_all"], use_container_width=True, type="primary"):
        st.session_state["trigger_save_all"] = True
        st.rerun()
    if c_d.button(t["btn_discard_all"], use_container_width=True):
        reset_all_editors()

# 7. Data Loading for Metrics
if "employees_df" not in st.session_state:
    st.session_state["employees_df"] = pd.read_csv(EMPLOYEE_FILE)
if "income_df" not in st.session_state:
    st.session_state["income_df"] = pd.read_csv(INCOME_FILE)
if "pref_df" not in st.session_state:
    st.session_state["pref_df"] = pd.read_csv(PREF_MATRIX_FILE)

# Dashboard Summary Metrics
with st.container():
    m1, m2, m3, m4, m5 = st.columns(5)
    
    emp_df = st.session_state["employees_df"]
    inc_df = st.session_state["income_df"]
    
    se_count = len(emp_df[emp_df["type"] == "Self-Employed"])
    ce_count = len(emp_df[emp_df["type"] == "Company-Employed"])
    total_salary = emp_df["salary"].sum()
    total_days = len(inc_df)
    total_income = inc_df["good_life"].sum() + inc_df["tianyuan"].sum()
    
    m1.metric(t["metric_se"], se_count)
    m2.metric(t["metric_ce"], ce_count)
    m3.metric(t["metric_salary"], f"¥{total_salary:,}")
    m4.metric(t["metric_days"], total_days)
    m5.metric(t["metric_income"], f"¥{total_income:,}")

st.markdown("---")

tab_employees, tab_income, tab_pref, tab_generate = st.tabs(
    [t["tab_employees"], t["tab_income"], t["tab_pref"], t["tab_generate"]]
)

# 8. Tab Implementations
with tab_employees:
    st.header(t["header_employees"])
    st.caption(t["caption_employees"])
    st.info(t["info_employees"])

    display_emp = st.session_state["employees_df"].copy()
    display_emp["type"] = display_emp["type"].map(lambda x: type_map.get(x, x))
    display_emp["exclusive_company"] = display_emp["exclusive_company"].fillna("").map(lambda x: comp_map.get(x, x))

    _emp_editor_key = f"employees_editor_{st.session_state.get('employees_version', 0)}_{lang}"
    edited_emp_display = st.data_editor(
        display_emp,
        num_rows="dynamic",
        column_config={
            "name": st.column_config.TextColumn(t["col_name"], required=True),
            "type": st.column_config.SelectboxColumn(t["col_type"], options=list(type_map.values()), required=True),
            "salary": st.column_config.NumberColumn(t["col_salary"], min_value=1, step=1, required=True),
            "exclusive_company": st.column_config.SelectboxColumn(t["col_exclusive"], options=list(comp_map.values())),
        },
        width="stretch",
        key=_emp_editor_key,
    )

    def do_save_employees(df):
        if df.empty:
            st.error(t["err_emp_empty"])
            return False
        elif df[["name", "type", "salary"]].isnull().any(axis=None):
            st.error(t["err_emp_missing"])
            return False
        else:
            save_df = df.copy()
            save_df["type"] = save_df["type"].map(lambda x: rev_type_map.get(x, x))
            save_df["exclusive_company"] = save_df["exclusive_company"].map(lambda x: rev_comp_map.get(x, ""))
            save_df["salary"] = save_df["salary"].astype("Int64")
            save_df.to_csv(EMPLOYEE_FILE, index=False)
            st.session_state["employees_df"] = save_df.copy()
            st.session_state["sanity_passed"] = False
            return True

    if st.session_state.get("trigger_save_all") and "employees" in unsaved_tabs:
        do_save_employees(edited_emp_display)

    _emp_col_add, _emp_col_save = st.columns([1, 1])
    with _emp_col_add:
        if st.button(t["btn_add_emp"], key="emp_add", use_container_width=True):
            _new_row = pd.DataFrame([{"name": "", "type": type_map["Self-Employed"], "salary": 1, "exclusive_company": ""}])
            updated_display = pd.concat([edited_emp_display, _new_row], ignore_index=True)
            updated_internal = updated_display.copy()
            updated_internal["type"] = updated_internal["type"].map(lambda x: rev_type_map.get(x, x))
            updated_internal["exclusive_company"] = updated_internal["exclusive_company"].map(lambda x: rev_comp_map.get(x, ""))
            st.session_state["employees_df"] = updated_internal
            st.session_state["employees_version"] = st.session_state.get("employees_version", 0) + 1
            st.rerun()
    with _emp_col_save:
        if st.button(t["btn_save_emp"], key="emp_save", use_container_width=True, type="primary"):
            if do_save_employees(edited_emp_display):
                st.success(t["msg_emp_saved"])
                st.session_state["employees_version"] = st.session_state.get("employees_version", 0) + 1
                st.rerun()

with tab_income:
    st.header(t["header_income"])
    st.caption(t["caption_income"])
    st.info(t["info_income"])

    _inc_editor_key = f"income_editor_{st.session_state.get('income_version', 0)}_{lang}"
    edited_inc = st.data_editor(
        st.session_state["income_df"],
        num_rows="dynamic",
        column_config={
            "day": st.column_config.NumberColumn(t["col_day"], disabled=True, help=t["help_day"]),
            "good_life": st.column_config.NumberColumn(t["col_gl_income"], min_value=0, step=1),
            "tianyuan": st.column_config.NumberColumn(t["col_ty_income"], min_value=0, step=1),
        },
        width="stretch",
        key=_inc_editor_key,
    )

    def do_save_income(df):
        if df.empty:
            st.error(t["err_inc_empty"])
            return False
        elif df[["good_life", "tianyuan"]].isnull().any(axis=None):
            st.error(t["err_inc_missing"])
            return False
        else:
            _saved_inc = df.copy()
            _saved_inc["day"] = range(1, len(_saved_inc) + 1)
            _saved_inc[["good_life", "tianyuan"]] = _saved_inc[["good_life", "tianyuan"]].astype("Int64")
            _saved_inc.to_csv(INCOME_FILE, index=False)
            st.session_state["income_df"] = _saved_inc.copy()
            
            # Sync Pref Matrix
            _new_days = _saved_inc["day"].tolist()
            _pref_old = pd.read_csv(PREF_MATRIX_FILE)
            _companies_order = list(dict.fromkeys(_pref_old["Company"].tolist()))
            _employee_cols_p = [c for c in _pref_old.columns if c not in ("Company", "Day")]
            _pref_lookup = {(str(r["Company"]), int(r["Day"])): r for _, r in _pref_old.iterrows()}
            _new_rows = []
            for _company in _companies_order:
                for _day in _new_days:
                    _existing = _pref_lookup.get((_company, int(_day)))
                    _row = {"Company": _company, "Day": int(_day)}
                    for _col in _employee_cols_p:
                        _row[_col] = int(_existing[_col]) if _existing is not None else 1
                    _new_rows.append(_row)
            _pref_new = pd.DataFrame(_new_rows)[["Company", "Day"] + _employee_cols_p]
            _pref_new.to_csv(PREF_MATRIX_FILE, index=False)
            st.session_state["pref_df"] = _pref_new.copy()
            st.session_state["sanity_passed"] = False
            return True

    if st.session_state.get("trigger_save_all") and "income" in unsaved_tabs:
        do_save_income(edited_inc)

    _inc_col_add, _inc_col_save = st.columns([1, 1])
    with _inc_col_add:
        if st.button(t["btn_add_day"], key="inc_add", use_container_width=True):
            _next_day = int(edited_inc["day"].max()) + 1 if len(edited_inc) else 1
            _new_row = pd.DataFrame([{"day": _next_day, "good_life": 0, "tianyuan": 0}])
            st.session_state["income_df"] = pd.concat([edited_inc, _new_row], ignore_index=True)
            st.session_state["income_version"] = st.session_state.get("income_version", 0) + 1
            st.rerun()
    with _inc_col_save:
        if st.button(t["btn_save_income"], key="inc_save", use_container_width=True, type="primary"):
            if do_save_income(edited_inc):
                st.success(t["msg_inc_saved"].format(n=len(st.session_state["income_df"])))
                st.session_state["income_version"] = st.session_state.get("income_version", 0) + 1
                st.session_state["pref_version"] = st.session_state.get("pref_version", 0) + 1
                st.rerun()

def _pref_int_to_label_df(df: pd.DataFrame, int_to_label, available_label) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col in ("Company", "Day"): continue
        out[col] = out[col].apply(lambda v: int_to_label.get(int(v), available_label) if pd.notna(v) else available_label)
    return out

def _pref_label_to_int_df(df: pd.DataFrame, label_to_int) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col in ("Company", "Day"): continue
        out[col] = out[col].apply(lambda v: label_to_int.get(v, 1)).astype("Int64")
    return out

with tab_pref:
    st.header(t["header_pref"])
    st.caption(t["caption_pref"])
    pref_label_unavailable = t["label_unavailable"]
    pref_label_available = t["label_available"]
    pref_label_preferred = t["label_preferred"]
    pref_int_to_label = {0: pref_label_unavailable, 1: pref_label_available, 2: pref_label_preferred}
    pref_label_to_int = {v: k for k, v in pref_int_to_label.items()}
    pref_options = [pref_label_unavailable, pref_label_available, pref_label_preferred]
    st.info(t["info_pref"].format(u=pref_label_unavailable, a=pref_label_available, p=pref_label_preferred))

    _pref_df_int = st.session_state["pref_df"]
    _employee_cols = [c for c in _pref_df_int.columns if c not in ("Company", "Day")]
    _pref_df_display = _pref_int_to_label_df(_pref_df_int, pref_int_to_label, pref_label_available)
    _pref_col_config = {"Company": st.column_config.TextColumn(t["col_company"], disabled=True), "Day": st.column_config.NumberColumn(t["col_day"], disabled=True)}
    for _col in _employee_cols:
        _pref_col_config[_col] = st.column_config.SelectboxColumn(_col, options=pref_options, required=True)

    _pref_editor_key = f"pref_editor_{st.session_state.get('pref_version', 0)}_{lang}"
    edited_pref_display = st.data_editor(_pref_df_display, num_rows="fixed", column_config=_pref_col_config, width="stretch", key=_pref_editor_key)

    def do_save_pref(display_df):
        try:
            edited_pref = _pref_label_to_int_df(display_df, pref_label_to_int)
        except (KeyError, ValueError) as _exc:
            st.error(t["err_pref_parse"].format(e=_exc))
            return False
        else:
            edited_pref.to_csv(PREF_MATRIX_FILE, index=False)
            st.session_state["pref_df"] = edited_pref.copy()
            st.session_state["sanity_passed"] = False
            return True

    if st.session_state.get("trigger_save_all") and "pref" in unsaved_tabs:
        do_save_pref(edited_pref_display)

    if st.button(t["btn_save_pref"], use_container_width=True, type="primary"):
        if do_save_pref(edited_pref_display):
            st.success(t["msg_pref_saved"])
            st.session_state["pref_version"] = st.session_state.get("pref_version", 0) + 1
            st.rerun()

# 9. Handle Save All trigger completion
if st.session_state.get("trigger_save_all"):
    st.session_state["trigger_save_all"] = False
    st.success(t["msg_all_saved"])
    reset_all_editors()

with tab_generate:
    st.header(t["header_gen"])
    st.subheader(t["summary_header"])
    
    if "seed" not in st.session_state: st.session_state["seed"] = random.SystemRandom().randrange(2**32)
    if "sanity_passed" not in st.session_state: st.session_state["sanity_passed"] = False
    if "sanity_errors" not in st.session_state: st.session_state["sanity_errors"] = []
    if "last_output_path" not in st.session_state: st.session_state["last_output_path"] = None
    if "last_log" not in st.session_state: st.session_state["last_log"] = ""
    
    c_seed, c_status = st.columns([2, 1])
    with c_seed:
        seed_input = st.text_input(t["label_seed"], value=str(st.session_state["seed"]), key="seed_input")
    with c_status:
        # Display status based on session state
        if st.session_state["sanity_errors"]:
            st.markdown(f"### {t['status_error']}")
        elif st.session_state["sanity_passed"]:
            st.markdown(f"### {t['status_ready']}")
        else:
            st.markdown(f"### {t['status_pending']}")
    
    # Sanity result area
    if st.session_state["sanity_errors"]:
        st.error(t["err_sanity_failed"] + "\n".join(f"• {e}" for e in st.session_state["sanity_errors"]))
    elif st.session_state["sanity_passed"]:
        st.success(t["msg_sanity_passed"])

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        # Define label clearly
        label_sanity = t["btn_run_sanity"]
        if st.button(label_sanity, use_container_width=True, key="btn_run_sanity_check"):
            try: st.session_state["seed"] = int(seed_input)
            except ValueError: st.error(t["err_seed_int"]); st.stop()
            
            # Perform check
            _errors = run_sanity_check(st.session_state["employees_df"], st.session_state["pref_df"], st.session_state["income_df"], lang=lang)
            st.session_state["sanity_errors"] = _errors
            st.session_state["sanity_passed"] = (len(_errors) == 0)
            st.rerun() # Trigger a clean rerun to update UI state and button labels
    
    with col_btn2:
        # Define label clearly and ensure it's a string
        label_gen = str(t["btn_generate"])
        # Important: Assign to variable BEFORE calling button
        is_ready = st.session_state.get("sanity_passed", False)
        
        if st.button(label_gen, disabled=not is_ready, use_container_width=True, type="primary", key="btn_trigger_generate"):
            try: _seed = int(seed_input)
            except ValueError: st.error(t["err_seed_int"]); st.stop()
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
            _prior_level = _root.level
            _root.setLevel(logging.INFO)
            try:
                _rng = _rnd.Random(_seed); _se, _ce, _companies = load_all()
                check_se_feasibility(_se, _companies)
                for _c in _companies.values():
                    for _d in _c.days: _c.get_day(_d).compute_se_target_from_ce(0)
                schedule_se(_se, _companies, _rng); solve_salaries(_se, _companies, _rng); plan_ce(_ce, _companies, _rng)
                _ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                _output_path = os.path.join(OUTPUT_DIR, f"report_seed{_seed}_{_ts}.xlsx")
                generate_report(_se, _ce, _companies, seed=_seed, output_path=_output_path)
                from src.config import SE_SALARY_UNIT
                _deviations = []
                for _c in _companies.values():
                    for _dn in _c.days:
                        _dl = _c.get_day(_dn)
                        if _dl.is_full_ce_absorption: continue
                        _fval = round(_dl.formula_check); _dev = abs(_fval - _dl.cleaned_income)
                        if _dev > SE_SALARY_UNIT: _deviations.append(t["deviation_msg"].format(company=_c.name, day=_dn, formula=_fval, cleaned=_dl.cleaned_income, dev=_dev))
                st.success(t["msg_gen_success"].format(p=_output_path))
                if _deviations: st.warning(t["warn_deviation"].format(n=len(_deviations), u=SE_SALARY_UNIT) + "\n".join(f"• {d}" for d in _deviations))
                st.session_state["last_output_path"] = _output_path; st.session_state["last_log"] = _log_buffer.getvalue()
            except Exception as _exc: st.error(t["err_pipeline"].format(e=_exc)); st.session_state["last_log"] = _log_buffer.getvalue()
            finally: _root.removeHandler(_handler); _root.setLevel(_prior_level)

    if st.session_state.get("last_log"): 
        with st.expander(t["label_log"], expanded=True):
            st.text_area(t["label_log"], st.session_state["last_log"], height=300, label_visibility="collapsed")
    
    _lp = st.session_state.get("last_output_path")
    if _lp and os.path.exists(_lp):
        with open(_lp, "rb") as _f: st.download_button(label=t["btn_download"], data=_f.read(), file_name=os.path.basename(_lp), mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
