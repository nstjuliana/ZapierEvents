# Deployment Process Guide

## Quick Reference: Deploying New Changes

After writing new Python code, follow these steps:

### Option 1: Deployment Script (Recommended)

Use the provided deployment script which includes validation and configuration display:

**Windows (PowerShell):**
```powershell
.\scripts\deploy.ps1
```

**Linux/Mac (Bash):**
```bash
./scripts/deploy.sh
```

The script will:
- Validate SAM CLI and AWS credentials
- Display configuration (including auth status)
- Build and deploy the application
- Show API endpoints after deployment

**Note:** Auth is **DISABLED** on the `/events` endpoint (publicly accessible).

### Option 2: Manual Deployment

```bash
# 1. Build the application
sam build

# 2. Deploy to AWS
sam deploy
```

That's it! SAM will:
- Package your code and dependencies
- Upload to S3
- Update the CloudFormation stack
- Deploy new Lambda code

### Option 3: Automated Deployment (CI/CD)

If you push to the `main` branch, GitHub Actions will automatically:
1. Build the application
2. Deploy to AWS

**No manual steps needed!**

---

## Detailed Deployment Workflow

### Step-by-Step Process

#### 1. **Make Your Code Changes**
Edit your Python files in `src/`:
- `src/main.py` - Main FastAPI application
- `src/config/settings.py` - Configuration
- Add new modules in `src/` as needed

#### 2. **Update Dependencies (if needed)**
If you added new Python packages:
```bash
# Edit requirements.txt or src/requirements.txt
# Then rebuild
sam build
```

#### 3. **Test Locally (Optional but Recommended)**
```bash
# Build first
sam build

# Start local API server
sam local start-api --port 3000

# Test in another terminal
curl http://localhost:3000/health
# or test your new endpoint
```

#### 4. **Deploy to AWS**
```bash
sam build && sam deploy
```

Or separately:
```bash
sam build
sam deploy
```

#### 5. **Verify Deployment**
```bash
# Check CloudFormation stack status
aws cloudformation describe-stacks --stack-name triggers-api-dev

# Test the endpoint
curl https://mmghecrjr5.execute-api.us-east-1.amazonaws.com/health

# View logs
sam logs -n HealthFunction --stack-name triggers-api-dev --tail
```

---

## What Happens During Deployment

### `sam build` Process:
1. **Validates** the SAM template (`template.yaml`)
2. **Resolves dependencies** from `src/requirements.txt`
3. **Packages** your code and dependencies
4. **Creates** deployment artifacts in `.aws-sam/build/`

### `sam deploy` Process:
1. **Uploads** code package to S3 bucket
2. **Creates/updates** CloudFormation changeset
3. **Shows** what will change (if any)
4. **Deploys** changes to AWS
5. **Updates** Lambda function code
6. **Outputs** API URLs and resource ARNs

---

## Common Scenarios

### Scenario 1: Adding a New Endpoint

**Example:** Adding `POST /events`

1. **Edit `src/main.py`:**
```python
@app.post("/events")
async def create_event(event_data: dict):
    # Your code here
    return {"status": "created"}
```

2. **Update `template.yaml`** (if needed for new routes - SAM auto-discovers FastAPI routes):
```yaml
# Usually no changes needed - API Gateway discovers routes automatically
# But you may need to add permissions for DynamoDB, etc.
```

3. **Deploy:**
```bash
sam build
sam deploy
```

### Scenario 2: Adding a New Dependency

1. **Edit `src/requirements.txt`:**
```txt
fastapi==0.115.0
mangum==0.18.0
# Add your new package
new-package==1.0.0
```

2. **Deploy:**
```bash
sam build  # This installs new dependencies
sam deploy
```

### Scenario 3: Adding AWS Resources (DynamoDB, SQS, etc.)

1. **Edit `template.yaml`:**
```yaml
Resources:
  EventsTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: events
      # ... table configuration
```

2. **Update Lambda permissions** (if needed):
```yaml
HealthFunction:
  Properties:
    Policies:
      - DynamoDBCrudPolicy:
          TableName: !Ref EventsTable
```

3. **Deploy:**
```bash
sam build
sam deploy
```

### Scenario 4: Environment Variable Changes

