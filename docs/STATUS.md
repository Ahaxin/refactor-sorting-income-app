# Project Status — 2026-05-16

## What Was Built (This Session)

A Streamlit GUI (`gui.py`) for editing input data and running the salary planning pipeline.
All 9 tasks from the implementation plan are complete.

### Completed Tasks

| # | Task | Commit |
|---|---|---|
| 1 | Add `exclusive_company` column to `employee_data.csv` | `1d488aa` |
| 2 | Fold `exclusive_company` into `_load_employees()`; remove `preferences.csv` dependency | `befaf4a` |
| 3 | Dynamic output filename: `report_seed{N}_{YYYYMMDD_HHMMSS}.xlsx` | `48d8ca8` |
| 4 | `src/sanity.py` — pure-Python sanity check utility + 7 unit tests | `89ff6af` |
| 5 | Scaffold `gui.py` with 4-tab Streamlit structure | `af57524` |
| 6–8 | Employees, Income, Preference Matrix tabs with data editors + save guards | `a0c40e6`, `b0eeecf` |
| 9 | Generate tab: seed input, sanity check, pipeline run, log display, download | `a83ef18`, `8133871` |

### Files Added / Modified

| File | Change |
|---|---|
| `gui.py` | **New** — Streamlit app entry point |
| `src/sanity.py` | **New** — `run_sanity_check(employees_df, pref_df)` |
| `data/employee_data.csv` | Added `exclusive_company` column |
| `src/config.py` | Removed `PREF_ALT_FILE` constant |
| `src/loaders/data_loader.py` | Reads `exclusive_company` from employee CSV; removed `_load_exclusive_companies()` |
| `src/reports/excel_writer.py` | Added `output_path: str | None` parameter to `generate_report()` |
| `src/models/employee.py` | Updated stale comments |
| `main.py` | Builds timestamped output filename |
| `requirements.txt` | Added `streamlit>=1.35` |
| `tests/test_data_loader_excl.py` | **New** — 2 tests for exclusive_company loading |
| `tests/test_excel_output_path.py` | **New** — 2 tests for dynamic output path |
| `tests/test_sanity.py` | **New** — 7 tests for sanity check |

### Test Status

**46 tests — all passing.**

---

## Known Issues (Non-Blocking)

### Pyright False Positives

Pyright reports `reportMissingImports` for `streamlit` and `src.*` packages. This is a configuration gap — no `pyrightconfig.json` points Pyright at the virtual environment. The app runs correctly; these are lint-only warnings.

**Fix when needed:** Create `pyrightconfig.json` at project root:
```json
{
  "venvPath": ".",
  "venv": ".venv",
  "pythonVersion": "3.11"
}
```

### GUI Known Limitations

1. **No undo after Save** — Streamlit has no undo; users should keep backups of CSVs before editing.
2. **Preference matrix Company column shows internal keys** (`good_life` / `tianyuan`) instead of display names.
3. **No CSV caching** — all three CSVs are re-read on every Streamlit rerun (imperceptible for current file sizes).
4. **`preferred_company` field on Employee model is loaded but never read** by any engine code — dead field, safe to remove in a future cleanup.

---

## What To Do Next

### Immediate (before sharing with others)

1. **Run `superpowers:finishing-a-development-branch`** — decide whether to merge to main, create a PR, or squash commits.
2. **Manual GUI smoke test** — run `streamlit run gui.py`, exercise all tabs end-to-end with real data, verify the Excel output.
3. **Add `pyrightconfig.json`** — eliminates the false-positive import warnings.

### Follow-Up Enhancements (not in current scope)

- Display `good_life` / `tianyuan` as "Good Life" / "Tianyuan" in the Preference Matrix Company column.
- Cache CSV reads with `@st.cache_data` for larger datasets.
- Add `data_version` counter in session state to auto-invalidate sanity check when data is saved.
- Remove dead `preferred_company` field from `src/models/employee.py`.

---

## How To Run

```bash
# Install dependencies (once)
pip install -r requirements.txt

# Launch the GUI
streamlit run gui.py

# Or run the CLI directly
python main.py --seed 42
```
