# Task Dependency Agent

Task Dependency Agent (TDA) is a FastAPI microservice that resolves task execution orderings for multi-step projects. It accepts task graphs, performs cycle detection plus topological sorting, and returns an execution plan along with blocked-task diagnostics. The agent also persists previously solved graphs to a lightweight long-term memory (LTM) store so repeated calls can be answered instantly.

## Features
- FastAPI service with `/health` and `/task` endpoints.
- Dependency resolver that surfaces execution order, blocked tasks, and cycles.
- Supervisor-facing request/response contract compatible with other agents.
- JSON-based LTM cache stored under `LTM/tda_ltm.json`.
- Comprehensive pytest suite covering success paths and cycle handling.

## Repository Layout
- `main_api.py` – FastAPI entry point that wires HTTP requests to the agent.
- `api/main.py` – Thin Vercel adapter that exposes the FastAPI `app` for serverless hosting.
- `agent/worker_tda.py` – Core TaskDependencyAgent implementation.
- `agent/worker_base.py` – Shared worker interface and messaging helpers.
- `LTM/tda_ltm.json` – Default long-term memory file (auto-created).
- `tests/` – Unit tests for supervisor request handling and cycle detection.
- `vercel.json` – Route configuration for the Vercel deployment.

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

## Running the API
Start the FastAPI server through Uvicorn:
```bash
python main_api.py
```
By default the app listens on `http://0.0.0.0:9001`.

### Health Check
```bash
curl http://localhost:9001/health
```

### Task Resolution Endpoint
Send a supervisor-compatible payload to `/task`:
```bash
curl -X POST http://localhost:9001/task ^
  -H "Content-Type: application/json" ^
  -d "{
    \"request_id\": \"demo-001\",
    \"agent_name\": \"task_dependency_agent\",
    \"intent\": \"task.resolve_dependencies\",
    \"input\": {
      \"tasks\": [
        {\"id\": \"design\", \"depends_on\": []},
        {\"id\": \"build\", \"depends_on\": [\"design\"]},
        {\"id\": \"test\", \"depends_on\": [\"build\"]}
      ]
    }
  }"
```
The response contains `execution_order`, `blocked_tasks`, `cycles_detected`, and echo data such as `request_id`.

## Deploying to Vercel
This repo is wired for Vercel’s native Python runtime via `vercel.json` and the `api/main.py` entrypoint.

1. Install the Vercel CLI (requires Node.js):
   ```bash
   npm i -g vercel
   ```
2. Authenticate: `vercel login`.
3. From the repo root, run `vercel` to create the project (accept defaults or set a custom name).
4. Deploy with `vercel --prod` once you are satisfied with the preview build.

Behind the scenes Vercel:
- Installs dependencies from `requirements.txt`.
- Packages `api/main.py`, which simply imports the FastAPI `app` defined in `main_api.py`.
- Routes every request (`/(.*)`) to the ASGI app via the Python serverless runtime defined in `vercel.json`.

After deployment you can hit the same `/health` and `/task` paths on your Vercel domain.

### Current Production Deployment
- Health check: https://task-dependency-agent.vercel.app/ returns a JSON confirmation that the service is running. [[source]](https://task-dependency-agent.vercel.app/)

If you redeploy under a different organization/project, update this section with the new domain.

## Long-Term Memory (Caching)
Every task graph is normalized to JSON and cached in `LTM/tda_ltm.json`. You can change the storage path via the `ltm_file` constructor parameter in `TaskDependencyAgent`. Delete the JSON file if you want to reset cached answers.

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

## Troubleshooting
- **HTTP 422 errors** – Ensure your payload matches the `AgentRequest` schema defined in `main_api.py`.
- **invalid_agent / unsupported_intent responses** – Confirm `agent_name` is `task_dependency_agent` and `intent` is `task.resolve_dependencies`.
- **Permission issues writing LTM** – Check that the process can create or modify files under `LTM/`.

For additional questions or integration support, inspect `agent/worker_tda.py` and adapt the request contract to your supervisor or orchestration layer.

