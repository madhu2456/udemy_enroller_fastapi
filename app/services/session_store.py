"""Long-term encrypted persistent storage and lifecycle for Udemy session credentials.

Features:
1. Encrypted storage in SQLite database (`users` table) and local backup file (`data/.session.enc` with 0600 permissions).
2. Uses salted Fernet encryption via HKDF-SHA256 from app.security.
3. Automatically restores and verifies sessions on startup.
4. Alerts the user only when saved session credentials have truly expired (typically 30-90 days).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from loguru import logger

from app.models.database import SessionLocal, User
from app.security import (
    decrypt_cookies,
    encrypt_cookies_salted,
    generate_cookie_salt,
)
from app.services.udemy_client import UdemyClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SESSION_BACKUP_FILE = PROJECT_ROOT / "data" / ".session.enc"
DEFAULT_LOCAL_EMAIL = "local@udemyenroller.app"


def save_persistent_session(
    cookies: Dict[str, str],
    display_name: str = "",
    user_id: Optional[str] = None,
    currency: str = "USD",
) -> bool:
    """Save Udemy session credentials securely for long-term persistence."""
    access_token = cookies.get("access_token", "").strip()
    if not access_token:
        logger.warning("Cannot save empty access_token to persistent session store.")
        return False

    client_id = cookies.get("client_id", "").strip()
    csrf_token = cookies.get("csrf_token", "").strip()
    cookie_payload = {
        "access_token": access_token,
        "client_id": client_id,
        "csrf_token": csrf_token,
    }

    salt = generate_cookie_salt()
    encrypted_blob = encrypt_cookies_salted(cookie_payload, salt)

    # 1. Persist to SQLite Database
    db_saved = False
    try:
        with SessionLocal() as db:
            user = db.query(User).filter((User.email == DEFAULT_LOCAL_EMAIL) | (User.udemy_cookies.isnot(None))).first()
            if not user:
                user = User(
                    email=DEFAULT_LOCAL_EMAIL,
                    udemy_display_name=display_name or "Udemy User",
                    udemy_cookies=encrypted_blob,
                    cookies_salt=salt,
                    currency=(currency or "USD").lower(),
                )
                db.add(user)
            else:
                user.udemy_cookies = encrypted_blob
                user.cookies_salt = salt
                if display_name:
                    user.udemy_display_name = display_name
                if currency:
                    user.currency = currency.lower()

            db.commit()
            db_saved = True
            logger.info("Saved persistent session to database.")
    except Exception as e:
        logger.warning(f"Could not save session to database: {e}")

    # 2. Persist to Local Encrypted Backup File (data/.session.enc) with 0600 permissions
    file_saved = False
    try:
        SESSION_BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
        backup_data = {
            "salt": salt,
            "blob": encrypted_blob,
            "display_name": display_name,
            "user_id": user_id,
            "currency": currency,
        }
        raw_text = json.dumps(backup_data)

        # Write safely with atomic rename and 0600 permissions
        temp_file = SESSION_BACKUP_FILE.with_suffix(".tmp")
        temp_file.write_text(raw_text, encoding="utf-8")
        try:
            os.chmod(temp_file, 0o600)
        except OSError:
            pass
        temp_file.replace(SESSION_BACKUP_FILE)
        file_saved = True
        logger.info(f"Saved persistent session backup to {SESSION_BACKUP_FILE}.")
    except Exception as e:
        logger.warning(f"Could not save session backup file: {e}")

    return db_saved or file_saved


def load_persistent_session() -> Optional[Dict[str, Any]]:
    """Load and decrypt saved persistent Udemy session credentials."""
    # 1. Attempt to load from Database
    try:
        with SessionLocal() as db:
            user = db.query(User).filter(User.udemy_cookies.isnot(None), User.cookies_salt.isnot(None)).first()
            if user and user.udemy_cookies and user.cookies_salt:
                decrypted = decrypt_cookies(user.udemy_cookies, user.cookies_salt)
                if decrypted and isinstance(decrypted, dict) and decrypted.get("access_token"):
                    return {
                        "access_token": decrypted.get("access_token", ""),
                        "client_id": decrypted.get("client_id", ""),
                        "csrf_token": decrypted.get("csrf_token", ""),
                        "display_name": user.udemy_display_name or "Udemy User",
                        "currency": (user.currency or "USD").upper(),
                    }
    except Exception as e:
        logger.debug(f"DB session load error (falling back to file): {e}")

    # 2. Fallback to Local Encrypted Backup File
    if SESSION_BACKUP_FILE.exists():
        try:
            raw_text = SESSION_BACKUP_FILE.read_text(encoding="utf-8")
            backup_data = json.loads(raw_text)
            salt = backup_data.get("salt")
            blob = backup_data.get("blob")
            if salt and blob:
                decrypted = decrypt_cookies(blob, salt)
                if decrypted and isinstance(decrypted, dict) and decrypted.get("access_token"):
                    return {
                        "access_token": decrypted.get("access_token", ""),
                        "client_id": decrypted.get("client_id", ""),
                        "csrf_token": decrypted.get("csrf_token", ""),
                        "display_name": backup_data.get("display_name", "Udemy User"),
                        "user_id": backup_data.get("user_id"),
                        "currency": (backup_data.get("currency", "USD")).upper(),
                    }
        except Exception as e:
            logger.warning(f"Could not load session backup file: {e}")

    return None


def clear_persistent_session() -> bool:
    """Wipe saved session from database and local backup file."""
    # 1. Clear in Database
    try:
        with SessionLocal() as db:
            users = db.query(User).filter(User.udemy_cookies.isnot(None)).all()
            for u in users:
                u.udemy_cookies = None
                u.cookies_salt = None
            db.commit()
    except Exception as e:
        logger.debug(f"DB session wipe error: {e}")

    # 2. Delete Local File
    if SESSION_BACKUP_FILE.exists():
        try:
            SESSION_BACKUP_FILE.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"File session wipe error: {e}")

    return True


async def verify_and_restore_session() -> Tuple[bool, Optional[UdemyClient], Optional[Dict[str, Any]], Optional[str]]:
    """Restore saved session, verify it against the Udemy API, and report state.

    Returns:
        (is_valid, client, session_dict, error_or_notes)
    """
    saved = load_persistent_session()
    if not saved or not saved.get("access_token"):
        return False, None, None, "No saved session found"

    client = UdemyClient()
    try:
        client.cookie_login(
            access_token=saved["access_token"],
            client_id=saved.get("client_id", ""),
            csrf_token=saved.get("csrf_token", ""),
        )
        await client.get_session_info()

        if client.is_authenticated:
            try:
                await client.get_enrolled_courses()
            except Exception as e:
                logger.debug(f"Could not pre-fetch course library: {e}")

            lib_count = len(client.enrolled_courses or {})
            curr = (client.currency or saved.get("currency", "USD")).upper()
            display_name = client.display_name or saved.get("display_name", "Udemy User")

            # Update saved display name and currency if changed
            save_persistent_session(
                cookies={
                    "access_token": saved["access_token"],
                    "client_id": saved.get("client_id", ""),
                    "csrf_token": saved.get("csrf_token", ""),
                },
                display_name=display_name,
                user_id=client.udemy_user_id,
                currency=curr,
            )

            session_data = {
                "display_name": display_name,
                "user_id": client.udemy_user_id,
                "currency": curr,
                "library_count": lib_count,
                "access_token": saved["access_token"],
                "client_id": saved.get("client_id", ""),
                "csrf_token": saved.get("csrf_token", ""),
                "is_saved": True,
            }
            return True, client, session_data, None
        else:
            return False, None, saved, "Session expired or credentials invalid on Udemy"
    except Exception as e:
        logger.warning(f"Error validating saved session: {e}")
        return False, None, saved, str(e)
