# Phase 3: Delivery & Retry Logic

## Overview

**Goal:** Implement automated event delivery with push-first strategy, SQS queue integration, and intelligent retry logic.

**Duration:** 3-4 days

**Success Criteria:**
- Events automatically pushed to Zapier on creation
- Failed pushes queue to SQS for retry
- Retry logic with exponential backoff
- Dead Letter Queue for permanently failed events
- SQS polling Lambda for inbox delivery

**Deliverable:** Fully automated hybrid push/pull delivery system with fault tolerance.

---

## Prerequisites

- Phase 2 completed (event retrieval working)
- DynamoDB storing events
- /inbox endpoint operational

---

## Features & Tasks

### Feature 1: SQS Queue Infrastructure

**Description:** Add SQS queues for event delivery and failed message handling.

**Steps:**
1. Add InboxQueue to SAM template (Standard SQS)
2. Add InboxDLQ (Dead Letter Queue) for failed deliveries
3. Configure visibility timeout (5 minutes)
4. Configure message retention (7 days)
5. Add queue URLs to Lambda environment variables

**Validation:**
- Queues created successfully on deployment
- DLQ configured with correct maxReceiveCount
- Lambda has permissions to send/receive messages

**Template Addition:**
```yaml
Resources:
  InboxQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: !Sub '${AWS::StackName}-inbox-queue'
      VisibilityTimeout: 300  # 5 minutes
      MessageRetentionPeriod: 604800  # 7 days
      ReceiveMessageWaitTimeSeconds: 20  # Long polling
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt InboxDLQ.Arn
        maxReceiveCount: 5
      Tags:
        - Key: Environment
          Value: dev
        - Key: Service
          Value: triggers-api

  InboxDLQ:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: !Sub '${AWS::StackName}-inbox-dlq'
      MessageRetentionPeriod: 1209600  # 14 days
      Tags:
        - Key: Environment
          Value: dev
        - Key: Service
          Value: triggers-api

  # Add queue permissions to EventsFunction
  EventsFunction:
    Type: AWS::Serverless::Function
    Properties:
      # ... existing properties ...
      Environment:
        Variables:
          EVENTS_TABLE_NAME: !Ref EventsTable
          INBOX_QUEUE_URL: !Ref InboxQueue
          ZAPIER_WEBHOOK_URL: !Ref ZapierWebhookUrl
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref EventsTable
        - SQSSendMessagePolicy:
            QueueName: !GetAtt InboxQueue.QueueName

Parameters:
  ZapierWebhookUrl:
    Type: String
    Description: Zapier webhook URL for push delivery
    Default: https://hooks.zapier.com/hooks/catch/mock/
```

---

### Feature 2: SQS Client Module

**Description:** Create SQS client wrapper for queue operations.

**Steps:**
1. Create `src/queue/sqs.py` with SQSClient class
2. Implement `send_message()` for queueing events
3. Implement `receive_messages()` for polling
4. Implement `delete_message()` after successful processing
5. Add structured logging for all operations

**Validation:**
- Messages send successfully to SQS
- Messages can be received and processed
- Messages delete after acknowledgment

