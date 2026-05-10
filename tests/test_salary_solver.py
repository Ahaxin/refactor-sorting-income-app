"""Tests for the SE salary solver — exact monthly targets."""
import math
import random
import pytest
from src.models.company import Company
from src.models.employee import SelfEmployedEmployee
from src.config import GOOD_LIFE, TIANYUAN, MIN_SALARY, MAX_SALARY, SE_SALARY_UNIT


def _make_scenario(n_days, incomes_gl, se_targets):
    rng = random.Random(99)
    gl = Company(GOOD_LIFE)
    for d, inc in enumerate(incomes_gl, start=1):
        gl.add_day(d, inc)
        gl.get_day(d).compute_se_target_from_ce(0)
    companies = {GOOD_LIFE: gl, TIANYUAN: Company(TIANYUAN)}
    workers = []
    for i, tgt in enumerate(se_targets):
        w = SelfEmployedEmployee(f"W{i}", tgt)
        w.preferences = {GOOD_LIFE: {d: 2 for d in range(1, n_days + 1)}, TIANYUAN: {}}
        workers.append(w)
    return workers, companies, rng


def test_solver_hits_exact_monthly_targets():
    from src.engine.se_scheduler import schedule_se
    from src.engine.salary_solver import solve_salaries
    # 2 workers × 800 = 1600 total; 2 days × SE_day_target 800 = 1600 total (consistent)
    # Both workers work both days, each gets 400/day → 800/month exactly
    workers, companies, rng = _make_scenario(2, [2000] * 2, [800, 800])
    schedule_se(workers, companies, rng)
    solve_salaries(workers, companies, rng)
    for w in workers:
        assert w.actual_monthly_salary == w.salary, \
            f"{w.name}: actual={w.actual_monthly_salary} target={w.salary}"


def test_solver_satisfies_daily_column_sums():
    from src.engine.se_scheduler import schedule_se
    from src.engine.salary_solver import solve_salaries
    workers, companies, rng = _make_scenario(2, [2000] * 2, [800, 800])
    schedule_se(workers, companies, rng)
    solve_salaries(workers, companies, rng)
    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            if dl.se_day_target > 0:
                assert dl.se_total == dl.se_day_target, \
                    f"{company.name} day {day}: se_total={dl.se_total} target={dl.se_day_target}"


def test_solver_individual_salaries_in_bounds():
    from src.engine.se_scheduler import schedule_se
    from src.engine.salary_solver import solve_salaries
    workers, companies, rng = _make_scenario(2, [2000] * 2, [800, 800])
    schedule_se(workers, companies, rng)
    solve_salaries(workers, companies, rng)
    for w in workers:
        for (c, d), sal in w.schedule.items():
            assert MIN_SALARY <= sal <= MAX_SALARY, f"{w.name} day {d}: {sal} out of [120,400]"
            assert sal % SE_SALARY_UNIT == 0, f"{w.name} day {d}: {sal} not even"


def test_solver_deterministic():
    from src.engine.se_scheduler import schedule_se
    from src.engine.salary_solver import solve_salaries
    workers1, companies1, rng1 = _make_scenario(2, [2000] * 2, [800, 800])
    workers2, companies2, rng2 = _make_scenario(2, [2000] * 2, [800, 800])
    schedule_se(workers1, companies1, rng1)
    schedule_se(workers2, companies2, rng2)
    solve_salaries(workers1, companies1, rng1)
    solve_salaries(workers2, companies2, rng2)
    for w1, w2 in zip(workers1, workers2):
        assert w1.schedule == w2.schedule


def test_repair_swap_lets_worker_hit_target_when_all_days_at_column_cap():
    """Worker hits monthly target via co-worker swap when all shared days are at col_target."""
    from src.engine.salary_solver import _repair
    # Setup: Worker A works Day 1 only (target=202).
    # Worker B works Days 1 and 2 (target=490).
    # After Sinkhorn: Day 1 is at col_target (A=200, B=200). Day 2 has headroom (B=290 < 300).
    # Without swap: A can't add to Day 1 (col would exceed target). A stays at 200 ≠ 202.
    # With swap: reduce B on Day 1 by 2 → B=198, increase A → 202. B recovers 2 on Day 2.
    gl = Company(GOOD_LIFE)
    gl.add_day(1, 1000)   # se_day_target = 400
    gl.add_day(2, 750)    # se_day_target = 300
    for d in gl.days:
        gl.get_day(d).compute_se_target_from_ce(0)
    companies = {GOOD_LIFE: gl}

    a = SelfEmployedEmployee("A", 202)
    a.schedule = {(GOOD_LIFE, 1): 0}

    b = SelfEmployedEmployee("B", 490)
    b.schedule = {(GOOD_LIFE, 1): 0, (GOOD_LIFE, 2): 0}

    matrix = {
        ("A", GOOD_LIFE, 1): 200,
        ("B", GOOD_LIFE, 1): 200,   # col1 sum=400=target, no direct headroom for A
        ("B", GOOD_LIFE, 2): 290,   # col2 sum=290<300, B can recover here after swap
    }
    slots = {
        (GOOD_LIFE, 1): [a, b],
        (GOOD_LIFE, 2): [b],
    }

    _repair(matrix, [a, b], slots, companies)

    assert matrix[("A", GOOD_LIFE, 1)] == 202, \
        f"A should reach target 202 via swap, got {matrix[('A', GOOD_LIFE, 1)]}"
    a_total = matrix[("A", GOOD_LIFE, 1)]
    b_total = matrix[("B", GOOD_LIFE, 1)] + matrix[("B", GOOD_LIFE, 2)]
    assert a_total == 202, f"A monthly total {a_total} != target 202"
    assert b_total == 490, f"B monthly total {b_total} != target 490"
