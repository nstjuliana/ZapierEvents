# Tech Stack Documentation

## Overview

This document defines the technology stack for the Zapier Triggers API. The stack is designed to support:
- High availability (99.9% reliability target)
- Low latency (< 100ms response time)
- Serverless architecture on AWS
- Event-driven automation with push/pull delivery model
- Python-based implementation

---

## Architecture Components

### 1. API Framework
**Selected: FastAPI**

- Modern, high-performance ASGI framework
- Built-in async support for Lambda performance
- Automatic OpenAPI/Swagger documentation generation
- Pydantic integration for request/response validation
- Type hints and native JSON schema support
- Primary API layer for all endpoints (/events, /inbox, /replay)

**Alternative Considered:** Flask + Flask-RESTful (simpler but less performant)

#### FastAPI Best Practices
- **Async/await**: Use `async def` for endpoints that make I/O calls (DynamoDB, SQS, HTTP); use regular `def` only for pure compute
- **Dependency injection**: Use FastAPI dependencies for reusable logic (auth, database connections, settings)
- **Path operations order**: Define specific routes before generic ones (e.g., `/events/recent` before `/events/{id}`)
- **Response models**: Always specify `response_model` for type safety and automatic validation
- **Status codes**: Use `status_code` parameter explicitly for clarity and documentation
- **Background tasks**: Use `BackgroundTasks` for operations that can happen after response (logging, cleanup)
- **Error handling**: Use `HTTPException` for API errors with proper status codes and detail messages
- **Request validation**: Leverage Pydantic models for request body, query params, and path params
- **API versioning**: Use path prefixes for API versions: `/v1/events`, `/v2/events`

#### FastAPI Limitations
- **Lambda cold starts**: First request after idle period has latency (5-10 seconds); mitigate with provisioned concurrency
- **Memory overhead**: ASGI server and FastAPI add ~50MB to memory footprint
- **Debugging async**: Async stack traces can be harder to debug than synchronous code
- **No WebSocket support in Lambda**: WebSockets require persistent connections (use API Gateway WebSocket API separately)
- **Limited middleware options**: Some Flask middleware not compatible with ASGI

#### FastAPI Conventions
- **Router organization**: Use `APIRouter` to organize routes by feature: `events_router`, `inbox_router`
- **File naming**: Name route files after resource: `events.py`, `inbox.py`, `replay.py`
- **Function naming**: Use verb_noun pattern: `create_event`, `get_events`, `replay_event`
- **Dependency naming**: Suffix with `_dep`: `get_db_dep`, `get_current_user_dep`
- **Model location**: Keep request/response models in `models/` directory

#### FastAPI Common Pitfalls
- **Blocking calls in async**: Calling synchronous blocking code in `async def` (use `run_in_executor` or make it sync)
- **Missing await**: Forgetting to `await` async functions causes coroutine errors
- **Dependency scope**: Creating new database connections per request without pooling
- **Not handling exceptions**: Unhandled exceptions return 500 instead of proper error responses
- **Over-using Background Tasks**: Background tasks fail silently; use for non-critical operations only
- **Circular imports**: Importing routers that import dependencies that import routers
- **Query parameter defaults**: Forgetting `= None` for optional query params causes validation errors

---

### 2. AWS Compute Layer
**Selected: AWS Lambda + API Gateway**

- Serverless, auto-scaling compute
- Pay-per-invocation pricing model
- Built-in multi-AZ redundancy
- No infrastructure management
- API Gateway provides 99.99% SLA
- Native integration with other AWS services
- Handles event ingestion, validation, and storage operations

**Alternative Considered:** AWS ECS Fargate (more control but higher operational overhead)

#### AWS Lambda Best Practices
- **Memory allocation**: Start with 512MB-1024MB; more memory = faster CPU and lower cost per execution time
- **Timeout configuration**: Set realistic timeouts (30s for API calls, not default 3s)
- **Environment variables**: Use for configuration; avoid hardcoding values
- **Cold start optimization**: Keep deployment package small (<50MB), minimize imports, use provisioned concurrency for critical functions
- **Connection reuse**: Initialize clients (boto3, httpx) outside handler for connection reuse
- **Error handling**: Return structured error responses; don't let exceptions propagate uncaught
- **Logging**: Use structured logging with context (request_id, event_id); logs go to CloudWatch automatically
- **Versioning**: Use Lambda versions and aliases for blue-green deployments
- **Layers**: Use Lambda Layers for shared dependencies across functions

#### AWS API Gateway Best Practices
- **HTTP API vs REST API**: Use HTTP API (cheaper, faster, lower latency) unless need REST-specific features
- **Caching**: Enable caching for GET endpoints that return same data frequently
- **Request validation**: Use request validators to reject invalid requests before Lambda invocation
- **Throttling**: Set per-client throttling limits to prevent abuse
- **CORS**: Configure CORS properly for web client access
- **Custom domain**: Use custom domain with ACM certificate for production
- **Usage plans**: Create usage plans to manage API keys and quotas
- **Logging**: Enable access logging and execution logging for debugging

#### AWS Lambda Limitations
- **Execution time**: 15-minute maximum execution time (use Step Functions for longer processes)
- **Deployment package**: 50MB zipped, 250MB unzipped (use Layers for large dependencies)
- **Concurrent executions**: Account-level limit (1000 default, can request increase)
- **Cold starts**: 1-10 second latency on first invocation after idle period
- **/tmp storage**: 512MB-10GB ephemeral storage only
- **Stateless**: Cannot maintain state between invocations

#### AWS API Gateway Limitations
- **Payload size**: 10MB maximum request/response payload
- **Timeout**: 29-second maximum integration timeout
- **WebSocket**: Separate API type; HTTP API doesn't support WebSockets
- **Request validation**: Limited validation capabilities compared to application-level validation

#### AWS Lambda Conventions
- **Handler naming**: Use `handler` or `lambda_handler` as entry point function name
- **Function naming**: Use descriptive names: `triggers-api-events-post`, `triggers-api-inbox-get`
- **IAM roles**: One role per function with least-privilege permissions
- **Tags**: Tag functions with environment, service, owner for cost tracking

#### AWS API Gateway Conventions
- **Stage names**: Use lowercase: `dev`, `staging`, `prod`
- **Resource naming**: Use plural nouns: `/events`, `/inbox`
- **Method naming**: Use standard HTTP methods: GET, POST, PUT, DELETE
- **Error responses**: Return standard HTTP status codes with JSON error bodies

#### AWS Lambda Common Pitfalls
- **Cold start ignorance**: Not optimizing for cold starts, causing poor user experience
- **Shared state**: Trying to maintain state between invocations (use DynamoDB or ElastiCache)
- **Synchronous invocations**: Using Lambda for long-running tasks synchronously
- **Not reusing connections**: Creating new boto3 clients inside handler function
- **Environment variable limits**: Exceeding 4KB environment variable size limit
- **Timeout too short**: Functions timing out due to insufficient timeout configuration
- **Memory too low**: Running out of memory causing failures and slow execution
- **Not monitoring**: Ignoring CloudWatch metrics (duration, errors, throttles)

