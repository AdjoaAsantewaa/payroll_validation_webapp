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


def send_credentials_email(to_email: str, name: str, password: str) -> None:
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
        return

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)
