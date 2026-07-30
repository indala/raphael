"""Native Email tool schemas and functions — send, read, and search emails."""

from actions import email_action


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "send_email",
                "description": "Send an email message via SMTP to a recipient with optional subject, HTML body, and file attachments. Requires EMAIL_USER and EMAIL_PASSWORD (App Password) in configuration.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to_email": {
                            "type": "string",
                            "description": "Recipient email address (e.g., 'user@example.com')",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Subject line of the email",
                        },
                        "body": {
                            "type": "string",
                            "description": "Text or HTML body content of the email",
                        },
                        "is_html": {
                            "type": "boolean",
                            "description": "Set to true if body is HTML formatted. Default: false.",
                        },
                        "attachments": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of local file paths to attach to the email.",
                        },
                    },
                    "required": ["to_email", "subject", "body"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_inbox",
                "description": "Read latest emails from specified IMAP mailbox folder (default: INBOX). Returns sender, subject, date, and body snippets.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "folder": {
                            "type": "string",
                            "description": "IMAP mailbox folder to read (default: 'INBOX').",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of recent emails to fetch (default: 5).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_emails",
                "description": "Search IMAP mailbox for emails matching a search query or keyword (subject, sender, or content).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Keyword, subject phrase, or sender email to search for.",
                        },
                        "folder": {
                            "type": "string",
                            "description": "IMAP mailbox folder to search (default: 'INBOX').",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of matching emails to return (default: 5).",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    ]


def send_email(to_email: str, subject: str, body: str, is_html: bool = False, attachments: list[str] | None = None) -> dict:
    return email_action.send_email(to_email=to_email, subject=subject, body=body, is_html=is_html, attachments=attachments)


def read_inbox(folder: str = "INBOX", limit: int = 5) -> dict:
    return email_action.read_inbox(folder=folder, limit=limit)


def search_emails(query: str, folder: str = "INBOX", limit: int = 5) -> dict:
    return email_action.search_emails(query=query, folder=folder, limit=limit)
