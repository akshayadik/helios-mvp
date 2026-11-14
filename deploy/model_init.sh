#!/bin/sh
# S4.3 model-init (design C-d): pull the model into the shared volume with a
# private Ollama server, then stop. Runs before the model service starts, so
# the two servers never share the volume at the same time. The digest is
# checked afterwards by model-check against EXPECTED_MODEL_DIGEST.
set -eu
MODEL="${HELIOS_MODEL:-llama3.1:8b}"
ollama serve >/tmp/ollama-init.log 2>&1 &
pid=$!
tries=0
until ollama list >/dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "$tries" -gt 60 ]; then
    echo "model-init: Ollama did not start" >&2
    cat /tmp/ollama-init.log >&2
    exit 1
  fi
  sleep 1
done
rc=0
ollama pull "$MODEL" || rc=$?
kill "$pid"
wait "$pid" || true
exit "$rc"