#### AWS API Gateway Common Pitfalls
- **Missing CORS**: Web clients blocked by CORS errors
- **No request validation**: Allowing invalid requests to reach Lambda, wasting invocations
- **Overly permissive**: Not setting throttling limits, allowing abuse
- **Poor error handling**: Not mapping Lambda errors to proper HTTP status codes
- **Not using caching**: Missing caching opportunities for read-heavy endpoints
- **Incorrect stage variables**: Hardcoding values instead of using stage variables
- **No monitoring**: Not enabling CloudWatch logs for troubleshooting

---

### 3. Database/Primary Storage
**Selected: Amazon DynamoDB**

- Serverless, fully managed NoSQL database
- Single-digit millisecond latency
- 99.99% availability SLA
- Auto-scaling with on-demand pricing
- Built-in encryption at rest
- Point-in-time recovery
- Stores events, API keys, delivery status, and metadata

**Alternative Considered:** Amazon RDS PostgreSQL (relational but requires more management)

#### DynamoDB Best Practices
- **Table design**: Design for access patterns, not entities; denormalize data for single-table design when possible
- **Partition keys**: Choose high-cardinality partition keys to distribute load evenly (use event_id, user_id)
- **Sort keys**: Use sort keys for range queries and to group related items (timestamp, status)
- **GSI strategically**: Create Global Secondary Indexes for alternate access patterns, but sparingly (cost)
- **Batch operations**: Use `batch_write_item` and `batch_get_item` for bulk operations (25 items max per batch)
- **Consistent reads**: Use eventually consistent reads (default) unless strong consistency required
- **Sparse indexes**: Use sparse GSIs (only items with index attribute are indexed) to reduce costs
- **TTL for cleanup**: Use Time To Live (TTL) to automatically delete old events (30-90 days)
- **On-demand vs provisioned**: Use on-demand pricing for unpredictable workloads; provisioned for steady state
- **Item size**: Keep items under 400KB; split large items or use S3 references

#### DynamoDB Limitations
- **Item size**: 400KB maximum item size (including attribute names)
- **Query limitations**: Can only query on partition key + sort key; need GSI for other queries
- **No joins**: Cannot join tables; must denormalize or make multiple queries
- **Transaction limits**: 25 items maximum per transaction; 4MB total transaction size
- **Batch limits**: 25 items per batch operation; 16MB total batch size
- **Eventually consistent**: Default reads are eventually consistent (up to 1 second delay)

#### DynamoDB Conventions
- **Table naming**: Use lowercase with hyphens: `triggers-api-events`, `triggers-api-api-keys`
- **Attribute naming**: Use snake_case for attribute names: `event_id`, `created_at`, `delivery_status`
- **Primary key naming**: Use `PK` and `SK` for generic single-table design, or descriptive names for single-purpose tables
- **Timestamp format**: Store timestamps as ISO 8601 strings or Unix epoch integers
- **Status values**: Use consistent status enums: `pending`, `delivered`, `failed`, `replayed`

#### DynamoDB Common Pitfalls
- **Hot partitions**: Using low-cardinality partition keys causing uneven distribution
- **Scanning tables**: Using `scan` instead of `query` for large tables (expensive and slow)
- **Missing error handling**: Not handling `ProvisionedThroughputExceededException` with retries
- **Over-provisioning**: Provisioning too much capacity, wasting money
- **Not using batch operations**: Making individual put/get calls instead of batching
- **Ignoring LSI limitations**: Local Secondary Indexes share partition key; limited to 5 per table
- **Not enabling point-in-time recovery**: Risk of data loss without backups
- **Attribute name bloat**: Using long attribute names (they count toward item size)
- **Not monitoring**: Ignoring CloudWatch metrics for throttling, consumed capacity

---

### 4. Message Queue/Event Delivery
**Selected: Amazon SQS**

- Fully managed message queue service
- At-least-once delivery guarantee
- Automatic scaling
- Dead Letter Queue (DLQ) support for failed deliveries
- Server-side encryption
- Up to 14-day message retention
- Buffer for event delivery and retry logic
- Powers the inbox queue for polling

**Alternative Considered:** Amazon EventBridge (more features but added complexity)

#### SQS Best Practices
- **Visibility timeout**: Set visibility timeout appropriate for processing time (30s-5min for our use case)
- **Dead Letter Queue**: Always configure DLQ with max receive count (3-5 retries)
- **Batch operations**: Use `send_message_batch` and `receive_message` (up to 10 messages) for efficiency
- **Message attributes**: Use message attributes for metadata; keep message body for event data only
- **Long polling**: Use long polling (WaitTimeSeconds=20) to reduce empty receives and API costs
- **FIFO vs Standard**: Use Standard queue (higher throughput); FIFO only if order critical
- **Message deduplication**: Include deduplication ID in messages to prevent duplicates (5-minute window)
- **Monitoring**: Monitor queue depth, age of oldest message, and DLQ depth
- **Encryption**: Enable server-side encryption with KMS for sensitive event data
- **Retention period**: Set based on use case (4 hours to 14 days); use 3-7 days for event delivery

#### SQS Limitations
- **Message size**: 256KB maximum message size (store large payloads in S3)
- **Message delay**: Maximum 15-minute delay for delayed messages
- **Retention**: 14-day maximum retention period
- **Visibility timeout**: 12-hour maximum visibility timeout
- **Batch size**: 10 messages maximum per batch operation
- **FIFO throughput**: 300 messages/second (3000 with batching) for FIFO queues
- **At-least-once delivery**: Standard queues may deliver message more than once (must be idempotent)

#### SQS Conventions
- **Queue naming**: Use descriptive names with environment: `triggers-api-inbox-prod`, `triggers-api-inbox-dlq-prod`
- **DLQ naming**: Suffix with `-dlq`: `triggers-api-inbox-dlq-prod`
- **Message attributes**: Use PascalCase for attribute names: `EventType`, `Timestamp`, `CorrelationId`
- **Error handling**: Move to DLQ after 3-5 failed attempts
- **Polling**: Use long polling with 20-second wait time

#### SQS Common Pitfalls
- **Short polling**: Using short polling (default), increasing API costs and latency
- **No DLQ**: Missing DLQ configuration, losing failed messages permanently
- **Visibility timeout too short**: Messages reappearing before processing completes
- **Not deleting messages**: Forgetting to delete after successful processing (reprocessing)
- **Large messages**: Exceeding 256KB limit; store large payloads in S3 instead
- **Not handling duplicates**: Assuming exactly-once delivery (Standard queues are at-least-once)
- **Synchronous processing**: Processing messages synchronously instead of in parallel
- **Not monitoring DLQ**: DLQ filling up without alerts or processing

---

### 5. Lambda ASGI Adapter
**Selected: Mangum**

- Official ASGI adapter for AWS Lambda
- Handles API Gateway event conversion
- Supports HTTP APIs and REST APIs
- Active maintenance and community support
- Bridges FastAPI to Lambda runtime

**Alternative Considered:** AWS Lambda Powertools (comprehensive but heavier)

