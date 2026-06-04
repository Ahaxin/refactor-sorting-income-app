# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for the Salary Planner Windows application.
Builds a --onedir bundle that includes the Streamlit server + GUI.
"""

import os
import sys
from pathlib import Path

# --- Paths ---
_PROJECT_DIR = Path(r"F:\PROJECTS\refactor_sorting_income_app")
_STREAMLIT_DIR = Path(r"C:\Users\Xin Chang\AppData\Local\Programs\Python\Python311\Lib\site-packages\streamlit")

# --- Streamlit hidden imports ---
# Streamlit has many subpackages that PyInstaller won't auto-detect.
# Use collect_submodules to find them all automatically.
from PyInstaller.utils.hooks import collect_submodules as _collect_submodules, copy_metadata as _copy_metadata
_STREAMLIT_HIDDEN_IMPORTS = _collect_submodules("streamlit")

# --- Collect streamlit static assets ---
_STREAMLIT_DATA = []
_static_src = _STREAMLIT_DIR / "static"
if _static_src.is_dir():
    _STREAMLIT_DATA.append(
        (str(_static_src), os.path.join("streamlit", "static"))
    )

# Also collect the proto stubs
_proto_src = _STREAMLIT_DIR / "proto"
if _proto_src.is_dir():
    _STREAMLIT_DATA.append(
        (str(_proto_src), os.path.join("streamlit", "proto"))
    )

# --- Project data files ---
_PROJECT_DATA = [
    # Data CSV files
    (str(_PROJECT_DIR / "data" / "employee_data.csv"), "data"),
    (str(_PROJECT_DIR / "data" / "income_data.csv"), "data"),
    (str(_PROJECT_DIR / "data" / "updated_preference.csv"), "data"),
    # Source modules
    (str(_PROJECT_DIR / "src"), "src"),
    # GUI entry point (at project root)
    (str(_PROJECT_DIR / "gui.py"), "."),
]

# --- Collect package metadata (dist-info) ---
# Streamlit and its deps use importlib.metadata to check versions at runtime.
# PyInstaller strips these by default, so we must explicitly include them.
_METADATA_PACKAGES = [
    "streamlit",
    "pandas",
    "numpy",
    "openpyxl",
    "altair",
    "pyarrow",
    "pydeck",
    "tornado",
    "watchdog",
    "blinker",
    "cachetools",
    "click",
    "gitpython",
    "pillow",
    "protobuf",
    "pydantic",
    "requests",
    "rich",
    "tenacity",
    "toml",
    "tzlocal",
    "validators",
    "pyyaml",
    "jinja2",
    "markupsafe",
]
_metadata_datas = []
for _pkg in _METADATA_PACKAGES:
    try:
        _metadata_datas.extend(_copy_metadata(_pkg))
    except Exception:
        pass  # package not installed

# --- Analysis overrides ---
a = Analysis(
    [str(_PROJECT_DIR / "run_app.py")],
    pathex=[str(_PROJECT_DIR)],
    binaries=[],
    datas=_STREAMLIT_DATA + _PROJECT_DATA + _metadata_datas,
    hiddenimports=_STREAMLIT_HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "IPython",
        "jupyter",
        "notebook",
        "sympy",
        "sqlalchemy",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SalaryPlanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for log output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SalaryPlanner",
)
