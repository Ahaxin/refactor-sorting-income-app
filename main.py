"""
Monthly Work/Salary Plan Generator
"""

import argparse
import logging
import os
import random
import sys

from src.config import OUTPUT_FILE
from src.loaders.data_loader import load_all
from src.engine.feasibility import check_se_feasibility
from src.engine.ce_planner import plan_ce
from src.engine.se_scheduler import schedule_se
from src.engine.salary_solver import solve_salaries
from src.reports.excel_writer import generate_report


def _resolve_seed(args) -> tuple[int, str]:
    if args.seed is not None:
        return args.seed, "from --seed"
    env_val = os.environ.get("SALARY_SEED")
    if env_val is not None:
        return int(env_val), "from SALARY_SEED env var"
    seed = random.SystemRandom().randrange(2 ** 32)
    return seed, "auto-generated"


def setup_logging() -> None:
    os.makedirs("output", exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("output/run.log", mode="w", encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Monthly salary plan generator")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Monthly Work/Salary Plan Generator — starting")

    seed, provenance = _resolve_seed(args)
    logger.info(f"Random seed: {seed} ({provenance})")
    rng = random.Random(seed)

    # 1. Load data
    se_workers, ce_workers, companies = load_all()

    # 2. Pre-flight feasibility check
    check_se_feasibility(se_workers, companies)

    # 3. SE day targets (assume CE = 0 for scheduling phase)
    for company in companies.values():
        for day in company.days:
            dl = company.get_day(day)
            dl.compute_se_target_from_ce(0)

    # 4. SE schedule
    schedule_se(se_workers, companies, rng)

    # 5. SE salary solver
    solve_salaries(se_workers, companies, rng)

    # 6. CE plan (formula residual after SE)
    plan_ce(ce_workers, companies, rng)

    # 7. Generate report
    generate_report(se_workers, ce_workers, companies, seed=seed)

    logger.info(f"Done. Output written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