#### Mangum Best Practices
- **Handler setup**: Create handler once at module level, not inside Lambda handler
- **API Gateway integration**: Use HTTP API for better performance; REST API for advanced features
- **Lifespan events**: Support FastAPI lifespan events for startup/shutdown logic
- **Binary responses**: Configure binary media types in API Gateway for non-JSON responses
- **Custom domain**: Use custom domain to avoid exposing Lambda URL structure
- **Error handling**: Let Mangum handle ASGI exceptions; FastAPI error handlers work automatically

#### Mangum Limitations
- **Cold start overhead**: Adds ~100-200ms to cold start time
- **Binary support**: Binary responses require API Gateway binary media type configuration
- **WebSocket**: Does not support WebSocket connections (use API Gateway WebSocket separately)
- **Streaming**: No support for streaming responses (Lambda limitation)

#### Mangum Conventions
- **Handler naming**: Use `handler` as function name for consistency with Lambda conventions
- **Initialization**: Initialize FastAPI app at module level, wrap with Mangum for handler
- **Configuration**: Pass `lifespan="off"` if not using lifespan events to reduce cold start

#### Mangum Common Pitfalls
- **Recreating handler**: Creating new Mangum instance per invocation (should be module-level)
- **Missing binary config**: Not configuring binary media types in API Gateway
- **CORS issues**: Not configuring CORS middleware in FastAPI or API Gateway
- **Path parameter encoding**: URL-encoded characters in path parameters not decoded properly

---

### 6. Authentication & Authorization
**Selected: AWS API Gateway Lambda Authorizer**

- Native API Gateway integration
- Custom authorization logic in Python
- Caches authorization decisions (5 minutes default)
- Returns IAM policies for fine-grained access
- Validates API keys and enforces permissions

**Alternative Considered:** AWS Cognito (feature-rich but overkill for API key auth)

#### Lambda Authorizer Best Practices
- **Caching**: Use authorizer caching (5 minutes) to reduce Lambda invocations and latency
- **Cache key**: Include all relevant identifiers in cache key (API key, user ID)
- **Policy generation**: Return restrictive policies; deny by default, allow specific resources
- **Error handling**: Return `401 Unauthorized` for invalid credentials, `403 Forbidden` for insufficient permissions
- **Context variables**: Pass user context to downstream Lambda via `context` field
- **Token extraction**: Extract token from `Authorization` header; handle missing/malformed tokens gracefully
- **Database lookup**: Use DynamoDB query (not scan) to validate API keys efficiently
- **Hashing**: Compare bcrypt hashes of API keys, never store plaintext
- **TTL**: Include token/key expiration in validation logic

#### Lambda Authorizer Limitations
- **Timeout**: 30-second maximum authorizer timeout
- **Payload size**: 1MB maximum payload size for authorizer response
- **Cache limitations**: Cache key limited to 128 characters
- **Cold starts**: First invocation after idle has cold start latency
- **No token refresh**: Cached authorization persists for TTL (5 minutes); can't revoke mid-session

#### Lambda Authorizer Conventions
- **Function naming**: Name authorizer function descriptively: `triggers-api-authorizer`
- **Policy format**: Use AWS IAM policy format with `Allow`/`Deny` effects
- **Context naming**: Use camelCase for context variables: `userId`, `userRole`, `apiKeyId`
- **Response structure**: Return `principalId`, `policyDocument`, and `context` in response
- **Error responses**: Use consistent error responses; don't expose sensitive information

#### Lambda Authorizer Common Pitfalls
- **Overly permissive policies**: Allowing `*` resources or actions (security risk)
- **Not caching**: Setting cache TTL to 0, causing performance issues
- **Incorrect cache key**: Cache key doesn't include all relevant auth factors
- **Missing error handling**: Not handling database errors gracefully
- **Synchronous database calls**: Blocking calls in async context (use async DynamoDB client)
- **Not logging**: Missing authentication logs for security auditing
- **Exposing errors**: Returning detailed error messages revealing system internals
- **Cache invalidation**: No mechanism to invalidate cached authorizations when permissions change

---

### 7. Secrets Management
**Selected: AWS Secrets Manager**

- Automatic secret rotation capability
- Fine-grained IAM access control
- Encryption with AWS KMS
- Versioning and audit trail via CloudTrail
- CloudFormation integration
- Stores API keys, database credentials, encryption keys

**Alternative Considered:** AWS Systems Manager Parameter Store (cheaper but no auto-rotation)

#### AWS Secrets Manager Best Practices
- **Rotation**: Enable automatic rotation for database credentials and API keys (30-90 days)
- **Versioning**: Use versioning to roll back secret changes if needed
- **IAM permissions**: Use least-privilege IAM policies; grant access only to specific secrets
- **Caching**: Cache secrets in Lambda memory for duration of container lifetime (reduce API calls)
- **Tagging**: Tag secrets with environment, service, owner for organization and cost tracking
- **Deletion**: Use deletion window (7-30 days) to prevent accidental permanent deletion
- **Encryption**: Use customer-managed KMS keys for sensitive secrets (better audit trail)
- **Naming**: Use hierarchical naming: `/{environment}/{service}/{secret-name}`
- **SDK usage**: Use boto3 client to retrieve secrets; handle exceptions gracefully

#### AWS Secrets Manager Limitations
- **Cost**: $0.40 per secret per month + $0.05 per 10,000 API calls (more expensive than Parameter Store)
- **Size**: 65KB maximum secret size
- **Rotation**: Rotation requires Lambda function; not all services supported out-of-box
- **Latency**: API calls add latency (~50-100ms); cache secrets to mitigate
- **Regional**: Secrets are regional; need cross-region replication for multi-region apps

#### AWS Secrets Manager Conventions
- **Secret naming**: Use forward slashes for hierarchy: `/prod/triggers-api/db-password`
- **Description**: Add meaningful descriptions for each secret
- **Tags**: Always tag with `Environment`, `Service`, `Owner`
- **Rotation schedule**: Standard rotation: 30 days for API keys, 90 days for database passwords

#### AWS Secrets Manager Common Pitfalls
- **Not caching**: Fetching secret on every Lambda invocation (slow and expensive)
- **Hardcoded ARNs**: Hardcoding secret ARNs instead of using names with `SecretId`
- **Missing error handling**: Not handling `ResourceNotFoundException` when secret doesn't exist
- **Excessive permissions**: Granting `secretsmanager:*` instead of specific actions
- **Not using rotation**: Manual secret rotation (error-prone, forgot to rotate)
- **Logging secrets**: Accidentally logging secret values in CloudWatch Logs
- **No deletion window**: Setting deletion window to 0 (immediate, irreversible deletion)

---

### 8. Encryption
**Selected: AWS KMS (Key Management Service)**

- Customer-managed or AWS-managed keys
- Automatic key rotation
- CloudTrail audit logging
- Fine-grained access control via IAM
- Envelope encryption pattern
- Encrypts DynamoDB, sensitive event fields, and secrets

**Alternative Considered:** Python cryptography library with self-managed keys (more control but higher burden)