1. **Edit `template.yaml`:**
```yaml
Globals:
  Function:
    Environment:
      Variables:
        LOG_LEVEL: INFO
        NEW_VAR: value  # Add here
```

2. **Or use `src/config/settings.py`** (recommended):
```python
class Settings(BaseSettings):
    new_var: str = Field(default="default")
```

3. **Deploy:**
```bash
sam build
sam deploy
```

---

## CI/CD Pipeline (GitHub Actions)

### Automatic Deployment

When you push to `main` branch:

```bash
git add .
git commit -m "Add new feature"
git push origin main
```

GitHub Actions automatically:
1. ✅ Checks out code
2. ✅ Sets up Python 3.11
3. ✅ Sets up SAM CLI
4. ✅ Configures AWS credentials (from secrets)
5. ✅ Builds application
6. ✅ Deploys to AWS

### Manual Trigger

You can also trigger deployment manually:
1. Go to GitHub Actions tab
2. Select "Deploy to AWS" workflow
3. Click "Run workflow"

### Required GitHub Secrets

For CI/CD to work, add these secrets in GitHub:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

**Settings → Secrets and variables → Actions → New repository secret**

---

## Deployment Best Practices

### ✅ Do:
- Test locally before deploying
- Review CloudFormation changeset before deploying
- Use version control (commit before deploying)
- Check logs after deployment
- Test the deployed endpoint

### ❌ Don't:
- Deploy untested code directly to production
- Skip the build step
- Ignore CloudFormation errors
- Deploy without checking changeset

---

## Troubleshooting Deployment

### Issue: Build Fails
```bash
# Check Python version
python --version  # Should be 3.11+

# Check dependencies
pip install -r src/requirements.txt

# Try clean build
rm -rf .aws-sam
sam build
```

### Issue: Deploy Fails
```bash
# Check AWS credentials
aws sts get-caller-identity

# Check CloudFormation stack
aws cloudformation describe-stacks --stack-name triggers-api-dev

# View detailed error
sam deploy --debug
```

### Issue: Lambda Function Not Updating
```bash
# Force rebuild
sam build --use-container

# Check if code actually changed
# SAM only updates if code/dependencies changed
```

### Issue: API Gateway Not Routing
```bash
# Check routes
aws apigatewayv2 get-routes --api-id mmghecrjr5

# Check integrations
aws apigatewayv2 get-integrations --api-id mmghecrjr5

# View Lambda logs
sam logs -n HealthFunction --stack-name triggers-api-dev --tail
```

---

## Quick Commands Cheat Sheet

```bash
# Build
sam build

# Deploy
sam deploy

# Build + Deploy
sam build && sam deploy

# Test locally
sam local start-api --port 3000

# View logs
sam logs -n HealthFunction --stack-name triggers-api-dev --tail

# Validate template
sam validate

# Delete stack (careful!)
sam delete --stack-name triggers-api-dev

# Check stack status
aws cloudformation describe-stacks --stack-name triggers-api-dev
```

---

## Deployment Time Estimates

- **Code-only change:** ~30-60 seconds
- **Dependency change:** ~1-2 minutes
- **Infrastructure change:** ~2-5 minutes
- **First deployment:** ~3-5 minutes

---

## What Gets Updated

### Code Changes:
- ✅ Lambda function code
- ✅ Dependencies (if requirements.txt changed)
- ❌ Infrastructure (if template.yaml unchanged)

### Infrastructure Changes:
- ✅ New AWS resources
- ✅ Updated resource configurations
- ✅ IAM permissions
- ✅ Environment variables

### What Doesn't Change:
- ❌ API Gateway API ID (unless you delete/recreate)
- ❌ Lambda function name (unless you change template)
- ❌ S3 bucket (managed by SAM)

---

## Rollback Process

If something goes wrong:

### Option 1: Revert Code and Redeploy
```bash
git revert HEAD
sam build
sam deploy
```

### Option 2: Delete and Redeploy
```bash
sam delete --stack-name triggers-api-dev
sam build
sam deploy
```

### Option 3: CloudFormation Rollback
CloudFormation automatically rolls back if deployment fails.

---

## Summary

**For most code changes:**
```bash
sam build && sam deploy
```

**That's it!** SAM handles everything else automatically.

For infrastructure changes, update `template.yaml` first, then deploy.

