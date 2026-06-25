# Installs the durable Postgres (corpus) tunnel as a per-user Startup item (NO admin).
# Hidden .vbs in the Startup folder launches the self-healing loop at every logon.
# Re-run to refresh. To remove: delete the file printed below.
$ErrorActionPreference = 'Stop'

$src     = 'C:\Users\Dell\Desktop\rig-surveillance\products\ask-rig\scripts\postgres-tunnel-hidden.vbs'
$startup = [Environment]::GetFolderPath('Startup')
$dest    = Join-Path $startup 'RIG-Postgres-Tunnel.vbs'

if (-not (Test-Path $src)) { throw "Launcher not found: $src" }

Copy-Item -Path $src -Destination $dest -Force
Write-Host "Installed Startup item: $dest"
Write-Host "Runs hidden at every logon. Log: C:\Users\Dell\.postgres-tunnel.log"
Write-Host "To uninstall: Remove-Item '$dest'"
