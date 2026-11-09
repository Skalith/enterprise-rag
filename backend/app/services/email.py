"""Password-reset email delivery.

Transport selection:
  * `SMTP_HOST` set     -> real SMTP (SSL or STARTTLS).
  * otherwise           -> log transport: the reset link is written to the backend
                           log so the flow is usable in development. The raw token
                           is only logged when `ENV` is not production.

Returns a small dict describing what happened, never the raw token.
"""

import smtplib
from email.message import EmailMessage
from typing import Dict

from ..config import settings
from ..observability.logging import get_logger

logger = get_logger("email")

RESET_SUBJECT = "Reset your Enterprise RAG password"


def reset_url(raw_token: str) -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/reset-password?token={raw_token}"


def send_password_reset(to_email: str, raw_token: str) -> Dict[str, str]:
    url = reset_url(raw_token)
    body = (
        "Someone requested a password reset for your account.\n\n"
        f"Reset link (valid for {settings.PASSWORD_RESET_TTL_MIN} minutes):\n\n"
        f"  {url}\n\n"
        "If you did not request this, ignore this email — the password stays unchanged.\n"
    )

    if settings.SMTP_HOST:
        message = EmailMessage()
        message["From"] = settings.SMTP_FROM
        message["To"] = to_email
        message["Subject"] = RESET_SUBJECT
        message.set_content(body)

        try:
            if settings.SMTP_PORT == 465:
                with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                    if settings.SMTP_USER:
                        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
                    server.send_message(message)
            else:
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                    server.starttls()
                    if settings.SMTP_USER:
                        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
                    server.send_message(message)
        except Exception as exc:
            logger.error("email.send_failed", to=to_email, error=str(exc)[:300])
            raise
        logger.info("email.password_reset_sent", to=to_email, transport="smtp")
        return {"transport": "smtp", "to": to_email}

    # Log transport. Never leak the token into production logs.
    if settings.is_production:
        logger.warning("email.reset_link_not_sent", to=to_email, reason="no SMTP configured")
    else:
        logger.info("email.reset_link", to=to_email, reset_url=url)
    return {"transport": "log", "to": to_email}