#### AWS KMS Best Practices
- **Customer-managed keys**: Use customer-managed keys (CMK) for sensitive data (better control, audit)
- **Automatic rotation**: Enable automatic key rotation annually for CMKs
- **Key policies**: Use key policies combined with IAM policies for fine-grained access control
- **Aliases**: Use aliases for keys to avoid exposing key IDs: `alias/triggers-api-prod`
- **Multi-region keys**: Use multi-region keys for cross-region encryption/decryption
- **Envelope encryption**: Use envelope encryption for large data (encrypt data key, not data directly)
- **CloudTrail**: Enable CloudTrail logging to audit all key usage
- **Deletion**: Use key deletion waiting period (7-30 days) to prevent accidental deletion
- **Grant usage**: Use grants for temporary key access (auto-revoked when not needed)

#### AWS KMS Limitations
- **Cost**: $1/month per CMK + $0.03 per 10,000 requests
- **Request limits**: 1,000-10,000 requests per second depending on operation (shared per account)
- **Encryption size**: 4KB maximum plaintext size for direct encryption
- **Regional**: Keys are regional (except multi-region keys)
- **Rotation**: Automatic rotation only for symmetric CMKs, not asymmetric keys

#### AWS KMS Conventions
- **Key naming**: Use descriptive aliases: `alias/triggers-api-events-prod`, `alias/triggers-api-db-prod`
- **Key description**: Include purpose and usage: "Encrypts DynamoDB events table for Triggers API"
- **Tag keys**: Tag with `Environment`, `Service`, `Owner`, `CostCenter`
- **Key policies**: Separate key administrator and key user permissions

#### AWS KMS Common Pitfalls
- **Direct encryption of large data**: Trying to encrypt data larger than 4KB directly (use envelope encryption)
- **Not using aliases**: Using key IDs directly, making key rotation difficult
- **Overly permissive policies**: Allowing `kms:*` or not restricting key usage
- **Not enabling rotation**: Missing automatic key rotation for long-lived keys
- **Ignoring throttling**: Not handling `ThrottlingException` with retries and exponential backoff
- **Cost overruns**: Excessive API calls due to not caching encrypted data keys
- **Missing CloudTrail**: Not logging key usage for security auditing
- **Disabled keys**: Accidentally disabling keys causing application failures

---

### 9. Monitoring & Logging
**Selected: Amazon CloudWatch + AWS X-Ray**

- CloudWatch: Native AWS integration for logs, metrics, and alarms
- X-Ray: Distributed tracing and service map visualization
- Lambda automatic logging to CloudWatch
- Custom metrics and dashboards
- Log retention policies
- Trace event flow across services for debugging

**Alternative Considered:** CloudWatch only (simpler but less visibility)

#### CloudWatch Best Practices
- **Log groups**: Create separate log groups per Lambda function for organization
- **Retention**: Set appropriate log retention (7-90 days) to control costs
- **Structured logging**: Use JSON format for logs (better querying in CloudWatch Insights)
- **Log sampling**: Sample logs for high-volume operations to reduce costs
- **Metrics**: Create custom metrics for business KPIs (event ingestion rate, delivery success rate)
- **Dashboards**: Build dashboards for key metrics and operational health
- **Alarms**: Set alarms for critical metrics (error rate, latency, throttling)
- **Insights queries**: Use CloudWatch Insights for log analysis and troubleshooting
- **Metric filters**: Create metric filters to extract metrics from logs

#### AWS X-Ray Best Practices
- **Sampling**: Use sampling rules to control trace volume (1% for high-volume APIs)
- **Annotations**: Add annotations for filtering traces (event_id, user_id, status)
- **Metadata**: Add metadata for additional context (payload size, retry count)
- **Subsegments**: Create subsegments for DynamoDB, SQS, HTTP calls for detailed timing
- **Service map**: Use service map to visualize dependencies and latencies
- **Trace analysis**: Use trace analysis to identify bottlenecks and errors
- **Integration**: Enable X-Ray in Lambda, API Gateway, DynamoDB for end-to-end tracing

#### CloudWatch Limitations
- **Cost**: Logs and metrics can become expensive at high volume
- **Query limitations**: CloudWatch Insights has query time limits and result size limits
- **Latency**: 1-5 minute delay for metric aggregation
- **Log size**: 256KB maximum log event size
- **Retention**: Logs retained indefinitely by default (must set retention to control costs)

#### AWS X-Ray Limitations
- **Overhead**: Adds latency (~1-2ms per request) and memory overhead
- **Sampling**: Not all requests traced (by design); may miss rare errors
- **Cost**: $5 per million traces recorded + $0.50 per million traces retrieved/scanned
- **Trace data retention**: 30-day retention limit for trace data

#### CloudWatch Conventions
- **Log group naming**: Use function name: `/aws/lambda/triggers-api-events-post`
- **Metric namespace**: Use service name: `TriggersAPI`
- **Metric naming**: Use PascalCase: `EventIngestionRate`, `DeliverySuccessRate`
- **Alarm naming**: Use descriptive names: `TriggersAPI-HighErrorRate-Prod`

#### CloudWatch Common Pitfalls
- **No retention set**: Indefinite log retention causing high costs
- **Missing alarms**: Not setting alarms for critical metrics
- **Unstructured logs**: Plain text logs difficult to query
- **No sampling**: Logging everything at high volume (expensive)
- **Ignoring Insights**: Not using CloudWatch Insights for log analysis
- **Too many metrics**: Creating excessive custom metrics (expensive)
- **Alarm fatigue**: Too many false-positive alarms (ignored alarms)

#### AWS X-Ray Common Pitfalls
- **Not enabling**: X-Ray disabled, missing visibility into performance issues
- **Over-sampling**: Sampling 100% causing high costs
- **Missing annotations**: Not adding annotations, difficult to filter traces
- **Ignoring service map**: Not using service map to identify bottlenecks
- **No subsegments**: Coarse-grained traces without subsegments

---

### 10. Infrastructure as Code (IaC)
**Selected: AWS SAM (Serverless Application Model)**

- AWS-native serverless infrastructure as code
- Extension of CloudFormation
- Local testing with SAM CLI
- Built-in templates for Lambda, API Gateway, DynamoDB
- Simplified syntax for serverless resources
- Native integration with AWS tooling

**Alternative Considered:** Terraform (multi-cloud but more complex for pure AWS)

#### AWS SAM Best Practices
- **Template organization**: Use nested stacks for large applications
- **Parameters**: Use parameters for environment-specific values (stage, region)
- **Globals**: Define global properties for functions (runtime, timeout, memory)
- **Layering**: Use Lambda Layers for shared dependencies
- **Local testing**: Use `sam local` to test functions and APIs locally
- **Validation**: Validate templates with `sam validate` before deployment
- **Build command**: Use `sam build` to package dependencies correctly
- **Deployment**: Use `sam deploy --guided` for interactive deployment
- **Versioning**: Use SAM template versioning and ChangeSets for safe updates

#### AWS SAM Limitations
- **CloudFormation limits**: Inherits CloudFormation limits (200 resources per stack)
- **Deployment time**: Large stacks can take 10-30 minutes to deploy
- **Error messages**: CloudFormation error messages can be cryptic
- **State management**: No native state locking (use S3 buckets with versioning)
- **Rollback limitations**: Automatic rollback not always reliable

