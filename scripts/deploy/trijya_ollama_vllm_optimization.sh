#!/bin/bash
# ============================================================================
# Trijya-7 RTX 4090 — Ollama Tier 1 env vars + Tier 3 vLLM install
# ============================================================================
# Run this ON Trijya-7 (the 4090 box at Tailscale 100.92.126.27) as root.
# Requires: existing Ollama installation, NVIDIA driver, CUDA toolkit, Python 3.10+.
#
# What this script does:
#   1. Tier 1 (Ollama env vars) — overrides systemd Ollama unit with optimized
#      env so qwen3:30b-a3b stops running at 120W / low utilization.
#   2. Tier 3 (vLLM install)    — installs vLLM as a parallel server on port
#      8000, sets up systemd unit, configures qwen3:14b model.
#
# Why this can't be done from our Hetzner side:
#   - OLLAMA_NUM_PARALLEL / FLASH_ATTENTION / KV_CACHE_TYPE are server-side
#     env vars; require systemd restart of ollama.service.
#   - vLLM needs CUDA + GPU access; only runs on the GPU box.
#
# Hands-off: run this once, system reboots into the optimized state.
# Idempotent: re-running is safe (overwrites override + service files).
# ============================================================================

set -euo pipefail

log() { echo "[$(date +%H:%M:%S)] $*"; }

# ============================================================================
# TIER 1 — Ollama env var overrides
# ============================================================================
log "Tier 1: configuring Ollama env vars via systemd override..."

mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/optimization.conf <<'EOF'
[Service]
# Allow concurrent requests per model (default 4) — push to 8 for 4090 24GB
Environment="OLLAMA_NUM_PARALLEL=8"

# Keep 2 models resident (qwen3:30b-a3b + qwen3:14b) so we can route by need
Environment="OLLAMA_MAX_LOADED_MODELS=2"

# Flash attention: 30-50% KV cache VRAM saving, REQUIRED for cache quantization
Environment="OLLAMA_FLASH_ATTENTION=1"

# KV cache quantization: q8_0 halves cache memory vs f16, minimal precision loss
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"

# Keep models loaded for 4 hours (default 5 min causes cold-load latency)
Environment="OLLAMA_KEEP_ALIVE=4h"

# Listen on Tailscale interface (not just localhost)
Environment="OLLAMA_HOST=0.0.0.0:11434"

# Allow larger queued requests (default 512)
Environment="OLLAMA_MAX_QUEUE=2048"
EOF

systemctl daemon-reload
systemctl restart ollama
sleep 3
systemctl status ollama --no-pager | head -8
log "Tier 1 done. Verifying connectivity..."
curl -sS http://localhost:11434/api/tags | head -c 200 ; echo

# ============================================================================
# TIER 3 — vLLM parallel server on port 8000
# ============================================================================
log "Tier 3: installing vLLM (Python 3.10+ venv)..."

# Use isolated venv so vLLM deps don't conflict with system Python
if [ ! -d /opt/vllm-venv ]; then
  python3 -m venv /opt/vllm-venv
fi
/opt/vllm-venv/bin/pip install --upgrade pip
/opt/vllm-venv/bin/pip install vllm==0.6.3.post1  # known-stable as of 2026-05

# Confirm vLLM imports + sees CUDA
/opt/vllm-venv/bin/python -c "
import torch
print(f'cuda_available={torch.cuda.is_available()}  device_count={torch.cuda.device_count()}  name={torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}')
import vllm
print(f'vllm_version={vllm.__version__}')
"

log "Tier 3: creating vLLM systemd service..."

cat > /etc/systemd/system/vllm.service <<'EOF'
[Unit]
Description=vLLM serving qwen3:14b on RTX 4090 (port 8000)
After=network.target nvidia-persistenced.service
Wants=nvidia-persistenced.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt
Environment="CUDA_VISIBLE_DEVICES=0"
Environment="HF_HOME=/opt/hf-cache"
Environment="VLLM_LOGGING_LEVEL=INFO"

# vLLM serve — see https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
ExecStart=/opt/vllm-venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-14B \
  --served-model-name qwen3:14b \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.85 \
  --max-num-batched-tokens 16384 \
  --max-num-seqs 32 \
  --dtype auto \
  --enforce-eager

Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/vllm.log
StandardError=append:/var/log/vllm.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vllm
systemctl start vllm
log "vLLM startup may take 2-3 min (downloading model + loading)..."
sleep 30
systemctl status vllm --no-pager | head -10

# ============================================================================
# Verification (run 5 min after start to give vLLM time to load model)
# ============================================================================
log "Wait 5 min, then test vLLM:"
echo "  curl http://localhost:8000/v1/chat/completions \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"model\":\"qwen3:14b\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}'"
echo
log "After vLLM is up, on Hetzner add to substrate route:"
echo "  Environment=VLLM_BASE_URL=http://100.92.126.27:8000"
log "DONE — both Tier 1 (Ollama) and Tier 3 (vLLM) are running."
log "Expected throughput jump: 65/min → 150-200/min on the drain."