**Code Template:**
```python
"""
Module: queue/sqs.py
Description: SQS client for event queue operations.

Handles sending events to inbox queue, receiving messages for
processing, and deleting messages after successful delivery.
"""

import boto3
import json
from typing import List, Dict, Any, Optional
from botocore.exceptions import ClientError

from src.utils.logger import get_logger

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
        self.queue_url = queue_url
        self.sqs = boto3.client('sqs')
    
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
        """
        try:
            response = self.sqs.send_message(
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
                error=str(e)
            )
            raise
    
    async def receive_messages(
        self,
        max_messages: int = 10,
        wait_time_seconds: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Receive messages from SQS queue.
        
        Uses long polling to reduce empty receives and API costs.
        
        Args:
            max_messages: Maximum number of messages to receive (1-10)
            wait_time_seconds: Long polling wait time (up to 20 seconds)
            
        Returns:
            List of message dictionaries with Body and ReceiptHandle
            
        Raises:
            ClientError: If SQS operation fails
        """
        try:
            response = self.sqs.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_seconds,
                MessageAttributeNames=['All'],
                AttributeNames=['All']
            )
            
            messages = response.get('Messages', [])
            logger.info(
                "Messages received from SQS",
                count=len(messages),
                queue_url=self.queue_url
            )
            
            return messages
            
        except ClientError as e:
            logger.error(
                "Failed to receive messages from SQS",
                error=str(e)
            )
            raise
    
    async def delete_message(self, receipt_handle: str) -> None:
        """
        Delete message from queue after successful processing.
        
        Args:
            receipt_handle: Receipt handle from received message
            
        Raises:
            ClientError: If SQS operation fails
        """
        try:
            self.sqs.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle
            )
            
            logger.info("Message deleted from SQS", queue_url=self.queue_url)
            
        except ClientError as e:
            logger.error(
                "Failed to delete message from SQS",
                error=str(e)
            )
            raise
```

---

### Feature 3: Push Delivery Module

**Description:** Implement HTTP push delivery to Zapier webhook.

**Steps:**
1. Create `src/delivery/push.py` with delivery functions
2. Use httpx AsyncClient for HTTP requests
3. Add timeout configuration (10 seconds)
4. Include retry logic for transient failures
5. Log all delivery attempts with results

**Validation:**
- Successfully pushes events to Zapier
- Handles network errors gracefully
- Timeouts work correctly

**Code Template:**
```python
"""
Module: delivery/push.py
Description: Push event delivery to Zapier webhook.

Implements HTTP push delivery with timeout handling and
error recovery for transient failures.
"""

import httpx
from typing import Dict, Any
from datetime import datetime, timezone

from src.models.event import Event
from src.utils.logger import get_logger
from src.config.settings import settings

logger = get_logger(__name__)

class PushDeliveryClient:
    """
    HTTP client for pushing events to Zapier.
    
    Handles delivery attempts with proper timeout and
    error handling for network issues.
    """
    
    def __init__(self, webhook_url: str):
        """
        Initialize push delivery client.
        
        Args:
            webhook_url: Zapier webhook URL for delivery
        """
        self.webhook_url = webhook_url
        self.timeout = httpx.Timeout(10.0, connect=5.0)
    
    async def deliver_event(self, event: Event) -> bool:
        """
        Deliver event to Zapier via HTTP POST.
        
        Args:
            event: Event to deliver
            
        Returns:
            True if delivery successful, False otherwise
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                payload = {
                    'event_id': event.event_id,
                    'event_type': event.event_type,
                    'payload': event.payload,
                    'metadata': event.metadata,
                    'created_at': event.created_at.isoformat()
                }
                
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                )
                
                response.raise_for_status()
                
                logger.info(
                    "Event delivered successfully",
                    event_id=event.event_id,
                    status_code=response.status_code,
                    response_time_ms=response.elapsed.total_seconds() * 1000
                )
                
                return True
                
            except httpx.TimeoutException:
                logger.warning(
                    "Event delivery timeout",
                    event_id=event.event_id,
                    webhook_url=self.webhook_url
                )
                return False
                
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Event delivery HTTP error",
                    event_id=event.event_id,
                    status_code=e.response.status_code,
                    response=e.response.text
                )
                return False
                
            except Exception as e:
                logger.error(
                    "Event delivery failed",
                    event_id=event.event_id,
                    error=str(e)
                )
                return False
```

---

### Feature 4: Retry Logic with Tenacity

**Description:** Implement intelligent retry logic with exponential backoff.

**Steps:**
1. Create `src/delivery/retry.py` with retry decorator
2. Configure exponential backoff (1s, 2s, 4s, 8s, 16s)
3. Add jitter to prevent thundering herd
4. Retry only on transient errors (timeout, 5xx)
5. Log each retry attempt

