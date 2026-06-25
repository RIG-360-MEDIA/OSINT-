' Launches the durable Postgres tunnel hidden (no console window).
' Third Run arg 0 = hidden, False = don't wait. Used by the Startup item.
Set sh = CreateObject("WScript.Shell")
sh.Run """C:\Program Files\Git\usr\bin\bash.exe"" -lc ""/c/Users/Dell/Desktop/rig-surveillance/products/ask-rig/scripts/postgres-tunnel.sh""", 0, False
