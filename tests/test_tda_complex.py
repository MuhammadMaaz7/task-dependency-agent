from agents.workers.worker_tda import TaskDependencyAgent


def build_agent(tmp_path):
    return TaskDependencyAgent(
        agent_id="task_dependency_agent",
        supervisor_id="supervisor",
        ltm_file=str(tmp_path / "tda_ltm.json"),
    )


def test_cycle_detection_returns_blocked_and_cycles(tmp_path):
    agent = build_agent(tmp_path)
    request = {
        "request_id": "req-cycle",
        "agent_name": "task_dependency_agent",
        "intent": "task.resolve_dependencies",
        "input": {
            "tasks": [
                {"id": "1", "depends_on": ["3"]},
                {"id": "2", "depends_on": ["1"]},
                {"id": "3", "depends_on": ["2"]},
            ]
        },
        "context": {},
    }

    response = agent.handle_supervisor_request(request)

    assert response["status"] == "success"
    result = response["output"]["result"]
    assert set(result["blocked_tasks"]) == {"1", "2", "3"}
    assert result["cycles_detected"]
