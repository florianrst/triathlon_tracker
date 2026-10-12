#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PID_FILE=".streamlit.pid"
LOG_FILE="streamlit.log"
PORT="${PORT:-8501}"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Already running (PID $(cat "$PID_FILE"))."
    exit 0
fi

nohup uv run streamlit run webapp/app.py --server.port "$PORT" > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo "Streamlit démarré (PID $(cat "$PID_FILE")), port $PORT, logs dans $LOG_FILE."
