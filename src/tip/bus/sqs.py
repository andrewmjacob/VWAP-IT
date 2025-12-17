from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
import os
import boto3


@dataclass
class SQSConfig:
    queue_url: str
    dlq_url: Optional[str] = None
    region: str = "us-east-1"
    endpoint_url: Optional[str] = None


class SQSBus:
    def __init__(self, cfg: SQSConfig):
        self.cfg = cfg
        endpoint = cfg.endpoint_url or os.getenv("AWS_ENDPOINT_URL")
        self.client = boto3.client("sqs", region_name=cfg.region, endpoint_url=endpoint)

    def publish(self, payload: dict) -> None:
        self.client.send_message(QueueUrl=self.cfg.queue_url, MessageBody=json.dumps(payload))
