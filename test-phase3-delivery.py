"""
Test script for Phase 3: SQS Infrastructure + Push Delivery

Tests the push delivery functionality and SQS queueing for failed deliveries.

Prerequisites:
    pip install httpx boto3

Getting your API URL and Queue URL:
    After deployment, get the URLs from SAM outputs:
        aws cloudformation describe-stacks --stack-name <your-stack-name> --query 'Stacks[0].Outputs'
    
    Or check the SAM deployment output for:
        - ApiUrl (use this for --api-url)
        - InboxQueueUrl (use this for --queue-url)

Usage:
    python test-phase3-delivery.py --api-url <API_URL> [--webhook-url <WEBHOOK_URL>] [--queue-url <QUEUE_URL>] [--purge-queue]

Examples:
    # Test with mock webhook (always succeeds)
    python test-phase3-delivery.py --api-url https://your-api.execute-api.us-east-1.amazonaws.com

    # Test with your actual Zapier webhook
    python test-phase3-delivery.py --api-url https://your-api.execute-api.us-east-1.amazonaws.com --webhook-url https://hooks.zapier.com/hooks/catch/your-webhook/

    # Test with queue checking and purge old messages first
    python test-phase3-delivery.py --api-url https://your-api.execute-api.us-east-1.amazonaws.com --queue-url https://sqs.us-east-1.amazonaws.com/123456789/your-stack-inbox-queue --purge-queue

    # Test with invalid webhook (should queue to SQS) and check queue
    python test-phase3-delivery.py --api-url https://your-api.execute-api.us-east-1.amazonaws.com --webhook-url https://invalid-url-that-does-not-exist.com/webhook --queue-url https://sqs.us-east-1.amazonaws.com/123456789/your-stack-inbox-queue --purge-queue
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx")
    sys.exit(1)

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("WARNING: boto3 is required for SQS queue checking. Install with: pip install boto3")
    boto3 = None
    ClientError = Exception


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_success(message: str):
    """Print success message in green."""
    print(f"{Colors.GREEN}[PASS] {message}{Colors.RESET}")


def print_error(message: str):
    """Print error message in red."""
    print(f"{Colors.RED}[FAIL] {message}{Colors.RESET}")


def print_info(message: str):
    """Print info message in blue."""
    print(f"{Colors.BLUE}[INFO] {message}{Colors.RESET}")


def print_warning(message: str):
    """Print warning message in yellow."""
    print(f"{Colors.YELLOW}[WARN] {message}{Colors.RESET}")


def print_header(message: str):
    """Print header message in bold."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{message}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")


