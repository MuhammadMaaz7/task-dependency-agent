import requests
import json

BASE_URL = "https://task-dependency-agent.vercel.app"


def pretty(obj):
    return json.dumps(obj, indent=2)


def test_health_check():
    url = f"{BASE_URL}/health"
    response = requests.get(url)

    print("\n=== HEALTH CHECK RESPONSE ===")
    print(pretty(response.json()))

    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "ok"
    assert data["agent"] == "task_dependency_agent"


def test_resolve_dependencies_success():
    url = f"{BASE_URL}/task"

    payload = {
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
        "context": {"user_id": "demo"}
    }

    print("\n=== REQUEST: RESOLVE DEPENDENCIES SUCCESS ===")
    print(pretty(payload))

    response = requests.post(url, json=payload)

    print("\n=== RESPONSE ===")
    print(pretty(response.json()))

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "success"
    assert data["error"] is None
    assert data["output"]["result"]["execution_order"] == ["A", "B", "C"]


def test_invalid_agent_error():
    url = f"{BASE_URL}/task"

    payload = {
        "request_id": "req-002",
        "agent_name": "wrong_agent",
        "intent": "task.resolve_dependencies",
        "input": {"tasks": []},
        "context": {}
    }

    print("\n=== REQUEST: INVALID AGENT ===")
    print(pretty(payload))

    response = requests.post(url, json=payload)

    print("\n=== RESPONSE ===")
    print(pretty(response.json()))

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "error"
    assert data["error"]["type"] == "invalid_agent"


def test_cycle_detection():
    url = f"{BASE_URL}/task"

    payload = {
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
        "context": {}
    }

    print("\n=== REQUEST: CYCLE DETECTION ===")
    print(pretty(payload))

    response = requests.post(url, json=payload)

    print("\n=== RESPONSE ===")
    print(pretty(response.json()))

    assert response.status_code == 200

    data = response.json()
    result = data["output"]["result"]

    assert data["status"] == "success"
    assert set(result["blocked_tasks"]) == {"1", "2", "3"}
    assert len(result["cycles_detected"]) > 0
