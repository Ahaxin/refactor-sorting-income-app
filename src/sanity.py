import pandas as pd

_VALID_TYPES = {"Self-Employed", "Company-Employed"}


def run_sanity_check(
    employees_df: pd.DataFrame,
    pref_df: pd.DataFrame,
    income_df: pd.DataFrame | None = None,
) -> list[str]:
    """
    Returns a list of human-readable error strings.
    Empty list means all checks passed.
    """
    errors: list[str] = []

    for _, row in employees_df.iterrows():
        name = str(row["name"]).strip()
        if str(row["type"]).strip() not in _VALID_TYPES:
            errors.append(f"{name}: invalid type '{row['type']}' (must be Self-Employed or Company-Employed)")
        try:
            salary = int(row["salary"])
        except (ValueError, TypeError):
            salary = 0
        if salary <= 0:
            errors.append(f"{name}: salary must be a positive integer (got {row['salary']})")

    names = [str(r).strip() for r in employees_df["name"]]
    seen: set[str] = set()
    for n in names:
        if n in seen:
            errors.append(f"Duplicate employee name: '{n}'")
        seen.add(n)

    pref_cols = set(pref_df.columns) - {"Company", "Day"}
    missing = [n for n in names if n not in pref_cols]
    if missing:
        errors.append(f"Employees missing from preference matrix: {missing}")

    employee_pref_cols = [c for c in pref_df.columns if c not in ("Company", "Day")]
    for _, row in pref_df.iterrows():
        company = str(row["Company"]).strip()
        try:
            day = int(row["Day"])
        except (ValueError, TypeError):
            continue
        available = [c for c in employee_pref_cols if int(row[c]) > 0]
        if not available:
            errors.append(
                f"No employee is available for {company} day {day} "
                "(all preferences are 0 — at least one employee must be 1 or 2)."
            )

    if income_df is not None:
        try:
            inc_days = {int(d) for d in income_df["day"].tolist()}
            pref_days = {int(d) for d in pref_df["Day"].tolist()}
            only_inc = sorted(inc_days - pref_days)
            only_pref = sorted(pref_days - inc_days)
            if only_inc:
                errors.append(
                    f"Days present in Income but missing from Preference Matrix: {only_inc}. "
                    "Re-save the Income tab to auto-sync."
                )
            if only_pref:
                errors.append(
                    f"Days present in Preference Matrix but missing from Income: {only_pref}. "
                    "Re-save the Income tab to auto-sync."
                )
        except (KeyError, ValueError, TypeError):
            pass

    return errors
