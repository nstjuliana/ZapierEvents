# Phase 3 Deployment Testing Guide

## 🎉 Deployment Successful! Now Let's Test It

Your Phase 3 deployment is complete. This guide provides comprehensive testing to verify all features work correctly in production.

## 🚀 Quick Start Testing

### Option 1: Python Script (Recommended)
```bash
# Install dependencies (if not already installed)
pip install requests

# Run the comprehensive test
python test_deployment.py --api-url "https://your-api-id.execute-api.region.amazonaws.com"
```

### Option 2: Curl Script (Linux/Mac)
```bash
# Make script executable
chmod +x test_deployment_curl.sh

# Run the test
./test_deployment_curl.sh "https://your-api-id.execute-api.region.amazonaws.com"
```

### Option 3: Manual Testing
Follow the step-by-step manual testing section below.

## 📊 Expected Test Results

### ✅ **Successful Test Output:**
```
🚀 Phase 3 Deployment Testing
API URL: https://abc123.execute-api.us-east-1.amazonaws.com
API Key: your-api-key

🧪 Testing: Health Endpoint
✅ PASSED: Health Endpoint

🧪 Testing: Event Creation & Delivery
✅ PASSED: Event Creation & Delivery

🧪 Testing: Failed Delivery & Queuing
✅ PASSED: Failed Delivery & Queuing

🧪 Testing: Event Retrieval & Listing
✅ PASSED: Event Retrieval & Listing

🧪 Testing: Inbox Functionality
✅ PASSED: Inbox Functionality

=============================================================
DEPLOYMENT TEST SUMMARY
=============================================================
Tests Passed: 5/5
Success Rate: 100%

🎉 ALL TESTS PASSED!
Your Phase 3 deployment is working perfectly!
```

## 🧪 Manual Testing Steps

If you prefer to test manually or need to debug issues:

### 1. **Test Health Endpoint**
```bash
curl "https://your-api-id.execute-api.region.amazonaws.com/health"
```
**Expected:** `{"status": "ok", "message": "Triggers API is healthy", "version": "0.1.0"}`

### 2. **Create Test Event**
```bash
curl -X POST "https://your-api-id.execute-api.region.amazonaws.com/events" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "test.manual",
    "payload": {"message": "manual test"},
    "metadata": {"source": "manual_test"}
  }'
```
**Expected:** `202 Accepted` with event_id in response

### 3. **Check Event Status**
```bash
curl "https://your-api-id.execute-api.region.amazonaws.com/events/EVENT_ID_FROM_STEP_2" \
  -H "Authorization: Bearer YOUR_API_KEY"
```
**Expected:** Event details with status `delivered` or `pending`

### 4. **List Recent Events**
```bash
curl "https://your-api-id.execute-api.region.amazonaws.com/events?limit=5" \
  -H "Authorization: Bearer YOUR_API_KEY"
```
**Expected:** Array of recent events

### 5. **Check Inbox**
```bash
curl "https://your-api-id.execute-api.region.amazonaws.com/inbox?limit=5" \
  -H "Authorization: Bearer YOUR_API_KEY"
```
**Expected:** JSON array of inbox events (may be empty if all delivered successfully)
```json
[
  {
    "event_id": "evt_abc123xyz456",
    "event_type": "order.created",
    "status": "pending",
    "created_at": "2024-01-15T10:30:01Z",
    "delivered_at": null,
    "delivery_attempts": 1
  }
]
```

## 🔍 Monitoring & Verification

### **CloudWatch Monitoring**
1. **Open CloudWatch Console** → Dashboards → `triggers-api-dev-monitoring`
2. **Verify Metrics:**
   - EventCreated count increasing
   - EventDelivered count increasing
   - Inbox depth (should be low)
   - API Gateway and Lambda metrics

### **Lambda Logs**
1. **Open CloudWatch Console** → Logs → Log Groups
2. **Check Logs:**
   - `/aws/lambda/triggers-api-dev-EventsFunction` - API requests
   - `/aws/lambda/triggers-api-dev-DeliveryWorkerFunction` - SQS processing

