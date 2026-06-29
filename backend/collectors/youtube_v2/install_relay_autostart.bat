@echo off
REM ============================================================================
REM  Installs the "RIG YouTube Relay" auto-start task (runs the relay at logon).
REM  RUN THIS ONCE, AS ADMINISTRATOR  (right-click -> Run as administrator).
REM  After this, the relay launches automatically every time you log in, and
REM  retries 3x if it fails to start.
REM ============================================================================
setlocal
set "BAT=C:\Users\Dell\Desktop\rig-surveillance\backend\collectors\youtube_v2\start_relay.bat"

schtasks /Create /TN "RIG YouTube Relay" /SC ONLOGON /RL HIGHEST /F ^
  /TR "cmd /c \"%BAT%\""

if %ERRORLEVEL%==0 (
  echo.
  echo  [OK] "RIG YouTube Relay" task created — relay will auto-start at logon.
  echo  Starting it now as well...
  call "%BAT%"
) else (
  echo.
  echo  [FAILED] Could not create the task. Make sure you ran this AS ADMINISTRATOR.
)
echo.
pause
