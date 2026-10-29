#!/bin/bash
# Yerel LLM sunucusunu (llama.cpp) baslatir. OpenAI uyumlu uc: http://127.0.0.1:8080/v1
# Kullanim: scripts/llm_baslat.sh [gpu|cpu]
set -euo pipefail
DIZIN="${LLAMA_DIZIN:-$HOME/llm}"
MODEL="${LLAMA_MODEL:-$DIZIN/qwen3-4b-instruct-2507-q4_k_m.gguf}"
SUNUCU="$(ls -d "$DIZIN"/llama-b*/ | tail -1)llama-server"

if [ "${1:-gpu}" = "cpu" ]; then
    ARAC=(--device none -ngl 0 -t 4)
else
    # Vulkan cihaz adi icin: llama-server --list-devices
    ARAC=(--device "${LLAMA_CIHAZ:-Vulkan1}" -ngl 99)
fi
exec "$SUNUCU" -m "$MODEL" "${ARAC[@]}" -c 4096 --host 127.0.0.1 --port 8080 \
    --chat-template-kwargs '{"enable_thinking":false}'