### **SQS Queues**
1. **Open SQS Console**
2. **Check Queues:**
   - `triggers-api-dev-inbox-queue` - Should be mostly empty
   - `triggers-api-dev-inbox-dlq` - Should be empty (no failed messages)

### **DynamoDB Table**
1. **Open DynamoDB Console** → Tables → `triggers-api-dev-events`
2. **Query Recent Events:**
   ```sql
   SELECT * FROM "triggers-api-dev-events"
   WHERE created_at >= '2024-01-01T00:00:00Z'
   ORDER BY created_at DESC
   LIMIT 10
   ```

## 🚨 Troubleshooting

### **Test Failures:**

#### **Health Endpoint Fails (401/403)**
- **Issue:** API Gateway authentication not configured
- **Fix:** Check if API has authentication enabled in template
- **Verify:** `sam deploy` may have overridden auth settings

#### **Event Creation Fails (401 Unauthorized)**
- **Issue:** Invalid or missing API key
- **Fix:** Use correct API key from your deployment
- **Check:** API key authentication in CloudWatch logs

#### **Event Status Stuck on "pending"**
- **Issue:** Zapier webhook not responding or network issues
- **Normal:** With mock webhook, events may stay pending
- **Verify:** Check Lambda logs for delivery attempts

#### **Inbox Has Many Events**
- **Issue:** Delivery consistently failing
- **Check:**
  - Zapier webhook URL configuration
  - Network connectivity from Lambda
  - Webhook service availability

#### **CloudWatch Metrics Not Appearing**
- **Issue:** IAM permissions or metric publishing failures
- **Check:** Lambda logs for metric publishing errors
- **Verify:** `CloudWatchPutMetricPolicy` attached to functions

### **Performance Issues:**

#### **High Latency**
- **Check:** Lambda function memory allocation (currently 512MB)
- **Optimize:** Increase memory if needed for better CPU performance

#### **SQS Processing Delays**
- **Check:** Event source mapping batch size (currently 10)
- **Monitor:** SQS message age in CloudWatch

## 🎯 Phase 3 Features Verification

When all tests pass, your deployment includes:

### ✅ **Core Features**
- **Event Ingestion:** RESTful API accepts JSON events
- **Immediate Delivery:** Events pushed to Zapier webhooks
- **Status Tracking:** Events tracked in DynamoDB with timestamps
- **Error Handling:** Failed deliveries logged and queued

### ✅ **Advanced Features**
- **Retry Logic:** Exponential backoff (1s→2s→4s→8s→16s)
- **SQS Queuing:** Failed deliveries automatically queued
- **Lambda Worker:** SQS messages processed asynchronously
- **DLQ Monitoring:** Email alerts for permanently failed messages
- **CloudWatch Metrics:** Complete observability dashboard

### ✅ **Production Readiness**
- **Fault Tolerant:** Automatic retry and dead letter queues
- **Scalable:** Serverless architecture handles traffic spikes
- **Observable:** Comprehensive monitoring and alerting
- **Secure:** API key authentication and IAM permissions

## 🎉 Success Confirmation

**Your Phase 3 deployment is successful when:**

✅ **All tests pass (5/5)**
✅ **Events created and delivered successfully**
✅ **CloudWatch metrics updating**
✅ **No errors in Lambda logs**
✅ **SQS queues remain empty (successful processing)**
✅ **DLQ stays empty (no permanent failures)**

## 🚀 Next Steps

1. **Replace Mock Webhook:** Update `ZapierWebhookUrl` with real Zapier webhook
2. **Configure Alerts:** Ensure DLQ alert emails are going to the right address
3. **Monitor Performance:** Set up CloudWatch alarms for error rates
4. **Scale Testing:** Send higher volumes to test auto-scaling
5. **Documentation:** Update your API documentation with the new endpoints

**Congratulations! Your automated event delivery system is now live!** 🚀

---

*Need help? Check the CloudWatch logs for detailed error information.*