#### AWS SAM Conventions
- **File naming**: Use `template.yaml` for main template
- **Resource naming**: Use PascalCase: `EventsFunction`, `InboxFunction`
- **Logical IDs**: Use descriptive logical IDs matching function purpose
- **Output naming**: Use PascalCase for outputs: `ApiUrl`, `EventsTableName`
- **Parameter naming**: Use PascalCase with type suffix: `StageName`, `MemorySize`

#### AWS SAM Common Pitfalls
- **Not using sam build**: Deploying without building, missing dependencies
- **Hardcoded values**: Hardcoding environment-specific values in template
- **Missing IAM permissions**: Underprivileged Lambda execution roles
- **Circular dependencies**: Creating circular dependencies between resources
- **Not testing locally**: Deploying without local testing (slow feedback loop)
- **Large deployment packages**: Including unnecessary files in deployment package
- **No rollback plan**: Deploying breaking changes without rollback strategy

---

### 11. Testing Framework
**Selected: pytest**

- Most popular Python testing framework
- Fixture system for test setup and teardown
- Parametrized testing support
- Extensive plugin ecosystem
- Async test support via pytest-asyncio
- Unit tests and integration tests

**Alternative Considered:** unittest (built-in but more verbose)

#### pytest Best Practices
- **Test organization**: Group tests in `tests/` directory, mirror source structure
- **Naming**: Name test files `test_*.py`, test functions `test_*`
- **Fixtures**: Use fixtures for setup/teardown; use `conftest.py` for shared fixtures
- **Assertions**: Use plain `assert` statements; pytest provides detailed failure messages
- **Parametrize**: Use `@pytest.mark.parametrize` for testing multiple inputs
- **Markers**: Use markers to categorize tests: `@pytest.mark.unit`, `@pytest.mark.integration`
- **Coverage**: Use `pytest-cov` to measure code coverage
- **Async tests**: Use `pytest-asyncio` with `@pytest.mark.asyncio` for async tests
- **Mock carefully**: Use `pytest-mock` or built-in `unittest.mock` for mocking

#### pytest Limitations
- **Learning curve**: Fixture system can be confusing for beginners
- **Magic**: Some pytest features use "magic" (auto-discovery, fixture injection)
- **Debugging**: Debugging can be harder due to pytest's test collection and execution model
- **Parallel execution**: Requires `pytest-xdist` plugin for parallel test execution

#### pytest Conventions
- **File structure**: Mirror source structure in tests: `src/handlers/events.py` → `tests/unit/handlers/test_events.py`
- **Fixture naming**: Use descriptive names: `dynamodb_table`, `mock_sqs_client`, `sample_event`
- **Test naming**: Use descriptive names: `test_create_event_success`, `test_create_event_invalid_payload`
- **Conftest placement**: Place `conftest.py` at appropriate level (tests root, package level)

#### pytest Common Pitfalls
- **Fixture scope**: Using wrong fixture scope (function vs module vs session)
- **Test isolation**: Tests depending on each other or sharing mutable state
- **Missing async marker**: Forgetting `@pytest.mark.asyncio` for async tests
- **Over-mocking**: Mocking too much, reducing test value
- **Not using parametrize**: Duplicating test code instead of parametrizing
- **Conftest pollution**: Putting too many fixtures in root `conftest.py`
- **Ignoring warnings**: Not fixing deprecation warnings from pytest or dependencies

---

### 12. AWS Service Mocking
**Selected: moto**

- Mock AWS services locally for testing
- Supports DynamoDB, SQS, S3, Lambda, etc.
- No AWS account needed for unit tests
- Fast test execution
- Active development and maintenance
- Unit test AWS interactions without real API calls

**Alternative Considered:** LocalStack (full emulation but heavier)

#### moto Best Practices
- **Decorators**: Use `@mock_dynamodb`, `@mock_sqs` decorators for test functions or classes
- **Context managers**: Use context managers for fine-grained control: `with mock_dynamodb():`
- **Setup/teardown**: Create tables/queues in fixtures or setUp methods
- **Multiple services**: Can mock multiple services simultaneously
- **Environment variables**: Mock handles AWS credentials automatically (uses dummy values)
- **Reset state**: Each mock starts clean; no need to clean up between tests
- **Boto3 client**: Use boto3 client normally; moto intercepts calls

#### moto Limitations
- **Not all services**: Not all AWS services supported (check documentation)
- **Incomplete implementations**: Some AWS API features not fully implemented
- **No IAM validation**: IAM policies not enforced in moto mocks
- **Behavior differences**: Some behaviors differ from real AWS services
- **No cost/throttling**: Doesn't simulate AWS costs or throttling

#### moto Conventions
- **Decorator placement**: Place moto decorators closest to function (innermost decorator)
- **Fixture naming**: Prefix fixtures with `mock_`: `mock_dynamodb_table`, `mock_sqs_queue`
- **Resource cleanup**: Not needed with moto (each test starts fresh), but good practice

#### moto Common Pitfalls
- **Using real credentials**: Accidentally using real AWS credentials (moto uses fake ones)
- **Missing decorator**: Forgetting moto decorator, causing tests to use real AWS
- **Wrong decorator order**: Placing moto decorators in wrong order (matters with multiple mocks)
- **Assuming full compatibility**: Assuming moto behavior exactly matches AWS
- **Not checking moto version**: Using features not yet implemented in installed moto version
- **Complex scenarios**: Testing complex AWS scenarios that moto doesn't fully support

---

### 13. HTTP Client
**Selected: httpx**

- Modern async HTTP client
- HTTP/2 support
- Connection pooling
- Configurable timeouts
- Retry logic support
- Drop-in replacement for requests
- Push events to Zapier workflow engine

**Alternative Considered:** requests + tenacity (synchronous only)

#### httpx Best Practices
- **Async client**: Use `httpx.AsyncClient()` for async operations in FastAPI
- **Client reuse**: Create client once, reuse across requests (connection pooling)
- **Timeouts**: Always set explicit timeouts: `timeout=httpx.Timeout(10.0, connect=5.0)`
- **Context manager**: Use context manager for automatic cleanup: `async with httpx.AsyncClient() as client:`
- **HTTP/2**: Enable HTTP/2 for better performance: `http2=True`
- **Retry logic**: Combine with tenacity for automatic retries
- **Error handling**: Handle `httpx.HTTPError`, `httpx.TimeoutException`, `httpx.NetworkError`
- **Headers**: Set common headers (User-Agent, Authorization) on client level
- **Connection limits**: Configure connection pool size: `limits=httpx.Limits(max_connections=100)`

#### httpx Limitations
- **Learning curve**: Async API different from synchronous requests library
- **HTTP/2 overhead**: HTTP/2 adds memory overhead; only enable if beneficial
- **Debugging**: Async errors can be harder to debug than synchronous
- **Compatibility**: Not 100% compatible with requests (similar but different API)

#### httpx Conventions
- **Client naming**: Use `http_client` or `async_client` for variable names
- **Method naming**: Use lowercase HTTP methods: `client.get()`, `client.post()`
- **Error handling**: Catch specific exceptions, not broad `Exception`
- **Response checking**: Use `response.raise_for_status()` to check for HTTP errors

