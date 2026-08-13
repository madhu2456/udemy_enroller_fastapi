"""One-time migration: re-encrypt legacy cookie blobs under per-session salts.

RUN ONLY AFTER BACKUP/RESTORE DRILL (Phase-0 gate). Do not run against a live
database until scripts/backup_sqlite.sh + the docs/ops/backup-restore.md
restore drill have been exercised and a verified backup exists.

Behavior:
- Dry-run by default: only reports how many user rows still hold a legacy
  (unsalted) cookie blob — never writes.
- ``--apply`` performs the rewrite AND requires ``--backup-verified``; without
  that flag the script refuses to write (exit code 2).
- Legacy decrypt is fail-closed: in DEPLOYMENT_ENV=server|production set
  ALLOW_LEGACY_COOKIE_DECRYPT=1 for the migration window, then switch it off.
- Emits a JSON report: {mode, total, migrated, failed, legacy_remaining}.
  Exit code 0 only when failed == 0.

Usage:
    python scripts/migrate_cookies_per_session.py                 # dry-run
    python scripts/migrate_cookies_per_session.py --apply --backup-verified
"""

import argparse
import json
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from loguru import logger

from app.models.database import SessionLocal, User
from app.security import (
    _allow_legacy_cookie_decrypt,
    decrypt_cookies,
    encrypt_cookies_salted,
    generate_cookie_salt,
)


def _candidate_rows(db):
    """Users holding a cookie blob that is not yet under a per-session salt.

    Rows with no salt, or whose salt no longer round-trips (e.g. tampered or
    written before the column existed), are candidates for re-encryption.
    """
    rows = db.query(User).filter(User.udemy_cookies.isnot(None)).all()
    candidates = []
    for user in rows:
        if not user.udemy_cookies:
            continue
        salt = (user.cookies_salt or "").strip()
        if not salt:
            candidates.append(user)
        elif decrypt_cookies(user.udemy_cookies, salt) is None:
            candidates.append(user)
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Re-encrypt legacy (unsalted) udemy_cookies blobs under per-session "
            "salts (F-ENRL-C01). Dry-run by default; --apply writes."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write changes (default: dry-run only)",
    )
    parser.add_argument(
        "--backup-verified",
        action="store_true",
        help="confirm the backup/restore drill (Phase-0 gate) has been exercised",
    )
    args = parser.parse_args()

    if args.apply and not args.backup_verified:
        logger.error(
            "Refusing to apply: --backup-verified is required. Run the "
            "backup/restore drill (Phase-0 gate) first and pass --backup-verified."
        )
        return 2

    if not _allow_legacy_cookie_decrypt():
        logger.error(
            "Legacy decrypt path is disabled (server/production mode). Set "
            "ALLOW_LEGACY_COOKIE_DECRYPT=1 for the migration window, then "
            "switch it off afterwards."
        )
        return 2

    db = SessionLocal()
    try:
        candidates = _candidate_rows(db)
        report = {
            "mode": "apply" if args.apply else "dry-run",
            "total": len(candidates),
            "migrated": 0,
            "failed": 0,
            "legacy_remaining": len(candidates),
        }
        for user in candidates:
            decrypted = decrypt_cookies(user.udemy_cookies)
            if not isinstance(decrypted, dict):
                report["failed"] += 1
                logger.warning(
                    f"User {user.id}: legacy blob not decryptable — left untouched"
                )
                continue
            if not args.apply:
                continue
            salt = generate_cookie_salt()
            user.cookies_salt = salt
            user.udemy_cookies = encrypt_cookies_salted(decrypted, salt)
            db.commit()
            report["migrated"] += 1
            report["legacy_remaining"] -= 1
            logger.info(f"User {user.id}: migrated to per-session envelope")
        print(json.dumps(report, indent=2))
        return 0 if report["failed"] == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
