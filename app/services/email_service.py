import aiosmtplib
from email.message import EmailMessage

from app.core.config import settings


async def send_verification_email(to: str, token: str) -> None:
    """Send email verification link."""
    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = "Verify your email"
    msg.set_content(
        f"Please verify your email using this token: {token}\n"
        f"This token expires in 1 hour."
    )
    await _send(msg)


async def send_reset_email(to: str, token: str) -> None:
    """Send password reset link."""
    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = "Reset your password"
    msg.set_content(
        f"Use this token to reset your password: {token}\n"
        f"This token expires in 30 minutes."
    )
    await _send(msg)


async def _send(msg: EmailMessage) -> None:
    """Send an email via SMTP."""
    await aiosmtplib.send(
        msg,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER or None,
        password=settings.SMTP_PASSWORD or None,
        start_tls=settings.SMTP_PORT == 587,
        use_tls=settings.SMTP_PORT == 465,
    )
