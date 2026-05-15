import pandas as pd

_VALID_TYPES = {"Self-Employed", "Company-Employed"}


def run_sanity_check(employees_df: pd.DataFrame, pref_df: pd.DataFrame) -> list[str]:
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

    return errors
