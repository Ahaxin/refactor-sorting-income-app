"""
Employee model classes for self-employed and company-employed workers.
"""

import math
from src.config import (
    PREDEFINED_DAILY,
    TYPE_SELF_EMPLOYED, TYPE_COMPANY_EMPLOYED,
)


class Employee:
    """Base class for all employees."""

    def __init__(self, name: str, emp_type: str, salary: int):
        self.name = name
        self.emp_type = emp_type
        self.salary = salary          # monthly target (SE) or monthly cap (CE)
        self.exclusive_company: str | None = None   # set by loader from preferences.csv
        self.preferred_company: str | None = None   # set by loader from preferences.csv
        # preferences[company][day] = 0 | 1 | 2  — populated by data_loader
        self.preferences: dict[str, dict[int, int]] = {}

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name!r})"


class SelfEmployedEmployee(Employee):
    """
    A self-employed worker whose monthly salary must exactly equal `salary`
    and whose individual daily pay must be in [MIN_SALARY, MAX_SALARY] (multiples of SALARY_UNIT).
    """

    def __init__(self, name: str, salary: int):
        super().__init__(name, TYPE_SELF_EMPLOYED, salary)
        # Target number of working days derived from predefined daily rate
        self.target_days: int = math.ceil(salary / PREDEFINED_DAILY)
        # Day-count envelope set by scheduler based on [MIN_SALARY, MAX_SALARY]
        self.min_days: int = 1
        self.max_days: int = salary  # safe upper bound; overwritten by scheduler

        # Filled in by the scheduler / salary solver
        self.schedule: dict[tuple[str, int], int] = {}
        # key: (company, day) → value: daily salary assigned (0 if not yet set)

    @property
    def assigned_days(self) -> int:
        return len(self.schedule)

    @property
    def actual_monthly_salary(self) -> int:
        return sum(self.schedule.values())

    def add_shift(self, company: str, day: int, salary: int = 0):
        """Register a work shift. Salary is filled in by the solver later."""
        self.schedule[(company, day)] = salary

    def remove_shift(self, company: str, day: int):
        self.schedule.pop((company, day), None)

    def is_working_on(self, day: int) -> bool:
        """Return True if this worker is already assigned to any company on `day`."""
        return any(d == day for (_, d) in self.schedule)

    def company_on_day(self, day: int) -> str | None:
        for (c, d) in self.schedule:
            if d == day:
                return c
        return None


class CompanyEmployedEmployee(Employee):
    """
    A company-employed worker paid a fixed daily rate derived from their monthly cap.
    Their pay does NOT go through the 40% SE rule; instead CE salaries reduce the
    base income before the SE budget is computed.
    """

    def __init__(self, name: str, salary: int):
        super().__init__(name, TYPE_COMPANY_EMPLOYED, salary)
        # Filled in by the scheduler after eligible days are determined
        self.daily_rate: int = 0
        self.schedule: dict[tuple[str, int], int] = {}
        # key: (company, day) → daily_rate for that day

    @property
    def assigned_days(self) -> int:
        return len(self.schedule)

    @property
    def actual_monthly_salary(self) -> int:
        return sum(self.schedule.values())

    def add_shift(self, company: str, day: int):
        """Register a CE work shift at the worker's daily_rate."""
        self.schedule[(company, day)] = self.daily_rate

    def is_working_on(self, day: int) -> bool:
        return any(d == day for (_, d) in self.schedule)

    def company_on_day(self, day: int) -> str | None:
        for (c, d) in self.schedule:
            if d == day:
                return c
        return None
