"""
Desktop Notification Module — Native Windows Toast Notifications.

Delivers desktop toast alerts for completed background tasks, goal updates,
or user notifications using Windows PowerShell / WinRT fallback.
"""

import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)


def send_notification(title: str, message: str, app_id: str = "Raphael AI") -> bool:
    """Send a native Windows desktop Toast notification.

    Args:
        title: Notification header title.
        message: Body content of the toast message.
        app_id: Application identifier.

    Returns:
        True if notification was dispatched, False otherwise.
    """
    if sys.platform != "win32":
        logger.debug("Desktop notification skipped — non-Windows platform")
        return False

    # Clean quotes for PowerShell command string
    safe_title = title.replace('"', '""').replace("'", "''")
    safe_message = message.replace('"', '""').replace("'", "''")
    safe_app_id = app_id.replace('"', '""').replace("'", "''")

    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    $template = @"
    <toast>
        <visual>
            <binding template="ToastGeneric">
                <text hint-style="subtitle">{safe_title}</text>
                <text hint-style="body">{safe_message}</text>
            </binding>
        </visual>
    </toast>
"@
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{safe_app_id}").Show($toast)
    """

    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            ps_script,
        ]
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            timeout=5,
        )
        logger.info("Sent desktop notification: '%s'", title)
        return True
    except Exception as e:
        logger.warning("Failed to send desktop notification: %s", e)
        return False
