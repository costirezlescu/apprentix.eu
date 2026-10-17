#!/bin/bash
# Re-test every URL in data/sources.csv the way a pipeline would (plain HTTP, no browser).
# Usage: scripts/source_check.sh   (from the repo root)
UA="Mozilla/5.0 (compatible; CedefopDaily-sourcecheck)"
tail -n +2 data/sources.csv | while IFS=, read -r id name circle kind url rest; do
  case "$url" in http*) ;; *) continue ;; esac
  tmp=$(mktemp)
  r=$(curl -s -o "$tmp" -w '%{http_code}' -A "$UA" -L --max-time 20 "$url")
  items=$(grep -o '<item>\|<entry>' "$tmp" | wc -l | tr -d ' ')
  printf '%-20s %s  items=%s\n' "$id" "$r" "$items"
  rm -f "$tmp"
done