#### httpx Common Pitfalls
- **Not reusing client**: Creating new client per request (no connection pooling)
- **Missing timeouts**: No timeout causing indefinite hangs
- **Blocking in async**: Using synchronous `httpx.Client()` in async functions
- **Not handling errors**: Not catching HTTP errors, network errors, timeouts
- **Large responses**: Loading large responses into memory (use streaming)
- **Connection leaks**: Not closing client properly (use context manager)

---

### 14. Data Validation & Serialization
**Selected: Pydantic v2**

- Type-safe data validation
- JSON schema generation
- Native FastAPI integration
- Excellent error messages
- Performance improvements in v2
- Event payload validation, API models, configuration

**Alternative Considered:** marshmallow (more flexible but verbose)

#### Pydantic Best Practices
- **BaseModel**: Inherit from `BaseModel` for all models
- **Type hints**: Use proper type hints: `str`, `int`, `list[str]`, `Optional[str]`
- **Field validators**: Use `@field_validator` for custom validation logic
- **Model validators**: Use `@model_validator` for validating multiple fields together
- **Config**: Use `ConfigDict` for model configuration (v2 syntax)
- **Aliases**: Use `Field(alias="...")` for JSON field name mapping
- **Defaults**: Provide defaults or use `Optional` for optional fields
- **Immutability**: Use `frozen=True` for immutable models
- **JSON schema**: Use `model_json_schema()` to generate JSON schemas

#### Pydantic Limitations
- **Validation overhead**: Adds validation overhead (minimal but present)
- **Complex types**: Some complex Python types not directly supported
- **Error messages**: Default error messages may not be user-friendly (customize with validators)
- **Serialization**: Some custom types need custom serializers

#### Pydantic Conventions
- **Model naming**: Use PascalCase: `EventRequest`, `EventResponse`, `InboxItem`
- **Field naming**: Use snake_case: `event_id`, `created_at`, `delivery_status`
- **File organization**: Group related models in same file or module
- **Documentation**: Use docstrings and field descriptions for auto-generated docs

#### Pydantic Common Pitfalls
- **Missing type hints**: Forgetting type hints causes validation to be skipped
- **Mutable defaults**: Using mutable defaults (list, dict) without `Field(default_factory=...)`
- **Circular imports**: Creating circular dependencies between models
- **V1 vs V2 syntax**: Mixing Pydantic v1 and v2 syntax (use v2 consistently)
- **Over-validation**: Adding unnecessary validation that hurts performance
- **Not using Field**: Not using `Field()` for validation constraints (min, max, regex)

---

### 15. Structured Logging
**Selected: structlog**

- Structured logging optimized for CloudWatch
- JSON output format
- Contextual log enrichment (event_id, user_id, etc.)
- Better log querying in CloudWatch Insights
- Performance-focused design
- Application logging with rich context

**Alternative Considered:** python-json-logger (simpler but fewer features)

#### structlog Best Practices
- **Configuration**: Configure structlog at application startup
- **Context binding**: Use `log.bind()` to add context to logger
- **Processors**: Use processors for consistent log formatting (timestamps, log levels)
- **JSON renderer**: Use `JSONRenderer()` for CloudWatch-friendly logs
- **Log levels**: Use appropriate log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Correlation IDs**: Bind request_id/correlation_id to logger for request tracing
- **Sensitive data**: Avoid logging sensitive data (API keys, passwords, PII)
- **Performance**: Use `BoundLogger` for performance-critical code

#### structlog Limitations
- **Learning curve**: More complex than standard logging library
- **Configuration**: Requires upfront configuration
- **Compatibility**: Not fully compatible with standard logging (use bridges)
- **Overhead**: Slight performance overhead compared to standard logging

#### structlog Conventions
- **Logger naming**: Use `structlog.get_logger(__name__)` for logger instances
- **Field naming**: Use snake_case for log fields: `event_id`, `user_id`, `request_id`
- **Context binding**: Bind context early in request lifecycle
- **Log messages**: Use descriptive messages: "Event created successfully"

#### structlog Common Pitfalls
- **Not configuring**: Using structlog without proper configuration
- **Logging objects**: Logging non-serializable objects (use `.to_dict()` or `str()`)
- **Missing context**: Not binding enough context for debugging
- **Over-logging**: Logging too much at INFO level (use DEBUG for verbose logs)
- **Not using processors**: Missing useful processors (add_timestamp, add_log_level)
- **Logging secrets**: Accidentally logging sensitive data

---

### 16. Password/API Key Hashing
**Selected: passlib with bcrypt**

- Industry-standard password hashing
- bcrypt algorithm (secure, intentionally slow)
- Configurable work factor
- Automatic salt generation
- Hash verification utilities
- Hash API keys before storing in DynamoDB

**Alternative Considered:** argon2-cffi (newer algorithm but bcrypt is proven)

#### passlib + bcrypt Best Practices
- **Work factor**: Use appropriate work factor (12-14 for bcrypt)
- **Context object**: Use `CryptContext` for flexible hash management
- **Verification**: Use `context.verify()` to check hashes
- **Hash storage**: Store full hash string (includes salt, algorithm, work factor)
- **Timing attacks**: Use `context.verify()` (constant-time comparison)
- **Rehashing**: Rehash when work factor increases (use `context.needs_update()`)
- **Error handling**: Handle verification errors gracefully

#### passlib + bcrypt Limitations
- **Performance**: Intentionally slow (good for security, but adds latency)
- **bcrypt limits**: 72-character maximum password length
- **Work factor**: Higher work factor = more secure but slower
- **Memory**: Uses memory for key derivation (minimal for bcrypt)

#### passlib + bcrypt Conventions
- **Work factor**: Use 12 for development, 13-14 for production
- **Hash storage**: Store as string, not binary
- **Variable naming**: Use descriptive names: `hashed_key`, `api_key_hash`

#### passlib + bcrypt Common Pitfalls
- **Low work factor**: Using work factor < 12 (too fast, less secure)
- **Comparing hashes directly**: Using `==` instead of `verify()` (timing attacks)
- **Not handling errors**: Not catching `ValueError` from invalid hashes
- **Storing plaintext**: Storing plaintext passwords/keys (never do this)
- **bcrypt encoding**: Not encoding password to bytes before hashing
- **Truncation**: Not warning about 72-character bcrypt limit

---

### 17. Configuration Management
**Selected: pydantic-settings**

- Type-safe settings from environment variables
- Validation at application startup
- .env file support for local development
- Nested configuration objects
- Integrates seamlessly with Pydantic models
- Load configuration, AWS region, table names, timeouts

**Alternative Considered:** python-decouple (simpler but no validation)

#### pydantic-settings Best Practices
- **BaseSettings**: Inherit from `BaseSettings` for settings classes
- **Environment variables**: Use uppercase for environment variable names
- **Type hints**: Use proper type hints with defaults or `Optional`
- **Validation**: Leverage Pydantic validators for config validation
- **.env files**: Use `.env` for local development; production uses actual env vars
- **Nested settings**: Group related settings in nested models
- **Secrets**: Load secrets from AWS Secrets Manager, not env vars in production
- **Model config**: Use `SettingsConfigDict` for configuration (case_sensitive, env_file)

