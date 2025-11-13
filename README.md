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

### ⚡ Fast Local Development (Recommended)

For fast local development, use **uvicorn directly** instead of SAM Local. This avoids Docker container overhead and is much faster:

**Option 1: Use the run script (easiest)**
```bash
# Windows
run_local.bat

# Linux/Mac
python run_local.py --reload
```

**Option 2: Run uvicorn directly**
```bash
uvicorn src.main:app --reload --port 8000
```

**Setup:**
1. Create a `.env` file in the project root (copy from `.env.example` if available)
2. Set required environment variables:
   - `EVENTS_TABLE_NAME` (e.g., `test-events-table`)
   - `API_KEYS_TABLE_NAME` (e.g., `test-api-keys-table`)
   - `INBOX_QUEUE_URL` (e.g., `https://sqs.us-east-1.amazonaws.com/123456789/test-queue`)
   - `ZAPIER_WEBHOOK_URL` (e.g., `https://hooks.zapier.com/hooks/catch/test/`)

**Access:**
- Health check: http://localhost:8000/health
- API docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 🐳 SAM Local (Lambda Testing - Slow)

**Only use SAM Local when you need to test Lambda-specific behavior.** It's much slower because it uses Docker containers:

```bash
# Build the application
sam build

# Start local API (add --skip-pull-image to avoid rebuilding images)
sam local start-api --port 3000 --skip-pull-image

# In another terminal, test the endpoint
curl http://localhost:3000/health
```

**Note:** SAM Local rebuilds Docker images on each request, making it very slow for development. Use uvicorn for day-to-day development instead.

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

## API Documentation

### Endpoints

#### GET /events - List Events with Advanced Filtering

Retrieve a paginated list of events with powerful filtering capabilities.

**Query Parameters:**
- `status` (optional): Filter by delivery status (`pending`, `delivered`, `failed`, `replayed`)
- `limit` (optional): Maximum number of events to return (default: 50, max: 100)
- `cursor` (optional): Pagination cursor for retrieving the next page of results

**Advanced Filtering:**
The API supports complex filtering on event payload and metadata fields using various comparison operators:

**Supported Operators:**
- `eq` (default): Exact match (`?field=value`)
- `gt, gte, lt, lte`: Numeric/date comparisons (`?field[gte]=100`)
- `ne`: Not equal (`?field[ne]=value`)
- `contains`: String contains (`?field[contains]=text`)
- `startswith`: String starts with (`?field[startswith]=prefix`)

**Special Date Filters:**
- `created_after`, `created_before`: Filter by event creation date
- `delivered_after`, `delivered_before`: Filter by delivery date

**Examples:**

```bash
# Basic status filtering (existing functionality)
GET /events?status=pending&limit=10

# Filter by exact payload field
GET /events?payload.order_id=12345

# Filter by numeric comparison
GET /events?payload.amount[gte]=100

# Filter by nested payload fields
GET /events?payload.customer.email[contains]=gmail.com

# Filter by metadata
GET /events?metadata.source=ecommerce

# Combine multiple filters
GET /events?status=delivered&payload.amount[gte]=50&metadata.source=api

# Date filtering
GET /events?created_after=2024-01-15T00:00:00Z
GET /events?delivered_before=2024-01-16T00:00:00Z

# String operations
GET /events?event_type[startswith]=order.
GET /events?payload.customer.email[contains]=@company.com

# Complex filtering with pagination
GET /events?payload.status=failed&limit=50
```

**Response:**
```json
[
  {
    "event_id": "evt_abc123xyz456",
    "event_type": "order.created",
    "payload": {"order_id": "12345", "amount": 99.99},
    "metadata": {"source": "ecommerce"},
    "status": "delivered",
    "created_at": "2024-01-15T10:30:01Z",
    "delivered_at": "2024-01-15T10:30:02Z",
    "delivery_attempts": 1,
    "message": "Event retrieved successfully"
  }
]
```

**Notes:**
- Filters are applied after retrieving events from the database
- Complex filters may result in fetching more events than requested for accurate pagination
- Status filtering uses efficient database indexes when used alone
- Combining status filters with custom filters works seamlessly

**📖 For detailed filtering documentation**, see [`_docs/event-filtering.md`](_docs/event-filtering.md) for:
- Complete operator reference
- Advanced examples and use cases
- Performance considerations
- Best practices and troubleshooting

#### POST /events - Create Event

Create and ingest a new event with automatic delivery attempt.

**Request Body:**
```json
{
  "event_type": "order.created",
  "payload": {
    "order_id": "12345",
    "amount": 99.99,
    "customer": {
      "email": "user@example.com"
    }
  },
  "metadata": {
    "source": "ecommerce-platform",
    "version": "2.1.0"
  },
  "idempotency_key": "order-12345-2024-01-15"
}
```

#### GET /events/{event_id} - Get Single Event

Retrieve a specific event by its ID.

```bash
GET /events/evt_abc123xyz456
```

#### PATCH /events/{event_id} - Update Event

Update an event's payload, metadata, or idempotency key.

#### DELETE /events/{event_id} - Delete Event

Permanently remove an event from the system.

#### POST /events/{event_id}/acknowledge - Acknowledge Delivery

Mark an event as successfully delivered.

#### GET /inbox - Get Pending Events

Retrieve events waiting for delivery (alias for `GET /events?status=pending`).

### Batch Operations

The API supports efficient batch operations for processing multiple events in a single request:

#### POST /events/batch - Batch Create Events

Create up to 100 events in a single request with automatic delivery attempts.

**Request Body:**
```json
{
  "events": [
    {
      "event_type": "order.created",
      "payload": {"order_id": "123", "amount": 99.99},
      "metadata": {"source": "api"},
      "idempotency_key": "order-123-2024-01-15"
    },
    {
      "event_type": "order.updated",
      "payload": {"order_id": "123", "status": "shipped"}
    }
  ]
}
```

**Response:**
```json
{
  "results": [
    {
      "index": 0,
      "success": true,
      "event": {
        "event_id": "evt_abc123xyz456",
        "status": "delivered",
        "message": "Event created and delivered"
      }
    }
  ],
  "summary": {
    "total": 2,
    "successful": 1,
    "failed": 1
  }
}
```

#### PATCH /events/batch - Batch Update Events

Update up to 100 events with ownership validation and automatic redelivery.

#### DELETE /events/batch - Batch Delete Events

Delete up to 100 events with ownership validation and idempotent behavior.

**📖 For complete batch API documentation**, see [`_docs/event-batching.md`](_docs/event-batching.md) for:
- Detailed request/response formats
- Error handling and status codes
- Performance considerations
- Client code examples
- Best practices

### Interactive Documentation

- **Swagger UI**: Visit `/docs` for interactive API documentation
- **ReDoc**: Visit `/redoc` for alternative documentation format

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

