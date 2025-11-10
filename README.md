# Zapier Triggers API

Event ingestion and delivery API for Zapier-like webhooks with AWS infrastructure.

## Overview

This is a serverless API built with FastAPI and deployed on AWS Lambda using SAM (Serverless Application Model). It provides a robust event ingestion and delivery system with webhook functionality.

**Current Phase:** Phase 0 - Setup & Deployment Pipeline

## Prerequisites

- Python 3.11+
- AWS CLI installed and configured
- AWS SAM CLI installed
- AWS account with appropriate permissions

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd ZapierEvents
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

## Local Development

### Run locally with Uvicorn

```bash
uvicorn src.main:app --reload --port 8000
```

Visit http://localhost:8000/health to see the health check endpoint.

API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Test locally with SAM CLI

```bash
# Build the application
sam build

# Start local API
sam local start-api --port 3000

# In another terminal, test the endpoint
curl http://localhost:3000/health
```

## Deployment

### Deploy to AWS

1. **Build the application:**
   ```bash
   sam build
   ```

2. **Deploy (first time - guided):**
   ```bash
   sam deploy --guided
   ```
   
   Follow the prompts:
   - Stack name: `triggers-api-dev`
   - AWS Region: `us-east-1` (or your preferred region)
   - Confirm changes before deploy: `Y`
   - Allow SAM CLI IAM role creation: `Y`
   - Save arguments to configuration file: `Y`

3. **Deploy (subsequent times):**
   ```bash
   sam build && sam deploy
   ```

4. **Get the API URL:**
   ```bash
   aws cloudformation describe-stacks \
     --stack-name triggers-api-dev \
     --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
     --output text
   ```

### Test Deployed Endpoint

```bash
# Replace <API_URL> with your actual API Gateway URL
curl https://<API_URL>/health
```

Expected response:
```json
{
  "status": "ok",
  "message": "Hello World",
  "version": "0.1.0"
}
```

## Project Structure

```
ZapierEvents/
├── .github/
│   └── workflows/          # CI/CD pipeline configurations
├── _docs/                  # Project documentation
├── src/
│   ├── config/            # Configuration management
│   │   ├── __init__.py
│   │   └── settings.py
│   └── main.py            # FastAPI application entry point
├── tests/                 # Test suite
├── .env.example           # Environment variable template
├── .gitignore            # Git ignore rules
├── README.md             # This file
├── requirements.txt      # Python dependencies
└── template.yaml         # AWS SAM template
```

## Technology Stack

- **Framework:** FastAPI
- **Runtime:** Python 3.11
- **Deployment:** AWS Lambda + API Gateway
- **IaC:** AWS SAM
- **Adapter:** Mangum (ASGI to Lambda)

## CI/CD Pipeline

The project uses GitHub Actions for automated deployment. Pushes to the `main` branch trigger automatic builds and deployments to AWS.

To set up:
1. Add AWS credentials to GitHub Secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`

## Monitoring

View Lambda logs in CloudWatch:
```bash
sam logs -n HealthFunction --stack-name triggers-api-dev --tail
```

## Troubleshooting

### SAM build fails
- Ensure Python 3.11 is installed
- Check that `requirements.txt` has correct package versions
- Try: `sam build --use-container`

### Lambda times out
- Check CloudWatch logs for errors
- Increase timeout in `template.yaml`
- Verify Lambda has necessary IAM permissions

### API Gateway returns 403
- Check CORS configuration in `template.yaml`
- Verify API Gateway stage is deployed
- Check Lambda function permissions

## Development Phases

- [x] **Phase 0:** Setup & Deployment Pipeline (Current)
- [ ] **Phase 1:** MVP - Core Event Ingestion
- [ ] **Phase 2:** Retrieval & Monitoring
- [ ] **Phase 3:** Delivery & Retry Logic
- [ ] **Phase 4:** Replay & Polish

## License

MIT

## Contributing

See `_docs/development-plan.md` for detailed development roadmap.

