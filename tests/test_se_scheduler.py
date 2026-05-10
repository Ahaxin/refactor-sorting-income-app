"""Tests for SE scheduler."""
import math
import random
import pytest
from src.models.company import Company
from src.models.employee import SelfEmployedEmployee
from src.config import GOOD_LIFE, TIANYUAN


def _setup():
    rng = random.Random(42)
    gl = Company(GOOD_LIFE)
    ty = Company(TIANYUAN)
    for d in range(1, 6):
        gl.add_day(d, 2000)
        ty.add_day(d, 1500)
    companies = {GOOD_LIFE: gl, TIANYUAN: ty}

    # Compute SE targets for each day (CE = 0 on all days)
    for c in companies.values():
        for d in c.days:
            c.get_day(d).compute_se_target_from_ce(0)

    w1 = SelfEmployedEmployee("Alice", 400)
    w1.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {}}
    w2 = SelfEmployedEmployee("Bob", 400)
    w2.preferences = {GOOD_LIFE: {d: 1 for d in range(1, 6)}, TIANYUAN: {}}
    return [w1, w2], companies, rng


def test_se_workers_assigned_enough_days():
    """Each SE worker gets at least min_days = ceil(target/400) days."""
    from src.engine.se_scheduler import schedule_se
    workers, companies, rng = _setup()
    schedule_se(workers, companies, rng)
    for w in workers:
        min_days = math.ceil(w.salary / 400)
        assert w.assigned_days >= min_days, f"{w.name}: {w.assigned_days} < {min_days}"


def test_no_double_booking():
    """No worker appears at two companies on the same day."""
    from src.engine.se_scheduler import schedule_se
    workers, companies, rng = _setup()
    schedule_se(workers, companies, rng)
    for w in workers:
        days_worked = [d for (_, d) in w.schedule]
        assert len(days_worked) == len(set(days_worked)), f"{w.name} double-booked"


def test_workers_respect_preferences():
    """Workers only appear on days where P > 0."""
    from src.engine.se_scheduler import schedule_se
    workers, companies, rng = _setup()
    schedule_se(workers, companies, rng)
    for w in workers:
        for (company, day) in w.schedule:
            pref = w.preferences.get(company, {}).get(day, 0)
            assert pref > 0, f"{w.name} assigned to {company} day {day} with P=0"


def test_schedule_is_deterministic():
    """Same seed → same schedule."""
    from src.engine.se_scheduler import schedule_se

    def make_scenario():
        gl = Company(GOOD_LIFE)
        for d in range(1, 6):
            gl.add_day(d, 2000)
            gl.get_day(d).compute_se_target_from_ce(0)
        companies = {GOOD_LIFE: gl, TIANYUAN: Company(TIANYUAN)}
        w = SelfEmployedEmployee("Alice", 400)
        w.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {}}
        return [w], companies

    workers1, companies1 = make_scenario()
    workers2, companies2 = make_scenario()
    schedule_se(workers1, companies1, random.Random(99))
    schedule_se(workers2, companies2, random.Random(99))
    assert workers1[0].schedule == workers2[0].schedule


def test_min_days_computed_from_predefined_daily():
    """Scheduler sets min_days = ceil(salary/PREDEFINED_DAILY), not ceil(salary/MAX_SALARY)."""
    from src.engine.se_scheduler import schedule_se
    from src.config import PREDEFINED_DAILY
    gl = Company(GOOD_LIFE)
    for d in range(1, 8):
        gl.add_day(d, 2000)
        gl.get_day(d).compute_se_target_from_ce(0)
    companies = {GOOD_LIFE: gl, TIANYUAN: Company(TIANYUAN)}
    w = SelfEmployedEmployee("Sisi", 400)
    w.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 8)}, TIANYUAN: {}}
    schedule_se([w], companies, random.Random(42))
    expected_min = math.ceil(w.salary / PREDEFINED_DAILY)  # ceil(400/180) = 3
    assert w.min_days == expected_min, \
        f"min_days should be {expected_min} (ceil(salary/PREDEFINED_DAILY)), got {w.min_days}"


def test_fill_budget_deficient_adds_extra_slot():
    """Worker gets an extra slot when max achievable salary < target on current schedule."""
    from src.engine.se_scheduler import _fill_budget_deficient
    from src.config import PREDEFINED_DAILY, MIN_SALARY
    # Days 1-3: Yang+Ling share (se_target=260). Yang earns at most 140/day.
    # Day 4: Yang alone (se_target=300). Available extra slot.
    # Pre-assign Yang to days 1,2,3 → max_achievable = (260-120)*3 = 420 < 500 = target.
    gl = Company(GOOD_LIFE)
    for d in [1, 2, 3]:
        gl.add_day(d, 650)
        gl.get_day(d).compute_se_target_from_ce(0)
    gl.add_day(4, 750)
    gl.get_day(4).compute_se_target_from_ce(0)
    companies = {GOOD_LIFE: gl, TIANYUAN: Company(TIANYUAN)}

    yang = SelfEmployedEmployee("Yang", 500)
    yang.preferences = {GOOD_LIFE: {1: 2, 2: 2, 3: 2, 4: 2}, TIANYUAN: {}}
    yang.min_days = math.ceil(yang.salary / PREDEFINED_DAILY)
    yang.max_days = math.floor(yang.salary / MIN_SALARY)
    yang.target_days = yang.min_days
    yang.schedule = {(GOOD_LIFE, 1): 0, (GOOD_LIFE, 2): 0, (GOOD_LIFE, 3): 0}

    ling = SelfEmployedEmployee("Ling", 360)
    ling.preferences = {GOOD_LIFE: {1: 2, 2: 2, 3: 2}, TIANYUAN: {}}
    ling.min_days = math.ceil(ling.salary / PREDEFINED_DAILY)
    ling.max_days = math.floor(ling.salary / MIN_SALARY)
    ling.target_days = ling.min_days
    ling.schedule = {(GOOD_LIFE, 1): 0, (GOOD_LIFE, 2): 0, (GOOD_LIFE, 3): 0}

    _fill_budget_deficient([yang, ling], companies, random.Random(42), [yang, ling])

    assert (GOOD_LIFE, 4) in yang.schedule, (
        f"Yang should be assigned Day 4 to cover budget deficit "
        f"(max_achievable 420 < target 500)"
    )
