# GUI Design — Streamlit Data Editor & Report Generator

**Date:** 2026-05-15  
**Status:** Approved

---

## Overview

A single-file Streamlit GUI (`gui.py`) for editing the three input CSVs and running the monthly salary planning pipeline. Replaces the current CLI-only workflow.

---

## Architecture

- One new file: `gui.py` at the project root.
- No new directories.
- `requirements.txt` gains `streamlit>=1.35`.
- Run with: `streamlit run gui.py`
- The GUI reads/writes CSVs directly via pandas. For Generate, it imports and calls the pipeline functions from `src/` in-process.

```
refactor_sorting_income_app/
├── gui.py               ← new
├── main.py              (unchanged)
├── src/                 (data_loader.py updated)
├── data/
│   ├── employee_data.csv   (gains exclusive_company column)
│   ├── income_data.csv     (unchanged)
│   └── updated_preference.csv  (unchanged)
├── output/              (results land here)
└── requirements.txt     (+ streamlit)
```

---

## Input File Consolidation

`preferences.csv` is retired from active use. Its only live column (`exclusive_company`) is folded into `employee_data.csv` as an optional new column. `preferences.csv` stays on disk but is no longer read.

`employee_data.csv` columns after change:

| Column | Type | Notes |
|---|---|---|
| `name` | string | unique |
| `type` | string | `Self-Employed` or `Company-Employed` |
| `salary` | int | monthly target (SE) or cap (CE) |
| `exclusive_company` | string | blank, `Good Life`, or `Tianyuan` |

---

## Tab Structure

Four tabs: **Employees | Income | Preference Matrix | Generate**

### Employees Tab

- `st.data_editor` with columns:
  - `name` — free text
  - `type` — selectbox: `Self-Employed` / `Company-Employed`
  - `salary` — integer
  - `exclusive_company` — selectbox: blank / `Good Life` / `Tianyuan`
- Rows can be added or deleted.
- **Save** button writes back to `data/employee_data.csv`.

### Income Tab

- `st.data_editor` locked to 30 rows (no add/delete).
- Columns: `day` (read-only int), `good_life` (int), `tianyuan` (int).
- **Save** button writes back to `data/income_data.csv`.

### Preference Matrix Tab

- `st.data_editor` with 60 rows (2 companies × 30 days).
- `Company` and `Day` columns are read-only.
- Each employee column accepts integer values 0, 1, or 2.
- **Save** button writes back to `data/updated_preference.csv`.

### Generate Tab

- **Seed field** — text input pre-filled with a random integer on first load; user can edit freely.
- **Run Sanity Check** button — runs two checks:
  1. Employee completeness: all rows have a valid type (SE/CE), positive salary, no duplicate names.
  2. Preference coverage: every employee name in `employee_data.csv` appears as a column in `updated_preference.csv`.
- Sanity result displayed inline (success message or error details).
- **Generate** button — enabled only after sanity check passes. Runs the full pipeline in-process. Log output streamed to a `st.text_area`. On success, writes `output/report_seed{seed}_{YYYYMMDD}_{HHMMSS}.xlsx` and displays a download button.

---

## Code Changes to `src/`

### `src/loaders/data_loader.py`

- `_load_employees()` updated to read the new `exclusive_company` column from `employee_data.csv` and set `worker.exclusive_company` directly (replacing the old `_load_exclusive_companies()` function).
- `_load_exclusive_companies()` function removed.
- `PREF_ALT_FILE` constant in `src/config.py` removed.
- `load_all()` call updated to remove the `_load_exclusive_companies()` call.

### `src/config.py`

- Remove `PREF_ALT_FILE`.
- Update `OUTPUT_FILE` to support a dynamic filename (seed + datetime). The static `OUTPUT_FILE` constant is kept as a fallback default; callers pass the actual path.

### `src/reports/excel_writer.py`

- `generate_report()` already accepts `seed` parameter; no change needed to the function signature.
- Caller (`main.py` and `gui.py`) constructs the output filename as `output/report_seed{seed}_{YYYYMMDD}_{HHMMSS}.xlsx` and passes it in.

---

## Sanity Checks (detail)

| Check | Pass condition |
|---|---|
| Employee type valid | Each row has type exactly `Self-Employed` or `Company-Employed` |
| Salary positive | Each salary > 0 |
| No duplicate names | All names in `employee_data.csv` are unique |
| Preference coverage | Every name in `employee_data.csv` is a column in `updated_preference.csv` |

Failures are shown as a bulleted list of specific issues (not just a generic error).

---

## Out of Scope

- No authentication or multi-user support.
- No undo/redo beyond Streamlit's native data editor behaviour.
- No editing of `src/config.py` constants via the GUI.
- `preferences.csv` is not deleted — just no longer read.
