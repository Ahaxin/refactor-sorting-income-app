"""Shared test fixtures."""
import random
import pytest
from src.models.company import Company
from src.models.employee import SelfEmployedEmployee, CompanyEmployedEmployee
from src.config import GOOD_LIFE, TIANYUAN


@pytest.fixture
def simple_scenario():
    """
    2 SE workers, 1 CE worker, 5-day month.
    GL income: 2000/day. TY income: 1500/day.
    CE cap: 500 (Zhong → Good Life).
    SE targets: 400+400 = 800. total_clean = 5*(2000+1500) = 17500.
    max_SE = 0.4*17500 = 7000 >> 800. Feasible.
    """
    gl = Company(GOOD_LIFE)
    ty = Company(TIANYUAN)
    for d in range(1, 6):
        gl.add_day(d, 2000)
        ty.add_day(d, 1500)
    companies = {GOOD_LIFE: gl, TIANYUAN: ty}

    se1 = SelfEmployedEmployee("Alice", 400)
    se1.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {d: 1 for d in range(1, 6)}}

    se2 = SelfEmployedEmployee("Bob", 400)
    se2.preferences = {GOOD_LIFE: {d: 1 for d in range(1, 6)}, TIANYUAN: {d: 2 for d in range(1, 6)}}

    ce1 = CompanyEmployedEmployee("Zhong", 500)
    ce1.exclusive_company = GOOD_LIFE
    ce1.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {}}

    return {
        "se_workers": [se1, se2],
        "ce_workers": [ce1],
        "companies": companies,
    }
