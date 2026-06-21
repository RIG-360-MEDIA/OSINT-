# Installs the Ask-RIG SearXNG tunnel as a per-user Startup item (NO admin needed).
# A hidden .vbs in the user's Startup folder launches the self-healing tunnel loop
# at every logon. Re-run any time to refresh. To remove: delete the file printed below.
$ErrorActionPreference = 'Stop'

$src     = 'C:\Users\Dell\Desktop\rig-surveillance\products\ask-rig\scripts\searxng-tunnel-hidden.vbs'
$startup = [Environment]::GetFolderPath('Startup')          # ...\Start Menu\Programs\Startup
$dest    = Join-Path $startup 'RIG-SearXNG-Tunnel.vbs'

if (-not (Test-Path $src)) { throw "Launcher not found: $src" }

Copy-Item -Path $src -Destination $dest -Force
Write-Host "Installed Startup item: $dest"
Write-Host "Runs hidden at every logon. Log: C:\Users\Dell\.searxng-tunnel.log"
Write-Host "To uninstall: Remove-Item '$dest'"
