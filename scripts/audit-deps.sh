#!/usr/bin/env bash
#
# audit-deps.sh — pip-audit wrapper over requirements.lock (F-ENRL-C06).
#
# Usage:
#   scripts/audit-deps.sh          # audit requirements.lock (CI)
#
# Exit codes: 0 clean, 1 vulnerabilities found, 2 usage/config error.
#
# Allowlist / exceptions (documented, dated):
#   pip-audit supports --ignore-vuln <VULN_ID> (repeatable). NEVER add an
#   entry without a dated, concrete justification in the comment next to it —
#   every exception is a consciously accepted risk reviewed by the owner.
#   Keep the allowlist empty unless an active exception is needed. Template:
#   ALLOWLIST=(
#     --ignore-vuln PYSEC-0000-00000   # 2026-08-13: no fix released yet; pinned;
#                                      # advisory does not apply to this runtime
#   )
#
# Run only in CI (the GitHub Actions `test` job) and on demand; do not
# schedule heavy local scans — the same check runs on every pull request.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! python -m pip_audit --version >/dev/null 2>&1; then
  echo "error: pip-audit is not installed (install with: python -m pip install pip-audit)" >&2
  exit 2
fi

# Documented, dated exceptions — keep empty when none are active (see header).
ALLOWLIST=()

python -m pip_audit --requirement requirements.lock "${ALLOWLIST[@]}"
