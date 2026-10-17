#!/usr/bin/env bash
# 把 live.json 這次新產生的通知推到有開推播的手機（每批 25 台裝置，避免超過 Cloudflare 免費方案的 CPU 時間）
# 用法：scripts/notify.sh <舊 live.json> <新 live.json>；需要環境變數 CLOUDFLARE_API_TOKEN、CLOUDFLARE_ACCOUNT_ID
set -euo pipefail
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then echo '還沒設定 CF_API_TOKEN／CF_ACCOUNT_ID，跳過'; exit 0; fi
node scripts/new_events.mjs "$1" "$2" > /tmp/items.json
N=$(jq '.items | length' /tmp/items.json); echo "新通知 $N 則"
[ "$N" -gt 0 ] || exit 0
SUB=$(curl -fsS -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/subdomain" | jq -r '.result.subdomain')
KEY="$(printf '%s' "${CLOUDFLARE_API_TOKEN}value-push" | sha256sum | cut -d' ' -f1)"
START=0
while [ "$START" != null ]; do
  jq --argjson s "$START" '. + {start: $s, size: 25}' /tmp/items.json > /tmp/batch.json
  R=$(curl -fsS -X POST -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' --data @/tmp/batch.json "https://value-push.$SUB.workers.dev/send"); echo "$R"
  START=$(echo "$R" | jq -r '.next')
done