**Validation:**
- Retries occur on transient failures
- Exponential backoff timing is correct
- Permanent failures don't retry

**Code Template:**
```python
"""
Module: delivery/retry.py
Description: Retry logic for event delivery.

Implements intelligent retry strategies with exponential backoff
and jitter for handling transient delivery failures.
"""

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_log,
    after_log
)
import httpx
import logging

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Configure retry decorator for delivery attempts
delivery_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception_type((
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.HTTPStatusError
    )),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.INFO),
    reraise=True
)

async def retry_delivery(delivery_fn, event):
    """
    Retry event delivery with exponential backoff.
    
    Args:
        delivery_fn: Async function to attempt delivery
        event: Event to deliver
        
    Returns:
        True if delivery succeeds (after retries), False otherwise
    """
    try:
        @delivery_retry
        async def attempt_delivery():
            success = await delivery_fn(event)
            if not success:
                # Raise exception to trigger retry
                raise httpx.HTTPStatusError(
                    "Delivery failed",
                    request=None,
                    response=None
                )
            return success
        
        return await attempt_delivery()
        
    except Exception as e:
        logger.error(
            "Delivery failed after all retries",
            event_id=event.event_id,
            error=str(e)
        )
        return False
```

---

### Feature 5: Automatic Push on Event Creation

**Description:** Modify POST /events to attempt immediate push delivery.

**Steps:**
1. Update `create_event()` handler to attempt push after storage
2. If push succeeds, set status to "delivered"
3. If push fails, queue to SQS and set status to "pending"
4. Return appropriate status in response
5. Track delivery attempt in event metadata

**Validation:**
- Events push immediately on creation (happy path)
- Failed pushes queue correctly to SQS
- Event status reflects delivery state

**Code Modification:**
```python
@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=EventResponse)
async def create_event(
    request: CreateEventRequest,
    db_client: DynamoDBClient = Depends(get_db_client),
    sqs_client: SQSClient = Depends(get_sqs_client),
    delivery_client: PushDeliveryClient = Depends(get_delivery_client)
) -> EventResponse:
    """
    Create and ingest a new event with automatic delivery attempt.
    
    Attempts immediate push delivery to Zapier. If push succeeds,
    marks event as delivered. If push fails, queues to SQS for retry.
    
    Args:
        request: Event creation request
        db_client: DynamoDB client
        sqs_client: SQS client
        delivery_client: Push delivery client
        
    Returns:
        EventResponse with delivery status
    """
    # Generate event ID and create event
    event_id = f"evt_{uuid4().hex[:12]}"
    event = Event(
        event_id=event_id,
        event_type=request.event_type,
        payload=request.payload,
        metadata=request.metadata,
        status="pending",
        created_at=datetime.now(timezone.utc),
        delivered_at=None,
        delivery_attempts=0
    )
    
    # Store in DynamoDB first
    try:
        await db_client.put_event(event)
    except Exception as e:
        logger.error("Failed to store event", event_id=event_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store event"
        )
    
    # Attempt immediate push delivery
    try:
        delivery_success = await delivery_client.deliver_event(event)
        
        if delivery_success:
            # Update to delivered status
            event.status = "delivered"
            event.delivered_at = datetime.now(timezone.utc)
            event.delivery_attempts = 1
            await db_client.update_event(event)
            
            logger.info("Event delivered immediately", event_id=event_id)
            
        else:
            # Queue to SQS for retry
            await sqs_client.send_message(
                event_id=event_id,
                event_data=event.model_dump(mode='json')
            )
            
            logger.info("Event queued for retry", event_id=event_id)
            
    except Exception as e:
        # Queue to SQS as fallback
        logger.warning(
            "Push delivery failed, queueing to SQS",
            event_id=event_id,
            error=str(e)
        )
        try:
            await sqs_client.send_message(
                event_id=event_id,
                event_data=event.model_dump(mode='json')
            )
        except Exception as queue_error:
            logger.error(
                "Failed to queue event to SQS",
                event_id=event_id,
                error=str(queue_error)
            )
    
    return EventResponse(
        event_id=event.event_id,
        status=event.status,
        created_at=event.created_at,
        delivered_at=event.delivered_at,
        delivery_attempts=event.delivery_attempts,
        message=f"Event {event.status}"
    )
```

