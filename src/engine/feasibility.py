"""Pre-flight SE feasibility check."""
import logging
from src.config import RATIO
from src.models.company import Company
from src.models.employee import SelfEmployedEmployee

logger = logging.getLogger(__name__)


def compute_totals(
    se_workers: list[SelfEmployedEmployee],
    companies: dict[str, Company],
) -> tuple[int, float, int]:
    """Return (total_I_clean, max_SE_possible, sum_SE_targets)."""
    total_clean = sum(
        dl.cleaned_income
        for company in companies.values()
        for dl in company.ledger.values()
    )
    max_se = total_clean * RATIO
    sum_targets = sum(w.salary for w in se_workers)
    return total_clean, max_se, sum_targets


def check_se_feasibility(
    se_workers: list[SelfEmployedEmployee],
    companies: dict[str, Company],
) -> bool:
    """
    Returns True if SE targets are achievable (sum_targets <= 0.4 * total_I_clean).
    Logs a loud WARNING and returns False otherwise.
    """
    total_clean, max_se, sum_targets = compute_totals(se_workers, companies)
    if sum_targets > max_se:
        gap = sum_targets - max_se
        logger.warning("=" * 60)
        logger.warning("SE TARGETS INFEASIBLE — falling back to best-effort mode")
        logger.warning(f"  SE targets needed : {sum_targets:,.0f}")
        logger.warning(f"  Max SE possible   : {max_se:,.0f}  (0.4 × total I_clean {total_clean:,})")
        logger.warning(f"  Shortfall gap     : {gap:,.0f}")
        logger.warning("=" * 60)
        return False
    return True
