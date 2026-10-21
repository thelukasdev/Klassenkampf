#!/bin/sh
set -eu
# Delete and recreate in ONE atomic nft transaction; preserve every other table.
rules=$(mktemp)
trap 'rm -f "$rules"' EXIT
if /usr/sbin/nft list table inet kk_origin >/dev/null 2>&1; then
    printf 'delete table inet kk_origin\n' > "$rules"
fi
cat /etc/klassenkampf/cloudflare-origin.nft >> "$rules"
/usr/sbin/nft --check --file "$rules"
/usr/sbin/nft --file "$rules"
