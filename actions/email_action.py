"""
Email Action Module — Low-level SMTP/IMAP email handling.

Supports sending emails (with HTML formatting and attachments) via SMTP
and fetching/searching inbox emails via IMAP.
"""

import email
import imaplib
import logging
import os
import smtplib
from email.header import decode_header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def _get_config():
    """Retrieve email configuration parameters from config / environment."""
    return {
        "smtp_host": getattr(config, "EMAIL_HOST", os.getenv("EMAIL_HOST", "smtp.gmail.com")),
        "smtp_port": int(getattr(config, "EMAIL_PORT", os.getenv("EMAIL_PORT", "587"))),
        "user": getattr(config, "EMAIL_USER", os.getenv("EMAIL_USER", "")),
        "password": getattr(config, "EMAIL_PASSWORD", os.getenv("EMAIL_PASSWORD", "")),
        "imap_host": getattr(config, "IMAP_HOST", os.getenv("IMAP_HOST", "imap.gmail.com")),
        "imap_port": int(getattr(config, "IMAP_PORT", os.getenv("IMAP_PORT", "993"))),
    }


def send_email(
    to_email: str,
    subject: str,
    body: str,
    is_html: bool = False,
    attachments: list[str] | None = None,
) -> dict:
    """Send an email via SMTP with optional attachments.

    Returns dict with success status and message.
    """
    cfg = _get_config()
    if not cfg["user"] or not cfg["password"]:
        return {
            "success": False,
            "error": "Email credentials not configured. Please set EMAIL_USER and EMAIL_PASSWORD (App Password) in settings.toml (or via Settings dialog).",
        }

    msg = MIMEMultipart()
    msg["From"] = cfg["user"]
    msg["To"] = to_email
    msg["Subject"] = subject

    mime_type = "html" if is_html else "plain"
    msg.attach(MIMEText(body, mime_type, "utf-8"))

    if attachments:
        for filepath in attachments:
            path = Path(filepath)
            if path.exists():
                try:
                    with open(path, "rb") as f:
                        part = MIMEApplication(f.read(), Name=path.name)
                    part["Content-Disposition"] = f'attachment; filename="{path.name}"'
                    msg.attach(part)
                except Exception as e:
                    logger.warning("Failed to attach file %s: %s", filepath, e)
            else:
                logger.warning("Attachment file not found: %s", filepath)

    try:
        if cfg["smtp_port"] == 465:
            with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=15) as server:
                server.login(cfg["user"], cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=15) as server:
                server.starttls()
                server.login(cfg["user"], cfg["password"])
                server.send_message(msg)

        logger.info("Email sent successfully to %s", to_email)
        return {"success": True, "message": f"Email sent successfully to {to_email}"}
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return {"success": False, "error": f"Failed to send email: {e}"}


def _decode_str(s) -> str:
    """Safely decode encoded email header string."""
    if not s:
        return ""
    decoded_list = decode_header(s)
    header_parts = []
    for bytes_or_str, encoding in decoded_list:
        if isinstance(bytes_or_str, bytes):
            try:
                header_parts.append(bytes_or_str.decode(encoding or "utf-8", errors="replace"))
            except Exception:
                header_parts.append(bytes_or_str.decode("utf-8", errors="replace"))
        else:
            header_parts.append(str(bytes_or_str))
    return "".join(header_parts)


def read_inbox(folder: str = "INBOX", limit: int = 5) -> dict:
    """Fetch the latest N emails from specified IMAP mailbox folder."""
    cfg = _get_config()
    if not cfg["user"] or not cfg["password"]:
        return {
            "success": False,
            "error": "Email credentials not configured. Please set EMAIL_USER and EMAIL_PASSWORD (App Password) in settings.toml (or via Settings dialog).",
        }

    try:
        with imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"]) as mail:
            mail.login(cfg["user"], cfg["password"])
            mail.select(folder, readonly=True)

            status, messages = mail.search(None, "ALL")
            if status != "OK" or not messages[0]:
                return {"success": True, "count": 0, "emails": []}

            mail_ids = messages[0].split()
            latest_ids = mail_ids[-limit:]
            latest_ids.reverse()

            emails = []
            for mail_id in latest_ids:
                res, data = mail.fetch(mail_id, "(RFC822)")
                if res != "OK":
                    continue

                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = _decode_str(msg.get("Subject"))
                        sender = _decode_str(msg.get("From"))
                        date_str = msg.get("Date", "")

                        snippet = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                c_type = part.get_content_type()
                                c_disp = str(part.get("Content-Disposition"))
                                if c_type == "text/plain" and "attachment" not in c_disp:
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        snippet = payload.decode(errors="replace")[:300].strip()  # type: ignore[union-attr]
                                        break
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                snippet = payload.decode(errors="replace")[:300].strip()  # type: ignore[union-attr]

                        emails.append({
                            "id": mail_id.decode("utf-8"),
                            "subject": subject,
                            "from": sender,
                            "date": date_str,
                            "snippet": snippet,
                        })

            return {"success": True, "count": len(emails), "emails": emails}
    except Exception as e:
        logger.error("Failed to read inbox: %s", e)
        return {"success": False, "error": f"Failed to read inbox: {e}"}


def search_emails(query: str, folder: str = "INBOX", limit: int = 5) -> dict:
    """Search emails in IMAP mailbox using criteria or keyword."""
    cfg = _get_config()
    if not cfg["user"] or not cfg["password"]:
        return {
            "success": False,
            "error": "Email credentials not configured. Please set EMAIL_USER and EMAIL_PASSWORD (App Password) in settings.toml (or via Settings dialog).",
        }

    try:
        with imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"]) as mail:
            mail.login(cfg["user"], cfg["password"])
            mail.select(folder, readonly=True)

            search_criterion = f'TEXT "{query}"' if query else "ALL"
            status, messages = mail.search(None, search_criterion)
            if status != "OK" or not messages[0]:
                return {"success": True, "count": 0, "emails": []}

            mail_ids = messages[0].split()
            latest_ids = mail_ids[-limit:]
            latest_ids.reverse()

            emails = []
            for mail_id in latest_ids:
                res, data = mail.fetch(mail_id, "(RFC822)")
                if res != "OK":
                    continue

                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = _decode_str(msg.get("Subject"))
                        sender = _decode_str(msg.get("From"))
                        date_str = msg.get("Date", "")

                        snippet = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                c_type = part.get_content_type()
                                c_disp = str(part.get("Content-Disposition"))
                                if c_type == "text/plain" and "attachment" not in c_disp:
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        snippet = payload.decode(errors="replace")[:300].strip()  # type: ignore[union-attr]
                                        break
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                snippet = payload.decode(errors="replace")[:300].strip()  # type: ignore[union-attr]

                        emails.append({
                            "id": mail_id.decode("utf-8"),
                            "subject": subject,
                            "from": sender,
                            "date": date_str,
                            "snippet": snippet,
                        })

            return {"success": True, "count": len(emails), "emails": emails}
    except Exception as e:
        logger.error("Failed to search emails: %s", e)
        return {"success": False, "error": f"Failed to search emails: {e}"}