#### pydantic-settings Limitations
- **Environment only**: Primarily for environment variables; not for config files (JSON, YAML)
- **Type conversion**: Limited type conversion; complex types need custom parsing
- **Reloading**: Settings loaded once at startup; no hot reloading
- **Override complexity**: Overriding nested settings via env vars can be verbose

#### pydantic-settings Conventions
- **Class naming**: Use `Settings` suffix: `AppSettings`, `DatabaseSettings`
- **Field naming**: Use UPPERCASE for env var names, lowercase for field names
- **File naming**: Use `settings.py` or `config/settings.py`
- **Singleton**: Create single settings instance: `settings = Settings()`

#### pydantic-settings Common Pitfalls
- **Missing .env**: Assuming .env file exists (handle gracefully if missing)
- **Type mismatch**: Environment variables as strings not converting to expected types
- **Validation errors**: Not handling validation errors at startup
- **Secrets in .env**: Committing `.env` to version control with secrets
- **No defaults**: Missing defaults for optional configuration
- **Case sensitivity**: Env var case sensitivity issues (use `case_sensitive=False`)

---

### 18. Date/Time Handling
**Selected: Built-in datetime + python-dateutil**

- Python's datetime module (standard library)
- dateutil for advanced parsing and manipulation
- ISO 8601 format support
- Timezone-aware operations
- Event timestamps, TTL calculations, expiration logic

**Alternative Considered:** pendulum or arrow (friendlier API but additional dependency)

#### datetime + dateutil Best Practices
- **Timezone awareness**: Always use timezone-aware datetime objects (use UTC)
- **ISO 8601**: Use `isoformat()` for string serialization
- **Parsing**: Use `dateutil.parser.isoparse()` for ISO 8601 parsing
- **UTC**: Store all timestamps in UTC; convert to local time only for display
- **Comparison**: Only compare timezone-aware datetimes with each other
- **Current time**: Use `datetime.now(timezone.utc)` for current UTC time
- **Arithmetic**: Use `timedelta` for date/time arithmetic
- **Formatting**: Use `strftime()` for custom formatting when needed

#### datetime Limitations
- **API complexity**: datetime API can be confusing (naive vs aware, timezones)
- **Timezone handling**: Timezone handling not as elegant as newer libraries
- **Parsing**: Built-in `strptime()` requires format string; dateutil more flexible
- **Arithmetic**: Some date arithmetic operations are verbose

#### datetime Conventions
- **Variable naming**: Use descriptive names: `created_at`, `expires_at`, `delivered_at`
- **Timezone**: Always specify timezone: `datetime.now(timezone.utc)`
- **Storage format**: Store as ISO 8601 strings in DynamoDB or Unix timestamps
- **Type hints**: Use `datetime` type hint from `datetime` module

#### datetime Common Pitfalls
- **Naive datetime**: Using naive datetime objects (no timezone info)
- **Timezone mixing**: Comparing UTC with local time datetimes
- **String parsing**: Using `strptime()` without handling parse errors
- **Now() without UTC**: Using `datetime.now()` without timezone (gives local time)
- **JSON serialization**: Forgetting datetime objects aren't JSON serializable (use `isoformat()`)
- **Milliseconds**: Forgetting to handle microseconds when parsing timestamps

---

### 19. Retry Logic
**Selected: tenacity**

- Flexible retry library
- Exponential backoff with jitter
- Configurable stop conditions
- Async support
- Before/after callback hooks
- Retry failed push deliveries and DynamoDB operations

**Alternative Considered:** backoff (simpler but less flexible)

#### tenacity Best Practices
- **Decorator**: Use `@retry` decorator for functions that need retries
- **Stop strategy**: Use `stop=stop_after_attempt(3)` for maximum retry count
- **Wait strategy**: Use `wait=wait_exponential(multiplier=1, min=1, max=10)` for exponential backoff
- **Jitter**: Add jitter to prevent thundering herd: `wait_exponential(jitter=1)`
- **Retry conditions**: Use `retry=retry_if_exception_type(...)` to retry specific exceptions
- **Before/after hooks**: Use `before`, `after` callbacks for logging retry attempts
- **Async support**: Works with async functions transparently
- **Re-raise**: Use `reraise=True` to re-raise after all retries exhausted

#### tenacity Limitations
- **Complexity**: More complex than simpler retry libraries
- **Synchronous default**: Async support requires careful usage
- **No built-in metrics**: Doesn't track retry metrics (add manually in callbacks)

#### tenacity Conventions
- **Retry config**: Define retry configuration as constants or config
- **Logging**: Log retry attempts in `before` callback for debugging
- **Exception filtering**: Only retry transient errors, not permanent failures
- **Max attempts**: Use 3-5 max attempts for most use cases

#### tenacity Common Pitfalls
- **Retrying all exceptions**: Retrying non-retryable errors (validation, 404, etc.)
- **No max attempts**: Missing stop condition (infinite retries)
- **Linear backoff**: Using linear wait instead of exponential (causes congestion)
- **No jitter**: Missing jitter causing synchronized retries
- **Silent retries**: Not logging retry attempts for debugging
- **Blocking in async**: Using synchronous sleep in async code (tenacity handles this)

---

### 20. API Rate Limiting
**Selected: AWS API Gateway Rate Limiting**

- Built-in throttling per API key
- Per-method rate limits
- Burst limits configuration
- No code required (managed by AWS)
- Prevent API abuse and enforce quotas

**Alternative Considered:** slowapi (application-level, more flexible but requires management)

#### API Gateway Rate Limiting Best Practices
- **Usage plans**: Create usage plans for different API key tiers (free, pro, enterprise)
- **Throttle limits**: Set both rate limit (sustained) and burst limit
- **Per-key limits**: Associate API keys with usage plans for per-client limits
- **Rate limit headers**: Return `X-RateLimit-*` headers in responses (custom implementation)
- **429 responses**: Configure proper 429 Too Many Requests responses
- **Monitoring**: Monitor throttling metrics in CloudWatch
- **Quotas**: Set daily/monthly quotas in usage plans for cost control

#### API Gateway Rate Limiting Limitations
- **Per-API limits**: Limits apply at API level, not account-wide
- **No distributed limiting**: Each API Gateway instance tracks separately
- **Burst only**: Burst limit is short-term; can't configure longer windows
- **HTTP API**: HTTP APIs have simpler throttling than REST APIs
- **No custom rules**: Can't implement complex rate limiting logic (need Lambda)

#### API Gateway Conventions
- **Usage plan naming**: Use descriptive names: `Free-Tier`, `Pro-Tier`, `Enterprise`
- **Rate limits**: Set reasonable defaults: Free=100 req/s, Pro=1000 req/s
- **Burst limits**: Set burst = rate * 2 (allow short bursts)
- **Quota units**: Use requests/day or requests/month for quotas

#### API Gateway Common Pitfalls
- **No usage plans**: Not creating usage plans for API keys (no limits)
- **Too restrictive**: Setting limits too low, impacting legitimate users
- **Too permissive**: Setting limits too high, not protecting from abuse
- **Missing monitoring**: Not monitoring throttling events
- **Poor error messages**: Not providing clear 429 error responses
- **Account limits**: Hitting account-level API Gateway limits (10,000 req/s default)

