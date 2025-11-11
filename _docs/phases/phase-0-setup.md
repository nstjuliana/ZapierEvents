# Phase 0: Setup & Deployment Pipeline

## Overview

**Goal:** Establish AWS infrastructure and deploy a "Hello World" version of the Triggers API to validate the deployment pipeline.

**Duration:** 1-2 days

**Success Criteria:**
- AWS account configured with necessary services
- SAM template deploys successfully
- Lambda function responds to API Gateway requests
- Basic CI/CD pipeline operational
- "Hello World" endpoint returns 200 OK

**Deliverable:** A working AWS infrastructure that can deploy and run a simple Lambda-based API.

---

## Prerequisites

- AWS account with administrative access
- AWS CLI installed and configured locally
- Python 3.11+ installed
- SAM CLI installed
- Git repository initialized

---

## Features & Tasks

### Feature 1: AWS Account & CLI Setup

**Description:** Configure AWS account, create IAM user, and set up local AWS CLI credentials.

**Steps:**
1. Create AWS account or use existing one
2. Create IAM user with administrator access for development
3. Generate access keys and configure AWS CLI (`aws configure`)
4. Verify AWS CLI access: `aws sts get-caller-identity`
5. Set default region to `us-east-1` (or preferred region)

**Validation:**
- AWS CLI commands execute successfully
- IAM user has necessary permissions

---

### Feature 2: Project Directory Structure

**Description:** Create the basic project structure following project-rules.md conventions.

**Steps:**
1. Create directory structure: `src/`, `tests/`, `_docs/`
2. Create `src/main.py` with minimal FastAPI application
3. Create `requirements.txt` with FastAPI, Mangum, boto3
4. Create `.gitignore` for Python and AWS artifacts
5. Create `README.md` with project overview

**Validation:**
- Directory structure matches project-rules.md
- All required files present

**Files Created:**
```
zapier-triggers-api/
├── .gitignore
├── README.md
├── requirements.txt
├── src/
│   └── main.py
├── tests/
│   └── __init__.py
└── _docs/
    └── (existing documentation)
```

---

### Feature 3: Hello World FastAPI Application

**Description:** Create a minimal FastAPI application with a single health check endpoint.

**Steps:**
1. Create `src/main.py` with FastAPI app and `/health` endpoint
2. Add Mangum handler to wrap FastAPI for Lambda
3. Return JSON response: `{"status": "ok", "message": "Hello World"}`
4. Test locally with `uvicorn src.main:app --reload`
5. Verify endpoint responds at `http://localhost:8000/health`

**Validation:**
- FastAPI app runs locally
- `/health` endpoint returns 200 OK with JSON response

**Code Template:**
```python
"""
Module: main.py
Description: FastAPI application entry point for Triggers API.
"""

from fastapi import FastAPI
from mangum import Mangum

app = FastAPI(
    title="Zapier Triggers API",
    description="Event ingestion and delivery API",
    version="0.1.0"
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "Hello World",
        "version": "0.1.0"
    }

# Lambda handler
handler = Mangum(app, lifespan="off")
```

---

### Feature 4: AWS SAM Template

**Description:** Create SAM template to define Lambda function and API Gateway.

**Steps:**
1. Create `template.yaml` in project root
2. Define Lambda function with Python 3.11 runtime
3. Define HTTP API Gateway with `/health` route
4. Configure function timeout (30s) and memory (512MB)
5. Add outputs for API URL

**Validation:**
- SAM template validates: `sam validate`
- Template follows AWS SAM specification

**Template Structure:**
```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Zapier Triggers API - Phase 0 Setup

Globals:
  Function:
    Runtime: python3.11
    Timeout: 30
    MemorySize: 512
    Environment:
      Variables:
        LOG_LEVEL: INFO

Resources:
  TriggersApi:
    Type: AWS::Serverless::HttpApi
    Properties:
      StageName: dev
      CorsConfiguration:
        AllowOrigins:
          - "*"
        AllowMethods:
          - GET
          - POST
        AllowHeaders:
          - "*"

  HealthFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: main.handler
      Description: Health check endpoint
      Events:
        HealthCheck:
          Type: HttpApi
          Properties:
            ApiId: !Ref TriggersApi
            Path: /health
            Method: GET

Outputs:
  ApiUrl:
    Description: API Gateway endpoint URL
    Value: !Sub 'https://${TriggersApi}.execute-api.${AWS::Region}.amazonaws.com'
```

---

### Feature 5: Local Testing with SAM CLI

**Description:** Test the Lambda function locally using SAM CLI before deploying to AWS.

**Steps:**
1. Build the application: `sam build`
2. Start local API: `sam local start-api --port 3000`
3. Test health endpoint: `curl http://localhost:3000/health`
4. Verify response matches expected JSON
5. Stop local API (Ctrl+C)

**Validation:**
- SAM build completes without errors
- Local API starts successfully
- Health endpoint responds correctly

---

### Feature 6: Deploy to AWS

**Description:** Deploy the application to AWS using SAM CLI.

**Steps:**
1. Build application: `sam build`
2. Deploy with guided mode: `sam deploy --guided`
3. Configure stack name: `triggers-api-dev`
4. Confirm deployment and save configuration to `samconfig.toml`
5. Note the API Gateway URL from outputs

