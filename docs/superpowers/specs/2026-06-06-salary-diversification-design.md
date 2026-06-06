# Salary Diversification (Post-Tuning Randomization) — Design

Date: 2026-06-06
Status: Approved (pending spec review)

## Problem

After `solve_exact` runs, the schedule contains many identical daily salary
values. The MILP objective spreads each SE worker's monthly target across as
many days as possible (Phase 2) but never rewards *variety*, so HiGHS returns
vertex solutions that pile many cells at the same number (e.g. lots of `130`
for SE, repeated `140` for CE). The user wants the daily numbers to look more
varied — fewer exact duplicates — **without changing the solved guarantees**.

## Goal & Non-Goals

**Goal:** A deterministic post-tuning pass that diversifies individual daily SE
and CE salaries within a ±% band of each value, while keeping every hard
guarantee the solver produced *exactly* intact. After tuning, re-run validation
checks; if anything regressed, revert to the pristine solved schedule.

**Non-Goals:**
- No change to the solver itself or its objective.
- Not trying to maximize variety at the cost of any guarantee.

**In scope:** both the GUI generate path **and** the CLI (`main.py`).

## Invariants (must hold after tuning)

The diversification is built so that, by construction, all of these are
preserved relative to the solved state:

1. **Per-(company, day) SE total** unchanged → the 40% formula stays exact.
2. **Per-(company, day) CE total** unchanged → the 40% formula stays exact.
3. **Per SE worker monthly sum** unchanged → exact monthly target preserved.
4. **Per CE worker monthly sum** unchanged → monthly cap stays satisfied.
5. **Units:** SE values remain even (`SE_SALARY_UNIT=2`); CE values remain
   multiples of 5 (`CE_SALARY_UNIT=5`).
6. **Bounds & structure:** SE active cells stay in `[60, se_max]`; CE active
   cells stay in `[CE_SALARY_UNIT, ce_max]`. No active cell is zeroed and no new
   cell is created, so the active-slot set (and one-company-per-day) is untouched.
7. **Band:** each cell stays within ±`pct` of its *original solved value*.
8. **Determinism:** identical inputs + same `seed` → identical output.

## Approach: Cycle-based redistribution

Model each worker-type as a matrix `value[worker][(company, day)]`. The only
move that keeps **both** a day-column total and a worker-row total unchanged is a
4-cell cycle on two workers `w1, w2` who are both active on two common columns
`k1, k2`:

```
w1@k1 += δ    w1@k2 -= δ
w2@k1 -= δ    w2@k2 += δ
```

- Column sums (`k1`, `k2`) are preserved → invariants 1 & 2.
- Row sums (`w1`, `w2`) are preserved → invariants 3 & 4.
- `δ` is a nonzero multiple of the salary unit (2 for SE, 5 for CE).

### Feasible δ

Let the four current cell values be `v11=w1@k1, v12=w1@k2, v21=w2@k1,
v22=w2@k2`, originals `o11..o22`, per-cell band budget `B_ij = unit *
floor(o_ij * pct / unit)`, and active range `[lo, hi]` (`lo=60` SE,
`lo=CE_SALARY_UNIT` CE; `hi=se_max`/`ce_max`). After moving by δ:

```
w1@k1 = v11+δ   w1@k2 = v12-δ   w2@k1 = v21-δ   w2@k2 = v22+δ
```

Intersect, over all four cells, the range constraints `lo ≤ value ≤ hi` and the
band constraints `|value - o| ≤ B` to get `[δ_lo, δ_hi]`. Pick a random nonzero
δ in that range that is a multiple of `unit`. If the range admits no nonzero
multiple, skip this cycle.

### Driver loop

- Build `cols_of[worker] -> set of active (c,d)` and
  `workers_at[(c,d)] -> set of active workers`.
- Repeat `ITER_FACTOR * (#active cells)` attempts (`ITER_FACTOR = 8`), with a
  `random.Random(seed)`:
  1. pick a worker `w1` with ≥2 active columns;
  2. pick two distinct columns `k1, k2` of `w1`;
  3. pick `w2 ≠ w1` active at both `k1` and `k2` (skip if none);
  4. compute feasible δ, pick a random nonzero multiple of `unit`, apply it and
     write the four cells back to both `worker.schedule` and the day ledger.
- SE and CE are processed independently with their own unit/lo/hi.

Diversity is bounded by how many such cycles exist — inherent to "keep
everything exact." That is acceptable; even modest shuffling breaks up the
common values.

## Components

### New module: `src/engine/diversify.py`

```python
def diversify_schedule(
    se_workers, ce_workers, companies,
    pct: float = 0.15, seed: int = 0,
    se_max: int | None = None, ce_max: int | None = None,
) -> None
    # Mutates schedules + day ledgers in place. pct <= 0 is a no-op.

@dataclass
class VerifyReport:
    deviations: list[tuple[str, int, int]]     # (company, day, signed dev)
    shortfalls: list[tuple[str, int]]          # (se worker, signed gap)
    cap_violations: list[tuple[str, int]]      # (ce worker, overage)
    bound_violations: list[str]                # human-readable cell problems
    @property
    def ok(self) -> bool: ...
    def regressed_from(self, baseline_deviations, baseline_shortfalls) -> bool:
        # True if there are MORE deviations/shortfalls than the solver baseline,
        # or any cap/bound/unit violation.

def verify_schedule(se_workers, ce_workers, companies,
                    se_max=None, ce_max=None) -> VerifyReport
    # Recomputes everything from current model state. Read-only.
    # se_max/ce_max None -> MAX_SALARY / CE_MAX_PER_DAY from config.

def snapshot_schedules(se_workers, ce_workers, companies) -> dict
def restore_schedules(snapshot, se_workers, ce_workers, companies) -> None
    # Guardrail save/restore of schedule + ledger dicts.
```

