# Monthly Work/Salary Plan Generator

A Python application that generates optimal monthly work schedules and salary allocations for self-employed (SE) and company-employed (CE) workers, ensuring all constraints are met and the profit-sharing formula is satisfied exactly.

## Overview

The system allocates work shifts and salaries across multiple companies and days, balancing:
- **SE workers**: Must hit exact monthly salary targets, earning 40% of company daily income
- **CE workers**: Absorb residual income after SE allocation, bounded by individual monthly caps
- **Daily constraints**: Each day's budget is divided among assigned workers

## Algorithm: SE-First Pipeline

The solution uses a four-phase, deterministic pipeline:

### Phase 1: Feasibility Check
Validates that the system is mathematically solvable:
- Total SE targets ≤ 40% of total available income
- Logs warning if infeasible, continues with fallback

### Phase 2: SE Scheduling
Assigns SE workers to company-day slots:
1. **Compute day envelopes** per worker:
   - `min_days = ceil(salary / PREDEFINED_DAILY)` — minimum working days needed
   - `max_days = floor(salary / MIN_SALARY)` — maximum feasible working days
   - `target_days = ceil(salary / PREDEFINED_DAILY)` — preferred number of days

2. **Main loop**: For each day, select n workers (by preference and urgency) and assign them
3. **Fill under-scheduled**: Add workers below min_days to available slots
4. **Fill budget-deficient**: For workers whose scheduled days can't cover their target (due to co-worker minimums), add extra eligible slots with sufficient budget

### Phase 3: SE Salary Solver
Two-stage algorithm to assign exact daily SE salaries:

**Stage A: Sinkhorn Biproportional Fitting**
- Iteratively normalize row sums (each SE worker) and column sums (each day)
- Converges to a solution respecting both monthly targets and daily budgets
- Continuous values in [MIN_SALARY, MAX_SALARY]

**Stage B: Repair (Rounding + Adjustment)**
- **Phase A**: Round to even integers; reduce any column sum that exceeds se_day_target
- **Phase B**: Fix monthly row sums while respecting column upper bounds
  - Direct add: Increase worker's salary on an uncapped day
  - Swap: When direct add blocked, reduce a co-worker (if >MIN_SALARY) on the same day to make room
  - Swap allows salary movement within column-capped days while preserving column sums

### Phase 4: CE Residual Distribution
For each day (sorted by cleaned income descending):
- Compute CE residual: `I_clean - round(SE_total / 0.4)`
- Distribute to eligible CE workers, respecting monthly caps
- Uses random shuffling for deterministic variability

## Key Constants

```python
# Salary bounds (per day)
MIN_SALARY = 120           # Minimum daily earnings
MAX_SALARY = 400           # Maximum daily earnings
SE_SALARY_UNIT = 2         # SE salary granularity (even integers)
CE_SALARY_UNIT = 5         # CE salary granularity (multiples of 5)

# Scheduling
PREDEFINED_DAILY = 180     # Reference daily rate for min_days calculation

# Profit-sharing ratio
RATIO = 0.4                # SE gets 40% of company income

# Solver
SOLVER_MAX_ITER = 3000     # Max iterations for biproportional fitting
SOLVER_TOL = 0.1           # Convergence tolerance for Sinkhorn
```

## Invariants Maintained

1. **Row sum equality**: Each SE worker earns exactly their monthly target
2. **Column upper bound**: `SE_total[day] ≤ SE_day_target[day]` (ensures non-negative CE residual)
3. **Formula exactness**: `round(SE_total[day] / 0.4) + CE_total[day] = cleaned_income[day]`
4. **Salary bounds**: All per-day salaries in [MIN_SALARY, MAX_SALARY] (multiples of SALARY_UNIT)
5. **CE caps**: Each CE worker earns ≤ their monthly cap

## Running Tests

### All Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run all tests with coverage report
pytest tests/ --cov=src --cov-report=html
```

### Test Suites

```bash
# SE Scheduler tests (min_days, fill, preference respect, determinism)
pytest tests/test_se_scheduler.py -v

# Salary Solver tests (monthly targets, daily bounds, salary constraints)
pytest tests/test_salary_solver.py -v

# CE Planner tests (residual distribution, cap respect)
pytest tests/test_ce_planner.py -v

# Full pipeline integration tests (end-to-end consistency)
pytest tests/test_integration.py -v

# Config and model tests
pytest tests/test_config_models.py -v

