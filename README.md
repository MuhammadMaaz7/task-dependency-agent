# Task Dependency Agent

Task Dependency Agent (TDA) is a FastAPI microservice that automatically infers task dependencies using LLM analysis and determines optimal execution order. The agent analyzes task descriptions to understand relationships, eliminating the need for manual dependency specification.

## Features
- **LLM-Based Dependency Inference**: Uses OpenRouter API to automatically infer task dependencies from descriptions
- **Automatic Execution Ordering**: Calculates optimal task execution order using topological sorting
- **FastAPI Service**: RESTful API with `/health` and `/task` endpoints
- **MongoDB Integration**: Persistent task storage with atomic batch updates
- **Database Operations**: Retrieve tasks, infer dependencies, and update database automatically
- **Retry Logic**: Exponential backoff for both database and API operations
- **Structured Logging**: Comprehensive logging with timestamps and component names
- **Comprehensive Testing**: 32+ tests covering LLM inference, database operations, and error handling

## Repository Layout
- `api/main.py` – FastAPI application entry point for Vercel serverless hosting
- `agents/worker_tda.py` – Core TaskDependencyAgent with LLM inference and database integration
- `agents/worker_base.py` – Shared worker interface and messaging helpers
- `agents/database_client.py` – MongoDB Atlas client for task storage and retrieval
- `agents/openrouter_client.py` – OpenRouter API client for LLM-based dependency inference
- `LTM/tda_ltm.json` – Default long-term memory file (auto-created)
- `tests/` – Comprehensive test suite (32+ tests) covering all functionality
- `vercel.json` – Route configuration for Vercel deployment

## Prerequisites
- Python 3.11+ (matching the version used during development).
- pip (or uv/pipenv/poetry) for dependency installation.

### Python Dependencies
Install pinned dependencies from `requirements.txt`:
```bash
pip install -r requirements.txt
```

## Local Setup
1. Clone or open the repository.
2. (Optional) Create a virtual environment:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate  # Windows
   source .venv/bin/activate  # macOS/Linux
   ```
3. Install dependencies as described above.
4. Configure environment variables by copying `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
5. Update `.env` with your configuration:
   ```
   # MongoDB Configuration (required for database operations)
   MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/
   MONGODB_DATABASE=task_dependency_db
   MONGODB_COLLECTION=tasks
   
   # OpenRouter Configuration (required for LLM inference)
   OPENROUTER_API_KEY=your_api_key_here
   OPENROUTER_MODEL=openai/gpt-4  # Optional, defaults to gpt-4
   ```

## Running the API Locally
For local development, you can run the API using Uvicorn:
```bash
uvicorn api.main:app --host 0.0.0.0 --port 9001 --reload
```
By default the app listens on `http://0.0.0.0:9001`.

### Health Check
```bash
curl http://localhost:9001/health
```

### Task Resolution Endpoint
Send a supervisor-compatible payload to `/task` with task descriptions (no manual dependencies needed):
```bash
curl -X POST http://localhost:9001/task ^
  -H "Content-Type: application/json" ^
  -d "{
    \"request_id\": \"demo-001\",
    \"agent_name\": \"task_dependency_agent\",
    \"intent\": \"task.resolve_dependencies\",
    \"input\": {
      \"tasks\": [
        {
          \"id\": \"task-1\",
          \"name\": \"Setup Environment\",
          \"description\": \"Initialize the project and install dependencies\"
        },
        {
          \"id\": \"task-2\",
          \"name\": \"Build Application\",
          \"description\": \"Compile and build the application code\"
        },
        {
          \"id\": \"task-3\",
          \"name\": \"Run Tests\",
          \"description\": \"Execute unit and integration tests\"
        },
        {
          \"id\": \"task-4\",
          \"name\": \"Deploy\",
          \"description\": \"Deploy the tested application to production\"
        }
      ]
    }
  }"
```

**Response Format:**
```json
{
  "request_id": "demo-001",
  "agent_name": "task_dependency_agent",
  "status": "success",
  "output": {
    "result": {
      "dependencies": {
        "task-1": [],
        "task-2": ["task-1"],
        "task-3": ["task-2"],
        "task-4": ["task-3"]
      },
      "execution_order": ["task-1", "task-2", "task-3", "task-4"]
    },
    "confidence": 0.92,
    "details": "Dependency resolution completed"
  },
  "error": null
}
```

The LLM analyzes task descriptions and automatically infers which tasks depend on others, returning:
- `dependencies`: Map of task IDs to their dependency lists
- `execution_order`: Ordered list of task IDs for sequential execution

### Current Production Deployment
- Health check: https://task-dependency-agent.vercel.app/ returns a JSON confirmation that the service is running. [[source]](https://task-dependency-agent.vercel.app/)

## LLM-Based Dependency Inference

### How It Works
The TDA uses OpenRouter API to analyze task descriptions and automatically infer dependencies:

1. **Task Analysis**: The LLM receives task IDs, names, and descriptions
2. **Dependency Inference**: AI analyzes which tasks require outputs from other tasks
3. **Validation**: Ensures all inferred dependencies reference existing task IDs
4. **Execution Ordering**: Topological sort determines optimal execution sequence

### LLM Prompt Design
The system uses a carefully crafted prompt that instructs the LLM to:
- Identify tasks that must be completed before others
- Return results in strict JSON format
- Only reference task IDs provided in the input
- Explain reasoning for each dependency (for debugging)