---

### Feature 6: SQS Polling Lambda

**Description:** Create Lambda function to poll SQS and retry delivery.

**Steps:**
1. Create new Lambda function in SAM template
2. Configure SQS as event source (batch size 10)
3. Implement handler to process SQS messages
4. Attempt delivery for each message
5. Update DynamoDB status based on results

**Validation:**
- Lambda triggers on SQS messages
- Failed deliveries retry correctly
- Successful deliveries update status

**Template Addition:**
```yaml
Resources:
  DeliveryWorkerFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: delivery.worker.handler
      Description: Process events from inbox queue and retry delivery
      Environment:
        Variables:
          EVENTS_TABLE_NAME: !Ref EventsTable
          ZAPIER_WEBHOOK_URL: !Ref ZapierWebhookUrl
      Events:
        SQSEvent:
          Type: SQS
          Properties:
            Queue: !GetAtt InboxQueue.Arn
            BatchSize: 10
            MaximumBatchingWindowInSeconds: 5
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref EventsTable
        - SQSPollerPolicy:
            QueueName: !GetAtt InboxQueue.QueueName
```

**Worker Code:**
```python
"""
Module: delivery/worker.py
Description: SQS worker Lambda for event delivery.

Processes events from SQS inbox queue and retries delivery
to Zapier with status updates in DynamoDB.
"""

import json
from typing import Dict, Any

from src.models.event import Event
from src.delivery.push import PushDeliveryClient
from src.storage.dynamodb import DynamoDBClient
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for SQS event processing.
    
    Args:
        event: SQS event with batch of messages
        context: Lambda context
        
    Returns:
        Response with batch item failures (if any)
    """
    db_client = DynamoDBClient(settings.events_table_name)
    delivery_client = PushDeliveryClient(settings.zapier_webhook_url)
    
    batch_failures = []
    
    for record in event['Records']:
        try:
            # Parse event from SQS message
            event_data = json.loads(record['body'])
            event_obj = Event(**event_data)
            
            logger.info("Processing event from SQS", event_id=event_obj.event_id)
            
            # Attempt delivery
            success = await delivery_client.deliver_event(event_obj)
            
            if success:
                # Update status to delivered
                event_obj.status = "delivered"
                event_obj.delivered_at = datetime.now(timezone.utc)
                event_obj.delivery_attempts += 1
                await db_client.update_event(event_obj)
                
                logger.info("Event delivered from queue", event_id=event_obj.event_id)
            else:
                # Increment attempt count and return to queue
                event_obj.delivery_attempts += 1
                await db_client.update_event(event_obj)
                
                # Report failure to retry (message returns to queue)
                batch_failures.append({
                    'itemIdentifier': record['messageId']
                })
                
                logger.warning(
                    "Event delivery failed, will retry",
                    event_id=event_obj.event_id,
                    attempts=event_obj.delivery_attempts
                )
                
        except Exception as e:
            logger.error(
                "Error processing SQS message",
                message_id=record['messageId'],
                error=str(e)
            )
            batch_failures.append({
                'itemIdentifier': record['messageId']
            })
    
    return {'batchItemFailures': batch_failures}
```

---

### Feature 7: DLQ Monitoring and Alerts

**Description:** Set up CloudWatch alarms for Dead Letter Queue depth.

**Steps:**
1. Add CloudWatch alarm for DLQ message count > 0
2. Configure SNS topic for alarm notifications
3. Add email subscription to SNS topic
4. Test alarm by sending message to DLQ
5. Document DLQ investigation process

**Validation:**
- Alarm triggers when messages enter DLQ
- Email notifications received
- Alarm clears when DLQ is empty

