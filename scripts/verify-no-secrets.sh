#!/usr/bin/env bash
#
# verify-no-secrets.sh — scans for secret patterns and fails on matches.
# Output is REDACTED: only file + pattern class; matched values are never printed.
#
# Usage:
#   scripts/verify-no-secrets.sh            # scan staged changes (pre-commit)
#   scripts/verify-no-secrets.sh --tree     # scan all tracked files (CI)
#   scripts/verify-no-secrets.sh --history  # scan full git history (audit)
#
# Exit codes: 0 = clean, 1 = matches found, 2 = usage/error.
# No external deps (awk + grep only). If gitleaks is installed it is used for
# the staged-mode fast path; the grep/awk path always remains as fallback.
set -u

MODE="staged"
case "${1:-}" in
  "" | --staged) ;;
  --tree) MODE="tree" ;;
  --history) MODE="history" ;;
  *) echo "usage: $0 [--staged|--tree|--history]" >&2; exit 2 ;;
esac

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "error: not inside a git repository" >&2; exit 2; }
cd "$ROOT" || exit 2

# ---------------------------------------------------------------------------
# Pattern list: <regex>\t<label>  (POSIX ERE)
# ---------------------------------------------------------------------------
PATTERNS='
sk-(ant-)?[A-Za-z0-9_-]{44,}	openai/sk-api-key
AKIA[0-9A-Z]{16}	aws-access-key-id
ghp_[A-Za-z0-9]{36}	github-pat
github_pat_[A-Za-z0-9_]{20,}	github-pat-fine-grained
glpat-[A-Za-z0-9_-]{20,}	gitlab-pat
re_[A-Za-z0-9]{16}	stripe-key-restricted
(sk|rk)_live_[A-Za-z0-9]{16,}	stripe-live-key
AIza[0-9A-Za-z_-]{35}	google-api-key
xox[baprs]-[A-Za-z0-9-]{10,}	slack-token
-----BEGIN (RSA |OPENSSH |EC |DSA |PGP |ENCRYPTED )?PRIVATE KEY( BLOCK)?-----	private-key
COOKIE_ENCRYPTION_KEY[=:][^[:space:]#$]{6,}	cookie-encryption-key
SECRET_KEY[=:][^[:space:]#$]{6,}	secret-key
CSRF_SECRET[=:][^[:space:]#$]{6,}	csrf-secret
UPSTASH_REDIS_REST_TOKEN[=:][^[:space:]#$]{6,}	upstash-token
GITHUB_TOKEN[=:][^[:space:]#$]{4,}	github-token
POSTGRES_PASSWORD[=:][^[:space:]#$]{4,}	postgres-password
DB_PASSWORD[=:][^[:space:]#$]{4,}	db-password
MYSQL_PASSWORD[=:][^[:space:]#$]{4,}	mysql-password
REDIS_PASSWORD[=:][^[:space:]#$]{4,}	redis-password
NEXTAUTH_SECRET[=:][^[:space:]#$]{6,}	nextauth-secret
AUTH_SECRET[=:][^[:space:]#$]{6,}	auth-secret
JWT_SECRET[=:][^[:space:]#$]{6,}	jwt-secret
ENCRYPTION_KEY[=:][^[:space:]#$]{6,}	encryption-key
REVALIDATE_SECRET[=:][^[:space:]#$]{6,}	revalidate-secret
AWS_SECRET_ACCESS_KEY[=:][^[:space:]#$]{6,}	aws-secret-access-key
client_secret[=:][^[:space:]#$,;]{6,}	oauth-client-secret
STRIPE_SECRET_KEY[=:][^[:space:]#$]{6,}	stripe-secret-key
[A-Za-z0-9_.-]+://[^[:space:]/]+:[^@[:space:]]+@	url-with-credentials
'

# ---------------------------------------------------------------------------
# gitleaks fast path (staged mode only); the awk/grep path below always works.
# ---------------------------------------------------------------------------
if [ "$MODE" = "staged" ] && command -v gitleaks >/dev/null 2>&1; then
  if ! gitleaks protect --staged -v >/dev/null 2>&1; then
    echo "verify-no-secrets: gitleaks reported secrets in the staged diff (values redacted)" >&2
    exit 1
  fi
  exit 0
fi

AWKPROG="$(mktemp)"
trap 'rm -f "$AWKPROG"' EXIT
{
  cat <<'AWKHEAD'
function def(re, label) { np++; rg[np] = re; lb[np] = label }
# vph(): word-like (low-entropy) value/credential => placeholder, not a real secret.
function vph(line,   t) {
  t = ""
  if (match(line, /:\/\/[^@[:space:]]+@/)) {
    t = substr(line, RSTART, RLENGTH)
    sub(/^.*:\/\//, "", t)
    sub(/@.*$/, "", t)
    gsub(/[:]/, "", t)
  } else if (match(line, /[A-Za-z0-9_.-]+[=:][[:space:]]*/)) {
    t = substr(line, RSTART + RLENGTH)
    sub(/^["']+/, "", t)
    sub(/["'][,;]?[[:space:]]*$/, "", t)
    sub(/[,;][[:space:]]*$/, "", t)
    sub(/[[:space:]].*$/, "", t)
  } else if (match(line, /sk-[-A-Za-z0-9]+/)) {
    t = substr(line, RSTART + 3)
  }
  if (t == "" || length(t) < 6) return 0
  t = tolower(t)
  if (t ~ /^[a-z_!-]{6,64}$/) return 1
  return 0
}
function classify(line,   cls) {
  if (line ~ /\$\{\{|secrets\.|vars\.|inputs\.|actions\//) return "safe-ref"
  if (line ~ /settings\.|cfg\[|os\.environ|os\.getenv|getenv\(|process\.env/) return "safe-ref"
  if (line ~ /\$\{/) return "env-ref"
  if (line ~ /user:pass@|:pass@|:password@/) return "placeholder"
  if (line ~ /-----BEGIN/ && line ~ /-----END/) return "placeholder"
  if (tolower(line) ~ ph) return "placeholder"
  if (vph(line)) return "placeholder"
  return "CANDIDATE"
}
function check(line,   cls, hit, i) {
  cls = classify(line)
  if (cls != "CANDIDATE") return
  hit = ""
  for (i = 1; i <= np; i++) {
    if (match(line, rg[i])) { hit = lb[i]; break }
  }
  if (hit == "") return
  if (MODE == "history") print "CAND|" meta "|file=" file "|pattern=" hit
  else if (MODE == "diff") print "STAGED|file=" file "|pattern=" hit
  else print "TREE|file=" gfile "|line=" gln "|pattern=" hit
}
BEGIN {
  np = 0
AWKHEAD
  printf '%s\n' "$PATTERNS" | while IFS=$'\t' read -r re label; do
    [ -z "$re" ] && continue
    printf '  def("%s", "%s")\n' "$re" "$label"
  done
  cat <<'AWKTAIL'
  ph = "change[-_ ]?me|your[-_ ]|[Ee]xample|[Pp]laceholder|[Dd]ummy|[Rr]eplace|[Ss]ample|[Ff]ake|ci[-_ ]?only|ci[-_ ]?test|test[-_]|[Ii]nsecure|django-insecure|[Ll]orem|xxxx+|[Dd]ev-?only|pre-?prod|sanitized|redacted|[Pp]ending|to[-_ ]?be[-_ ]?(filled|set|done)|^changeme$|^secret$|^password$|^passwd$|^postgres$|^redis$|^root$|^admin$|123456|qwerty|random|generat"
}
MODE == "history" && /^COMMIT\|/ { meta = substr($0, 8); file = ""; next }
MODE == "history" && /^diff --git / {
  f = $0; sub(/^diff --git a\//, "", f); sub(/ b\/.*$/, "", f); file = f; next
}
MODE == "history" && /^\+\+\+ / {
  p = $0; sub(/^\+\+\+ /, "", p); sub(/\t.*$/, "", p)
  if (p !~ /^\/dev\/null/) file = p
  next
}
MODE == "history" && /^\+/ && !/^\+\+\+/ { check(substr($0, 2)); next }
MODE == "diff" && /^\+\+\+ / {
  p = $0; sub(/^\+\+\+ /, "", p); sub(/\t.*$/, "", p)
  if (p !~ /^\/dev\/null/) file = p
  next
}
MODE == "diff" && /^\+/ && !/^\+\+\+/ { check(substr($0, 2)); next }
MODE == "tree" {
  n = split($0, a, ":")
  if (n < 3) next
  gfile = a[1]; gln = a[2]
  rest = substr($0, length(a[1]) + length(a[2]) + 3)
  check(rest)
}
AWKTAIL
} > "$AWKPROG"

case "$MODE" in
  history)
    OUT="$(git log --all -p --format='COMMIT|%H|%ad|%s' --date=short | awk -v MODE=history -f "$AWKPROG")"
    ;;
  staged)
    OUT="$(git diff --cached -U0 --no-color --no-ext-diff | awk -v MODE=diff -f "$AWKPROG")"
    ;;
  tree)
    COMBINED="$(printf '%s\n' "$PATTERNS" | grep -v '^$' | cut -f1 | paste -sd'|' -)"
    OUT="$(git ls-files -z | xargs -0 -r grep -HnI --color=never -E "$COMBINED" 2>/dev/null | awk -v MODE=tree -f "$AWKPROG")"
    ;;
esac

if [ -n "$OUT" ]; then
  echo "verify-no-secrets: potential secrets detected (values REDACTED):"
  printf '%s\n' "$OUT"
  exit 1
fi
echo "verify-no-secrets: clean (mode=$MODE)"
exit 0
