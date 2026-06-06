"""Streamlit GUI for the monthly salary planner."""
import logging
import os
from datetime import datetime
from io import StringIO

import pandas as pd
import streamlit as st

from src.sanity import run_sanity_check
from src.i18n import I18N

# File Paths
EMPLOYEE_FILE = "data/employee_data.csv"
INCOME_FILE = "data/income_data.csv"
SE_PREF_FILE = "data/se_preference.csv"
CE_PREF_FILE = "data/ce_preference.csv"
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

    /* Workflow stepper */
    .stepper {
        display: flex;
        align-items: flex-start;
        padding: 1.2rem 1rem 0.8rem 1rem;
        margin: 0.4rem 0 1rem 0;
        background: white;
        border-radius: 12px;
        border: 1px solid #e3e6f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .step {
        display: flex;
        flex-direction: column;
        align-items: center;
        flex: 0 0 auto;
        min-width: 110px;
        text-align: center;
    }
    .step-circle {
        width: 44px;
        height: 44px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.3rem;
        font-weight: 700;
        color: white;
        margin-bottom: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .step-saved   .step-circle { background: #1cc88a; }
    .step-warn    .step-circle { background: #f6c23e; }
    .step-ready   .step-circle { background: #4e73df; }
    .step-done    .step-circle { background: #1cc88a; }
    .step-pending .step-circle { background: #dddfeb; color: #6e707e; box-shadow: none; }

    .step-label {
        font-weight: 600;
        color: #2e3a4b;
        font-size: 0.95rem;
        white-space: nowrap;
    }
    .step-status {
        font-size: 0.78rem;
        color: #6e707e;
        margin-top: 0.2rem;
        white-space: nowrap;
    }
    .step-connector {
        flex: 1;
        height: 3px;
        background: #e3e6f0;
        margin-top: 22px;
        border-radius: 2px;
        min-width: 20px;
    }
    .step-connector.done { background: #1cc88a; }

    /* Status pill for the save-all action bar */
    .status-pill {
        padding: 0.55rem 1rem;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.95rem;
        height: 100%;
        display: flex;
        align-items: center;
    }
    .status-pill.status-warn { background: #fff3cd; color: #856404; border: 1px solid #ffeaa7; }
    .status-pill.status-ok   { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
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
            
    _pv = st.session_state.get('pref_version', 0)
    for _pk in [f"se_pref_editor_{_pv}_{lang}", f"ce_gl_pref_editor_{_pv}_{lang}",
                f"ce_ty_pref_editor_{_pv}_{lang}", f"ce_flex_pref_editor_{_pv}_{lang}"]:
        if _pk in st.session_state:
            s = st.session_state[_pk]
            if s.get("edited_rows") or s.get("added_rows") or s.get("deleted_rows"):
                if "pref" not in unsaved:
                    unsaved.append("pref")
                break
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

def render_stepper(unsaved_tabs):
    """Render the 4-step workflow stepper above the dashboard."""
    sanity_passed = st.session_state.get("sanity_passed", False)
    last_path = st.session_state.get("last_output_path")
    generate_done = bool(sanity_passed and last_path and os.path.exists(last_path))

    steps = [
        ("①", t["step_employees"], "employees"),
        ("②", t["step_income"], "income"),
        ("③", t["step_pref"], "pref"),
        ("④", t["step_generate"], "generate"),
    ]

    rendered = []
    prev_complete = True
    for i, (num, label, key) in enumerate(steps):
        if key == "generate":
            if generate_done:
                state, status, complete = "done", t["step_done"], True
            elif sanity_passed:
                state, status, complete = "ready", t["step_ready"], False
            else:
                state, status, complete = "pending", t["step_pending"], False
        else:
            if key in unsaved_tabs:
                state, status, complete = "warn", t["step_unsaved"], False
            else:
                state, status, complete = "saved", t["step_saved"], True

        if i > 0:
            connector_class = "step-connector done" if prev_complete else "step-connector"
            rendered.append(f'<div class="{connector_class}"></div>')
        rendered.append(
            f'<div class="step step-{state}">'
            f'<div class="step-circle">{num}</div>'
            f'<div class="step-label">{label}</div>'
            f'<div class="step-status">{status}</div>'
            f'</div>'
        )
        prev_complete = complete

    st.markdown('<div class="stepper">' + "".join(rendered) + '</div>', unsafe_allow_html=True)

# 6. Global Prompt Bar  — always rendered so layout never shifts
unsaved_tabs = get_unsaved_changes()
render_stepper(unsaved_tabs)

def _save_all_callback():
    unsaved = get_unsaved_changes()
    saved_any = False
    if "employees" in unsaved and "_emp_edited_df" in st.session_state:
        if do_save_employees(st.session_state["_emp_edited_df"]):
            saved_any = True
    if "income" in unsaved and "_inc_edited_df" in st.session_state:
        if do_save_income(st.session_state["_inc_edited_df"]):
            saved_any = True
    if "pref" in unsaved and "_se_pref_edited_df" in st.session_state:
        if do_save_pref(
            st.session_state["_se_pref_edited_df"],
            st.session_state.get("_ce_gl_pref_edited_df"),
            st.session_state.get("_ce_ty_pref_edited_df"),
            st.session_state.get("_ce_flex_pref_edited_df"),
        ):
            saved_any = True
    if saved_any:
        st.session_state["employees_version"] = st.session_state.get("employees_version", 0) + 1
        st.session_state["income_version"] = st.session_state.get("income_version", 0) + 1
        st.session_state["pref_version"] = st.session_state.get("pref_version", 0) + 1
        st.session_state["_flash_saved"] = True

def _discard_all_callback():
    st.session_state["employees_version"] = st.session_state.get("employees_version", 0) + 1
    st.session_state["income_version"] = st.session_state.get("income_version", 0) + 1
    st.session_state["pref_version"] = st.session_state.get("pref_version", 0) + 1

_has_unsaved = bool(unsaved_tabs)
_c_msg, _c_save, _c_discard = st.columns([4, 1, 1])
with _c_msg:
    if _has_unsaved:
        st.markdown(f'<div class="status-pill status-warn">{t["warn_unsaved"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="status-pill status-ok">{t["status_all_saved"]}</div>', unsafe_allow_html=True)
with _c_save:
    st.button(t["btn_save_all"], on_click=_save_all_callback, disabled=not _has_unsaved, use_container_width=True, type="primary", key="btn_save_all_top")
with _c_discard:
    st.button(t["btn_discard_all"], on_click=_discard_all_callback, disabled=not _has_unsaved, use_container_width=True, key="btn_discard_all_top")

if st.session_state.pop("_flash_saved", False):
    st.success(t["msg_all_saved"])

# 7. Data Loading for Metrics
if "employees_df" not in st.session_state:
    st.session_state["employees_df"] = pd.read_csv(EMPLOYEE_FILE)
if "income_df" not in st.session_state:
    st.session_state["income_df"] = pd.read_csv(INCOME_FILE)
if "se_pref_df" not in st.session_state:
    st.session_state["se_pref_df"] = pd.read_csv(SE_PREF_FILE)
if "ce_pref_df" not in st.session_state:
    st.session_state["ce_pref_df"] = pd.read_csv(CE_PREF_FILE)

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
        height=(len(display_emp) + 2) * 36 + 3,
        key=_emp_editor_key,
    )
    st.session_state["_emp_edited_df"] = edited_emp_display

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

            # Sync SE and CE preference files to current employee names
            _se_names = [str(r["name"]).strip() for _, r in save_df.iterrows() if str(r["type"]).strip() == "Self-Employed"]
            _ce_names = [str(r["name"]).strip() for _, r in save_df.iterrows() if str(r["type"]).strip() == "Company-Employed"]
            _se_old = pd.read_csv(SE_PREF_FILE)
            _se_old_cols = [c for c in _se_old.columns if c != "Day"]
            _se_new = _se_old[["Day"]].copy()
            for _name in _se_names:
                _se_new[_name] = _se_old[_name] if _name in _se_old_cols else 1
            _se_new.to_csv(SE_PREF_FILE, index=False)
            st.session_state["se_pref_df"] = _se_new.copy()
            _ce_old = pd.read_csv(CE_PREF_FILE)
            _ce_old_cols = [c for c in _ce_old.columns if c not in ("Company", "Day")]
            _ce_new = _ce_old[["Company", "Day"]].copy()
            for _name in _ce_names:
                _ce_new[_name] = _ce_old[_name] if _name in _ce_old_cols else 1
            _ce_new.to_csv(CE_PREF_FILE, index=False)
            st.session_state["ce_pref_df"] = _ce_new.copy()
            st.session_state["pref_version"] = st.session_state.get("pref_version", 0) + 1

            st.session_state["sanity_passed"] = False
            return True

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
    _inc_df = st.session_state["income_df"]
    edited_inc = st.data_editor(
        _inc_df,
        num_rows="dynamic",
        column_config={
            "day": st.column_config.NumberColumn(t["col_day"], disabled=True, help=t["help_day"]),
            "good_life": st.column_config.NumberColumn(t["col_gl_income"], min_value=0, step=1),
            "tianyuan": st.column_config.NumberColumn(t["col_ty_income"], min_value=0, step=1),
        },
        width="stretch",
        height=(len(_inc_df) + 2) * 36 + 3,
        key=_inc_editor_key,
    )
    st.session_state["_inc_edited_df"] = edited_inc

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
            
            # Sync SE and CE preference files to new day list
            _new_days = _saved_inc["day"].tolist()
            _se_old = pd.read_csv(SE_PREF_FILE)
            _se_cols = [c for c in _se_old.columns if c != "Day"]
            _se_lookup = {int(r["Day"]): r for _, r in _se_old.iterrows()}
            _se_rows = []
            for _day in _new_days:
                _ex = _se_lookup.get(int(_day))
                _row = {"Day": int(_day)}
                for _col in _se_cols:
                    _row[_col] = int(_ex[_col]) if _ex is not None else 1
                _se_rows.append(_row)
            _se_new = pd.DataFrame(_se_rows)[["Day"] + _se_cols]
            _se_new.to_csv(SE_PREF_FILE, index=False)
            st.session_state["se_pref_df"] = _se_new.copy()
            _ce_old = pd.read_csv(CE_PREF_FILE)
            _ce_cols = [c for c in _ce_old.columns if c not in ("Company", "Day")]
            _companies_order = list(dict.fromkeys(_ce_old["Company"].tolist()))
            _ce_lookup = {(str(r["Company"]), int(r["Day"])): r for _, r in _ce_old.iterrows()}
            _ce_rows = []
            for _company in _companies_order:
                for _day in _new_days:
                    _ex = _ce_lookup.get((_company, int(_day)))
                    _row = {"Company": _company, "Day": int(_day)}
                    for _col in _ce_cols:
                        _row[_col] = int(_ex[_col]) if _ex is not None else 1
                    _ce_rows.append(_row)
            _ce_new = pd.DataFrame(_ce_rows)[["Company", "Day"] + _ce_cols]
            _ce_new.to_csv(CE_PREF_FILE, index=False)
            st.session_state["ce_pref_df"] = _ce_new.copy()
            st.session_state["sanity_passed"] = False
            return True

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

def _int_to_bool_df(df: pd.DataFrame, skip_cols: set) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col in skip_cols:
            continue
        out[col] = out[col].apply(lambda v: bool(int(v)) if pd.notna(v) else False)
    return out

def _bool_to_int_df(df: pd.DataFrame, skip_cols: set) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col in skip_cols:
            continue
        out[col] = out[col].apply(lambda v: 1 if v else 0).astype("Int64")
    return out

with tab_pref:
    st.header(t["header_pref"])
    st.caption(t["caption_pref"])
    _pv = st.session_state.get("pref_version", 0)

    # --- SE Availability ---
    st.subheader(t["header_se_pref"])
    st.caption(t["caption_se_pref"])
    _se_pref_int = st.session_state["se_pref_df"]
    _se_worker_cols = [c for c in _se_pref_int.columns if c != "Day"]
    _se_bool_df = _int_to_bool_df(_se_pref_int, {"Day"})
    _se_col_cfg: dict = {"Day": st.column_config.NumberColumn(t["col_day"], disabled=True)}
    for _col in _se_worker_cols:
        _se_col_cfg[_col] = st.column_config.CheckboxColumn(_col, default=True)
    _se_pref_key = f"se_pref_editor_{_pv}_{lang}"
    edited_se_pref = st.data_editor(
        _se_bool_df, num_rows="fixed", column_config=_se_col_cfg,
        use_container_width=True, height=(len(_se_bool_df) + 1) * 36 + 3,
        key=_se_pref_key, hide_index=True,
    )
    st.session_state["_se_pref_edited_df"] = edited_se_pref

    # --- CE Availability ---
    # Exclusive workers: show only their company's table. Flexible workers: one shared table.
    st.subheader(t["header_ce_pref"])
    st.caption(t["caption_ce_pref"])
    _ce_pref_int = st.session_state["ce_pref_df"]
    _ce_all_worker_cols = [c for c in _ce_pref_int.columns if c not in ("Company", "Day")]
    _day_col_cfg: dict = {"Day": st.column_config.NumberColumn(t["col_day"], disabled=True)}

    # Classify CE workers from employee data
    _emp_ce = st.session_state["employees_df"]
    _emp_ce = _emp_ce[_emp_ce["type"] == "Company-Employed"]
    _gl_excl_cols: list[str] = []
    _ty_excl_cols: list[str] = []
    _flex_cols: list[str] = []
    for _, _r in _emp_ce.iterrows():
        _n = str(_r["name"]).strip()
        if _n not in _ce_all_worker_cols:
            continue
        _excl = str(_r.get("exclusive_company", "")).strip().lower()
        if "good" in _excl:
            _gl_excl_cols.append(_n)
        elif "tian" in _excl or "yuan" in _excl:
            _ty_excl_cols.append(_n)
        else:
            _flex_cols.append(_n)

    edited_ce_gl = None
    if _gl_excl_cols:
        st.markdown(f"**{t['company_gl']}**")
        _ce_gl_int = _ce_pref_int[_ce_pref_int["Company"] == "good_life"][["Day"] + _gl_excl_cols].reset_index(drop=True)
        _ce_gl_bool = _int_to_bool_df(_ce_gl_int, {"Day"})
        _ce_gl_cfg = {**_day_col_cfg, **{c: st.column_config.CheckboxColumn(c, default=True) for c in _gl_excl_cols}}
        _ce_gl_key = f"ce_gl_pref_editor_{_pv}_{lang}"
        edited_ce_gl = st.data_editor(
            _ce_gl_bool, num_rows="fixed", column_config=_ce_gl_cfg,
            use_container_width=True, height=(len(_ce_gl_bool) + 1) * 36 + 3,
            key=_ce_gl_key, hide_index=True,
        )
        st.session_state["_ce_gl_pref_edited_df"] = edited_ce_gl

    edited_ce_ty = None
    if _ty_excl_cols:
        st.markdown(f"**{t['company_ty']}**")
        _ce_ty_int = _ce_pref_int[_ce_pref_int["Company"] == "tianyuan"][["Day"] + _ty_excl_cols].reset_index(drop=True)
        _ce_ty_bool = _int_to_bool_df(_ce_ty_int, {"Day"})
        _ce_ty_cfg = {**_day_col_cfg, **{c: st.column_config.CheckboxColumn(c, default=True) for c in _ty_excl_cols}}
        _ce_ty_key = f"ce_ty_pref_editor_{_pv}_{lang}"
        edited_ce_ty = st.data_editor(
            _ce_ty_bool, num_rows="fixed", column_config=_ce_ty_cfg,
            use_container_width=True, height=(len(_ce_ty_bool) + 1) * 36 + 3,
            key=_ce_ty_key, hide_index=True,
        )
        st.session_state["_ce_ty_pref_edited_df"] = edited_ce_ty

    edited_ce_flex = None
    if _flex_cols:
        st.markdown(f"**{t['ce_flexible_label']}**")
        _ce_flex_int = _ce_pref_int[_ce_pref_int["Company"] == "good_life"][["Day"] + _flex_cols].reset_index(drop=True)
        _ce_flex_bool = _int_to_bool_df(_ce_flex_int, {"Day"})
        _ce_flex_cfg = {**_day_col_cfg, **{c: st.column_config.CheckboxColumn(c, default=True) for c in _flex_cols}}
        _ce_flex_key = f"ce_flex_pref_editor_{_pv}_{lang}"
        edited_ce_flex = st.data_editor(
            _ce_flex_bool, num_rows="fixed", column_config=_ce_flex_cfg,
            use_container_width=True, height=(len(_ce_flex_bool) + 1) * 36 + 3,
            key=_ce_flex_key, hide_index=True,
        )
        st.session_state["_ce_flex_pref_edited_df"] = edited_ce_flex

    def do_save_pref(se_df, ce_gl_df, ce_ty_df, ce_flex_df):
        try:
            saved_se = _bool_to_int_df(se_df, {"Day"})
        except (KeyError, ValueError) as _exc:
            st.error(t["err_pref_parse"].format(e=_exc))
            return False
        gl_int = _bool_to_int_df(ce_gl_df, {"Day"}) if ce_gl_df is not None else None
        ty_int = _bool_to_int_df(ce_ty_df, {"Day"}) if ce_ty_df is not None else None
        flex_int = _bool_to_int_df(ce_flex_df, {"Day"}) if ce_flex_df is not None else None
        gl_lkp = {int(r["Day"]): r for _, r in gl_int.iterrows()} if gl_int is not None else {}
        ty_lkp = {int(r["Day"]): r for _, r in ty_int.iterrows()} if ty_int is not None else {}
        flex_lkp = {int(r["Day"]): r for _, r in flex_int.iterrows()} if flex_int is not None else {}
        _ce_old = st.session_state["ce_pref_df"]
        _days_ce = sorted(set(int(d) for d in _ce_old["Day"].tolist()))
        new_rows = []
        for _company in ["good_life", "tianyuan"]:
            for _day in _days_ce:
                row: dict = {"Company": _company, "Day": _day}
                for _col in _ce_all_worker_cols:
                    if _col in _gl_excl_cols:
                        row[_col] = int(gl_lkp[_day][_col]) if _company == "good_life" and _day in gl_lkp else 0
                    elif _col in _ty_excl_cols:
                        row[_col] = int(ty_lkp[_day][_col]) if _company == "tianyuan" and _day in ty_lkp else 0
                    else:
                        row[_col] = int(flex_lkp[_day][_col]) if _day in flex_lkp else 0
                new_rows.append(row)
        saved_ce = pd.DataFrame(new_rows)[["Company", "Day"] + _ce_all_worker_cols]
        saved_se.to_csv(SE_PREF_FILE, index=False)
        saved_ce.to_csv(CE_PREF_FILE, index=False)
        st.session_state["se_pref_df"] = saved_se.copy()
        st.session_state["ce_pref_df"] = saved_ce.copy()
        st.session_state["sanity_passed"] = False
        return True

    if st.button(t["btn_save_pref"], use_container_width=True, type="primary"):
        if do_save_pref(edited_se_pref, edited_ce_gl, edited_ce_ty, edited_ce_flex):
            st.success(t["msg_pref_saved"])
            st.session_state["pref_version"] = st.session_state.get("pref_version", 0) + 1
            st.rerun()

with tab_generate:
    st.header(t["header_gen"])
    st.subheader(t["summary_header"])

    if "sanity_passed" not in st.session_state: st.session_state["sanity_passed"] = False
    if "sanity_errors" not in st.session_state: st.session_state["sanity_errors"] = []
    if "last_output_path" not in st.session_state: st.session_state["last_output_path"] = None
    if "last_log" not in st.session_state: st.session_state["last_log"] = ""

    # Salary bound settings
    st.caption(t["caption_salary_bounds"])
    col_smin, col_se, col_ce, col_div = st.columns(4)
    # GUI-facing default per-day caps (intentionally independent of the
    # src.config fallbacks used by the CLI/solver/tests).
    _DEFAULT_SE_MIN = 100
    _DEFAULT_SE_MAX = 168
    _DEFAULT_CE_MAX = 420
    _DEFAULT_DIV_PCT = 50
    with col_se:
        se_max = st.number_input(
            t["label_se_max"], min_value=60, max_value=500,
            value=st.session_state.get("se_max_per_day", _DEFAULT_SE_MAX),
            step=2, key="input_se_max",
            help=t["help_se_max"])
        st.session_state["se_max_per_day"] = se_max
    with col_smin:
        # Concentrate knob: higher floor -> fewer, higher-paid SE days. Capped at
        # se_max so a_min never exceeds a_max (which would be infeasible).
        se_min = st.number_input(
            t["label_se_min"], min_value=60, max_value=se_max,
            value=min(st.session_state.get("se_min_per_day", _DEFAULT_SE_MIN), se_max),
            step=2, key="input_se_min",
            help=t["help_se_min"])
        st.session_state["se_min_per_day"] = se_min
    with col_ce:
        ce_max = st.number_input(
            t["label_ce_max"], min_value=0, max_value=1000,
            value=st.session_state.get("ce_max_per_day", _DEFAULT_CE_MAX),
            step=5, key="input_ce_max",
            help=t["help_ce_max"])
        st.session_state["ce_max_per_day"] = ce_max
    with col_div:
        div_pct = st.number_input(
            t["label_variation"], min_value=0, max_value=50,
            value=st.session_state.get("div_pct", _DEFAULT_DIV_PCT),
            step=1, key="input_div_pct",
            help=t["help_variation"])
        st.session_state["div_pct"] = div_pct

    # Scatter (randomized solver objective) — opt-in. OFF = today's spread.
    col_sc_on, col_sc_seed, _col_sc_pad = st.columns([1, 1, 2])
    with col_sc_on:
        scatter_on = st.checkbox(
            t["label_scatter"], value=st.session_state.get("scatter_on", True),
            key="input_scatter_on", help=t["help_scatter"])
        st.session_state["scatter_on"] = scatter_on
    with col_sc_seed:
        scatter_seed_val = st.number_input(
            t["label_scatter_seed"], min_value=0, max_value=999999,
            value=st.session_state.get("scatter_seed", 0),
            step=1, key="input_scatter_seed", disabled=not scatter_on,
            help=t["help_scatter_seed"])
        st.session_state["scatter_seed"] = scatter_seed_val
    scatter_seed = scatter_seed_val if scatter_on else None

    # Status indicator
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
        label_sanity = t["btn_run_sanity"]
        if st.button(label_sanity, use_container_width=True, key="btn_run_sanity_check"):
            _errors = run_sanity_check(
                st.session_state["employees_df"], st.session_state["se_pref_df"],
                st.session_state["ce_pref_df"], st.session_state["income_df"],
                lang=lang,
                se_max_per_day=se_max, ce_max_per_day=ce_max)
            st.session_state["sanity_errors"] = _errors
            st.session_state["sanity_passed"] = (len(_errors) == 0)
            st.rerun()

    with col_btn2:
        label_gen = str(t["btn_generate"])
        is_ready = st.session_state.get("sanity_passed", False)

        if st.button(label_gen, disabled=not is_ready, use_container_width=True, type="primary", key="btn_trigger_generate"):
            from src.loaders.data_loader import load_all
            from src.engine.feasibility import check_se_feasibility
            from src.engine.exact_solver import solve_exact
            from src.reports.excel_writer import generate_report, generate_simplified_report
            from src.config import SE_SALARY_UNIT

            _log_buffer = StringIO()
            _handler = logging.StreamHandler(_log_buffer)
            _handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s — %(message)s", "%H:%M:%S"))
            _root = logging.getLogger()
            _root.addHandler(_handler)
            _prior_level = _root.level
            _root.setLevel(logging.INFO)

            _status = st.status(t["spinner_solving"], expanded=False)

            try:
                _se, _ce, _companies = load_all()
                check_se_feasibility(_se, _companies)
                _report = solve_exact(_se, _ce, _companies,
                                      se_max_per_day=se_max, ce_max_per_day=ce_max,
                                      se_min_per_day=se_min, scatter_seed=scatter_seed)

                # Post-tuning: diversify duplicate salaries within a +/-% band,
                # then re-run checks. Revert to the solved schedule if anything
                # regressed (the guarantees the solver hit must be preserved).
                _reverted = False
                if div_pct > 0:
                    from src.engine.diversify import (
                        diversify_schedule, verify_schedule,
                        snapshot_schedules, restore_schedules,
                    )
                    _snap = snapshot_schedules(_se, _ce, _companies)
                    diversify_schedule(_se, _ce, _companies, pct=div_pct / 100,
                                       seed=0, se_max=se_max, ce_max=ce_max,
                                       se_min=se_min)
                    _vr = verify_schedule(_se, _ce, _companies,
                                          se_max=se_max, ce_max=ce_max,
                                          se_min=se_min)
                    if _vr.regressed_from(_report.deviations, _report.shortfalls):
                        restore_schedules(_snap, _se, _ce, _companies)
                        logging.getLogger("gui").warning(
                            "Post-tuning checks regressed — reverted to solved schedule.")
                        _reverted = True
                    else:
                        logging.getLogger("gui").info(
                            "Post-tuning diversification applied — checks passed.")

                _deviations = [
                    t["deviation_msg"].format(
                        company=_cn, day=_dn,
                        formula=_companies[_cn].get_day(_dn).cleaned_income - _dev,
                        cleaned=_companies[_cn].get_day(_dn).cleaned_income, dev=abs(_dev))
                    for _cn, _dn, _dev in _report.deviations
                ]
                _se_by_name = {w.name: w for w in _se}
                _shortfalls = [
                    t["shortfall_msg"].format(
                        name=_nm, target=_se_by_name[_nm].salary,
                        actual=_se_by_name[_nm].actual_monthly_salary, gap=_gap)
                    for _nm, _gap in _report.shortfalls
                ]

                _ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                _last_path = os.path.join(OUTPUT_DIR, f"report_{_ts}.xlsx")
                _last_simple_path = os.path.join(OUTPUT_DIR, f"report_{_ts}_simple.xlsx")
                generate_report(_se, _ce, _companies, seed=0, output_path=_last_path)
                generate_simplified_report(_se, _ce, _companies, output_path=_last_simple_path)
                _status.update(state="complete", expanded=False)

                if _reverted:
                    st.warning(t["warn_tuning_reverted"])

                if _report.perfect:
                    st.success(t["msg_gen_success"].format(p=_last_path))
                else:
                    st.warning(t["warn_solver_residual"].format(p=_last_path))
                    if _shortfalls:
                        st.warning(t["warn_shortfall"].format(n=len(_shortfalls)) + "\n".join(f"• {s}" for s in _shortfalls))
                    if _deviations:
                        st.warning(t["warn_deviation"].format(n=len(_deviations), u=SE_SALARY_UNIT) + "\n".join(f"• {d}" for d in _deviations))

                st.session_state["last_output_path"] = _last_path
                st.session_state["last_simple_path"] = _last_simple_path
                st.session_state["last_log"] = _log_buffer.getvalue()
            except Exception as _exc:
                _status.update(state="error")
                st.error(t["err_pipeline"].format(e=_exc))
                st.session_state["last_log"] = _log_buffer.getvalue()
            finally:
                _root.removeHandler(_handler); _root.setLevel(_prior_level)

    if st.session_state.get("last_log"): 
        with st.expander(t["label_log"], expanded=True):
            st.text_area(t["label_log"], st.session_state["last_log"], height=300, label_visibility="collapsed")
    
    _lp = st.session_state.get("last_output_path")
    _lsp = st.session_state.get("last_simple_path")
    _mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    _dl_col_full, _dl_col_simple = st.columns(2)
    with _dl_col_full:
        if _lp and os.path.exists(_lp):
            with open(_lp, "rb") as _f:
                st.download_button(label=t["btn_download_full"], data=_f.read(), file_name=os.path.basename(_lp), mime=_mime, use_container_width=True, key="dl_full")
    with _dl_col_simple:
        if _lsp and os.path.exists(_lsp):
            with open(_lsp, "rb") as _f:
                st.download_button(label=t["btn_download_simple"], data=_f.read(), file_name=os.path.basename(_lsp), mime=_mime, use_container_width=True, key="dl_simple")