**Template Addition:**
```yaml
Resources:
  DLQAlarmTopic:
    Type: AWS::SNS::Topic
    Properties:
      TopicName: !Sub '${AWS::StackName}-dlq-alarm'
      Subscription:
        - Endpoint: your-email@example.com
          Protocol: email

  DLQAlarm:
    Type: AWS::CloudWatch::Alarm
    Properties:
      AlarmName: !Sub '${AWS::StackName}-dlq-messages'
      AlarmDescription: Alert when messages enter DLQ
      MetricName: ApproximateNumberOfMessagesVisible
      Namespace: AWS/SQS
      Statistic: Sum
      Period: 300
      EvaluationPeriods: 1
      Threshold: 1
      ComparisonOperator: GreaterThanOrEqualToThreshold
      Dimensions:
        - Name: QueueName
          Value: !GetAtt InboxDLQ.QueueName
      AlarmActions:
        - !Ref DLQAlarmTopic
      TreatMissingData: notBreaching
```

---

### Feature 8: Update Event Status Method

**Description:** Add DynamoDB update method for event status changes.

**Steps:**
1. Add `update_event()` method to DynamoDBClient
2. Use update_item with condition expression
3. Only update status, delivered_at, and delivery_attempts
4. Add optimistic locking to prevent race conditions
5. Log all status changes

**Validation:**
- Status updates work correctly
- Concurrent updates handled safely
- All changes logged

---

### Feature 9: Delivery Metrics

**Description:** Add CloudWatch metrics for delivery success/failure rates.

**Steps:**
1. Publish DeliverySuccess metric on successful delivery
2. Publish DeliveryFailure metric on failed delivery
3. Publish DeliveryRetry metric on retry attempts
4. Track DLQ depth as custom metric
5. Add metrics to CloudWatch dashboard

**Validation:**
- Metrics update in real-time
- Dashboard shows delivery health
- Metrics help identify issues

---

### Feature 10: Integration Testing

**Description:** Test complete delivery flow end-to-end.

**Steps:**
1. Test immediate push delivery (happy path)
2. Test push failure → SQS queueing
3. Test SQS processing → retry → success
4. Test max retries → DLQ
5. Test acknowledgment flow

**Validation:**
- All delivery paths work correctly
- Retry logic functions properly
- DLQ catches permanent failures

---

## Phase 3 Completion Checklist

- [ ] SQS queues created (Inbox + DLQ)
- [ ] SQS client module implemented
- [ ] Push delivery module with httpx
- [ ] Retry logic with tenacity
- [ ] POST /events attempts immediate push
- [ ] SQS polling Lambda function
- [ ] DLQ monitoring and alerts
- [ ] DynamoDB update methods
- [ ] Delivery metrics published
- [ ] Integration tests passing
- [ ] Application deployed to AWS
- [ ] End-to-end delivery tested

---

## Testing

### Manual Testing

```bash
# Create event (should push immediately if Zapier reachable)
curl -X POST "$API_URL/events" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"event_type": "test.event", "payload": {"test": true}}'

# Check event status
curl "$API_URL/events/evt_abc123" \
  -H "Authorization: Bearer YOUR_API_KEY"

# Check SQS queue depth
aws sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attribute-names ApproximateNumberOfMessages

# Check DLQ
aws sqs get-queue-attributes \
  --queue-url "$DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages
```

---

## Next Steps

After completing Phase 3, proceed to:
- **Phase 4: Event Replay & Polish** - Implement replay API and final enhancements

**Phase 3 provides:**
- Automated event delivery
- Fault-tolerant delivery with retries
- Complete hybrid push/pull system
- Production-ready reliability

---

## Resources

- [SQS Best Practices](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-best-practices.html)
- [Lambda SQS Event Source](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Tenacity Documentation](https://tenacity.readthedocs.io/)
- [httpx Async Client](https://www.python-httpx.org/async/)

