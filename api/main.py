from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict, Optional
from agents.worker_tda import TaskDependencyAgent

app = FastAPI(title="Task Dependency Agent Service")

tda = TaskDependencyAgent(agent_id="task_dependency_agent", supervisor_id="supervisor")

class AgentRequest(BaseModel):
    request_id: str
    agent_name: str
    intent: str
    input: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None

@app.get("/health")
def health_check():
    return {"status": "ok", "agent": tda._id}

@app.post("/task", response_model=Dict[str, Any])
def handle_task(req: AgentRequest):
    return tda.handle_supervisor_request(req.dict())

# if __name__ == "__main__":
#     uvicorn.run("main_api:app", host="0.0.0.0", port=9001, reload=True)