`verify_schedule` recomputes from the live model:
- deviations: per non-CE-full `(c,d)`, `round(dl.formula_check) - dl.cleaned_income`;
- shortfalls: per SE worker, `actual_monthly_salary - salary`;
- cap_violations: per CE worker, `actual_monthly_salary - salary` when positive;
- bound_violations: any SE cell not even / outside `[60, se_max]`; any CE cell
  not a multiple of 5 / outside `[0, ce_max]`.

`se_day_target` and `formula_check` are derived from the per-day totals (which
are preserved), so no extra write-back is needed for them.

### GUI wiring: `gui.py` (Generate tab)

- Add a **"Variation band (%)"** `st.number_input` next to the SE/CE cap inputs:
  `min_value=0, max_value=50, value=15, step=1, key="input_div_pct"`, stored in
  `st.session_state["div_pct"]`.
- In the generate handler, **after** `solve_exact(...)` and **before** building
  the deviation/shortfall messages and generating the reports:
  ```python
  if div_pct > 0:
      _snap = snapshot_schedules(_se, _ce, _companies)
      diversify_schedule(_se, _ce, _companies, pct=div_pct/100, seed=0,
                         se_max=se_max, ce_max=ce_max)
      _v = verify_schedule(_se, _ce, _companies, se_max=se_max, ce_max=ce_max)
      if _v.regressed_from(_report.deviations, _report.shortfalls):
          restore_schedules(_snap, _se, _ce, _companies)
          logger.warning("Post-tuning checks regressed — reverted to solved schedule.")
          _reverted = True
      else:
          logger.info("Post-tuning diversification applied — checks passed.")
  ```
  Both report writers read the (now tuned) `schedule`/ledger dicts, so the full
  and simplified reports both reflect the diversified values. The
  deviation/shortfall summary built from `_report` remains accurate because the
  invariants guarantee the tuned state matches the solver baseline.
- If reverted, surface a translated `st.warning` (`warn_tuning_reverted`).

### CLI wiring: `main.py`

- Add `--variation PCT` (`type=int, default=15`, help: "±% band for salary
  diversification; 0 disables"). Validate/clamp to `[0, 50]`.
- Reuse the resolved `seed` (from `--seed` / `SALARY_SEED` / auto) for
  `diversify_schedule` so a CLI run is reproducible via the same seed it already
  logs.
- After `solve_exact(...)` and before `generate_report(...)`, apply the same
  guardrail as the GUI:
  ```python
  if variation > 0:
      snap = snapshot_schedules(se_workers, ce_workers, companies)
      diversify_schedule(se_workers, ce_workers, companies,
                         pct=variation/100, seed=seed)
      v = verify_schedule(se_workers, ce_workers, companies,
                          se_max=None, ce_max=None)   # config defaults
      if v.regressed_from(report.deviations, report.shortfalls):
          restore_schedules(snap, se_workers, ce_workers, companies)
          logger.warning("Post-tuning checks regressed — reverted to solved schedule.")
      else:
          logger.info("Post-tuning diversification applied — checks passed.")
  ```
  The CLI uses the config-default caps (`MAX_SALARY`, `CE_MAX_PER_DAY`), matching
  the solver call it already makes with defaults.

### i18n: `src/i18n.py`

Add to both `zh` and `en`:
- `label_variation` — input label (zh: "随机浮动幅度 (%)", en: "Variation Band (%)").
- `help_variation` — help text explaining values vary within ±band while all
  totals stay exact.
- `warn_tuning_reverted` — shown only if the guardrail reverts the tuning.

Logger lines stay English, matching the existing Pipeline Log style.

## Testing: `tests/test_diversify.py`

Build a small solved fixture (reuse the solver test fixtures / `load_all` on the
test data, or a hand-built model) and assert, after `diversify_schedule`:

1. **Invariants:** every per-(c,d) `se_total` and `ce_total`, and every worker's
   `actual_monthly_salary`, equal the pre-tuning values.
2. **Units/bounds:** all SE cells even and in `[60, se_max]`; all CE cells
   multiples of 5 and in `[0, ce_max]`.
3. **Band:** every cell within `±ceil(original*pct)` of its original.
4. **No-op:** `pct=0` leaves the schedule byte-for-byte identical.
5. **Determinism:** same seed → identical result; (optionally) different seed →
   may differ.
6. **Diversity:** on a fixture with cycle room, the count of duplicate values
   strictly decreases (or at least one cell changes).
7. **verify_schedule:** returns `ok` on a tuned schedule; `regressed_from`
   returns False vs. the solver baseline.
8. **snapshot/restore:** restore returns the model to the snapshot exactly.

## Risks

- **Limited diversity** when few cycles exist (sparse availability). Acceptable —
  inherent to exactness; the guardrail never makes things worse.
- **Performance:** `ITER_FACTOR * cells` attempts are cheap (pure Python dict
  math); negligible next to the MILP solve.
- The guardrail (snapshot → verify → revert) means a bug in the cycle math can
  never ship a worse report than the solver produced.
