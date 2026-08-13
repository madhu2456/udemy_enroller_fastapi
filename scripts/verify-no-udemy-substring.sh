#!/usr/bin/env bash
#
# verify-no-udemy-substring.sh — F-ENRL-C07 regression gate.
#
# Fails if any "is this Udemy?" check in app/services or scripts relies on
# substring / regex matching of the literal "udemy.com" (or bare "udemy")
# instead of the parse-based helpers in app/services/udemy_validation.py
# (exact-netloc allowlist). Substring checks accept hostile hosts
# (udemy.com.evil.com, eviludemy.com, user@udemy.com, udemy.com.,
# udemy.com:8443, IP literals, percent-encoding).
#
# Usage:
#   scripts/verify-no-udemy-substring.sh --tree    # all tracked files in app/services + scripts (CI)
#   scripts/verify-no-udemy-substring.sh           # staged diff (pre-commit)
#
# Exit codes: 0 = clean, 1 = matches found, 2 = usage/error.
# Scope: tracked *.py under app/services and tracked *.py/*.sh under scripts.
# Exempt: udemy_validation.py itself (the allowlist) and this gate script
# (its own FAMILY definitions must quote the literal patterns). Everything
# else is scanned — including scripts/, because coupon_checker.py and friends
# fetch Udemy URLs and must use the same helpers.
set -u

MODE="staged"
case "${1:-}" in
  "" | --staged) ;;
  --tree) MODE="tree" ;;
  *) echo "usage: $0 [--staged|--tree]" >&2; exit 2 ;;
esac

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "error: not inside a git repository" >&2; exit 2; }
cd "$ROOT" || exit 2

# ---------------------------------------------------------------------------
# Pattern families (POSIX ERE). Each matches a *check* on the literal host
# string — never URL construction ("https://www.udemy.com/...",
# 'domain=".udemy.com"') which is safe: no ` in ` operator follows the
# literal. `(www\.)?` also covers the www.-prefixed forms, which admit
# www.udemy.com.evil.com.
# ---------------------------------------------------------------------------
# "udemy.com" in url / "www.udemy.com" in url (incl. `not in`).
FAMILY1='["'"'"'](www\.)?udemy\.com["'"'"'][[:space:]]+(not[[:space:]]+)?in[[:space:]]'
# .startswith/.endswith/...("udemy.com" or "www.udemy.com").
FAMILY2='\.(endswith|startswith|contains|find|index|split|count|replace|strip|removeprefix|removesuffix)\([[:space:]]*["'"'"'](www\.)?udemy\.com["'"'"']'
# Regex literals: quoted string containing a backslash-escaped dot.
FAMILY3='["'"'"'][^"'"'"']*udemy\\\.com[^"'"'"']*["'"'"']'
# Bare "udemy" in url — admits eviludemy.com / udemy.evil.com. The quotes
# around `udemy` must be exact, so "superudemy" or URL literals don't match.
FAMILY4='["'"'"']udemy["'"'"'][[:space:]]+(not[[:space:]]+)?in[[:space:]]'

COMBINED="($FAMILY1|$FAMILY2|$FAMILY3|$FAMILY4)"

SCAN_PATHS='app/services scripts'
# Minimal exemptions — each is a potential hole, so keep them exact:
#  - app/services/udemy_validation.py: the canonical allowlist itself.
#  - scripts/verify-no-udemy-substring.sh: this gate (its own FAMILY lines
#    necessarily quote the literal patterns).
EXEMPT='^(app/services/udemy_validation\.py|scripts/verify-no-udemy-substring\.sh)$'

FILES="$(
  git ls-files -- 'app/services/*.py' 'scripts/*.py' 'scripts/*.sh' \
    | grep -vE "$EXEMPT"
)"

case "$MODE" in
  tree)
    OUT="$(
      printf '%s\n' "$FILES" | xargs -r grep -nHI -E "$COMBINED" 2>/dev/null
    )"
    ;;
  staged)
    OUT="$(
      git diff --cached -U0 --no-color --no-ext-diff -- $SCAN_PATHS \
        | grep -nE '^\+' | grep -v '^\+\+\+' | grep -E "$COMBINED"
    )"
    ;;
esac

if [ -n "$OUT" ]; then
  echo "verify-no-udemy-substring: substring/regex udemy.com checks found (F-ENRL-C07):"
  printf '%s\n' "$OUT"
  echo "Use app/services/udemy_validation.py helpers (is_udemy_netloc / is_udemy_url) instead."
  exit 1
fi

echo "verify-no-udemy-substring: clean (mode=$MODE)"
exit 0
