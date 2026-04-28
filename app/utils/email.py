"""Email utility — sends transactional emails via SMTP.

If SMTP is not configured (SMTP_HOST is blank) the email is logged at DEBUG
level instead of sent. This means the app boots and works in dev without any
mail server — token values appear in the application log.
"""
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html_body: str) -> None:
    """Send a single transactional email.  Silently logs if SMTP is unconfigured."""
    if not settings.SMTP_HOST:
        logger.debug(
            "SMTP not configured — email not sent.\nTo: %s\nSubject: %s\n\n%s",
            to_email, subject, html_body,
        )
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        if settings.SMTP_TLS:
            context = ssl.create_default_context()
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls(context=context)
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM, to_email, msg.as_string())
        else:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM, to_email, msg.as_string())
        logger.info("Email sent to %s: %s", to_email, subject)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)


def send_verification_email(to_email: str, token: str) -> None:
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;padding:32px 24px">
      <h2 style="margin:0 0 8px;font-size:22px;color:#111">Verify your email</h2>
      <p style="margin:0 0 24px;color:#555;font-size:15px;line-height:1.6">
        Thanks for signing up for DocForge! Click the button below to confirm your
        email address. The link expires in <strong>24 hours</strong>.
      </p>
      <a href="{verify_url}"
         style="display:inline-block;background:#6366f1;color:#fff;font-weight:600;
                font-size:15px;padding:12px 28px;border-radius:8px;text-decoration:none">
        Verify email
      </a>
      <p style="margin:24px 0 0;color:#999;font-size:13px">
        If you didn't create a DocForge account you can safely ignore this email.
      </p>
    </div>
    """
    send_email(to_email, "Verify your DocForge email", html)


def send_password_reset_email(to_email: str, token: str) -> None:
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;padding:32px 24px">
      <h2 style="margin:0 0 8px;font-size:22px;color:#111">Reset your password</h2>
      <p style="margin:0 0 24px;color:#555;font-size:15px;line-height:1.6">
        We received a request to reset the password for your DocForge account.
        Click the button below to choose a new password. The link expires in
        <strong>1 hour</strong>.
      </p>
      <a href="{reset_url}"
         style="display:inline-block;background:#6366f1;color:#fff;font-weight:600;
                font-size:15px;padding:12px 28px;border-radius:8px;text-decoration:none">
        Reset password
      </a>
      <p style="margin:24px 0 0;color:#999;font-size:13px">
        If you didn't request a password reset you can safely ignore this email.
        Your password will not be changed.
      </p>
    </div>
    """
    send_email(to_email, "Reset your DocForge password", html)