Example prompt structure:
```
System: You are a task dependency analyzer. Identify which tasks depend on others 
based on their descriptions. A task depends on another if it requires the other 
task's output or completion.

User: Analyze these tasks and identify dependencies:
- ID: task-1, Name: Setup, Description: Initialize project
- ID: task-2, Name: Build, Description: Compile the code
- ID: task-3, Name: Test, Description: Run tests on built application

Return JSON: {"dependencies": {"task-2": ["task-1"], "task-3": ["task-2"]}}
```

### Supported Models
Configure via `OPENROUTER_MODEL` environment variable:
- `openai/gpt-4` (default) - Most accurate for complex dependencies
- `openai/gpt-3.5-turbo` - Faster, good for simple workflows
- `anthropic/claude-3-opus` - Alternative high-quality option

## Database Integration Workflow

The TDA supports complete database-driven workflows:

### Complete Workflow
```python
from agents.worker_tda import TaskDependencyAgent
from agents.database_client import DatabaseClient

# Initialize with database client
db_client = DatabaseClient()
tda = TaskDependencyAgent("tda-1", "supervisor-1", db_client=db_client)

# Execute complete workflow: retrieve -> infer -> update
result = tda.process_task_with_database()

# Result contains inferred dependencies and execution order
print(result["dependencies"])
print(result["execution_order"])
```

### Workflow Steps
1. **Retrieve**: Query all tasks from MongoDB
2. **Infer**: Use LLM to analyze descriptions and infer dependencies
3. **Update**: Atomically update all tasks with `depends_on` arrays and execution order

## Long-Term Memory (Caching)
Task graphs can be cached in `LTM/tda_ltm.json` for faster repeated queries. You can change the storage path via the `ltm_file` constructor parameter in `TaskDependencyAgent`. Delete the JSON file to reset cached answers.

## Running Tests
### Local unit tests
Execute the pytest suite from the repository root:
```bash
pytest
```
Tests use temporary directories for LTM storage, so they do not mutate the real cache.

### Remote smoke tests
After deploying, hit the live endpoints:
```bash
# Health
curl https://task-dependency-agent.vercel.app/health

# Sample dependency resolution
curl -X POST https://task-dependency-agent.vercel.app/task \
  -H "Content-Type: application/json" \
  -d '{
        "request_id": "remote-demo-001",
        "agent_name": "task_dependency_agent",
        "intent": "task.resolve_dependencies",
        "input": {
          "tasks": [
            {"id": "design", "depends_on": []},
            {"id": "build", "depends_on": ["design"]},
            {"id": "test", "depends_on": ["build"]}
          ]
        }
      }'
```
Adjust the base URL if you deploy to a different Vercel project or environment.

## Database Client

The `DatabaseClient` class provides MongoDB Atlas integration with the following features:

### Key Features
- **Task Retrieval**: Query all tasks from the database with automatic field validation
- **Batch Updates**: Atomically update multiple tasks in a single transaction
- **Retry Logic**: Automatic retry with exponential backoff (up to 3 attempts) for database operations
- **Context Manager**: Supports `with` statement for automatic connection cleanup

### Usage Example
```python
from agents.database_client import DatabaseClient

# Initialize client (uses environment variables)
with DatabaseClient() as db_client:
    # Retrieve all tasks
    tasks = db_client.get_all_tasks()
    
    # Validate task data
    error = db_client.validate_task_data(tasks)
    if error:
        print(f"Validation error: {error}")
    
    # Update tasks with dependencies
    updates = [
        {
            "id": "task-1",
            "depends_on": ["task-0"],
            "execution_order": 1,
            "status": "ready"
        }
    ]
    db_client.update_tasks_batch(updates)
```

### Configuration
Set these environment variables in your `.env` file:
- `MONGODB_URI`: MongoDB Atlas connection string (required)
- `MONGODB_DATABASE`: Database name (default: `task_dependency_db`)
- `MONGODB_COLLECTION`: Collection name (default: `tasks`)

## Error Handling

The TDA includes comprehensive error handling with structured logging:

### OpenRouter API Errors
- **Authentication (401)**: Check `OPENROUTER_API_KEY` is valid
- **Rate Limiting (429)**: Automatic retry with backoff
- **Server Errors (5xx)**: Retries up to 3 times before failing

### Database Errors
- **Connection Failures**: Automatic retry with exponential backoff (1s, 2s, 4s)
- **Transaction Failures**: Automatic rollback to maintain consistency
- **Validation Errors**: Clear error messages for missing or invalid fields

### Logging
All operations are logged with:
- Timestamp
- Component name
- Log level (INFO, WARNING, ERROR)
- Detailed error messages with stack traces

## Troubleshooting
- **HTTP 422 errors** – Ensure your payload matches the `AgentRequest` schema defined in `api/main.py`
- **invalid_agent / unsupported_intent responses** – Confirm `agent_name` is `task_dependency_agent` and `intent` is `task.resolve_dependencies`
- **OpenRouter API errors** – Verify `OPENROUTER_API_KEY` is set correctly in `.env`
- **LLM inference failures** – Check OpenRouter API status and your API key validity
- **MongoDB connection errors** – Verify `MONGODB_URI` is correct and your IP is whitelisted in MongoDB Atlas
- **Database retry failures** – Check network connectivity and MongoDB Atlas cluster status
- **Permission issues writing LTM** – Check that the process can create or modify files under `LTM/`

For additional questions or integration support, inspect `agents/worker_tda.py` and adapt the request contract to your supervisor or orchestration layer.

