"""
backend/auth/email_service.py

Async email service for authentication emails.

Behaviour:
  - If SMTP_HOST is configured → send real email via aiosmtplib
  - Otherwise (dev mode) → log the email link to console for easy testing

All HTML templates are inline strings — no template engine dependency.
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.config import settings

logger = logging.getLogger(__name__)


# ── HTML Templates ─────────────────────────────────────────────────────────────

def _base_email(title: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#07070f;font-family:Inter,-apple-system,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#07070f;min-height:100vh;">
  <tr><td align="center" style="padding:40px 16px;">
    <table width="520" cellpadding="0" cellspacing="0" style="
      background:rgba(255,255,255,0.03);
      border:1px solid rgba(255,255,255,0.08);
      border-radius:16px;
      overflow:hidden;
    ">
      <!-- Header -->
      <tr><td style="
        padding:32px;
        background:linear-gradient(135deg,rgba(99,102,241,0.15),rgba(139,92,246,0.1));
        border-bottom:1px solid rgba(255,255,255,0.06);
      ">
        <div style="display:flex;align-items:center;gap:10px;">
          <div style="
            width:36px;height:36px;border-radius:10px;
            background:linear-gradient(135deg,#6366f1,#8b5cf6);
            display:inline-flex;align-items:center;justify-content:center;
            font-size:16px;color:white;font-weight:700;line-height:36px;
            text-align:center;
          ">D</div>
          <span style="font-size:18px;font-weight:700;color:#f8fafc;">DevAgent</span>
        </div>
      </td></tr>

      <!-- Body -->
      <tr><td style="padding:40px 32px;">
        {body_html}
      </td></tr>

      <!-- Footer -->
      <tr><td style="
        padding:24px 32px;
        border-top:1px solid rgba(255,255,255,0.06);
        text-align:center;
      ">
        <p style="color:#475569;font-size:12px;margin:0;">
          This email was sent by {settings.app_name}. If you didn't request this, you can safely ignore it.
        </p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""


def _verification_email_html(verify_url: str) -> str:
    body = f"""
      <h1 style="color:#f8fafc;font-size:22px;margin:0 0 12px;">Verify your email address</h1>
      <p style="color:#94a3b8;font-size:15px;line-height:1.6;margin:0 0 28px;">
        Welcome to {settings.app_name}! Click the button below to verify your email address
        and activate your account. This link expires in 24 hours.
      </p>
      <a href="{verify_url}" style="
        display:inline-block;
        background:linear-gradient(135deg,#6366f1,#8b5cf6);
        color:white;text-decoration:none;font-weight:600;
        padding:14px 32px;border-radius:10px;font-size:15px;
      ">Verify Email Address</a>
      <p style="color:#475569;font-size:13px;margin:24px 0 0;">
        Or copy this link: <a href="{verify_url}" style="color:#818cf8;">{verify_url}</a>
      </p>
    """
    return _base_email("Verify your DevAgent email", body)


def _reset_password_email_html(reset_url: str) -> str:
    body = f"""
      <h1 style="color:#f8fafc;font-size:22px;margin:0 0 12px;">Reset your password</h1>
      <p style="color:#94a3b8;font-size:15px;line-height:1.6;margin:0 0 28px;">
        We received a request to reset the password for your {settings.app_name} account.
        Click the button below to set a new password. This link expires in <strong style="color:#e2e8f0;">1 hour</strong>.
      </p>
      <a href="{reset_url}" style="
        display:inline-block;
        background:linear-gradient(135deg,#6366f1,#8b5cf6);
        color:white;text-decoration:none;font-weight:600;
        padding:14px 32px;border-radius:10px;font-size:15px;
      ">Reset Password</a>
      <p style="color:#475569;font-size:13px;margin:24px 0 0;">
        If you didn't request this, your account is safe — no changes have been made.
      </p>
    """
    return _base_email("Reset your DevAgent password", body)


# ── Sender ─────────────────────────────────────────────────────────────────────

async def _send_email(
    *,
    to_email: str,
    subject: str,
    html_body: str,
) -> None:
    """Internal: send an email. Falls back to console logging if SMTP not configured."""
    if not settings.smtp_host:
        logger.info(
            "📧 [DEV MODE — no SMTP] Email to %s\n   Subject: %s\n   "
            "Check the link in the HTML body above.",
            to_email, subject,
        )
        # Extract first http link for convenience
        import re
        links = re.findall(r'href="(https?://[^"]+)"', html_body)
        for link in links:
            if "verify" in link or "reset" in link:
                logger.info("   👉 Action link: %s", link)
                break
        return

    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            start_tls=True,
        )
        logger.info("Email sent to %s: %s", to_email, subject)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        raise


# ── Public API ─────────────────────────────────────────────────────────────────

async def send_verification_email(email: str, token: str) -> None:
    verify_url = f"{settings.app_base_url}/verify-email.html?token={token}"
    await _send_email(
        to_email=email,
        subject=f"Verify your {settings.app_name} email address",
        html_body=_verification_email_html(verify_url),
    )


async def send_password_reset_email(email: str, token: str) -> None:
    reset_url = f"{settings.app_base_url}/reset-password.html?token={token}"
    await _send_email(
        to_email=email,
        subject=f"Reset your {settings.app_name} password",
        html_body=_reset_password_email_html(reset_url),
    )
