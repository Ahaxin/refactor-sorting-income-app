"""
Company model holding daily income and the computed SE/CE ledger.
"""

from src.config import INCOME_UNIT, RATIO


def clean_income(raw: int) -> int:
    """Round income down to the nearest multiple of INCOME_UNIT."""
    return (raw // INCOME_UNIT) * INCOME_UNIT


class DayLedger:
    """Financial record for a single (company, day) pair."""

    def __init__(self, day: int, raw_income: int):
        self.day = day
        self.raw_income = raw_income
        self.cleaned_income: int = clean_income(raw_income)

        self.ce_salaries: dict[str, int] = {}
        self.se_salaries: dict[str, int] = {}
        self._se_day_target: int = 0
        self.is_full_ce_absorption: bool = False

    def compute_se_target_from_ce(self, ce_total: int) -> int:
        """
        SE_day_target = (I_clean - CE_total) * RATIO exactly.
        Sets is_full_ce_absorption when result is 0.
        Returns an even integer (guaranteed when I_clean and CE are multiples of 5).
        """
        net = self.cleaned_income - ce_total
        target = int(round(net * RATIO))
        self._se_day_target = target
        self.is_full_ce_absorption = (target == 0)
        return target

    @property
    def se_day_target(self) -> int:
        return self._se_day_target

    @property
    def se_budget(self) -> int:
        """Alias for backward-compat during transition."""
        return self._se_day_target

    @property
    def ce_total(self) -> int:
        return sum(self.ce_salaries.values())

    @property
    def se_total(self) -> int:
        return sum(self.se_salaries.values())

    @property
    def formula_check(self) -> float:
        """SE / RATIO + CE should equal I_clean."""
        if RATIO == 0:
            return 0.0
        return self.se_total / RATIO + self.ce_total


class Company:
    """Represents one company with daily income and the full monthly ledger."""

    def __init__(self, name: str):
        self.name = name
        self.ledger: dict[int, DayLedger] = {}

    def add_day(self, day: int, raw_income: int):
        self.ledger[day] = DayLedger(day, raw_income)

    def get_day(self, day: int) -> DayLedger:
        return self.ledger[day]

    @property
    def days(self) -> list[int]:
        return sorted(self.ledger.keys())

    @property
    def total_cleaned_income(self) -> int:
        return sum(dl.cleaned_income for dl in self.ledger.values())

    @property
    def total_se(self) -> int:
        return sum(dl.se_total for dl in self.ledger.values())

    @property
    def total_ce(self) -> int:
        return sum(dl.ce_total for dl in self.ledger.values())
