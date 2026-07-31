#!/bin/bash
# Rider Cup live pulls — Friday runner.
# Start this in a Terminal window in the morning and leave it running.
# It calls run.py every 15 minutes; run.py itself only does real work inside
# the 8:00a–3:00p window on the RUN_DATE in config.py (it skips otherwise),
# so you can start it early and it'll spring to life on its own.
#
#   caffeinate -i ./run_friday.sh      <- recommended (keeps the Mac awake)
#
# Stop it anytime with Ctrl+C.

cd "$(dirname "$0")" || exit 1
source .venv/bin/activate

echo "=================================================="
echo " Rider Cup live pulls — started $(date)"
echo " Pulls every 15 min; run.py self-guards to the"
echo " 8a-3p window on the RUN_DATE in config.py."
echo " Ctrl+C to stop."
echo "=================================================="

while true; do
  python run.py
  echo "--- next pull in 15 min ($(date '+%-I:%M %p')) ---"
  sleep 900
done