---

## Complete Tech Stack Summary

### Core Application Stack
```
API Framework:        FastAPI 0.104+
Lambda Adapter:       Mangum 0.17+
Data Validation:      Pydantic 2.5+
Configuration:        pydantic-settings 2.1+
HTTP Client:          httpx 0.25+
Retry Logic:          tenacity 8.2+
Logging:              structlog 23.2+
Hashing:              passlib[bcrypt] 1.7.4+
Date/Time:            python-dateutil 2.8+
```

### AWS Services
```
Compute:              AWS Lambda (Python 3.11+)
API Gateway:          AWS API Gateway (HTTP API)
Database:             Amazon DynamoDB
Message Queue:        Amazon SQS
Authentication:       Lambda Authorizer
Secrets:              AWS Secrets Manager
Encryption:           AWS KMS
Monitoring:           Amazon CloudWatch
Tracing:              AWS X-Ray
IaC:                  AWS SAM
Rate Limiting:        API Gateway Throttling
```

### Development & Testing
```
Testing Framework:    pytest 7.4+
Async Testing:        pytest-asyncio 0.21+
AWS Mocking:          moto 5.0+
Local Dev:            python-dotenv 1.0+
```

### AWS SDK
```
AWS Integration:      boto3 1.29+
```

---

## Project Structure

```
zapier-triggers-api/
├── template.yaml              # AWS SAM template
├── requirements.txt           # Production dependencies
├── requirements-dev.txt       # Development dependencies
├── .env.example              # Environment variable template
├── src/
│   ├── main.py               # FastAPI app initialization
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── events.py         # POST /events, GET /events
│   │   ├── inbox.py          # GET /inbox
│   │   └── replay.py         # POST /events/{id}/replay
│   ├── models/
│   │   ├── __init__.py
│   │   ├── event.py          # Event data models
│   │   ├── request.py        # API request models
│   │   └── response.py       # API response models
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── authorizer.py     # Lambda authorizer function
│   │   └── api_key.py        # API key validation logic
│   ├── storage/
│   │   ├── __init__.py
│   │   └── dynamodb.py       # DynamoDB operations
│   ├── queue/
│   │   ├── __init__.py
│   │   └── sqs.py            # SQS operations
│   ├── delivery/
│   │   ├── __init__.py
│   │   ├── push.py           # Push delivery to Zapier
│   │   └── retry.py          # Retry logic
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py       # Pydantic settings
│   └── utils/
│       ├── __init__.py
│       ├── logger.py         # Logging setup
│       └── helpers.py        # Utility functions
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # pytest fixtures
│   ├── unit/
│   │   ├── test_events.py
│   │   ├── test_inbox.py
│   │   ├── test_replay.py
│   │   └── test_auth.py
│   └── integration/
│       ├── test_api.py
│       └── test_delivery.py
└── _docs/
    ├── Project Overview.md
    ├── Brainstorming.md
    ├── user-flow.md
    └── tech-stack.md
```

---

## Requirements Files

### requirements.txt (Production)
```
fastapi>=0.104.0
mangum>=0.17.0
boto3>=1.29.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
passlib[bcrypt]>=1.7.4
structlog>=23.2.0
tenacity>=8.2.0
httpx>=0.25.0
python-dateutil>=2.8.0
```

### requirements-dev.txt (Development)
```
-r requirements.txt
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
moto>=5.0.0
python-dotenv>=1.0.0
black>=23.0.0
ruff>=0.1.0
mypy>=1.7.0
```

---

## Design Principles

### 1. Serverless-First
- Leverage managed AWS services to minimize operational overhead
- Auto-scaling by default
- Pay-per-use pricing model

### 2. High Availability
- Multi-AZ deployment across all services
- No single points of failure
- Built-in redundancy and failover

### 3. Security by Default
- Encryption at rest (KMS) and in transit (TLS 1.2+)
- API key authentication with Lambda Authorizer
- Secrets in AWS Secrets Manager (never in code)
- IAM policies for least-privilege access

### 4. Observability
- Structured logging with context (event_id, user_id)
- Distributed tracing with X-Ray
- CloudWatch metrics and alarms
- Request/response logging for debugging

### 5. Reliability
- Retry logic with exponential backoff
- Dead Letter Queues for failed events
- Idempotency support
- Event persistence guarantees

### 6. Developer Experience
- Type safety with Pydantic and type hints
- Automatic API documentation (OpenAPI/Swagger)
- Local testing with moto
- Clear error messages and validation

### 7. Performance
- Async I/O throughout the stack
- Connection pooling (httpx)
- Efficient DynamoDB queries
- Lambda cold start optimization

---

## Next Steps

1. **Environment Setup**: Create AWS account, configure credentials
2. **Repository Setup**: Initialize Git repository, add .gitignore
3. **Project Scaffolding**: Create directory structure, initialize Python package
4. **SAM Template**: Define infrastructure resources in template.yaml
5. **Core Models**: Implement Pydantic models for events and requests
6. **Database Schema**: Design DynamoDB table structure and indexes
7. **API Implementation**: Build FastAPI endpoints per user-flow.md
8. **Authentication**: Implement Lambda Authorizer for API keys
9. **Testing**: Write unit tests with pytest and moto
10. **Deployment**: Deploy to AWS with SAM CLI
11. **Monitoring**: Set up CloudWatch dashboards and alarms
12. **Documentation**: Generate OpenAPI docs, write developer guide

---

## Architecture Diagram

```
┌─────────────┐
│  Developer  │
└──────┬──────┘
       │ HTTPS
       ▼
┌──────────────────────┐
│   API Gateway        │ (Rate Limiting, Auth)
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Lambda Authorizer    │ (Validate API Key)
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Lambda (FastAPI)     │ (POST /events, GET /inbox, etc.)
│ - Event Validation   │
│ - Business Logic     │
└──┬─────────────────┬─┘
   │                 │
   ▼                 ▼
┌─────────────┐  ┌──────────────┐
│  DynamoDB   │  │     SQS      │ (Inbox Queue)
│  (Events)   │  │  (Delivery)  │
└─────────────┘  └──────┬───────┘
                        │
                        ▼
                 ┌──────────────────┐
                 │ Lambda (Delivery)│
                 │ Push to Zapier   │
                 └──────────────────┘
                        │
                        ▼
                 ┌──────────────────┐
                 │  Zapier System   │
                 └──────────────────┘

Monitoring: CloudWatch + X-Ray (spans all components)
Secrets: AWS Secrets Manager (accessed by Lambdas)
Encryption: AWS KMS (encrypts DynamoDB, SQS)
```

---

## Notes

- All services are deployed in the same AWS region for latency optimization
- DynamoDB and SQS use AWS-managed KMS keys by default
- Lambda functions run Python 3.11+ runtime
- API Gateway uses HTTP API (not REST API) for lower cost and latency
- Event retention in DynamoDB: configurable TTL (default 30 days)
- SQS message retention: 14 days maximum
- CloudWatch log retention: 90 days (configurable)

