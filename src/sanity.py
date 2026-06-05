import math

import pandas as pd

from src.config import RATIO, MAX_SALARY, CE_MAX_PER_DAY, INCOME_UNIT

_VALID_TYPES = {"Self-Employed", "Company-Employed"}


def _clean(v: int) -> int:
    return (v // INCOME_UNIT) * INCOME_UNIT


def _exclusive_of(raw) -> str | None:
    """Normalise an employee_data 'exclusive_company' cell to 'good_life'/'tianyuan'/None."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    s = str(raw).strip().lower()
    if "good" in s:
        return "good_life"
    if "tian" in s or "yuan" in s:
        return "tianyuan"
    return None


def check_feasibility(
    employees_df: pd.DataFrame,
    se_pref_df: pd.DataFrame,
    ce_pref_df: pd.DataFrame,
    income_df: pd.DataFrame,
    t: dict,
    se_max_per_day: int | None = None,
    ce_max_per_day: int | None = None,
) -> list[str]:
    """Structural feasibility analysis. Every check is a true *necessary* condition
    for a zero-shortfall / zero-deviation schedule, so a solvable dataset produces
    no messages — these only fire when the data makes the target genuinely
    impossible, pointing at the specific worker / day / total at fault."""
    _se_max = se_max_per_day if se_max_per_day is not None else MAX_SALARY
    _ce_max = ce_max_per_day if ce_max_per_day is not None else CE_MAX_PER_DAY
    errors: list[str] = []
    try:
        days = [int(d) for d in income_df["day"].tolist()]
        inc = {int(r["day"]): (_clean(int(r["good_life"])), _clean(int(r["tianyuan"])))
               for _, r in income_df.iterrows()}
    except (KeyError, ValueError, TypeError):
        return errors  # malformed income; basic checks already flagged it

    total_income = sum(gl + ty for gl, ty in inc.values())

    se = [(str(r["name"]).strip(), int(r["salary"]))
          for _, r in employees_df.iterrows() if str(r["type"]).strip() == "Self-Employed"]
    ce = [(str(r["name"]).strip(), int(r["salary"]), _exclusive_of(r.get("exclusive_company")))
          for _, r in employees_df.iterrows() if str(r["type"]).strip() == "Company-Employed"]

    total_se = sum(s for _, s in se)
    total_ce_cap = sum(c for _, c, _ in ce)

    # F1 — aggregate SE: SE pay comes out of 40% of income.
    max_se = RATIO * total_income
    if total_se > max_se:
        errors.append(t["sanity_infeasible_se_total"].format(
            se=total_se, cap=int(max_se), income=total_income))

    # F2 — aggregate CE: residual CE work needed if SE fully delivered.
    ce_needed = total_income - total_se / RATIO
    if total_ce_cap < math.floor(ce_needed):
        errors.append(t["sanity_infeasible_ce_total"].format(
            cap=total_ce_cap, need=int(math.ceil(ce_needed))))

    # F3 — per SE worker: enough eligible days to reach the monthly target.
    se_avail: dict[str, set[int]] = {n: set() for n, _ in se}
    se_cols = [c for c in se_pref_df.columns if c != "Day"]
    for _, row in se_pref_df.iterrows():
        try:
            d = int(row["Day"])
        except (ValueError, TypeError):
            continue
        for n in se_avail:
            if n in se_cols and int(row[n]) > 0:
                se_avail[n].add(d)
    for n, target in se:
        ndays = len(se_avail[n])
        if ndays * _se_max < target:
            errors.append(t["sanity_worker_unreachable"].format(
                name=n, days=ndays, maxreach=ndays * _se_max, target=target))

    # F4 — per (company, day): even devoting every eligible SE worker to this one
    # company cannot bridge what CE (per-day capped) leaves uncovered.
    ce_avail: dict[tuple[str, int], int] = {}
    ce_cols = [c for c in ce_pref_df.columns if c not in ("Company", "Day")]
    excl_map = {n: x for n, _, x in ce}
    for _, row in ce_pref_df.iterrows():
        comp = str(row["Company"]).strip().lower().replace(" ", "_")
        comp = "tianyuan" if "tian" in comp or "yuan" in comp else ("good_life" if "good" in comp else comp)
        try:
            d = int(row["Day"])
        except (ValueError, TypeError):
            continue
        cnt = 0
        for n in ce_cols:
            if int(row[n]) > 0 and excl_map.get(n) in (None, comp):
                cnt += 1
        ce_avail[(comp, d)] = cnt
    comp_label = {"good_life": t["company_gl"], "tianyuan": t["company_ty"]}
    for d in days:
        n_se_day = sum(1 for n in se_avail if d in se_avail[n])
        for comp_key in ("good_life", "tianyuan"):
            I = inc[d][0 if comp_key == "good_life" else 1]
            max_ce = min(I, ce_avail.get((comp_key, d), 0) * _ce_max)
            se_needed = RATIO * (I - max_ce)
            if se_needed > 0 and n_se_day * _se_max < se_needed:
                errors.append(t["sanity_day_uncoverable"].format(
                    company=comp_label.get(comp_key, comp_key), day=d,
                    need=int(math.ceil(se_needed)),
                    have=n_se_day, maxse=n_se_day * _se_max))
    return errors


def run_sanity_check(
    employees_df: pd.DataFrame,
    se_pref_df: pd.DataFrame,
    ce_pref_df: pd.DataFrame,
    income_df: pd.DataFrame | None = None,
    lang: str = "en",
    se_max_per_day: int | None = None,
    ce_max_per_day: int | None = None,
) -> list[str]:
    """
    Returns a list of human-readable error strings.
    Empty list means all checks passed.
    """
    from src.i18n import I18N
    t = I18N.get(lang, I18N["en"])
    errors: list[str] = []

    for _, row in employees_df.iterrows():
        name = str(row["name"]).strip()
        if str(row["type"]).strip() not in _VALID_TYPES:
            errors.append(t["sanity_invalid_type"].format(name=name, type=row["type"]))
        try:
            salary = int(row["salary"])
        except (ValueError, TypeError):
            salary = 0
        if salary <= 0:
            errors.append(t["sanity_positive_salary"].format(name=name, salary=row["salary"]))

    names = [str(r).strip() for r in employees_df["name"]]
    seen: set[str] = set()
    for n in names:
        if n in seen:
            errors.append(t["sanity_duplicate_name"].format(name=n))
        seen.add(n)

    se_names = [str(r["name"]).strip() for _, r in employees_df.iterrows() if str(r["type"]).strip() == "Self-Employed"]
    ce_names = [str(r["name"]).strip() for _, r in employees_df.iterrows() if str(r["type"]).strip() == "Company-Employed"]

    se_pref_cols = set(se_pref_df.columns) - {"Day"}
    missing_se = [n for n in se_names if n not in se_pref_cols]
    if missing_se:
        errors.append(t["sanity_missing_se_pref"].format(missing=missing_se))

    ce_pref_cols = set(ce_pref_df.columns) - {"Company", "Day"}
    missing_ce = [n for n in ce_names if n not in ce_pref_cols]
    if missing_ce:
        errors.append(t["sanity_missing_ce_pref"].format(missing=missing_ce))

    se_worker_cols = [c for c in se_pref_df.columns if c != "Day"]
    for _, row in se_pref_df.iterrows():
        try:
            day = int(row["Day"])
        except (ValueError, TypeError):
            continue
        available = [c for c in se_worker_cols if int(row[c]) > 0]
        if not available:
            errors.append(t["sanity_no_se_employee"].format(day=day))

    if income_df is not None:
        try:
            inc_days = {int(d) for d in income_df["day"].tolist()}
            se_days = {int(d) for d in se_pref_df["Day"].tolist()}
            ce_days = {int(d) for d in ce_pref_df["Day"].tolist()}

            only_inc_se = sorted(inc_days - se_days)
            only_se = sorted(se_days - inc_days)
            if only_inc_se:
                errors.append(t["sanity_inc_missing_pref"].format(days=only_inc_se))
            if only_se:
                errors.append(t["sanity_pref_missing_inc"].format(days=only_se))

            only_inc_ce = sorted(inc_days - ce_days)
            only_ce = sorted(ce_days - inc_days)
            if only_inc_ce:
                errors.append(t["sanity_inc_missing_pref"].format(days=only_inc_ce))
            if only_ce:
                errors.append(t["sanity_pref_missing_inc"].format(days=only_ce))
        except (KeyError, ValueError, TypeError):
            pass

    # Structural feasibility — only once basic integrity holds (days aligned, no
    # missing workers), so the feasibility math has clean inputs.
    if not errors and income_df is not None:
        errors.extend(check_feasibility(employees_df, se_pref_df, ce_pref_df, income_df, t,
                                        se_max_per_day=se_max_per_day, ce_max_per_day=ce_max_per_day))

    return errors
