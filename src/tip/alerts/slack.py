from __future__ import annotations

import os
from slack_sdk.webhook import WebhookClient


def send_slack(message: str, severity: int = 50) -> None:
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        return
    if severity < 80:
        # quiet by default, only high severity
        return
    WebhookClient(url).send(text=message)