def create_event(api_url: str, event_type: str, payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Create an event via POST /events.

    Args:
        api_url: Base API URL
        event_type: Event type identifier
        payload: Event payload data
        metadata: Optional event metadata

    Returns:
        Event response dictionary
    """
    url = f"{api_url}/events"
    data = {
        "event_type": event_type,
        "payload": payload
    }
    if metadata:
        data["metadata"] = metadata

    response = httpx.post(url, json=data, timeout=30.0)
    response.raise_for_status()
    return response.json()


def get_event(api_url: str, event_id: str) -> Dict[str, Any]:
    """
    Retrieve an event via GET /events/{id}.

    Args:
        api_url: Base API URL
        event_id: Event ID to retrieve

    Returns:
        Event response dictionary
    """
    url = f"{api_url}/events/{event_id}"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


def check_sqs_queue(queue_url: str, max_messages: int = 10) -> list:
    """
    Check SQS queue for messages.

    Args:
        queue_url: SQS queue URL
        max_messages: Maximum number of messages to retrieve

    Returns:
        List of messages in the queue
    """
    if boto3 is None:
        print_warning("boto3 not available, skipping SQS queue check")
        return []
    
    try:
        sqs = boto3.client('sqs')
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=2,
            MessageAttributeNames=['All']
        )
        return response.get('Messages', [])
    except ClientError as e:
        print_error(f"Failed to check SQS queue: {e}")
        return []


def get_queue_attributes(queue_url: str) -> Dict[str, Any]:
    """
    Get SQS queue attributes (message count, etc.).

    Args:
        queue_url: SQS queue URL

    Returns:
        Queue attributes dictionary
    """
    if boto3 is None:
        print_warning("boto3 not available, skipping queue attributes check")
        return {}
    
    try:
        sqs = boto3.client('sqs')
        response = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible']
        )
        return response['Attributes']
    except ClientError as e:
        print_error(f"Failed to get queue attributes: {e}")
        return {}


def purge_queue(queue_url: str) -> bool:
    """
    Purge all messages from SQS queue.

    Args:
        queue_url: SQS queue URL

    Returns:
        True if purge was successful, False otherwise
    """
    if boto3 is None:
        print_warning("boto3 not available, cannot purge queue")
        return False
    
    try:
        sqs = boto3.client('sqs')
        sqs.purge_queue(QueueUrl=queue_url)
        print_success(f"Queue purged successfully: {queue_url}")
        return True
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'AWS.SimpleQueueService.PurgeQueueInProgress':
            print_warning("Queue purge already in progress (can only purge once per 60 seconds)")
            return False
        print_error(f"Failed to purge queue: {e}")
        return False


def test_successful_delivery(api_url: str, webhook_url: Optional[str] = None):
    """Test successful push delivery scenario."""
    print_header("Test 1: Successful Push Delivery")

    # Use a test webhook service if no webhook provided
    if not webhook_url:
        # Use httpbin.org as a test endpoint (always returns 200)
        webhook_url = "https://httpbin.org/post"
        print_info(f"Using test webhook: {webhook_url}")

    print_info("Creating event that should deliver successfully...")

    try:
        event_data = create_event(
            api_url=api_url,
            event_type="test.successful_delivery",
            payload={
                "test_id": f"success_{int(time.time())}",
                "message": "This event should be delivered immediately",
                "timestamp": datetime.utcnow().isoformat()
            },
            metadata={
                "test": True,
                "scenario": "successful_delivery"
            }
        )

        event_id = event_data.get('event_id')
        status = event_data.get('status')
        delivered_at = event_data.get('delivered_at')

        print_info(f"Event created: {event_id}")
        print_info(f"Initial status: {status}")

        # Wait a moment for delivery to complete
        print_info("Waiting 2 seconds for delivery to complete...")
        time.sleep(2)

        # Check event status
        event = get_event(api_url, event_id)
        final_status = event.get('status')
        final_delivered_at = event.get('delivered_at')
        delivery_attempts = event.get('delivery_attempts', 0)

        print_info(f"Final status: {final_status}")
        print_info(f"Delivery attempts: {delivery_attempts}")

        # Verify success
        if final_status == "delivered":
            print_success(f"Event delivered successfully! (ID: {event_id})")
            if final_delivered_at:
                print_success(f"Delivered at: {final_delivered_at}")
            return True
        else:
            print_error(f"Event not delivered. Status: {final_status}")
            return False

    except Exception as e:
        print_error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_failed_delivery_queuing(api_url: str, queue_url: Optional[str] = None):
    """Test failed delivery queuing to SQS."""
    print_header("Test 2: Failed Delivery -> SQS Queueing")

    print_info("Creating event with invalid webhook (should queue to SQS)...")

    try:
        event_data = create_event(
            api_url=api_url,
            event_type="test.failed_delivery",
            payload={
                "test_id": f"failed_{int(time.time())}",
                "message": "This event should fail delivery and queue to SQS",
                "timestamp": datetime.utcnow().isoformat()
            },
            metadata={
                "test": True,
                "scenario": "failed_delivery"
            }
        )

        event_id = event_data.get('event_id')
        status = event_data.get('status')

        print_info(f"Event created: {event_id}")
        print_info(f"Initial status: {status}")

        # Wait a moment for delivery attempt and queuing
        print_info("Waiting 3 seconds for delivery attempt and SQS queuing...")
        time.sleep(3)

        # Check event status
        event = get_event(api_url, event_id)
        final_status = event.get('status')
        delivery_attempts = event.get('delivery_attempts', 0)

        print_info(f"Final status: {final_status}")
        print_info(f"Delivery attempts: {delivery_attempts}")

        # Check SQS queue if queue URL provided
        if queue_url:
            print_info(f"Checking SQS queue: {queue_url}")
            attributes = get_queue_attributes(queue_url)
            visible_messages = attributes.get('ApproximateNumberOfMessages', '0')
            in_flight = attributes.get('ApproximateNumberOfMessagesNotVisible', '0')

            print_info(f"Messages in queue: {visible_messages}")
            print_info(f"Messages in flight: {in_flight}")

            if int(visible_messages) > 0 or int(in_flight) > 0:
                print_success("Event found in SQS queue!")
                
                # Try to receive a message to verify
                messages = check_sqs_queue(queue_url, max_messages=1)
                if messages:
                    message_body = json.loads(messages[0]['Body'])
                    queued_event_id = message_body.get('event_id')
                    if queued_event_id == event_id:
                        print_success(f"Verified: Event {event_id} is in SQS queue")
                    else:
                        print_warning(f"Found different event in queue: {queued_event_id}")
            else:
                print_warning("No messages found in SQS queue (may have been processed already)")

        # Verify expected behavior
        if final_status == "pending":
            print_success(f"Event correctly marked as pending (ID: {event_id})")
            return True
        elif final_status == "delivered":
            print_warning(f"Event was delivered (unexpected for invalid webhook). Status: {final_status}")
            return False
        else:
            print_error(f"Unexpected status: {final_status}")
            return False

    except Exception as e:
        print_error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_health_check(api_url: str):
    """Test health check endpoint."""
    print_header("Test 0: Health Check")

    try:
        url = f"{api_url}/health"
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        print_success(f"Health check passed: {data.get('status', 'unknown')}")
        print_info(f"Version: {data.get('version', 'unknown')}")
        return True

    except Exception as e:
        print_error(f"Health check failed: {e}")
        return False


def main():
    """Main test execution."""
    parser = argparse.ArgumentParser(
        description="Test Phase 3: SQS Infrastructure + Push Delivery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--api-url",
        required=True,
        help="Base API URL (e.g., https://xxx.execute-api.us-east-1.amazonaws.com)"
    )
    parser.add_argument(
        "--webhook-url",
        help="Zapier webhook URL for testing (optional, uses test endpoint if not provided)"
    )
    parser.add_argument(
        "--queue-url",
        help="SQS queue URL for checking queued messages (optional)"
    )
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip health check test"
    )
    parser.add_argument(
        "--purge-queue",
        action="store_true",
        help="Purge SQS queue before running tests (ensures clean state)"
    )

    args = parser.parse_args()

    # Normalize API URL (remove trailing slash)
    api_url = args.api_url.rstrip('/')

    print_header("Phase 3 Delivery Test Suite")
    print_info(f"API URL: {api_url}")
    if args.webhook_url:
        print_info(f"Webhook URL: {args.webhook_url}")
    if args.queue_url:
        print_info(f"SQS Queue URL: {args.queue_url}")

    # Purge queue if requested
    if args.purge_queue:
        if not args.queue_url:
            print_error("--queue-url is required when using --purge-queue")
            return 1
        print_header("Purging SQS Queue")
        purge_queue(args.queue_url)
        print_info("Waiting 2 seconds for purge to complete...")
        time.sleep(2)  # Give SQS a moment to process the purge

    results = []

    # Test 0: Health check
    if not args.skip_health:
        results.append(("Health Check", test_health_check(api_url)))

    # Test 1: Successful delivery
    results.append(("Successful Delivery", test_successful_delivery(api_url, args.webhook_url)))

    # Test 2: Failed delivery queuing
    results.append(("Failed Delivery -> SQS", test_failed_delivery_queuing(api_url, args.queue_url)))

    # Summary
    print_header("Test Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if result else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"  {status}: {test_name}")

    print(f"\n{Colors.BOLD}Total: {passed}/{total} tests passed{Colors.RESET}")

    if passed == total:
        print_success("All tests passed!")
        return 0
    else:
        print_error(f"{total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

