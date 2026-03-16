#!/usr/bin/env bash
set -eu

BASE="/srv/2bananas/projects/commute-plan"
LOGDIR="$BASE/logs"
DAYS="${1:-14}"

if [[ ! "$DAYS" =~ ^[0-9]+$ ]]; then
  echo "Usage: $0 [days]" >&2
  exit 2
fi

if [[ ! -d "$LOGDIR" ]]; then
  echo "log_retention: log directory not found: $LOGDIR"
  exit 0
fi

cutoff_desc="older than $DAYS days"
echo "log_retention: pruning files in $LOGDIR ($cutoff_desc)"

removed=0
failed=0

while IFS= read -r -d '' f; do
  if rm -f -- "$f"; then
    removed=$((removed + 1))
  else
    failed=$((failed + 1))
    echo "log_retention: failed to remove $f" >&2
  fi
done < <(find "$LOGDIR" -mindepth 1 -type f ! -name '.gitkeep' -mtime "+$DAYS" -print0)

echo "log_retention: removed=$removed failed=$failed"
exit 0
