"""Minimal SMTP sender for admin-generated submitter credentials.

SMTP is optional: with SMTP_HOST unset (the local dev default), the message
is logged to console instead of sent, so `POST /admin/submitters` works with
zero mail setup -- same fallback convention as the ANTHROPIC_API_KEY mock.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, FRONTEND_URL

logger = logging.getLogger("app.email")


def send_credentials_email(to_email: str, name: str, password: str) -> bool:
    """Returns True only if a message was actually handed to an SMTP server --
    False when SMTP isn't configured (logged instead) or sending failed.
    Never raises: account creation must succeed regardless of email delivery,
    since the caller displays the credentials on screen either way."""
    login_url = f"{FRONTEND_URL}/login"
    subject = "Your Payroll Validation login"
    body = (
        f"Hello {name},\n\n"
        f"An account has been created for you on Payroll Validation.\n\n"
        f"Login: {login_url}\n"
        f"Email: {to_email}\n"
        f"Password: {password}\n\n"
        f"Please keep these details secure.\n"
    )

    if not SMTP_HOST:
        # warning, not info: this app does no logging.basicConfig, so a plain
        # info() would be silently dropped by Python's default handler --
        # warning is the lowest level that's actually visible in the console.
        logger.warning("SMTP not configured -- logging credentials email instead of sending.\n"
                        "To: %s\nSubject: %s\n%s", to_email, subject, body)
        return False

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        # Explicit timeout: an unreachable/misconfigured host otherwise hangs
        # on the OS-level TCP connect timeout (20s+), which risks the whole
        # request being killed by a platform-level function timeout (e.g.
        # Vercel's 30s) before the admin ever sees the response -- silently
        # turning "email is optional" into "email can block" in production.
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=8) as server:
            server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception:
        logger.exception("Failed to send credentials email to %s -- account was still created; "
                          "credentials must be shared manually.", to_email)
        return False
