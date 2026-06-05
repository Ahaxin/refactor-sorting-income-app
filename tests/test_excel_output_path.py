"""Tests that generate_report writes to a caller-supplied path."""
import copy
import os

from src.reports.excel_writer import generate_report
from src.engine.exact_solver import solve_exact


def _run_and_report(scenario, output_path):
    s = copy.deepcopy(scenario)
    solve_exact(s["se_workers"], s["ce_workers"], s["companies"])
    generate_report(
        s["se_workers"], s["ce_workers"], s["companies"],
        seed=0, output_path=output_path,
    )


def test_generate_report_writes_to_custom_path(tmp_path, simple_scenario):
    output_path = str(tmp_path / "report_20260515_120000.xlsx")
    _run_and_report(simple_scenario, output_path=output_path)
    assert os.path.exists(output_path)


def test_generate_report_default_path_still_works(tmp_path, simple_scenario, monkeypatch):
    import src.reports.excel_writer as ew
    default_path = str(tmp_path / "output" / "report.xlsx")
    monkeypatch.setattr(ew, "OUTPUT_FILE", default_path)
    _run_and_report(simple_scenario, output_path=None)
    assert os.path.exists(default_path)
