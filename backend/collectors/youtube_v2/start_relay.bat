@echo off
REM Auto-start launcher for the RIG YouTube transcript relay (authenticated).
REM Sets the burner-cookie path explicitly so the relay always comes up authenticated,
REM then launches it windowless (pythonw) and detached. Invoked by the "RIG YouTube Relay"
REM scheduled task at logon.
set "YT_COOKIES=D:\www.youtube.com_cookies (2).txt"
start "" "C:\Users\Dell\AppData\Local\Programs\Python\Python311\pythonw.exe" "C:\Users\Dell\Desktop\rig-surveillance\backend\collectors\youtube_v2\transcript_relay.py"
