#!/usr/bin/env bash
#
# verify-cf-cidrs.sh — Cloudflare CIDR drift guard
#
# Usage: ./scripts/verify-cf-cidrs.sh
#
# Fetches the currently published Cloudflare ranges (ips-v4 + ips-v6) and diffs
# them against the `set_real_ip_from` CIDRs embedded in the nginx heredoc in
# scripts/deploy.sh. Exits non-zero when Cloudflare has published new ranges so
# the heredoc gets updated.
#
# Offline behaviour: if cloudflare.com cannot be reached, prints a warning and
# exits 0 — CI must not fail when there is no network.
#
# NOTE: When Cloudflare announces new ranges, mirror the update to the Deals
# repo and the blog_platform repo (nginx conf.d/00-cloudflare-real-ip.conf) —
# they keep the same set_real_ip_from list.
#
set -euo pipefail

CF_V4_URL="https://www.cloudflare.com/ips-v4"
CF_V6_URL="https://www.cloudflare.com/ips-v6"
DEPLOY_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/deploy.sh"

if ! command -v curl >/dev/null 2>&1; then
    echo "WARNING: curl not available — skipping Cloudflare CIDR drift check" >&2
    exit 0
fi

cf_v4="$(curl -fsSL --max-time 15 "$CF_V4_URL" 2>/dev/null || true)"
cf_v6="$(curl -fsSL --max-time 15 "$CF_V6_URL" 2>/dev/null || true)"

if [ -z "$cf_v4" ] && [ -z "$cf_v6" ]; then
    echo "WARNING: could not fetch Cloudflare IP ranges (offline?) — skipping drift check" >&2
    exit 0
fi
if [ -z "$cf_v4" ] || [ -z "$cf_v6" ]; then
    echo "WARNING: partial fetch of Cloudflare IP ranges (v4=${cf_v4:+ok}, v6=${cf_v6:+ok}) — skipping drift check" >&2
    exit 0
fi

published="$(printf '%s\n%s\n' "$cf_v4" "$cf_v6" | sed '/^[[:space:]]*$/d' | sort -u)"
deployed="$(grep -E '^[[:space:]]*set_real_ip_from ' "$DEPLOY_SCRIPT" | awk '{print $2}' | tr -d ';' | sort -u)"

added="$(comm -23 <(printf '%s\n' "$published") <(printf '%s\n' "$deployed"))"
removed="$(comm -13 <(printf '%s\n' "$published") <(printf '%s\n' "$deployed"))"

if [ -n "$added" ] || [ -n "$removed" ]; then
    echo "DRIFT: Cloudflare published ranges differ from the scripts/deploy.sh heredoc" >&2
    if [ -n "$added" ]; then
        echo "New Cloudflare ranges NOT in scripts/deploy.sh:" >&2
        printf '%s\n' "$added" | sed 's/^/  /' >&2
    fi
    if [ -n "$removed" ]; then
        echo "Ranges in scripts/deploy.sh no longer published by Cloudflare:" >&2
        printf '%s\n' "$removed" | sed 's/^/  /' >&2
    fi
    echo "Update scripts/deploy.sh heredoc + blog conf.d + deals conf.d (mirror copies)." >&2
    exit 1
fi

echo "OK: scripts/deploy.sh set_real_ip_from ranges match Cloudflare published ranges ($(printf '%s\n' "$published" | wc -l | tr -d ' ') CIDRs)"
