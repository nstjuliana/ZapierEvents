# AWS Architecture Status

## Current Architecture (Phase 0 - Complete)

### ✅ Currently Configured Services

```
API Gateway HTTP API → Lambda (Python 3.11)
```

**Deployed Resources:**
1. **API Gateway HTTP API** (`TriggersApi`)
   - Type: HTTP API (API Gateway v2)
   - Stage: `$default`
   - CORS: Enabled for all origins
   - Endpoint: `https://mmghecrjr5.execute-api.us-east-1.amazonaws.com`

2. **Lambda Function** (`HealthFunction`)
   - Runtime: Python 3.11
   - Memory: 512 MB
   - Timeout: 30 seconds
   - Handler: `main.handler`
   - IAM Role: Auto-created with basic Lambda execution permissions

3. **IAM Role** (`HealthFunctionRole`)
   - Basic Lambda execution role
   - CloudWatch Logs permissions

4. **Lambda Permission** (`HealthFunctionHealthCheckPermission`)
   - Allows API Gateway to invoke the Lambda function

---

## Target Architecture (Full System)

```
API Gateway HTTP API → Lambda (Python) → DynamoDB (events)
                                           ↓
                                    SQS/EventBridge (delivery queue)
```

### ✅ Phase 0 (Complete)
- API Gateway HTTP API
- Lambda (Python 3.11)

### 🔜 Phase 1 (Next)
- DynamoDB Table (events storage)
- Additional Lambda functions for event ingestion
- API key authentication

### 🔜 Phase 2-3 (Future)
- SQS Queue or EventBridge (delivery queue)
- Additional Lambda functions for event delivery
- Retry logic and monitoring

---

## Service Comparison

| Service | Current Status | Target Phase | Purpose |
|---------|----------------|-------------|---------|
| **API Gateway** | ✅ Deployed | Phase 0 | HTTP API endpoint |
| **Lambda** | ✅ Deployed | Phase 0 | Request processing |
| **DynamoDB** | ❌ Not yet | Phase 1 | Event storage |
| **SQS/EventBridge** | ❌ Not yet | Phase 2-3 | Delivery queue |
| **CloudWatch** | ✅ Auto-enabled | All phases | Logging & monitoring |
| **IAM Roles** | ✅ Auto-created | All phases | Permissions |

---

## Current Infrastructure Details

### API Gateway HTTP API
- **API ID:** `mmghecrjr5`
- **Type:** HTTP API (v2) - faster and cheaper than REST API
- **Stage:** `$default` (no stage prefix in URL)
- **CORS:** Enabled for development
- **Routes:** 
  - `GET /health` → HealthFunction

### Lambda Function
- **Function Name:** `triggers-api-dev-HealthFunction-FhVD26FtEwTR`
- **ARN:** `arn:aws:lambda:us-east-1:971422717446:function:triggers-api-dev-HealthFunction-FhVD26FtEwTR`
- **Code Location:** `src/` directory
- **Dependencies:** Installed from `src/requirements.txt`

### IAM Permissions
Currently minimal - only what's needed for:
- Lambda execution
- CloudWatch Logs write access
- API Gateway invoke permission

**Note:** When we add DynamoDB and SQS in future phases, we'll need to add permissions to the Lambda execution role.

---

## Next Steps to Complete Architecture

### Phase 1: Add DynamoDB
- Create DynamoDB table for event storage
- Add DynamoDB permissions to Lambda role
- Implement `POST /events` endpoint
- Store events in DynamoDB

### Phase 2-3: Add Delivery Queue
- Create SQS queue or EventBridge rule
- Add SQS/EventBridge permissions to Lambda role
- Implement delivery Lambda function
- Set up retry logic

---

## CloudFormation Stack

**Stack Name:** `triggers-api-dev`  
**Region:** `us-east-1`  
**Status:** ✅ Active

All resources are managed through AWS SAM (Serverless Application Model) and deployed via CloudFormation.