**Validation:**
- CloudFormation stack creates successfully
- Lambda function is deployed
- API Gateway is accessible
- Health endpoint responds via AWS URL

**Expected Output:**
```
Stack triggers-api-dev outputs:
ApiUrl: https://abc123xyz.execute-api.us-east-1.amazonaws.com
```

---

### Feature 7: Test Deployed Endpoint

**Description:** Verify the deployed application works correctly in AWS.

**Steps:**
1. Get API URL from CloudFormation outputs
2. Test health endpoint: `curl https://<api-url>/health`
3. Verify 200 OK response with correct JSON
4. Check CloudWatch logs for Lambda invocation
5. Confirm no errors in logs

**Validation:**
- Deployed endpoint responds correctly
- CloudWatch logs show successful invocation
- Response time is reasonable (<1000ms for cold start)

---

### Feature 8: Basic CI/CD Pipeline (GitHub Actions)

**Description:** Set up automated deployment pipeline for push to main branch.

**Steps:**
1. Create `.github/workflows/deploy.yml`
2. Configure workflow to trigger on push to main
3. Add steps: checkout, setup Python, install dependencies, build, deploy
4. Configure AWS credentials using GitHub secrets
5. Test pipeline by pushing a minor change

**Validation:**
- Workflow runs successfully on push
- Application deploys to AWS automatically
- CloudFormation stack updates without errors

**Workflow Template:**
```yaml
name: Deploy to AWS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Set up SAM CLI
        uses: aws-actions/setup-sam@v2
      
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      
      - name: Build and deploy
        run: |
          sam build
          sam deploy --no-confirm-changeset --no-fail-on-empty-changeset
```

---

### Feature 9: Environment Configuration

**Description:** Set up environment-specific configuration management.

**Steps:**
1. Create `.env.example` with sample environment variables
2. Add AWS region, log level, and stage name variables
3. Create `src/config/__init__.py` and `src/config/settings.py`
4. Use pydantic-settings to load environment variables
5. Update main.py to use settings

**Validation:**
- Settings load correctly from environment
- Configuration is type-safe with validation
- `.env.example` documents all required variables

**Files Created:**
```
src/config/
├── __init__.py
└── settings.py
```

---

### Feature 10: Project Documentation

**Description:** Document the setup and deployment process.

**Steps:**
1. Update `README.md` with setup instructions
2. Add prerequisites section (AWS CLI, SAM CLI, Python)
3. Document local development steps
4. Document deployment process
5. Add troubleshooting section

**Validation:**
- New developer can follow README to deploy
- All commands are documented
- Common issues are addressed

---

## Phase 0 Completion Checklist

- [ ] AWS account configured with IAM user
- [ ] AWS CLI authenticated and working
- [ ] Project directory structure created
- [ ] FastAPI "Hello World" app running locally
- [ ] SAM template created and validated
- [ ] Application tested locally with SAM CLI
- [ ] Application deployed to AWS successfully
- [ ] Deployed endpoint responding correctly
- [ ] CloudWatch logs accessible and showing invocations
- [ ] CI/CD pipeline configured and tested
- [ ] Environment configuration implemented
- [ ] README.md updated with setup instructions

---

## Testing

### Manual Testing

1. **Local Test:**
   ```bash
   # Start local API
   sam local start-api
   
   # In another terminal
   curl http://localhost:3000/health
   # Expected: {"status": "ok", "message": "Hello World", "version": "0.1.0"}
   ```

2. **AWS Test:**
   ```bash
   # Get API URL from outputs
   API_URL=$(aws cloudformation describe-stacks \
     --stack-name triggers-api-dev \
     --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
     --output text)
   
   # Test endpoint
   curl $API_URL/health
   # Expected: {"status": "ok", "message": "Hello World", "version": "0.1.0"}
   ```

### Validation Criteria

- [ ] Health endpoint returns 200 OK
- [ ] Response is valid JSON
- [ ] Response includes status, message, and version
- [ ] Cold start time < 5 seconds
- [ ] Warm invocation time < 500ms
- [ ] CloudWatch logs contain no errors

---

## Troubleshooting

### Common Issues

**Issue: SAM build fails with dependency errors**
- Solution: Ensure `requirements.txt` lists correct versions
- Check Python version matches Lambda runtime (3.11)

**Issue: Lambda times out**
- Solution: Increase timeout in template.yaml (default 30s should be sufficient)
- Check CloudWatch logs for actual error

**Issue: API Gateway returns 403 Forbidden**
- Solution: Check CORS configuration in template.yaml
- Verify API Gateway stage is deployed

**Issue: CI/CD pipeline fails**
- Solution: Verify GitHub secrets are set correctly
- Check IAM permissions for deployment user
- Review GitHub Actions logs for specific error

---

## Next Steps

After completing Phase 0, proceed to:
- **Phase 1: MVP - Core Event Ingestion** - Implement POST /events endpoint, DynamoDB storage, and authentication

**Phase 0 provides:**
- Working AWS infrastructure
- Deployment pipeline
- Foundation for adding features
- Confidence in AWS setup

---

## Resources

- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Mangum Documentation](https://mangum.io/)
- [AWS Lambda Python](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html)

