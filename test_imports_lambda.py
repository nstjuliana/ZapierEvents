#!/usr/bin/env python3
"""
Test script to verify imports work correctly from Lambda context (src/ as root).
"""
import sys
import os

# Change to src directory to simulate Lambda environment
os.chdir('src')
sys.path.insert(0, '.')

print("=" * 60)
print("Testing imports from Lambda context (src/ as root)")
print("=" * 60)

try:
    print("\n1. Testing handlers.events import...")
    from handlers.events import router as events_router
    print("   ✓ handlers.events imported successfully")
except Exception as e:
    print(f"   ✗ FAILED: {type(e).__name__}: {e}")
    sys.exit(1)

try:
    print("\n2. Testing handlers.inbox import...")
    from handlers.inbox import router as inbox_router
    print("   ✓ handlers.inbox imported successfully")
except Exception as e:
    print(f"   ✗ FAILED: {type(e).__name__}: {e}")
    sys.exit(1)

try:
    print("\n3. Testing utils.filters import...")
    from utils.filters import parse_filter_params
    print("   ✓ utils.filters imported successfully")
except Exception as e:
    print(f"   ✗ FAILED: {type(e).__name__}: {e}")
    sys.exit(1)

try:
    print("\n4. Testing main app import...")
    from main import app, handler
    print("   ✓ main app imported successfully")
except Exception as e:
    print(f"   ✗ FAILED: {type(e).__name__}: {e}")
    sys.exit(1)

try:
    print("\n5. Testing filter parsing...")
    params = {'payload.order_id': '12345', 'metadata.source': 'test'}
    filters = parse_filter_params(params)
    print(f"   ✓ Parsed {len(filters)} filters successfully")
except Exception as e:
    print(f"   ✗ FAILED: {type(e).__name__}: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ ALL IMPORTS SUCCESSFUL - Lambda context working!")
print("=" * 60)

