from agents.workers.worker_tda import TaskDependencyAgent


def build_agent(tmp_path):
    return TaskDependencyAgent(
        agent_id="task_dependency_agent",
        supervisor_id="supervisor",
        ltm_file=str(tmp_path / "tda_ltm.json"),
    )


def test_handle_supervisor_request_success(tmp_path):
    agent = build_agent(tmp_path)
    request = {
        "request_id": "req-001",
        "agent_name": "task_dependency_agent",
        "intent": "task.resolve_dependencies",
        "input": {
            "tasks": [
                {"id": "A", "depends_on": []},
                {"id": "B", "depends_on": ["A"]},
                {"id": "C", "depends_on": ["B"]},
            ]
        },
        "context": {"user_id": "demo"},
    }

    response = agent.handle_supervisor_request(request)

    assert response["status"] == "success"
    assert response["output"]["result"]["execution_order"] == ["A", "B", "C"]
    assert response["error"] is None


def test_handle_supervisor_request_invalid_agent(tmp_path):
    agent = build_agent(tmp_path)
    request = {
        "request_id": "req-002",
        "agent_name": "unknown_agent",
        "intent": "task.resolve_dependencies",
        "input": {"tasks": []},
        "context": {},
    }

    response = agent.handle_supervisor_request(request)

    assert response["status"] == "error"
    assert response["error"]["type"] == "invalid_agent"
