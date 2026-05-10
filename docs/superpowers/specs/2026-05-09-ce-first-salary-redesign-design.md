# CE-first Salary Redesign — Design Spec

**Date:** 2026-05-09
**Status:** Draft for implementation planning
**Supersedes:** the SE-first scheduling logic in `src/engine/scheduler.py` and `src/engine/salary_solver.py`.

## 1. Problem statement

The current monthly work / salary planner (Good Life + Tianyuan) treats SE workers' monthly targets as best-effort: when the available budget is short, the solver logs shortfall and moves on. The owner has decided that semantics must invert:

- **SE workers must receive their full monthly target** (no shortfall under any normally-shaped input).
- **CE workers may shortfall**: there is no fixed daily rate, no last-day rebalancing, and CE workers may be absent on some preference-eligible days.
- The per-day, per-company balance is now an **exact equality**, not a floor:
  `Σ SE_day = (I_clean − Σ CE_day) × 0.4`.

The old code rounded the daily SE budget down to a multiple of 5, which produced systematic per-day under-allocation. The new code holds the formula exactly and lets CE absorb the slack instead.

## 2. Goals & non-goals

### Goals

- Hit each SE worker's monthly target *exactly* whenever the input is mathematically feasible.
- Enforce `Σ SE_day = (I_clean − Σ CE_day) × 0.4` as a per-day equality.
- Distribute total CE budget across CE workers proportionally to their monthly cap, capped above by cap.
- Concentrate CE shifts on higher-income days (per the owner's intuition that CE workers should mostly work on busy days).
- Make every run **deterministic given a logged random seed** while still randomized run-to-run by default.

### Non-goals

- No change to the input data formats (`employee_data.csv`, `income_data.csv`, `updated_preference.csv`).
- No change to the 4-sheet Excel report's overall structure (only added Summary fields).
- No change to existing constraints not explicitly called out: Lin → Tianyuan, Zhong → Good Life exclusivity; one worker / one company per day; preference values `P ∈ {0, 1, 2}` with `P=2` preferred over `P=1`; day 31 processed iff income data includes it.
- No new external dependencies (PuLP, OR-Tools, etc.) in the first iteration. Solver stays pure-Python.

## 3. Confirmed business rules

| # | Rule | Notes |
|---|------|-------|
| R1 | `Σ SE_day = (I_clean − Σ CE_day) × 0.4` per (company, day), exactly | Per-day hard equality. No flooring. |
| R2 | Each SE worker's monthly actual = monthly target, exactly | No shortfall under feasible input. |
| R3 | Each CE worker's monthly actual ≤ monthly cap | CE shortfall allowed. |
| R4 | Individual SE daily salary ∈ `[120, 400]`, **even integer** | Replaces the old "multiple of 5" rule for SE only. Equivalent to `salary / 0.4 = multiple of 5`. |
| R5 | Individual CE daily salary is a multiple of 5, ≥ 0 | If 0, the worker did not work that day (no shift recorded). |
| R6 | `I_clean` is a multiple of 5 | Existing cleaning step is unchanged. |
| R7 | CE worker may skip eligible (P > 0) days | The algorithm chooses CE working days. |
| R8 | CE worker has no fixed daily rate | Daily amount varies; bounded above by per-day `MAX_CE_PER_DAY = 400`. |
| R9 | Lin → Tianyuan only; Zhong → Good Life only | Exclusivity preserved. |
| R10 | One worker / one company / day | No double-booking. |

### Math consistency (sanity check)

- `I_clean` and individual CE salaries are multiples of 5 ⇒ `Σ CE_day` is a multiple of 5 ⇒ `(I_clean − Σ CE_day)` is a multiple of 5 ⇒ `(I_clean − Σ CE_day) × 0.4` is a multiple of 2.
- A multiple-of-2 SE_day is splittable into individual SE salaries that are even integers in `[120, 400]` whenever `SE_day = 0` or `SE_day ≥ 120`.
- The aggregate identity follows from the per-day formula:
  `Σ_days SE_day = Σ targets ⇒ Σ_days CE_day = Σ I_clean − 2.5 × Σ targets`.

## 4. Architecture

### 4.1 Pipeline (six phases)

| Phase | Responsibility | Module | Status |
|------|----------------|--------|--------|
| 0 | Resolve and log random seed | `main.py` | Modified |
| 1 | Load CSVs, audit, pre-flight feasibility check | `loaders/data_loader.py` (existing), `engine/feasibility.py` (new) | Mostly existing |
| 2 | **CE plan** — per-worker monthly amount; random income-weighted day selection; per-day distribution | `engine/ce_planner.py` (new, replaces CE half of `scheduler.py`) | New |
| 3 | **SE schedule** — assign SE workers to (company, day) within `0.4 × (I_clean − CE_day)` per-day cap | `engine/se_scheduler.py` (new, replaces SE half of `scheduler.py`) | New |
| 4 | **SE salary solver** — exact monthly targets, even-integer daily salaries | `engine/salary_solver.py` (rewritten) | Rewritten |
| 5 | Excel report | `reports/excel_writer.py` | Minor additions |

Old `engine/scheduler.py` is deleted. CE/SE phases no longer interleave; CE total is known before SE assignment begins.

### 4.2 Module dependency graph

```
main.py
  ├─ loaders/data_loader.py
  ├─ engine/feasibility.py        (new)
  ├─ engine/ce_planner.py         (new)
  ├─ engine/se_scheduler.py       (new)
  ├─ engine/salary_solver.py      (rewritten)
  └─ reports/excel_writer.py
```

Models (`SelfEmployedEmployee`, `CompanyEmployedEmployee`, `Company`, `DayLedger`) are reused with minor extensions (see §5).

## 5. Detailed design

### 5.1 Phase 0 — Seed handling

Resolution order in `main.py`:

1. CLI arg `--seed N`.
2. Env var `SALARY_SEED=N`.
3. Auto-generated: `random.SystemRandom().randrange(2**32)`.

The resolved seed is:

- Logged at INFO at the very start of the run, with provenance: `Random seed: 1234567890 (auto-generated)` or `(from --seed)` or `(from SALARY_SEED env var)`.
- Recorded in `output/run.log`.
- Written to the Summary sheet of the Excel report.

A single `random.Random(seed)` instance flows through all phases by parameter passing (the same pattern the existing code already uses for `rng`). Same seed + same input = byte-identical output.

`config.RANDOM_SEED` is removed.

### 5.2 Phase 1 — Feasibility check

After data loading, before CE planning, compute:

```python
total_I_clean = Σ_(c, d) I_clean[c, d]
Σ_targets = Σ_w SE_target[w]
SE_max_possible = 0.4 × total_I_clean       # the case where CE_day = 0 every day
```

If `Σ_targets > SE_max_possible`:

- Log a loud `WARNING`: `SE targets infeasible: need X, max possible Y, gap Z`.
- Continue with **best-effort fallback**: the SE solver runs in "shortfall is allowed, log per-worker gaps" mode. This matches the legacy behaviour and is the explicit answer to the rare edge case (the owner expects this branch to be unreachable in practice).

### 5.3 Phase 2 — CE plan

#### 5.3.1 Per-worker monthly amount

```python
total_CE_budget = total_I_clean − 2.5 × Σ_targets
Σ_caps = Σ_w CE_cap[w]
```

Two cases:

- `total_CE_budget ≥ Σ_caps`: every CE worker is targeted at their full cap. Leftover `phantom_CE = total_CE_budget − Σ_caps` is reserved as a single monthly summary item (see §5.6).
- `total_CE_budget < Σ_caps`: each CE worker's monthly amount is scaled proportionally to cap:
  `worker_monthly[w] = floor(cap[w] × total_CE_budget / Σ_caps / 5) × 5`. Any rounding deficit is absorbed by giving the largest-cap worker a +5 nudge until the sum matches `total_CE_budget`. CE shortfall vs. cap is recorded per worker.

Special handling: if `total_CE_budget < 0` (i.e., `Σ_targets > 0.4 × total_I_clean`, the infeasible branch from §5.2), every CE worker is set to `worker_monthly = 0` and Phase 2 is a no-op except for emitting the warning.

#### 5.3.2 Per-worker day selection

For each CE worker `w` with monthly amount `M`:

1. Build `D = {d | preferences[w][company_w][d] > 0}` at the worker's exclusive / preferred company.
2. Sort `D` by `I_clean[c, d]` descending.
3. Choose number of working days `k`:
   - `k_min = ceil(M / MAX_PER_DAY)` where `MAX_PER_DAY = 400`.
   - `k_max = |D|`.
   - If `k_min > k_max`: worker can't be paid in full → log shortfall, set `M ← MAX_PER_DAY × k_max`, take all eligible days.
   - Otherwise sample `k = rng.randint(k_min, max(k_min, min(k_max, ceil(M / 120))))`. The `max(k_min, ...)` outer guard handles the corner case where `ceil(M / 120) < k_min` (small `M` near the boundaries) — in that case `k = k_min` deterministically. The upper bound is the worst-case "spread thin" count; favoring fewer-but-busier days falls out of the income-sorted picking next.
4. Take the top `k` days from the sorted list, biased by income: pick the head deterministically when `k = k_min` (concentrated on busiest days), and add randomness to the tail when `k > k_min` by sampling weighted by `I_clean`.
5. Random-split `M` across these `k` days as multiples of 5 in `[5, MAX_PER_DAY]`. Reuse the proportional-random algorithm from the legacy `_split_budget`, adapted to the new range.

#### 5.3.3 Conflict resolution & SE-feasibility guard

CE workers are processed in random order (seeded). Per (c, d), maintain a running `CE_day[c, d]`. While placing a worker on a candidate day:

- **Double-booking**: if the worker already has a shift somewhere on day `d`, skip that day.
- **SE-feasibility**: the assignment must keep `CE_day[c, d] ∈ {0, …, I_clean[c, d] − 300} ∪ {I_clean[c, d]}`. The first interval keeps `0.4 × (I_clean − CE_day) ≥ 120` so at least one SE worker can fit; the singleton represents a whole-day CE absorption with no SE that day.
- If a candidate placement would push `CE_day` into the forbidden window `(I_clean − 300, I_clean)`, the algorithm first **tries to reduce the worker's share for that day** down to the largest multiple of 5 that keeps `CE_day ≤ I_clean − 300` — but only if the reduced share stays ≥ 5. Otherwise (reduced share would be 0 or negative), it **moves the worker to the next day** in their income-sorted list. This ordering is deterministic given the seed. After `MAX_RETRIES = 5` failed attempts on a worker, the worker accepts a partial monthly amount (CE shortfall logged).

#### 5.3.4 Validation pass (non-negativity guard)

After all CE workers are placed:

- Assert `CE_day[c, d] ≥ 0` for every (c, d). 0 is allowed (no CE that day).
- Assert each individual `ce_salaries[w][c, d] ≥ 0` and a multiple of 5.
- A failure here indicates an algorithm bug. Log a loud `WARNING` with `(worker, company, day, amount)` and surface it on the Summary sheet, but do not abort — the report should still emit so the user can inspect.

### 5.4 Phase 3 — SE schedule

Inputs: per-(c, d) `SE_day_target = 0.4 × (I_clean[c, d] − CE_day[c, d])`. By the §5.3.3 guard, `SE_day_target` is always either `0` or `≥ 120` (and always an even integer).

#### 5.4.1 Per-worker feasibility envelope

For each SE worker with target `T`:

- `min_days = ceil(T / 400)`.
- `max_days = floor(T / 120)`.
- `target_days_estimate = ceil(T / PREDEFINED_DAILY)` where `PREDEFINED_DAILY = 180` (kept as the *preferred* day count inside the envelope).

If `min_days > max_days` (shouldn't happen for normal targets but guarded), the worker is inherently infeasible — fall through to shortfall mode for that worker.

#### 5.4.2 Slot iteration

1. Build the list `S = {(c, d) | SE_day_target[c, d] ≥ 120}`. Skip slots with `SE_day_target = 0`.
2. Shuffle `S` with `rng`.
3. For each slot:
   - `n_min = ceil(SE_day_target / 400)`, `n_max = floor(SE_day_target / 120)`.
   - Eligible pool: workers with `P > 0` at that slot, satisfying exclusivity, not already booked elsewhere on day `d`, and `assigned_days < max_days`.
   - Sort pool by `(−P, −(target_days_estimate − assigned_days))` so P=2 outranks P=1, and under-scheduled workers get priority within the same P.
   - `n = rng.randint(n_min, min(n_max, len(pool)))` workers selected.
   - Assign each as an unsalaried shift (salary filled by Phase 4).

#### 5.4.3 Post-sweep for under-scheduled workers

Any SE worker with `assigned_days < min_days` enters a fill-in pass:

- Iterate over remaining slots that still have `n_workers < n_max` and the worker is eligible.
- Assign until the worker reaches `min_days` or no slots remain.
- If a worker still cannot reach `min_days`, the run is infeasible for that worker only. Log shortfall (consistent with §5.2 fallback semantics) and continue.

### 5.5 Phase 4 — SE salary solver

Given the assignment matrix `A[w, c, d] ∈ {0, 1}`, compute `s[w, c, d] ∈ {0} ∪ ([120, 400] ∩ 2ℤ)` such that:

- `s[w, c, d] = 0` iff `A[w, c, d] = 0`.
- `Σ_(c, d) s[w, c, d] = T_w` for every SE worker `w` (row sum = monthly target).
- `Σ_w s[w, c, d] = SE_day_target[c, d]` for every active slot (column sum = per-day target).

This is a transportation problem with integer-multiple-of-2 cell constraints and bounded support `[120, 400]`.

#### 5.5.1 Algorithm — two-stage, dependency-free

**Stage A: continuous Sinkhorn-style initialization**

- Treat `s[w, c, d]` as continuous in `[120, 400]` where `A=1`, else 0.
- Repeatedly normalise rows (to `T_w`) and columns (to `SE_day_target`), clamping every step to `[120, 400]`. The classic biproportional fitting / Sinkhorn loop.
- Bounded by `SOLVER_MAX_ITER` iterations or convergence within `SOLVER_TOL`.

**Stage B: integer rounding repair**

- Round each cell to the nearest even integer in `[120, 400]`. Both row and column sums break by small amounts.
- Run a swap loop: find a pair of cells `(w, c, d)` and `(w', c, d)` (same column) where shifting `+2 / −2` reduces a row violation without exceeding bounds; analogous for column violations. Apply, repeat. Swaps only operate on cells where `A=1`; zero cells (where `A=0`) stay zero, preserving the `s = 0 iff A = 0` invariant.
- Bounded by `SOLVER_MAX_ITER` iterations. If the loop saturates without reaching exact match, log the residual error per worker and per slot (these are the rare-but-possible non-converging inputs that would warrant adopting PuLP later).

#### 5.5.2 Fallback

Per-worker shortfall is recorded if the solver can't reach `T_w`. Per-slot deviation triggers a separate warning (it would mean the per-day formula is broken; treated as a bug indicator, not normal output).

### 5.6 Phase 5 — Excel report additions

Existing 4-sheet structure preserved. Summary sheet gains:

- **Run seed** with provenance.
- **Phantom CE** as a single line item: `phantom_CE = total_CE_budget − Σ ce_actual_monthly` when positive. The per-day formula verifier accepts this as an expected residual when `total_CE_budget > Σ_caps`, not a violation.
- **CE shortfall report** per worker: `actual / cap / gap`.
- **SE shortfall report** per worker: `actual / target / gap`. Gap should be 0 in normal operation.

Per-day classification (`is_infeasible`, `is_ce_only`) is removed. New flag: `is_full_ce_absorption` for slots where `SE_day_target = 0`.

The formula verifier (`_log_results` in the legacy code) updates to allow phantom-CE residual on impacted days without flagging a violation.

#### 5.6.1 Model surface changes

`src/models/company.py` requires more than just flag changes — the planner has flipped, so the legacy methods that derived an SE budget from CE no longer fit:

- `DayLedger.compute_se_budget(ce_total, min_salary)` is **replaced** by `DayLedger.compute_se_target_from_ce(ce_total)` returning `(I_clean − ce_total) × 0.4` exactly (no flooring, no `is_infeasible`/`is_ce_only` side-effects). The new flag `is_full_ce_absorption` is set when the result is 0.
- `DayLedger.formula_check` keeps its signature but its caller (the verifier) subtracts the per-day phantom-CE allocation before comparing to `cleaned_income`.
- `DayLedger.is_infeasible` and `DayLedger.is_ce_only` properties are removed.

These belong in the implementation plan; calling them out here so the planner sizes the model touch correctly.

## 6. Configuration changes

`src/config.py` updates:

- `SALARY_UNIT = 5` → split into:
  - `SE_SALARY_UNIT = 2`
  - `CE_SALARY_UNIT = 5`
  - `INCOME_UNIT = 5`
- `MAX_PER_DAY = 400` (used by both SE and CE).
- `MIN_SALARY = 120` (SE only; CE has no lower bound beyond > 0 if working).
- `RANDOM_SEED = 42` removed.
- `PREDEFINED_DAILY = 180` retained as the preferred day count for SE workers inside `[min_days, max_days]`.

## 7. Testing plan

A test pass should cover:

1. **Math invariants** — golden-input run; assert `Σ SE_day == (I_clean − Σ CE_day) × 0.4` for every (c, d) (modulo phantom CE).
2. **SE no-shortfall** — assert every SE worker's actual monthly == target.
3. **CE proportional shortfall** — manufactured input where `total_CE_budget < Σ_caps`; assert each CE worker's actual is `floor(cap × total_CE_budget / Σ_caps / 5) × 5` (with the rounding-correction nudge) up to ±5.
4. **Determinism** — same seed twice → identical Excel output (compare sheet-by-sheet).
5. **Different seeds → different runs** — different seed produces a different schedule but identical aggregate sums.
6. **Infeasible-input fallback** — `Σ_targets > 0.4 × total_I_clean`; assert warning emitted, run completes, shortfall logged per worker.
7. **Validation pass** — inject a deliberate negative CE share in a unit test; assert the validator warns.
8. **No bare `random.*` calls** — automated check (grep) ensures all randomness flows through the seeded `rng` instance, so the determinism guarantee from §5.1 isn't silently broken by an accidental import in a future change.

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| The SE salary solver's swap loop fails to converge on adversarial inputs. | Keep iteration bound and log residual; document the path to PuLP if seen in production. |
| CE day selection's SE-feasibility guard pushes a worker into too few days, causing CE shortfall even when `total_CE_budget ≥ Σ_caps`. | The greedy "biased to busy days" sort + 5-retry move-to-next-day path keeps this rare. Validation pass catches it; surfaced in Summary. |
| Random seed determinism is broken by accidental use of bare `random.*` calls. | Code review item; lint/grep for `random.` outside fixture code. |
| Phantom CE silently distorts day-formula verification. | Verifier explicitly subtracts known phantom amount before comparing. |

## 9. Out of scope (for this iteration)

- A proper LP/ILP solver (PuLP, OR-Tools). Revisit only if the dependency-free solver fails to converge on real inputs.
- Day-by-day balancing of CE earnings (ensuring no CE worker is concentrated entirely on 2 days, etc.). Acceptable for now.
- Per-worker preferences influencing CE day-selection beyond the binary `P > 0` filter. The income-weighting is the only tie-breaker.
