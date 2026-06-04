@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==============================================
echo   Monthly Salary Planner ^(YueDu GongZi JiHuaQi^)
echo ==============================================
echo.
echo Starting server... Browser will open automatically.
echo Close this window to stop the server.
echo.

start "" http://localhost:8501

streamlit run gui.py --server.port 8501 --server.headless true --browser.gatherUsageStats false --global.developmentMode false

pause
