import pandas as pd

_VALID_TYPES = {"Self-Employed", "Company-Employed"}


def run_sanity_check(
    employees_df: pd.DataFrame,
    pref_df: pd.DataFrame,
    income_df: pd.DataFrame | None = None,
    lang: str = "en",
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

    pref_cols = set(pref_df.columns) - {"Company", "Day"}
    missing = [n for n in names if n not in pref_cols]
    if missing:
        errors.append(t["sanity_missing_pref"].format(missing=missing))

    employee_pref_cols = [c for c in pref_df.columns if c not in ("Company", "Day")]
    for _, row in pref_df.iterrows():
        company = str(row["Company"]).strip()
        try:
            day = int(row["Day"])
        except (ValueError, TypeError):
            continue
        available = [c for c in employee_pref_cols if int(row[c]) > 0]
        if not available:
            errors.append(t["sanity_no_employee"].format(company=company, day=day))

    if income_df is not None:
        try:
            inc_days = {int(d) for d in income_df["day"].tolist()}
            pref_days = {int(d) for d in pref_df["Day"].tolist()}
            only_inc = sorted(inc_days - pref_days)
            only_pref = sorted(pref_days - inc_days)
            if only_inc:
                errors.append(t["sanity_inc_missing_pref"].format(days=only_inc))
            if only_pref:
                errors.append(t["sanity_pref_missing_inc"].format(days=only_pref))
        except (KeyError, ValueError, TypeError):
            pass

    return errors
