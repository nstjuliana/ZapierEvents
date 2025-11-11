"""
Module: sqs.py
Description: SQS client for event queue operations.

Handles sending events to inbox queue, receiving messages for
processing, and deleting messages after successful delivery.
"""

import json
from typing import Dict, Any, Optional
from aioboto3 import Session
from botocore.exceptions import ClientError

from utils.logger import get_logger

logger = get_logger(__name__)


class SQSClient:
    """
    SQS client for event queue operations.

    Provides methods for sending events to the inbox queue,
    receiving messages for processing, and managing message lifecycle.
    """

    def __init__(self, queue_url: str):
        """
        Initialize SQS client.

        Args:
            queue_url: URL of the SQS queue
        """
        if not queue_url or not isinstance(queue_url, str):
            raise ValueError("queue_url must be a non-empty string")

        self.queue_url = queue_url
        self.session = Session()

        logger.info(
            "SQS client initialized",
            queue_url=queue_url
        )

    async def send_message(
        self,
        event_id: str,
        event_data: Dict[str, Any],
        delay_seconds: int = 0
    ) -> str:
        """
        Send event to SQS queue.

        Args:
            event_id: Unique event identifier
            event_data: Event data to queue
            delay_seconds: Optional delay before message becomes available

        Returns:
            Message ID from SQS

        Raises:
            ClientError: If SQS operation fails
            ValueError: If parameters are invalid
        """
        if not event_id or not isinstance(event_id, str):
            raise ValueError("event_id must be a non-empty string")
        if not event_data or not isinstance(event_data, dict):
            raise ValueError("event_data must be a non-empty dictionary")

        try:
            async with self.session.client('sqs') as sqs:
                response = await sqs.send_message(
                    QueueUrl=self.queue_url,
                    MessageBody=json.dumps(event_data),
                    MessageAttributes={
                        'EventId': {
                            'StringValue': event_id,
                            'DataType': 'String'
                        }
                    },
                    DelaySeconds=delay_seconds
                )

                message_id = response['MessageId']
                logger.info(
                    "Message sent to SQS",
                    event_id=event_id,
                    message_id=message_id,
                    queue_url=self.queue_url
                )

                return message_id

        except ClientError as e:
            logger.error(
                "Failed to send message to SQS",
                event_id=event_id,
                error_code=e.response['Error']['Code'],
                error_message=e.response['Error']['Message']
            )
            raise

        except Exception as e:
            logger.error(
                "Unexpected error sending message to SQS",
                event_id=event_id,
                error=str(e)
            )
            raise
