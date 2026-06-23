# Installs the durable Ask-RIG dev server as a per-user Startup item (NO admin).
# A hidden .vbs in the Startup folder launches the self-restarting server loop at
# every logon. Re-run to refresh. To remove: delete the file printed below.
$ErrorActionPreference = 'Stop'

$src     = 'C:\Users\Dell\Desktop\rig-surveillance\products\ask-rig\scripts\askrig-server-hidden.vbs'
$startup = [Environment]::GetFolderPath('Startup')
$dest    = Join-Path $startup 'RIG-AskRig-Server.vbs'

if (-not (Test-Path $src)) { throw "Launcher not found: $src" }

Copy-Item -Path $src -Destination $dest -Force
Write-Host "Installed Startup item: $dest"
Write-Host "Runs hidden at every logon. Log: C:\Users\Dell\.askrig-server.log"
Write-Host "To uninstall: Remove-Item '$dest'"
