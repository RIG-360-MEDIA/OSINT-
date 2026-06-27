@echo off
REM Auto-start launcher for the RIG Instagram relay.
REM Runs on the local machine (residential IP) so Hetzner can fetch
REM Instagram profile posts without hitting datacenter IP blocks.
REM Add to Windows Task Scheduler: trigger = At logon, action = this file.
set "INSTA_SESSIONID=49722532349:d77wYnHIHqduGq:4:AYjlIuGU9orF6chWVRQNUWXpCBTrFZEX-TfCKxsCFQ"
start "" "C:\Users\Dell\AppData\Local\Programs\Python\Python311\pythonw.exe" "C:\Users\Dell\Desktop\rig-surveillance\backend\collectors\instagram_relay.py"
