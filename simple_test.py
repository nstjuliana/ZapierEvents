#!/usr/bin/env python3
"""
Simple test for Phase 3 features - basic functionality check
"""

import sys
import os

# Add src to path
sys.path.insert(0, 'src')

# Set minimal environment
os.environ.setdefault('EVENTS_TABLE_NAME', 'test-table')
os.environ.setdefault('API_KEYS_TABLE_NAME', 'test-keys')
os.environ.setdefault('INBOX_QUEUE_URL', 'test-queue')
os.environ.setdefault('ZAPIER_WEBHOOK_URL', 'test-webhook')

def test_imports():
    """Test that all Phase 3 modules can be imported."""
    print("Testing imports...")

    try:
        # Test retry logic import
        from delivery.retry import retry_delivery, delivery_retry
        print("[OK] Retry logic imported successfully")

        # Test worker import
        from delivery.worker import SyncPushDeliveryClient, handler
        print("[OK] SQS worker imported successfully")

        # Test metrics import
        from utils.metrics import MetricsClient
        print("[OK] Metrics client imported successfully")

        return True

    except ImportError as e:
        print(f"[FAIL] Import failed: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality without complex mocking."""
    print("\nTesting basic functionality...")

    try:
        from delivery.retry import delivery_retry
        from delivery.worker import SyncPushDeliveryClient
        from utils.metrics import MetricsClient

        # Test SyncPushDeliveryClient initialization
        client = SyncPushDeliveryClient("https://test.com/webhook")
        assert client.webhook_url == "https://test.com/webhook"
        print("[OK] SyncPushDeliveryClient initializes correctly")

        # Test MetricsClient initialization
        metrics = MetricsClient("TestNamespace")
        assert metrics.namespace == "TestNamespace"
        print("[OK] MetricsClient initializes correctly")

        # Test retry decorator exists
        assert delivery_retry is not None
        print("[OK] Retry decorator is available")

        return True

    except Exception as e:
        print(f"[FAIL] Basic functionality test failed: {e}")
        return False

def main():
    """Run simple tests."""
    print("[TEST] Simple Phase 3 Features Test")
    print("=" * 40)

    results = []

    # Test imports
    results.append(("Imports", test_imports()))

    # Test basic functionality
    results.append(("Basic Functionality", test_basic_functionality()))

    # Summary
    print("\n" + "=" * 40)
    print("SUMMARY:")
    passed = 0
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1

    print(f"\nPassed: {passed}/{len(results)}")

    if passed == len(results):
        print("[SUCCESS] All basic tests passed!")
        return 0
    else:
        print("[ERROR] Some tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
