"""
Monthly Work/Salary Plan Generator
"""

import argparse
import logging
import os
import random
import sys
from datetime import datetime

from src.config import OUTPUT_DIR
from src.loaders.data_loader import load_all
from src.engine.feasibility import check_se_feasibility
from src.engine.exact_solver import solve_exact
from src.engine.diversify import (
    diversify_schedule, verify_schedule, snapshot_schedules, restore_schedules,
)
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
    parser.add_argument("--variation", type=int, default=15,
                        help="diversification band as %% of the legal pay range (0 disables)")
    parser.add_argument("--se-min", type=int, default=None,
                        help="concentrate knob: min SE daily pay on a worked day "
                             "(default: config MIN_SALARY); higher = fewer, richer days")
    parser.add_argument("--scatter", action="store_true",
                        help="randomize the solver objective (uses the run seed) so "
                             "daily SE pay spreads out instead of piling at the floor")
    args = parser.parse_args()
    variation = max(0, min(50, args.variation))

    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Monthly Work/Salary Plan Generator — starting")

    seed, provenance = _resolve_seed(args)
    logger.info(f"Random seed: {seed} ({provenance})")

    # 1. Load data
    se_workers, ce_workers, companies = load_all()

    # 2. Pre-flight feasibility check
    check_se_feasibility(se_workers, companies)

    # 3. Exact joint SE+CE solve (deterministic — replaces schedule/solve/CE-plan)
    report = solve_exact(se_workers, ce_workers, companies, se_min_per_day=args.se_min,
                         scatter_seed=(seed if args.scatter else None))
    if not report.perfect:
        logger.warning(
            f"Solver could not fully satisfy all constraints: "
            f"{len(report.shortfalls)} shortfall(s), {len(report.deviations)} deviation(s)."
        )

    # 3b. Post-tuning: diversify duplicate salaries within a +/-% band, then
    # re-check. Revert to the solved schedule if anything regressed.
    if variation > 0:
        snap = snapshot_schedules(se_workers, ce_workers, companies)
        diversify_schedule(se_workers, ce_workers, companies,
                           pct=variation / 100, seed=seed, se_min=args.se_min)
        vr = verify_schedule(se_workers, ce_workers, companies, se_min=args.se_min)
        if vr.regressed_from(report.deviations, report.shortfalls):
            restore_schedules(snap, se_workers, ce_workers, companies)
            logger.warning("Post-tuning checks regressed — reverted to solved schedule.")
        else:
            logger.info("Post-tuning diversification applied — checks passed.")

    # 4. Generate report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"report_seed{seed}_{timestamp}.xlsx")
    generate_report(se_workers, ce_workers, companies, seed=seed, output_path=output_path)

    logger.info(f"Done. Output written to: {output_path}")


if __name__ == "__main__":
    main()