# Feasibility check tests
pytest tests/test_feasibility.py -v
```

### Test List

#### SE Scheduler Tests (tests/test_se_scheduler.py)
- `test_se_workers_assigned_enough_days` — Verify each SE worker gets ≥ min_days
- `test_no_double_booking` — No worker double-booked on same day
- `test_workers_respect_preferences` — Workers only assigned where preference > 0
- `test_schedule_is_deterministic` — Same seed produces identical schedule
- `test_min_days_computed_from_predefined_daily` — min_days = ceil(salary/PREDEFINED_DAILY), not ceil(salary/MAX_SALARY)
- `test_fill_budget_deficient_adds_extra_slot` — Workers with insufficient achievable salary get extra slots

#### Salary Solver Tests (tests/test_salary_solver.py)
- `test_solver_hits_exact_monthly_targets` — All SE workers earn exactly their monthly target
- `test_solver_satisfies_daily_column_sums` — Daily SE totals = SE_day_target
- `test_solver_individual_salaries_in_bounds` — All salaries in [MIN_SALARY, MAX_SALARY], multiples of 2
- `test_solver_deterministic` — Same seed produces identical salary allocation
- `test_repair_swap_lets_worker_hit_target_when_all_days_at_column_cap` — Swap mechanism allows salary movement on capped days

#### CE Planner Tests (tests/test_ce_planner.py)
- `test_ce_distribution_is_non_negative` — All CE salaries ≥ 0
- `test_ce_respects_monthly_caps` — No CE worker exceeds monthly cap
- `test_ce_distribution_deterministic` — Same seed produces identical distribution
- `test_ce_salaries_are_multiples_of_unit` — All CE salaries are multiples of CE_SALARY_UNIT

#### Integration Tests (tests/test_integration.py)
- `test_full_pipeline_hits_se_targets` — End-to-end: all SE workers hit exact targets
- `test_full_pipeline_satisfies_formula` — Formula exactness verified on all days
- `test_full_pipeline_deterministic` — Full pipeline is deterministic with fixed seed
- `test_full_pipeline_no_negative_salaries` — No negative salaries anywhere
- `test_full_pipeline_infeasible_case_logs_warning` — Gracefully handles infeasible scenarios
- `test_real_data_scenario` — Full pipeline with real employee and company data

#### Config and Model Tests (tests/test_config_models.py)
- Model instantiation and property tests
- Config constant tests

#### Feasibility Tests (tests/test_feasibility.py)
- `test_feasible_scenario_passes` — Valid scenario passes feasibility check
- `test_infeasible_scenario_fails` — Invalid scenario fails gracefully

**Total: 46 tests covering all phases, edge cases, and GUI sanity checks**

## Streamlit GUI

A browser-based GUI lets you edit input data and generate reports without touching the command line.

### Installation

```bash
pip install -r requirements.txt
```

### Launch

```bash
streamlit run gui.py
```

Streamlit opens a browser tab at `http://localhost:8501`.

### Tabs

| Tab | Purpose |
|-----|---------|
| **Employees** | Add, remove, or edit workers — name, type (SE/CE), monthly salary/cap, exclusive company |
| **Income** | Edit the 30-day income table for Good Life and Tianyuan |
| **Preference Matrix** | Set each worker's availability (0 = unavailable, 1 = available, 2 = preferred) per company per day |
| **Generate** | Run sanity check and produce the Excel report |

### Workflow

1. Edit data in the **Employees**, **Income**, and **Preference Matrix** tabs — click **Save** in each tab after making changes.
2. Switch to **Generate** and click **Run Sanity Check**. Errors are shown as a bulleted list; fix them and re-check.
3. Once sanity passes, optionally change the **Seed** field (pre-filled with a random integer), then click **Generate**.
4. Download the report via the **Download Report** button that appears on success.

### Output Filename

Reports are written to `output/` with the format:

```
report_seed{seed}_{YYYYMMDD_HHMMSS}.xlsx
```

---

## Running the Application (CLI)

### Basic Usage

```bash
# Generate plan with auto-generated seed
python main.py

# Generate plan with specific seed (for reproducibility)
python main.py --seed 42

# Or set seed via environment variable
$env:SALARY_SEED=42; python main.py
```

### Output

- **Console**: Detailed logs showing each phase (schedule summary, salary results, formula verification)
- **File**: `output/report_seed{seed}_{YYYYMMDD_HHMMSS}.xlsx` — Excel report with monthly and daily breakdowns

### Input Data

Place CSV files in `data/` directory:

| File | Columns | Notes |
|------|---------|-------|
| `employee_data.csv` | `name`, `type`, `salary`, `exclusive_company` | `type`: `Self-Employed` or `Company-Employed`; `exclusive_company`: blank, `Good Life`, or `Tianyuan` |
| `income_data.csv` | `day`, `good_life`, `tianyuan` | 30 rows, one per working day |
| `updated_preference.csv` | `Company`, `Day`, one column per employee | Values: 0 (unavailable), 1 (available), 2 (preferred) |

## Example Run

