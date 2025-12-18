from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import boto3

logger = logging.getLogger(__name__)


@dataclass
class ConsumerConfig:
    queue_url: str
    region: str
    batch_size: int = 10
    wait_time_seconds: int = 20  # Long polling
    visibility_timeout: int = 30


class BaseConsumer(ABC):
    """Base class for SQS consumers."""

    def __init__(self, config: ConsumerConfig):
        self.config = config
        self.sqs = boto3.client("sqs", region_name=config.region)
        self._running = False

    @abstractmethod
    def process_event(self, event: Dict[str, Any]) -> bool:
        """Process a single event. Return True if successful."""
        raise NotImplementedError

    def receive_messages(self) -> List[Dict[str, Any]]:
        """Receive messages from SQS with long polling."""
        response = self.sqs.receive_message(
            QueueUrl=self.config.queue_url,
            MaxNumberOfMessages=self.config.batch_size,
            WaitTimeSeconds=self.config.wait_time_seconds,
            VisibilityTimeout=self.config.visibility_timeout,
            MessageAttributeNames=["All"],
        )
        return response.get("Messages", [])

    def delete_message(self, receipt_handle: str) -> None:
        """Delete a successfully processed message."""
        self.sqs.delete_message(
            QueueUrl=self.config.queue_url,
            ReceiptHandle=receipt_handle,
        )

    def process_batch(self) -> Dict[str, int]:
        """Process a batch of messages. Returns stats."""
        stats = {"received": 0, "processed": 0, "failed": 0}
        
        messages = self.receive_messages()
        stats["received"] = len(messages)

        for msg in messages:
            try:
                body = json.loads(msg["Body"])
                if self.process_event(body):
                    self.delete_message(msg["ReceiptHandle"])
                    stats["processed"] += 1
                else:
                    stats["failed"] += 1
            except Exception:
                logger.exception(f"Error processing message {msg.get('MessageId')}")
                stats["failed"] += 1

        return stats

    def run(self, max_iterations: int = 0) -> None:
        """Run the consumer loop.
        
        Args:
            max_iterations: Stop after N iterations (0 = infinite)
        """
        self._running = True
        iterations = 0
        total_stats = {"received": 0, "processed": 0, "failed": 0}

        logger.info(f"Starting consumer for {self.config.queue_url}")

        while self._running:
            try:
                stats = self.process_batch()
                for k, v in stats.items():
                    total_stats[k] += v

                if stats["received"] > 0:
                    logger.info(f"Batch: {stats} | Total: {total_stats}")

                iterations += 1
                if max_iterations > 0 and iterations >= max_iterations:
                    logger.info(f"Reached max iterations ({max_iterations})")
                    break

            except KeyboardInterrupt:
                logger.info("Shutting down consumer")
                break
            except Exception:
                logger.exception("Error in consumer loop")
                time.sleep(5)  # Back off on error

        self._running = False
        logger.info(f"Consumer stopped. Final stats: {total_stats}")

    def stop(self) -> None:
        """Signal the consumer to stop."""
        self._running = False

