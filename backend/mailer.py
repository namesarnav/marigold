"""Transactional email, over AWS SES in production and the console in dev.

Named `mailer` rather than `email` so it does not shadow the stdlib package.

The default backend is "console": it logs the message and records it in
`SENT_EMAILS`, which is what lets the whole signup/verify/reset flow be
exercised end to end — by hand and in tests — with no AWS credentials. Set
`EMAIL_BACKEND=ses` to send for real.

Sends are best-effort by design. A failure to deliver must not roll back the
signup that triggered it: the user still exists and can hit "resend". Callers
therefore get a bool, not an exception.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import quote

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class SentEmail:
    to: str
    subject: str
    text_body: str
    html_body: str = ""
    headers: dict = field(default_factory=dict)


# Console-backend outbox. Tests read this to pull the link out of the email
# instead of reaching into the database for a token, which keeps them honest
# about what the user actually receives.
SENT_EMAILS: List[SentEmail] = []


def _send_console(message: SentEmail) -> bool:
    SENT_EMAILS.append(message)
    logger.info(
        "[email:console] to=%s subject=%s\n%s",
        message.to,
        message.subject,
        message.text_body,
    )
    return True


def _send_ses(message: SentEmail) -> bool:
    try:
        import boto3  # imported lazily: only needed for the SES backend
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        logger.error(
            "EMAIL_BACKEND=ses but boto3 is not installed; email to %s dropped.",
            message.to,
        )
        return False

    kwargs = {"region_name": settings.ses_region}
    # Omit explicit keys when unset so boto3 picks up the instance role, which
    # is how this runs on EC2. Only local development needs the env vars.
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    try:
        client = boto3.client("ses", **kwargs)
        request = {
            "Source": settings.ses_from_email,
            "Destination": {"ToAddresses": [message.to]},
            "Message": {
                "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": message.text_body, "Charset": "UTF-8"},
                    **(
                        {"Html": {"Data": message.html_body, "Charset": "UTF-8"}}
                        if message.html_body
                        else {}
                    ),
                },
            },
        }
        if settings.ses_configuration_set:
            request["ConfigurationSetName"] = settings.ses_configuration_set
        client.send_email(**request)
        return True
    except (BotoCoreError, ClientError) as exc:
        logger.error("SES send to %s failed: %s", message.to, exc)
        return False


def send_email(message: SentEmail) -> bool:
    if settings.email_backend == "ses":
        return _send_ses(message)
    return _send_console(message)


# --- Link builders ---------------------------------------------------------


def _frontend_link(path: str, token: str) -> str:
    base = settings.frontend_base_url.rstrip("/")
    return f"{base}{path}?token={quote(token, safe='')}"


def verification_link(token: str) -> str:
    return _frontend_link("/verify-email", token)


def reset_link(token: str) -> str:
    return _frontend_link("/reset-password", token)


# --- Messages --------------------------------------------------------------


def _wrap_html(heading: str, body: str, cta_label: str, cta_url: str) -> str:
    return f"""\
<html><body style="font-family:system-ui,-apple-system,sans-serif;color:#1a1a1a">
  <h2 style="margin:0 0 12px">{heading}</h2>
  <p style="margin:0 0 20px;line-height:1.5">{body}</p>
  <p style="margin:0 0 24px">
    <a href="{cta_url}"
       style="background:#1a1a1a;color:#fff;padding:11px 20px;border-radius:6px;
              text-decoration:none;display:inline-block">{cta_label}</a>
  </p>
  <p style="margin:0;color:#666;font-size:13px">
    If the button does not work, paste this into your browser:<br>
    <span style="word-break:break-all">{cta_url}</span>
  </p>
</body></html>"""


def send_verification_email(to: str, name: Optional[str], token: str) -> bool:
    url = verification_link(token)
    greeting = f"Hi {name}," if name else "Hi,"
    minutes = settings.verification_token_expire_minutes
    hours = max(1, minutes // 60)
    text = (
        f"{greeting}\n\n"
        "Confirm your email address to start using Marigold:\n\n"
        f"{url}\n\n"
        f"This link expires in {hours} hour(s). "
        "If you did not create an account, you can ignore this email.\n"
    )
    return send_email(
        SentEmail(
            to=to,
            subject="Confirm your email address",
            text_body=text,
            html_body=_wrap_html(
                "Confirm your email address",
                "Confirm your address to start using Marigold. This link expires "
                f"in {hours} hour(s).",
                "Confirm email",
                url,
            ),
        )
    )


def send_password_reset_email(to: str, name: Optional[str], token: str) -> bool:
    url = reset_link(token)
    greeting = f"Hi {name}," if name else "Hi,"
    minutes = settings.reset_token_expire_minutes
    text = (
        f"{greeting}\n\n"
        "You asked to reset your Marigold password. Choose a new one here:\n\n"
        f"{url}\n\n"
        f"This link expires in {minutes} minutes and can only be used once.\n"
        "If you did not request this, ignore this email — your password is "
        "unchanged.\n"
    )
    return send_email(
        SentEmail(
            to=to,
            subject="Reset your Marigold password",
            text_body=text,
            html_body=_wrap_html(
                "Reset your password",
                f"Choose a new password. This link expires in {minutes} minutes "
                "and can only be used once.",
                "Reset password",
                url,
            ),
        )
    )