```bash
$ python main.py --seed 42
19:46:21  INFO  Monthly Work/Salary Plan Generator — starting
19:46:21  INFO  Random seed: 42 (from --seed)
19:46:21  INFO  SE SCHEDULING PHASE
19:46:21  INFO    Jenny        [OK] days=10
19:46:21  INFO    Yang         [OK] days=7
...
19:46:21  INFO  SE SALARY SOLVER
19:46:21  INFO    Jenny        target= 1800 actual= 1800 [OK]
19:46:21  INFO    Yang         target= 1200 actual= 1200 [OK]
...
19:46:21  INFO  PER-DAY COLUMN BOUND CHECK (SE_total <= SE_day_target):
19:46:21  INFO    All days satisfy SE_total <= SE_day_target.
19:46:21  INFO  Done. Output written to: output/report.xlsx
```

## Architecture

```
gui.py                           # Streamlit GUI entry point
main.py                          # CLI entry point
src/
├── config.py                    # Constants and configuration
├── sanity.py                    # Input validation (used by GUI and tests)
├── models/
│   ├── employee.py             # SE and CE employee classes
│   └── company.py              # Company and DayLedger models
├── loaders/
│   └── data_loader.py          # CSV file loading and validation
├── engine/
│   ├── feasibility.py          # Phase 1: Feasibility checking
│   ├── se_scheduler.py         # Phase 2: SE scheduling (min_days, fill functions)
│   ├── salary_solver.py        # Phase 3: SE salary solving (Sinkhorn + repair)
│   └── ce_planner.py           # Phase 4: CE residual distribution
└── reports/
    └── excel_writer.py         # Excel report generation

tests/
├── test_config_models.py       # Model and config tests
├── test_feasibility.py         # Feasibility check tests
├── test_se_scheduler.py        # Scheduler tests (6+ tests)
├── test_salary_solver.py       # Solver tests (5+ tests)
├── test_ce_planner.py          # CE planner tests (4+ tests)
├── test_integration.py         # Full pipeline integration tests (8+ tests)
├── test_sanity.py              # Sanity check tests (7 tests)
├── test_data_loader_excl.py    # exclusive_company loading tests (2 tests)
└── test_excel_output_path.py   # Dynamic output path tests (2 tests)
```

## Performance

- **Typical run**: < 1 second (with seed=42 on real data)
- **Bottleneck**: Sinkhorn iteration (3000 max iterations × O(workers × days) per iteration)
- **Memory**: O(workers × days) for matrix storage

## Implementation Highlights

### Determinism
All randomness goes through a named `rng` instance passed through the pipeline. Tests verify determinism with fixed seeds.

### Numerical Stability
- Uses biproportional fitting (Sinkhorn) for well-conditioned matrix operations
- Clamps values to [MIN_SALARY, MAX_SALARY] after rounding to prevent divergence
- Iterates up to max_iter to allow convergence on tight problems

### Solver Robustness
- **Phase A (Column bounds)**: Prioritizes overshooting columns, reduces largest values first
- **Phase B (Row sums)**: Respects column bounds while fixing monthly targets
  - Direct add: Simple case when day has headroom
  - Swap: Handles column-capped days by moving salary between co-workers
- Logs warnings for max-iteration hits and negative salaries (validation)

### Budget-Deficient Scheduling
Detects when a worker's scheduled days can't cover their target due to co-worker constraints, then adds extra eligible slots. This ensures the solver has enough budget to work with for all workers.

## Known Limitations

1. **Infeasible scenarios**: If total SE targets > 40% of income, the system logs a warning but continues (may produce shortfalls)
2. **Integer constraints**: Rounding to even integers (SE) and multiples of 5 (CE) can introduce ±2-5 unit discrepancies
3. **Swap cycles**: In rare cases with all column-capped days and no uncapped recovery days, the swap mechanism may cycle without converging; limits to 3000 iterations and logs warning

## Testing Methodology

Tests use **Test-Driven Development (TDD)** with three-phase cycles:

1. **RED**: Write failing test
2. **GREEN**: Implement minimal code to pass
3. **REFACTOR**: Clean up while keeping tests green

All tests are deterministic (use fixed seeds) and verify:
- Exact monthly targets are hit
- Column bounds are satisfied
- Formula exactness (SE/0.4 + CE = I_clean)
- No negative salaries
- Preference and availability constraints respected

## Troubleshooting

**Q: Why are there column bound violations in the log?**
A: The log now only reports true violations (SE_total > target). If you see "All days satisfy...", the system is correct. SE_total can be less than SE_day_target; CE absorbs the residual.

**Q: Worker has a shortfall (negative GAP)?**
A: This indicates the worker's scheduled days don't have enough budget. The scheduler's budget-deficient fill attempts to add extra days, but if no eligible slots exist, a shortfall may occur. Check if the worker has preferences for additional days.

**Q: How do I reproduce a specific allocation?**
A: Use `--seed <number>`. All randomness is seeded, so the same seed produces identical allocations.

## References

- **Sinkhorn Method**: Sinkhorn, R. (1967). "Diagonal Equivalence to Matrices with Prescribed Row and Column Sums"
- **Biproportional Fitting**: Used in statistical disclosure control and matrix balancing
- **Profit-Sharing Formula**: Based on company contribution model where SE captures 40% of daily income
