#!/usr/bin/env bash
# One-command offline demo: seeds a fresh database and replays a scripted session.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
export DAYTODAY_LLM_PROVIDER="${DAYTODAY_LLM_PROVIDER:-mock}"

echo "== seeding =="
python -m daytoday.cli seed >/dev/null

for message in \
  "what did i write about normalisation" \
  "who won the 1983 world cup" \
  "remind me to submit the synopsis by friday 5pm" \
  "i spent 250 on coffee" \
  "how much did i spend this month" \
  "plan my day" \
  "review my week"
do
  echo
  echo "you > $message"
  python -m daytoday.cli ask "$message"
done
