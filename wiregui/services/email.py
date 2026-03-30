"""Email sending via aiosmtplib for magic links and notifications."""

import aiosmtplib
from email.message import EmailMessage

from loguru import logger

from wiregui.config import get_settings


async def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via configured SMTP. Returns True on success."""
    settings = get_settings()

    if not settings.smtp_host:
        logger.warning("SMTP not configured — email to {} not sent", to)
        return False

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info("Email sent to {}: {}", to, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to {}: {}", to, e)
        return False


async def send_magic_link(to: str, link: str) -> bool:
    """Send a magic link sign-in email."""
    subject = "WireGUI — Sign in link"
    body = f"""You requested a sign-in link for WireGUI.

Click here to sign in:
{link}

This link expires in 15 minutes. If you didn't request this, you can safely ignore this email.
"""
    return await send_email(to, subject, body)
