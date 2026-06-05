"""
Configuration constants for the monthly salary/schedule planner.
"""

# Salary granularity
SE_SALARY_UNIT = 2    # SE individual daily salary must be even integer
CE_SALARY_UNIT = 5    # CE individual daily salary must be multiple of 5
INCOME_UNIT = 5       # I_clean rounded to multiple of 5

# Salary bounds for SE workers (per day). CE has no per-day lower bound.
MIN_SALARY = 120
MAX_SALARY = 400      # SE individual per-day cap
CE_MAX_PER_DAY = 500  # CE individual per-day cap (allowed higher than SE)

# Used to estimate preferred number of working days per SE worker
PREDEFINED_DAILY = 180

# Sinkhorn solver settings
SOLVER_MAX_ITER = 500
SOLVER_TOL = 1e-1

# The 40% profit-sharing ratio
RATIO = 0.40

# Data file paths
DATA_DIR = "data"
EMPLOYEE_FILE = f"{DATA_DIR}/employee_data.csv"
INCOME_FILE = f"{DATA_DIR}/income_data.csv"
SE_PREFERENCE_FILE = f"{DATA_DIR}/se_preference.csv"
CE_PREFERENCE_FILE = f"{DATA_DIR}/ce_preference.csv"

# Output
OUTPUT_DIR = "output"
OUTPUT_FILE = f"{OUTPUT_DIR}/report.xlsx"

# Company name constants
GOOD_LIFE = "good_life"
TIANYUAN = "tianyuan"
COMPANY_NAMES = [GOOD_LIFE, TIANYUAN]

# Employee type constants
TYPE_SELF_EMPLOYED = "Self-Employed"
TYPE_COMPANY_EMPLOYED = "Company-Employed"
