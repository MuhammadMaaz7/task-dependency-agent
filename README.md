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
- `agent/worker_tda.py` – Core TaskDependencyAgent implementation.
- `agent/worker_base.py` – Shared worker interface and messaging helpers.
- `LTM/tda_ltm.json` – Default long-term memory file (auto-created).
- `tests/` – Unit tests for supervisor request handling and cycle detection.

## Prerequisites
- Python 3.11+ (matching the version used during development).
- pip (or uv/pipenv/poetry) for dependency installation.

### Python Dependencies
Install FastAPI, Uvicorn, and test tooling:
```bash
pip install fastapi uvicorn pydantic pytest
```
If you prefer a pinned environment, create a `requirements.txt` with the same packages and install via `pip install -r requirements.txt`.

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

## Long-Term Memory (Caching)
Every task graph is normalized to JSON and cached in `LTM/tda_ltm.json`. You can change the storage path via the `ltm_file` constructor parameter in `TaskDependencyAgent`. Delete the JSON file if you want to reset cached answers.

## Running Tests
Execute the pytest suite from the repository root:
```bash
pytest
```
Tests use temporary directories for LTM storage, so they do not mutate the real cache.

## Troubleshooting
- **HTTP 422 errors** – Ensure your payload matches the `AgentRequest` schema defined in `main_api.py`.
- **invalid_agent / unsupported_intent responses** – Confirm `agent_name` is `task_dependency_agent` and `intent` is `task.resolve_dependencies`.
- **Permission issues writing LTM** – Check that the process can create or modify files under `LTM/`.

For additional questions or integration support, inspect `agent/worker_tda.py` and adapt the request contract to your supervisor or orchestration layer.

