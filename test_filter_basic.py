#!/usr/bin/env python3
"""
Test basic filter functionality to identify the 500 error cause.
"""
import sys
sys.path.insert(0, 'src')

from utils.filters import parse_filter_params

# Test 1: Empty query params (like GET /events with no params)
print("Test 1: Empty query params")
try:
    result = parse_filter_params({})
    print(f"  ✓ Success: {result}")
except Exception as e:
    print(f"  ✗ FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Only reserved params (like GET /events?status=pending)
print("\nTest 2: Only reserved params")
try:
    result = parse_filter_params({'status': 'pending', 'limit': '50'})
    print(f"  ✓ Success: {result}")
except Exception as e:
    print(f"  ✗ FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Valid filter
print("\nTest 3: Valid filter")
try:
    result = parse_filter_params({'payload.order_id': '12345'})
    print(f"  ✓ Success: {result}")
except Exception as e:
    print(f"  ✗ FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Filter with operator
print("\nTest 4: Filter with operator")
try:
    result = parse_filter_params({'payload.amount[gte]': '100'})
    print(f"  ✓ Success: {result}")
except Exception as e:
    print(f"  ✗ FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

