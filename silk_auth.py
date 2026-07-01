"""مصادقة سِلك — Silk magic-link authentication (V3, stdlib-only).

No passwords to store or leak. Flow:
    request_magic_link(email) -> emails (or, without SMTP configured, logs) a
        one-time link valid for 15 minutes
    verify_magic_link(token)  -> single-use; returns a session token good for
        30 days

Pure stdlib (secrets/hashlib/hmac/smtplib) — no new dependency. Only the raw
token is ever emailed; only its SHA-256 hash is stored (silk_db), so a DB leak
alone can't be replayed into a session. `import silk_auth` works offline —
SMTP is attempted only when SMTP_HOST is actually configured.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets

import silk_db

log = logging.getLogger(__name__)

_LINK_TTL_MINUTES = 15
_SESSION_TTL_DAYS = 30


def _hash(token: str) -> str:
    """بصمة الرمز — SHA-256 hex digest; only this is ever persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _send_email(to_email: str, subject: str, body: str) -> bool:
    """أرسل بريداً حقيقياً إن أُعِدّ SMTP — real send if SMTP_HOST is configured.

    Without SMTP configured (local dev / no provider chosen yet), logs the
    message body (which contains the login link) at INFO level instead of
    silently failing — the operator can still complete the flow by reading
    server logs. This is NOT a substitute for real SMTP in production; set
    SMTP_HOST there.
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        log.info("SMTP not configured — magic link for %s:\n%s", to_email, body)
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText

        port = int(os.environ.get("SMTP_PORT", "587"))
        user = os.environ.get("SMTP_USER", "").strip()
        password = os.environ.get("SMTP_PASSWORD", "").strip()
        sender = os.environ.get("SMTP_FROM", user or "no-reply@silk.local").strip()

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email

        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.sendmail(sender, [to_email], msg.as_string())
        return True
    except Exception as e:  # noqa: BLE001 — auth email is best-effort, never crash
        log.warning("magic-link email send failed for %s: %s", to_email, e)
        return False


def request_magic_link(email: str, base_url: str) -> dict:
    """اطلب رابط دخول سحري — issue a one-time login link for `email`.

    Returns {"sent": bool} — sent=True means it was actually emailed via SMTP;
    False means SMTP isn't configured and the link was only logged (dev mode).
    Never reveals whether the email is a known user (same response either way).
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"sent": False, "error": "بريد إلكتروني غير صالح — invalid email"}

    token = secrets.token_urlsafe(32)
    silk_db.store_magic_link(email, _hash(token), ttl_minutes=_LINK_TTL_MINUTES)
    link = f"{base_url.rstrip('/')}/auth/verify?token={token}"
    body = (f"رابط الدخول لمنصة سِلك (صالح {_LINK_TTL_MINUTES} دقيقة):\n{link}\n\n"
            "لو لم تطلب هذا الرابط، تجاهل هذه الرسالة.")
    sent = _send_email(email, "رابط الدخول — منصة سِلك", body)
    return {"sent": sent}


def verify_magic_link(token: str) -> dict | None:
    """تحقق من الرابط وأصدر جلسة — consume a one-time token, return a session.

    Returns {"session_token", "email", "user_id"} on success, or None if the
    token is missing/expired/already used — never guesses a user.
    """
    if not token:
        return None
    email = silk_db.consume_magic_link(_hash(token))
    if email is None:
        return None
    user_id = silk_db.get_or_create_user(email)
    session_token = secrets.token_urlsafe(32)
    silk_db.store_session(user_id, _hash(session_token), ttl_days=_SESSION_TTL_DAYS)
    return {"session_token": session_token, "email": email, "user_id": user_id}


def session_user_id(session_token: str) -> int | None:
    """المستخدم الحالي — resolve a bearer session token to a user id, or None."""
    if not session_token:
        return None
    return silk_db.session_user_id(_hash(session_token))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk auth — magic link demo (SQLite fallback, SMTP unset -> logs the link)")
    req = request_magic_link("demo@example.com", "http://localhost:8000")
    print("  request:", req)
