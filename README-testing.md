# Phase 2 Endpoints Testing

This script tests all the Phase 2 endpoints for the Triggers API.

## Usage

```bash
python test-phase2-endpoints.py
```

## What it tests

### 1. Health Check
- **Endpoint**: `GET /health`
- **Expected**: 200 OK with API status information

### 2. List All Events
- **Endpoint**: `GET /events`
- **Expected**: 200 OK with JSON array of all events
- **Tests**: Response parsing, event count, sample data

### 3. Get Specific Event
- **Endpoint**: `GET /events/{id}`
- **Expected**: 200 OK with single event details
- **Tests**: Uses first event from list, validates all fields

### 4. Get Inbox (Pending Events)
- **Endpoint**: `GET /inbox`
- **Expected**: 200 OK with JSON array of pending events only
- **Tests**: Response parsing, status filtering (excludes delivered events)

### 5. Acknowledge Event
- **Endpoint**: `POST /events/{id}/acknowledge`
- **Expected**: 204 No Content
- **Tests**: Acknowledgment success, status update verification, timestamp validation

## Sample Output

```
Phase 2 Endpoints Testing Script
API Base URL: https://mmghecrjr5.execute-api.us-east-1.amazonaws.com
Timestamp: 2025-11-10T16:38:40.653569

============================================================
 Testing Health Check
============================================================

GET /health
Status: 200
Response: {
  "status": "ok",
  "message": "Triggers API is healthy",
  "version": "0.1.0",
  "environment": "dev"
}

[SUCCESS] Health check passed:
  Status: ok
  Version: 0.1.0
  Environment: dev

Testing Phase 2 Endpoints:
[... tests continue ...]

============================================================
 Test Results Summary
============================================================
GET /events                    [PASS]
GET /events/{id}              [PASS]
GET /inbox                     [PASS]
POST /events/{id}/acknowledge [PASS]

Overall: 4/4 tests passed
SUCCESS: All Phase 2 endpoints are working correctly!
```

## Requirements

- Python 3.x
- `requests` library (`pip install requests`)

## Configuration

The script is configured for the deployed API at:
```python
API_BASE_URL = "https://mmghecrjr5.execute-api.us-east-1.amazonaws.com"
```

To test against a different environment, update this URL in the script.

## Notes

- The script handles both successful and error responses gracefully
- It provides detailed output for debugging failed requests
- The acknowledgment test modifies data (changes event status to 'delivered')
- All endpoints are tested with realistic data from the actual deployed system
