#!/usr/bin/env python3
"""
Phase 2 Endpoints Testing Script

Tests all Phase 2 endpoints for the Triggers API:
- GET /events - List all events
- GET /events/{id} - Get specific event
- GET /inbox - Get pending events
- POST /events/{id}/acknowledge - Acknowledge event delivery

Usage: python test-phase2-endpoints.py
"""

import requests
import json
import sys
from datetime import datetime

# API Configuration
API_BASE_URL = "https://mmghecrjr5.execute-api.us-east-1.amazonaws.com"

def print_header(title):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def print_response(method, url, response):
    """Print formatted API response"""
    print(f"\n{method} {url}")
    print(f"Status: {response.status_code}")

    if response.status_code == 204:
        print("Response: No Content (204)")
        return

    try:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
    except:
        print(f"Response: {response.text}")

def test_get_events():
    """Test GET /events endpoint"""
    print_header("Testing GET /events")

    url = f"{API_BASE_URL}/events"
    response = requests.get(url)

    print_response("GET", "/events", response)

    if response.status_code == 200:
        try:
            data = response.json()
            print(f"\n[SUCCESS] Successfully retrieved {len(data)} events")
            if data:
                print(f"Sample event: {data[0]['event_id']} ({data[0]['status']})")
        except:
            print("[ERROR] Failed to parse JSON response")
    else:
        print(f"[ERROR] Request failed with status {response.status_code}")

    return response

def test_get_specific_event():
    """Test GET /events/{id} endpoint"""
    print_header("Testing GET /events/{id}")

    # First get list of events to pick one
    url = f"{API_BASE_URL}/events"
    response = requests.get(url)

    if response.status_code != 200:
        print("[ERROR] Cannot test specific event - GET /events failed")
        return None

    try:
        events = response.json()
        if not events:
            print("[INFO] No events available to test specific event retrieval")
            return None

        # Test with the first event
        event_id = events[0]['event_id']
        url = f"{API_BASE_URL}/events/{event_id}"
        response = requests.get(url)

        print_response("GET", f"/events/{event_id}", response)

        if response.status_code == 200:
            try:
                data = response.json()
                print(f"\n[SUCCESS] Successfully retrieved event {data['event_id']}")
                print(f"  Type: {data['event_type']}")
                print(f"  Status: {data['status']}")
                print(f"  Created: {data['created_at']}")
            except:
                print("[ERROR] Failed to parse JSON response")
        else:
            print(f"[ERROR] Request failed with status {response.status_code}")

        return response

    except:
        print("[ERROR] Failed to parse events list")
        return None

def test_get_inbox():
    """Test GET /inbox endpoint"""
    print_header("Testing GET /inbox")

    url = f"{API_BASE_URL}/inbox"
    response = requests.get(url)

    print_response("GET", "/inbox", response)

    if response.status_code == 200:
        try:
            data = response.json()
            print(f"\n[SUCCESS] Successfully retrieved {len(data)} pending events from inbox")
            if data:
                print(f"Sample pending event: {data[0]['event_id']} ({data[0]['status']})")
        except:
            print("[ERROR] Failed to parse JSON response")
    else:
        print(f"[ERROR] Request failed with status {response.status_code}")

    return response

def test_acknowledge_event():
    """Test POST /events/{id}/acknowledge endpoint"""
    print_header("Testing POST /events/{id}/acknowledge")

    # First get list of events to find a pending one
    url = f"{API_BASE_URL}/events"
    response = requests.get(url)

    if response.status_code != 200:
        print("[ERROR] Cannot test acknowledgment - GET /events failed")
        return None

    try:
        events = response.json()
        pending_events = [e for e in events if e['status'] == 'pending']

        if not pending_events:
            print("[INFO] No pending events available to acknowledge")
            return None

        # Test with the first pending event
        event_id = pending_events[0]['event_id']
        url = f"{API_BASE_URL}/events/{event_id}/acknowledge"
        response = requests.post(url)

        print_response("POST", f"/events/{event_id}/acknowledge", response)

        if response.status_code == 204:
            print(f"\n[SUCCESS] Successfully acknowledged event {event_id}")

            # Verify the event is now delivered
            verify_url = f"{API_BASE_URL}/events/{event_id}"
            verify_response = requests.get(verify_url)

            if verify_response.status_code == 200:
                data = verify_response.json()
                if data['status'] == 'delivered':
                    print(f"[SUCCESS] Event status updated to: {data['status']}")
                    if data['delivered_at']:
                        print(f"[SUCCESS] Delivered timestamp: {data['delivered_at']}")
                else:
                    print(f"[ERROR] Event status not updated: {data['status']}")
            else:
                print("[ERROR] Could not verify event status update")

        else:
            print(f"[ERROR] Acknowledgment failed with status {response.status_code}")

        return response

    except Exception as e:
        print(f"[ERROR] Error during acknowledgment test: {e}")
        return None

def test_health_check():
    """Test health check endpoint"""
    print_header("Testing Health Check")

    url = f"{API_BASE_URL}/health"
    response = requests.get(url)

    print_response("GET", "/health", response)

    if response.status_code == 200:
        try:
            data = response.json()
            print("\n[SUCCESS] Health check passed:")
            print(f"  Status: {data['status']}")
            print(f"  Version: {data['version']}")
            print(f"  Environment: {data['environment']}")
        except:
            print("[ERROR] Failed to parse health check response")
    else:
        print(f"[ERROR] Health check failed with status {response.status_code}")

    return response

def main():
    """Run all Phase 2 endpoint tests"""
    print("Phase 2 Endpoints Testing Script")
    print(f"API Base URL: {API_BASE_URL}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Test health check first
    health_response = test_health_check()

    if health_response and health_response.status_code != 200:
        print("\n[X] Health check failed - API may not be available")
        sys.exit(1)

    # Test all Phase 2 endpoints
    results = []

    print("\nTesting Phase 2 Endpoints:")

    # 1. GET /events
    events_response = test_get_events()
    results.append(("GET /events", events_response and events_response.status_code == 200))

    # 2. GET /events/{id}
    specific_response = test_get_specific_event()
    results.append(("GET /events/{id}", specific_response and specific_response.status_code == 200))

    # 3. GET /inbox
    inbox_response = test_get_inbox()
    results.append(("GET /inbox", inbox_response and inbox_response.status_code == 200))

    # 4. POST /events/{id}/acknowledge
    acknowledge_response = test_acknowledge_event()
    results.append(("POST /events/{id}/acknowledge", acknowledge_response and acknowledge_response.status_code == 204))

    # Summary
    print_header("Test Results Summary")

    passed = 0
    total = len(results)

    for endpoint, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print("15")
        if success:
            passed += 1

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("SUCCESS: All Phase 2 endpoints are working correctly!")
    else:
        print("WARNING: Some tests failed - check the output above")
        sys.exit(1)

if __name__ == "__main__":
    main()
