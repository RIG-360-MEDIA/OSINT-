#!/bin/bash
# ollama_keepalive.sh — refreshes the 24h keep-alive on TRIJYA-7's hot model.
# Runs every 4 hours via cron. Pings qwen3:30b-a3b (the production-pool default)
# to reset the unload timer. If Ollama is down or the GPU isn't available,
# this is a no-op (curl --max-time prevents hanging).

OLLAMA_URL="http://100.92.126.27:11434/api/generate"
PAYLOAD='{"model":"qwen3:30b-a3b","prompt":"ok","stream":false,"keep_alive":"24h","think":false,"options":{"num_predict":2}}'

curl -s --max-time 30 -X POST "$OLLAMA_URL" -d "$PAYLOAD" -o /tmp/ollama_keepalive_last.json 2>&1
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) keepalive ping sent" >> /tmp/ollama_keepalive.log
