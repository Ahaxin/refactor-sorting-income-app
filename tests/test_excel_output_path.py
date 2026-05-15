"""Tests that generate_report writes to a caller-supplied path."""
import os
import random
from src.reports.excel_writer import generate_report
from src.engine.feasibility import check_se_feasibility
from src.engine.ce_planner import plan_ce
from src.engine.se_scheduler import schedule_se
from src.engine.salary_solver import solve_salaries


def _run_and_report(scenario, seed, output_path):
    import copy
    s = copy.deepcopy(scenario)
    rng = random.Random(seed)
    check_se_feasibility(s["se_workers"], s["companies"])
    for company in s["companies"].values():
        for day in company.days:
            s["companies"][company.name].get_day(day).compute_se_target_from_ce(0)
    schedule_se(s["se_workers"], s["companies"], rng)
    solve_salaries(s["se_workers"], s["companies"], rng)
    plan_ce(s["ce_workers"], s["companies"], rng)
    generate_report(
        s["se_workers"], s["ce_workers"], s["companies"],
        seed=seed, output_path=output_path,
    )


def test_generate_report_writes_to_custom_path(tmp_path, simple_scenario):
    output_path = str(tmp_path / "report_seed42_20260515_120000.xlsx")
    _run_and_report(simple_scenario, seed=42, output_path=output_path)
    assert os.path.exists(output_path)


def test_generate_report_default_path_still_works(tmp_path, simple_scenario, monkeypatch):
    import src.config as cfg
    default_path = str(tmp_path / "output" / "report.xlsx")
    monkeypatch.setattr(cfg, "OUTPUT_FILE", default_path)
    import importlib, src.reports.excel_writer as ew
    importlib.reload(ew)
    _run_and_report(simple_scenario, seed=42, output_path=None)
    assert os.path.exists(default_path)
