#!/bin/bash
# AutoAdly - keeps main.py running forever, restarting it immediately if it
# ever crashes for any reason, and logging everything (including crashes) with timestamps.

cd "$(dirname "$0")"
source .venv/bin/activate

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting main.py..." | tee -a crash_log.txt
    python3 main.py 2>&1 | tee -a crash_log.txt
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] main.py exited — restarting in 5 seconds..." | tee -a crash_log.txt
    sleep 5
done
