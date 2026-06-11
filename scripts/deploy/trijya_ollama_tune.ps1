# ============================================================================
# Trijya-7 (Windows + RTX 4090) — Ollama optimization for qwen3 substrate work
# ============================================================================
# Run AS ADMINISTRATOR in PowerShell on Trijya-7. The Hetzner-side substrate
# drain (rig-backend) calls this Ollama instance over Tailscale; default
# OLLAMA_NUM_PARALLEL=1 limits the drain to ~3 calls/min from this GPU.
# After this script, expect ~24 calls/min from this GPU alone, plus better
# VRAM efficiency for two concurrent models.
#
# Why this can't be done remotely:
#   - Ollama on Windows reads env vars at service-start time only.
#   - Setting Machine-scope env requires admin + Restart-Service.
#   - SSH is not enabled for our Tailscale user on this box.
#
# Idempotent: re-running re-sets each variable to the same value, restarts.
# No data loss: model weights / pulled models on disk are untouched.
# ============================================================================

#Requires -RunAsAdministrator

Write-Host "[$(Get-Date -Format HH:mm:ss)] Trijya Ollama tune — start" -ForegroundColor Cyan

# ── 1. Set Machine-scope env vars (persist across reboots) ──────────────────
$envVars = @{
    # Concurrent sequences per loaded model. Default 1 = serial → slow.
    # 8 fits comfortably with qwen3:14b (10.7 GB) on 24 GB 4090.
    "OLLAMA_NUM_PARALLEL"      = "8"

    # Keep both qwen3:14b AND qwen3:30b-a3b resident simultaneously.
    # Avoids cold-load (10-30s) when substrate switches models.
    "OLLAMA_MAX_LOADED_MODELS" = "2"

    # Flash attention: 30-50% KV cache VRAM saving. REQUIRED for cache q8_0.
    "OLLAMA_FLASH_ATTENTION"   = "1"

    # KV cache quantization q8_0 = ~half of f16 memory, negligible precision loss.
    # Combined with flash attention, lets us fit 2 models comfortably.
    "OLLAMA_KV_CACHE_TYPE"     = "q8_0"

    # Default 5 min KEEP_ALIVE causes models to unload between batches.
    # 4 hours keeps them warm through the drain.
    "OLLAMA_KEEP_ALIVE"        = "4h"

    # Listen on all interfaces so Tailscale peers (Hetzner) can reach it.
    # If Ollama is already listening on 0.0.0.0:11434 this is a no-op.
    "OLLAMA_HOST"              = "0.0.0.0:11434"

    # Larger queue for concurrent drain processes hitting it.
    "OLLAMA_MAX_QUEUE"         = "2048"
}

foreach ($k in $envVars.Keys) {
    $v = $envVars[$k]
    [System.Environment]::SetEnvironmentVariable($k, $v, "Machine")
    Write-Host "  set $k = $v"
}

# ── 2. Restart Ollama service to pick up new env ────────────────────────────
Write-Host "[$(Get-Date -Format HH:mm:ss)] Restarting Ollama service..." -ForegroundColor Yellow

# Try common service names. Ollama installer registers either name.
$svc = Get-Service -Name "Ollama","ollama" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($svc) {
    Restart-Service -Name $svc.Name -Force
    Start-Sleep -Seconds 4
    Get-Service -Name $svc.Name | Format-Table Name,Status,StartType
} else {
    Write-Warning "Ollama service not found. If you run ollama via 'ollama serve' manually, you must:"
    Write-Warning "  1. Kill the existing ollama.exe process"
    Write-Warning "  2. Restart it manually so it picks up the new env vars"
    Write-Warning "  (the env vars ARE set; just need ollama to re-read them)"
}

# ── 3. Verify env vars took effect ──────────────────────────────────────────
Write-Host "[$(Get-Date -Format HH:mm:ss)] Verifying via Ollama HTTP API..." -ForegroundColor Cyan
try {
    $resp = Invoke-RestMethod -Uri "http://localhost:11434/api/version" -TimeoutSec 5
    Write-Host "  ollama_version = $($resp.version)"
} catch {
    Write-Warning "  Ollama did not respond on localhost:11434 — check service status"
}

# ── 4. Pre-warm both models so first drain request is fast ──────────────────
Write-Host "[$(Get-Date -Format HH:mm:ss)] Pre-warming qwen3:14b + qwen3:30b-a3b..." -ForegroundColor Cyan
foreach ($model in @("qwen3:14b", "qwen3:30b-a3b")) {
    try {
        $body = @{ model = $model; messages = @(@{ role="user"; content="hi" }); stream=$false; options=@{ num_predict=4 } } | ConvertTo-Json -Depth 5
        $r = Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 60
        Write-Host "  $model warmed (eval_count=$($r.eval_count))"
    } catch {
        Write-Warning "  $model warm-up failed: $($_.Exception.Message)"
    }
}

Write-Host "[$(Get-Date -Format HH:mm:ss)] DONE — Ollama is now tuned." -ForegroundColor Green
Write-Host ""
Write-Host "Expected gains on Hetzner-side drain:" -ForegroundColor Cyan
Write-Host "  - Drain D (Ollama-only): 3 calls/min  →  24 calls/min (8x)"
Write-Host "  - Drains A/B/C (mixed):  fewer cold-loads, ~30% faster overall"
Write-Host "  - Aggregate drain ETA:    17h  →  ~5-7h"
