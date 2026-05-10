"""Integration tests: math invariants, determinism, infeasible fallback."""
import random
import pytest
from src.engine.feasibility import check_se_feasibility
from src.engine.ce_planner import plan_ce
from src.engine.se_scheduler import schedule_se
from src.engine.salary_solver import solve_salaries
from src.models.employee import SelfEmployedEmployee, CompanyEmployedEmployee
from src.models.company import Company
from src.config import GOOD_LIFE, TIANYUAN, MIN_SALARY, MAX_SALARY


def _run_pipeline(scenario, seed):
    import copy
    s = copy.deepcopy(scenario)
    rng = random.Random(seed)
    check_se_feasibility(s["se_workers"], s["companies"])
    for company in s["companies"].values():
        for day in company.days:
            dl = company.get_day(day)
            dl.compute_se_target_from_ce(0)
    schedule_se(s["se_workers"], s["companies"], rng)
    solve_salaries(s["se_workers"], s["companies"], rng)
    plan_ce(s["ce_workers"], s["companies"], rng)
    return s


def _make_balanced_scenario():
    """
    2 SE workers × target 800, 2 GL days × SE_target 800.
    Total row = total col = 1600. Solver must assign 400/slot.
    No CE, so formula is clean.
    """
    gl = Company(GOOD_LIFE)
    for d in range(1, 3):
        gl.add_day(d, 2000)
    companies = {GOOD_LIFE: gl, TIANYUAN: Company(TIANYUAN)}

    se1 = SelfEmployedEmployee("Alice", 800)
    se1.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 3)}, TIANYUAN: {}}
    se2 = SelfEmployedEmployee("Bob", 800)
    se2.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 3)}, TIANYUAN: {}}

    return {"se_workers": [se1, se2], "ce_workers": [], "companies": companies}


def test_se_no_shortfall():
    """Every SE worker hits their monthly target exactly in a balanced scenario."""
    s = _run_pipeline(_make_balanced_scenario(), seed=42)
    for w in s["se_workers"]:
        assert w.actual_monthly_salary == w.salary, \
            f"{w.name}: actual={w.actual_monthly_salary} target={w.salary}"


def test_per_day_formula_exact():
    """For every day where SE workers are assigned, SE_total == SE_day_target."""
    s = _run_pipeline(_make_balanced_scenario(), seed=42)
    for company in s["companies"].values():
        for day in company.days:
            dl = company.get_day(day)
            if dl.is_full_ce_absorption or dl.se_total == 0:
                continue
            assert dl.se_total == dl.se_day_target, \
                f"{company.name} day {day}: se={dl.se_total} target={dl.se_day_target}"


def test_determinism(simple_scenario):
    """Same seed → identical results."""
    s1 = _run_pipeline(simple_scenario, seed=777)
    s2 = _run_pipeline(simple_scenario, seed=777)
    for w1, w2 in zip(s1["se_workers"], s2["se_workers"]):
        assert w1.schedule == w2.schedule, f"{w1.name} schedule differs"
    for w1, w2 in zip(s1["ce_workers"], s2["ce_workers"]):
        assert w1.schedule == w2.schedule, f"{w1.name} schedule differs"


def test_different_seeds_produce_different_schedules(simple_scenario):
    """Different seeds produce different SE assignments."""
    results = set()
    for seed in range(10):
        s = _run_pipeline(simple_scenario, seed=seed)
        key = tuple(sorted(s["se_workers"][0].schedule.items()))
        results.add(key)
    assert len(results) > 1, "All seeds produced identical schedules"


def test_infeasible_se_fallback(caplog):
    """When SE targets > 0.4 * total_I_clean, warns loudly and continues."""
    import logging
    gl = Company(GOOD_LIFE)
    gl.add_day(1, 500)
    companies = {GOOD_LIFE: gl, TIANYUAN: Company(TIANYUAN)}
    se = [SelfEmployedEmployee("X", 500)]
    se[0].preferences = {GOOD_LIFE: {1: 2}, TIANYUAN: {}}
    with caplog.at_level(logging.WARNING):
        result = check_se_feasibility(se, companies)
    assert result is False
    assert "infeasible" in caplog.text.lower()


def test_ce_non_negativity(simple_scenario):
    """No CE salary is negative."""
    s = _run_pipeline(simple_scenario, seed=42)
    for company in s["companies"].values():
        for day in company.days:
            dl = company.get_day(day)
            assert dl.ce_total >= 0
            for amt in dl.ce_salaries.values():
                assert amt >= 0


def test_se_no_shortfall_with_ce_workers(simple_scenario):
    """SE workers hit exact monthly targets even when CE workers are present."""
    s = _run_pipeline(simple_scenario, seed=42)
    for w in s["se_workers"]:
        assert w.actual_monthly_salary == w.salary, \
            f"{w.name}: actual={w.actual_monthly_salary} target={w.salary}"


def test_se_never_exceeds_day_target(simple_scenario):
    """SE_total on any assigned day never exceeds SE_day_target (column upper bound)."""
    s = _run_pipeline(simple_scenario, seed=42)
    for company in s["companies"].values():
        for day in company.days:
            dl = company.get_day(day)
            if dl.se_total == 0:
                continue
            assert dl.se_total <= dl.se_day_target, (
                f"{company.name} day {day}: SE_total={dl.se_total} "
                f"> SE_day_target={dl.se_day_target}"
            )


def test_no_per_day_formula_deviation():
    """SE/0.4 + CE equals I_clean exactly on every day when CE provides full coverage."""
    gl = Company(GOOD_LIFE)
    for d, inc in enumerate([2000, 2500, 1500, 3000, 1800], start=1):
        gl.add_day(d, inc)
        gl.get_day(d).compute_se_target_from_ce(0)
    companies = {GOOD_LIFE: gl, TIANYUAN: Company(TIANYUAN)}

    se1 = SelfEmployedEmployee("Alice", 600)
    se1.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {}}
    se2 = SelfEmployedEmployee("Bob", 400)
    se2.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {}}

    ce = CompanyEmployedEmployee("Zhong", 9000)
    ce.exclusive_company = GOOD_LIFE
    ce.preferences = {GOOD_LIFE: {d: 2 for d in range(1, 6)}, TIANYUAN: {}}

    rng = random.Random(42)
    schedule_se([se1, se2], companies, rng)
    solve_salaries([se1, se2], companies, rng)
    plan_ce([ce], companies, rng)

    for day in gl.days:
        dl = gl.get_day(day)
        formula_val = round(dl.formula_check)
        assert formula_val == dl.cleaned_income, (
            f"Day {day}: SE/0.4+CE={formula_val} != I_clean={dl.cleaned_income} "
            f"(SE_total={dl.se_total}, CE_total={dl.ce_total}, "
            f"SE_target={dl.se_day_target})"
        )


def test_no_bare_random_calls():
    """All randomness in engine files goes through a named rng instance, not bare random.*."""
    import pathlib, re
    bare_pattern = re.compile(r'\brandom\.(random|randint|shuffle|choice|sample|uniform|seed)\s*\(')
    engine_dir = pathlib.Path("src/engine")
    violations = []
    for py_file in engine_dir.glob("*.py"):
        for lineno, line in enumerate(py_file.read_text(encoding='utf-8').splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            m = bare_pattern.search(line)
            if m:
                before = line[:m.start()].rstrip()
                if not before.endswith("."):
                    violations.append(f"{py_file}:{lineno}: {stripped}")
    assert not violations, "Bare random.* calls found:\n" + "\n".join(violations)
