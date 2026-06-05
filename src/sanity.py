import pandas as pd

_VALID_TYPES = {"Self-Employed", "Company-Employed"}


def run_sanity_check(
    employees_df: pd.DataFrame,
    se_pref_df: pd.DataFrame,
    ce_pref_df: pd.DataFrame,
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

    return errors
