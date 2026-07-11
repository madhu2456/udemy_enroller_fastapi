"""Tests for session expiry cleanup and Udemy cookie wipe."""

import secrets
from datetime import timedelta
from types import SimpleNamespace

from app.models.database import (
    Base,
    SessionLocal,
    User,
    UserSession,
    UserSettings,
    _utcnow_naive,
    engine,
)
from app.security import encrypt_cookies
from app.session_lifecycle import cleanup_expired_session, enforce_session_limit


def _make_user_with_session(*, expired: bool, cookies: bool = True):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    email = f"life_{secrets.token_hex(4)}@example.com"
    user = User(
        email=email,
        udemy_display_name="Life",
        udemy_cookies=encrypt_cookies({"access_token": "t", "client_id": "c"})
        if cookies
        else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserSettings(user_id=user.id))
    token = secrets.token_hex(32)
    if expired:
        expires = _utcnow_naive() - timedelta(hours=1)
    else:
        expires = _utcnow_naive() + timedelta(hours=5)
    session = UserSession(token=token, user_id=user.id, expires_at=expires)
    db.add(session)
    db.commit()
    db.refresh(session)
    return db, user, session, token


class TestSessionLifecycle:
    def test_expired_last_session_wipes_cookies(self):
        db, user, session, token = _make_user_with_session(expired=True)
        try:
            assert user.udemy_cookies is not None
            cleanup_expired_session(db, session, app_state=None)

            db2 = SessionLocal()
            try:
                u = db2.query(User).filter(User.id == user.id).first()
                assert u is not None
                assert u.udemy_cookies is None
                assert (
                    db2.query(UserSession).filter(UserSession.token == token).first()
                    is None
                )
            finally:
                db2.close()
        finally:
            db.close()

    def test_expired_session_keeps_cookies_if_other_active_session(self):
        db, user, expired_session, exp_token = _make_user_with_session(expired=True)
        try:
            active_token = secrets.token_hex(32)
            db.add(
                UserSession(
                    token=active_token,
                    user_id=user.id,
                    expires_at=_utcnow_naive() + timedelta(hours=2),
                )
            )
            db.commit()

            cleanup_expired_session(db, expired_session, app_state=None)

            db2 = SessionLocal()
            try:
                u = db2.query(User).filter(User.id == user.id).first()
                assert u is not None
                assert u.udemy_cookies is not None  # still needed by other session
                assert (
                    db2.query(UserSession).filter(UserSession.token == exp_token).first()
                    is None
                )
                assert (
                    db2.query(UserSession)
                    .filter(UserSession.token == active_token)
                    .first()
                    is not None
                )
            finally:
                db2.close()
        finally:
            db.close()


class TestSessionLimit:
    def test_enforce_session_limit_revokes_oldest(self):
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            user = User(email=f"cap_{secrets.token_hex(4)}@example.com")
            db.add(user)
            db.commit()
            db.refresh(user)
            db.add(UserSettings(user_id=user.id))

            tokens = []
            for i in range(4):
                t = secrets.token_hex(32)
                tokens.append(t)
                db.add(
                    UserSession(
                        token=t,
                        user_id=user.id,
                        expires_at=_utcnow_naive() + timedelta(hours=2),
                        created_at=_utcnow_naive() - timedelta(minutes=10 - i),
                    )
                )
            db.commit()

            clients = {t: object() for t in tokens}
            app_state = SimpleNamespace(udemy_clients=clients, session_cache=None)

            revoked = enforce_session_limit(
                db,
                user.id,
                max_sessions=3,
                app_state=app_state,
                keep_token=tokens[-1],
            )
            assert len(revoked) == 1
            assert revoked[0] == tokens[0]
            assert tokens[0] not in clients

            remaining = (
                db.query(UserSession)
                .filter(UserSession.user_id == user.id)
                .count()
            )
            assert remaining == 3
            assert (
                db.query(UserSession)
                .filter(UserSession.token == tokens[-1])
                .first()
                is not None
            )
        finally:
            db.close()

    def test_enforce_session_limit_disabled_when_zero(self):
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            user = User(email=f"cap0_{secrets.token_hex(4)}@example.com")
            db.add(user)
            db.commit()
            db.refresh(user)
            for _ in range(5):
                db.add(
                    UserSession(
                        token=secrets.token_hex(32),
                        user_id=user.id,
                        expires_at=_utcnow_naive() + timedelta(hours=1),
                    )
                )
            db.commit()
            revoked = enforce_session_limit(
                db, user.id, max_sessions=0, app_state=None
            )
            assert revoked == []
            assert (
                db.query(UserSession).filter(UserSession.user_id == user.id).count()
                == 5
            )
        finally:
            db.close()
