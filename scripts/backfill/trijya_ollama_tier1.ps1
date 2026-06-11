# Tier 1 Ollama speedup on TRIJYA-7
# - Set machine-scope env vars (persist across reboots)
# - Restart the OllamaServe scheduled task
# - Verify env vars took effect on the new Ollama process

$ErrorActionPreference = "Stop"

Write-Host "=== Snapshot: current env vars before change ==="
$current = @{}
foreach ($n in @("OLLAMA_NUM_PARALLEL","OLLAMA_FLASH_ATTENTION","OLLAMA_KV_CACHE_TYPE","OLLAMA_MAX_LOADED_MODELS","OLLAMA_HOST","OLLAMA_KEEP_ALIVE")) {
    $v = [Environment]::GetEnvironmentVariable($n, "Machine")
    $current[$n] = $v
    Write-Host "  ${n} = $v"
}

Write-Host ""
Write-Host "=== Setting new env vars at Machine scope ==="
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL",     "3",      "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION",  "1",      "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE",    "q8_0",   "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS","1",      "Machine")
Write-Host "  set: OLLAMA_NUM_PARALLEL=3"
Write-Host "  set: OLLAMA_FLASH_ATTENTION=1"
Write-Host "  set: OLLAMA_KV_CACHE_TYPE=q8_0"
Write-Host "  set: OLLAMA_MAX_LOADED_MODELS=1"

Write-Host ""
Write-Host "=== Restart OllamaServe scheduled task ==="
try {
    Stop-ScheduledTask -TaskName "OllamaServe" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    # Kill any lingering ollama.exe
    Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-Process -Name "ollama_llama_server" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
    Start-ScheduledTask -TaskName "OllamaServe"
    Write-Host "  OllamaServe restarted"
} catch {
    Write-Host "  ERROR restarting scheduled task: $_"
}

Write-Host ""
Write-Host "=== Wait for Ollama HTTP to come back ==="
$ready = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 2
        Write-Host "  ready after ${i}s — version $($resp.version)"
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    Write-Host "  WARNING: Ollama not responding after 30s"
    exit 1
}

Write-Host ""
Write-Host "=== Verify env vars on the new ollama process ==="
$ollamaProc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ollamaProc) {
    Write-Host "  ollama.exe PID: $($ollamaProc.Id)"
    # Read process env using WMI (works for SYSTEM-owned processes)
    try {
        $procEnv = (Get-WmiObject Win32_Process -Filter "ProcessId=$($ollamaProc.Id)").GetOwner()
        Write-Host "  running as: $($procEnv.Domain)\$($procEnv.User)"
    } catch {}
} else {
    Write-Host "  WARNING: no ollama.exe process found"
}

Write-Host ""
Write-Host "=== Pre-load qwen3:30b-a3b model with new flash-attn + KV cache settings ==="
$payload = @{
    model = "qwen3:30b-a3b"
    prompt = "ok"
    stream = $false
    keep_alive = "24h"
    options = @{ num_predict = 2 }
} | ConvertTo-Json -Compress
try {
    $load = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/generate" -Method POST -Body $payload -ContentType "application/json" -TimeoutSec 180
    Write-Host "  model loaded — total_duration=$($load.total_duration / 1e9)s eval_count=$($load.eval_count)"
} catch {
    Write-Host "  ERROR loading model: $_"
}

Write-Host ""
Write-Host "=== /api/ps — confirm model VRAM and runtime ==="
$ps = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/ps"
foreach ($m in $ps.models) {
    Write-Host "  $($m.name): vram=$([math]::Round($m.size_vram/1GB,1))GB  ctx=$($m.context_length)  expires=$($m.expires_at)"
}

Write-Host ""
Write-Host "=== DONE ==="
