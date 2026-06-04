"""
Salary Planner - Windows Launcher
Entry point for the PyInstaller-packaged app.
Starts the Streamlit server and opens the browser.
"""
import os
import sys
import socket
import shutil
import threading
import webbrowser
from pathlib import Path


def _find_free_port(start: int = 8501) -> int:
    """Find a free port starting from `start`."""
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return 8501  # fallback


def _get_app_dir() -> str:
    """
    Get the directory where the .exe (or script) is located.
    This is where data/ and output/ live.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def _get_bundle_dir() -> str:
    """Get the directory containing bundled resources (sys._MEIPASS)."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


def main():
    app_dir = _get_app_dir()
    bundle_dir = _get_bundle_dir()

    # Change to the app directory so relative paths in gui.py work
    os.chdir(app_dir)

    # Ensure data/ and output/ directories exist
    for d in ["data", "output"]:
        os.makedirs(os.path.join(app_dir, d), exist_ok=True)

    # Copy default data files from bundle to app_dir/data/ if they don't exist
    bundle_data = os.path.join(bundle_dir, "data")
    cwd_data = os.path.join(app_dir, "data")
    if os.path.isdir(bundle_data) and os.path.normpath(bundle_data) != os.path.normpath(cwd_data):
        for fname in os.listdir(bundle_data):
            src = os.path.join(bundle_data, fname)
            dst = os.path.join(cwd_data, fname)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"[init] Created default: data/{fname}")

    # Add bundle_dir to sys.path so gui.py can import src/*
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)

    # Find gui.py in the bundle
    gui_path = os.path.join(bundle_dir, "gui.py")
    if not os.path.isfile(gui_path):
        gui_path = os.path.join(app_dir, "gui.py")
    if not os.path.isfile(gui_path):
        print(f"ERROR: Cannot find gui.py (looked in {bundle_dir} and {app_dir})")
        sys.exit(1)

    port = _find_free_port()

    # Banner
    print(f"""
╔══════════════════════════════════════════════╗
║    Monthly Salary Planner  月度工资计划器     ║
║                                              ║
║  Opening browser at http://localhost:{port:<5}     ║
║                                              ║
║  Close this window to stop the server         ║
╚══════════════════════════════════════════════╝
""")
    sys.stdout.flush()

    # Set Streamlit config BEFORE importing streamlit
    os.environ["STREAMLIT_SERVER_PORT"] = str(port)
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    os.environ["STREAMLIT_SERVER_ENABLE_CORS"] = "false"
    os.environ["STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION"] = "false"
    os.environ["STREAMLIT_SERVER_RUN_ON_SAVE"] = "false"
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"  # Disable file watching entirely

    # Open browser after a short delay
    def _open_browser():
        import time
        time.sleep(2.0)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=_open_browser, daemon=True).start()

    # Use streamlit's bootstrap to run gui.py directly (no subprocess)
    import streamlit.web.bootstrap as bootstrap
    from streamlit import config as _config

    # Override config programmatically
    _config.set_option("server.port", port)
    _config.set_option("server.headless", True)
    _config.set_option("browser.gatherUsageStats", False)
    _config.set_option("global.developmentMode", False)
    _config.set_option("server.enableCORS", False)
    _config.set_option("server.enableXsrfProtection", False)
    _config.set_option("server.runOnSave", False)
    _config.set_option("server.fileWatcherType", "none")

    # Run the app
    bootstrap.run(gui_path, is_hello=False, args=[], flag_options={})


if __name__ == "__main__":
    main()
