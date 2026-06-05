"""Integration tests that survive the move to the exact solver:
the pre-flight feasibility warning and the engine's no-bare-random discipline.
(Full schedule correctness now lives in test_exact_solver.py.)"""
import logging

from src.engine.feasibility import check_se_feasibility
from src.models.employee import SelfEmployedEmployee
from src.models.company import Company
from src.config import GOOD_LIFE, TIANYUAN


def test_infeasible_se_fallback(caplog):
    """When SE targets > 0.4 * total_I_clean, warns loudly and returns False."""
    gl = Company(GOOD_LIFE)
    gl.add_day(1, 500)
    companies = {GOOD_LIFE: gl, TIANYUAN: Company(TIANYUAN)}
    se = [SelfEmployedEmployee("X", 500)]
    se[0].preferences = {GOOD_LIFE: {1: 1}, TIANYUAN: {}}
    with caplog.at_level(logging.WARNING):
        result = check_se_feasibility(se, companies)
    assert result is False
    assert "infeasible" in caplog.text.lower()


def test_no_bare_random_calls():
    """All randomness in engine files goes through a named rng instance, not bare random.*."""
    import pathlib
    import re
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
