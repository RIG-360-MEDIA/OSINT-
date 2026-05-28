@echo off
REM Start the boss's Morning Brief locally on http://localhost:5173
REM Uses Python's built-in HTTP server. Press Ctrl+C to stop.

cd /d "%~dp0"
echo.
echo ======================================================
echo  Boss's Morning Brief — local dev server
echo  Open http://localhost:5173 in your browser
echo  Press Ctrl+C in this window to stop
echo ======================================================
echo.
py -3 -m http.server 5173
