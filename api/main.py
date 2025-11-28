import sys
import os

# Get absolute path to project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict, Optional
from agents.worker_tda import TaskDependencyAgent
from agents.database_client import DatabaseClient

app = FastAPI(title="Task Dependency Agent Service")

# Initialize database client
try:
    db_client = DatabaseClient()
    tda = TaskDependencyAgent(
        agent_id="task_dependency_agent", 
        supervisor_id="supervisor",
        db_client=db_client
    )
except Exception as e:
    print(f"Warning: Failed to initialize database client: {e}")
    # Initialize without database client (will fail on database operations)
    tda = TaskDependencyAgent(agent_id="task_dependency_agent", supervisor_id="supervisor")

class AgentRequest(BaseModel):
    request_id: str
    agent_name: str
    intent: str
    input: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None

@app.get("/")
def root():
    return {"message": "Task Dependency Agent Service is running"}

@app.get("/health")
def health_check():
    return {"status": "ok", "agent": tda._id}

@app.post("/task", response_model=Dict[str, Any])
def handle_task(req: AgentRequest):
    return tda.handle_supervisor_request(req.dict())

# if __name__ == "__main__":
#     uvicorn.run("main_api:app", host="0.0.0.0", port=9001, reload=True)
