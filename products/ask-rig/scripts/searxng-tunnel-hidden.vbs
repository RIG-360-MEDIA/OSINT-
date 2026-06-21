' Launches the SearXNG tunnel loop completely hidden (no console window).
' The third Run arg 0 = hidden, False = don't wait. Called by the
' "RIG SearXNG Tunnel" Scheduled Task at logon.
Set sh = CreateObject("WScript.Shell")
sh.Run """C:\Program Files\Git\usr\bin\bash.exe"" -lc ""/c/Users/Dell/Desktop/rig-surveillance/products/ask-rig/scripts/searxng-tunnel.sh >> /c/Users/Dell/.searxng-tunnel.log 2>&1""", 0, False
