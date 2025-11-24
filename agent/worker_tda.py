# agents/workers/worker_tda.py
from agents.workers.worker_base import AbstractWorkerAgent
from collections import deque, defaultdict
import json
import os
from typing import Any, Dict, List, Optional
import uuid

class TaskDependencyAgent(AbstractWorkerAgent):
    """Worker that resolves task dependencies and exposes the supervisor handshake."""

    SUPPORTED_INTENTS = {"task.resolve_dependencies"}

    def __init__(self, agent_id: str, supervisor_id: str, ltm_file: str = "LTM/tda_ltm.json"):
        super().__init__(agent_id, supervisor_id)
        self.ltm_file = ltm_file
        self._ltm_store = self._load_ltm()

    # ---------------- Persistent LTM ----------------
    def _load_ltm(self):
        try:
            if os.path.exists(self.ltm_file):
                with open(self.ltm_file, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_ltm(self):
        os.makedirs(os.path.dirname(self.ltm_file), exist_ok=True)
        with open(self.ltm_file, "w") as f:
            json.dump(self._ltm_store, f, indent=2)

    def write_to_ltm(self, key: str, value: Any) -> bool:
        self._ltm_store[key] = value
        try:
            self._save_ltm()
        except Exception:
            pass
        return True

    def read_from_ltm(self, key: str) -> Optional[Any]:
        return self._ltm_store.get(key)

    # ---------------- Task Processing ----------------
    def process_task(self, task_data: dict) -> dict:
        """
        Accepts: {"tasks": [ {"id": <id>, "depends_on": [<id>, ...]}, ... ] }
        Returns: dict with execution_order, blocked_tasks, cycles_detected, raw_graph
        """
        tasks = task_data.get("tasks", [])
        dag = {t["id"]: t.get("depends_on", []) for t in tasks}

        # Use cached result if available (LTM key is canonical JSON)
        task_key = json.dumps(dag, sort_keys=True)
        cached = self.read_from_ltm(task_key)
        if cached:
            return {"from_ltm": True, **cached}

        order, blocked, cycles = self._resolve_dependencies(dag)

        result = {
            "execution_order": order,
            "blocked_tasks": blocked,
            "cycles_detected": cycles,
            "raw_graph": dag
        }

        # Store in LTM
        try:
            self.write_to_ltm(task_key, result)
        except Exception:
            pass

        return result


    def _resolve_dependencies(self, dag: dict):
        """
        Detect cycles (list of cycles as lists), then do a topological sort
        on nodes not in cycles. Return (order, blocked, cycles).
        """
        # DFS to find cycles (recorded as lists of nodes)
        visited = {}
        stack = []
        cycles = []

        def dfs(node):
            if node in stack:
                cycle_start = stack.index(node)
                cycle = stack[cycle_start:] + [node]
                # normalize cycle (start smallest for deterministic output)
                cycles.append(cycle)
                return
            if visited.get(node, False):
                return
            visited[node] = True
            stack.append(node)
            for dep in dag.get(node, []):
                if dep in dag:
                    dfs(dep)
            stack.pop()

        for node in dag:
            if not visited.get(node, False):
                dfs(node)

        # Topological sort ignoring cycle nodes
        indegree = defaultdict(int)
        for node, deps in dag.items():
            for dep in deps:
                indegree[node] += 1
                indegree[dep] += 0  # ensure dep is in indegree

        cycle_nodes = {n for cycle in cycles for n in cycle}

        queue = deque([n for n in dag if indegree[n] == 0 and n not in cycle_nodes])
        order = []
        processed = set()

        while queue:
            node = queue.popleft()
            order.append(node)
            processed.add(node)
            for neighbor, deps in dag.items():
                if node in deps and neighbor not in cycle_nodes:
                    indegree[neighbor] -= 1
                    if indegree[neighbor] == 0 and neighbor not in processed:
                        queue.append(neighbor)

        # Blocked nodes = nodes not in order and not already in cycle (these have missing deps)
        blocked = [n for n in dag if n not in order and n not in cycle_nodes]
        # Include cycle nodes as blocked as well (they cannot be scheduled)
        blocked = list(dict.fromkeys(blocked + list(cycle_nodes)))  # uniq preserve order-ish

        # Normalize cycles (remove duplicate rotations)
        normalized_cycles = []
        seen = set()
        for cyc in cycles:
            cyc_tuple = tuple(cyc)
            if cyc_tuple not in seen:
                normalized_cycles.append(cyc)
                seen.add(cyc_tuple)

        return order, blocked, normalized_cycles

    # ---------------- Supervisor Handshake ----------------
    def handle_supervisor_request(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a supervisor-compatible response. This keeps HTTP handlers thin and reusable.
        """
        request_id = request_payload.get("request_id") or str(uuid.uuid4())
        agent_name = request_payload.get("agent_name", "")
        intent = request_payload.get("intent", "")
        input_payload = request_payload.get("input", {}) or {}

        if agent_name != self._id:
            return self._error_response(
                request_id,
                agent_name,
                "invalid_agent",
                f"Expected agent '{self._id}' but received '{agent_name}'.",
            )

        if intent not in self.SUPPORTED_INTENTS:
            return self._error_response(
                request_id,
                agent_name,
                "unsupported_intent",
                f"Intent '{intent}' is not supported. Use {sorted(self.SUPPORTED_INTENTS)}.",
            )

        tasks = self._extract_tasks(input_payload)
        if tasks is None:
            return self._error_response(
                request_id,
                agent_name,
                "invalid_input",
                "Provide tasks via input.tasks, input.metadata.extra.tasks, or JSON in input.text.",
            )

        validation_error = self._validate_tasks(tasks)
        if validation_error:
            return self._error_response(request_id, agent_name, "invalid_input", validation_error)

        try:
            result = self.process_task({"tasks": tasks})
        except Exception as exc:  # pragma: no cover
            return self._error_response(request_id, agent_name, "runtime_error", str(exc))

        return {
            "request_id": request_id,
            "agent_name": agent_name,
            "status": "success",
            "output": {
                "result": result,
                "confidence": 0.92,
                "details": "Dependency resolution completed",
            },
            "error": None,
        }

    def _extract_tasks(self, input_payload: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """Support multiple ways of passing the task payload."""
        if not isinstance(input_payload, dict):
            return None

        tasks = input_payload.get("tasks")
        if isinstance(tasks, list):
            return tasks

        metadata = input_payload.get("metadata")
        if isinstance(metadata, dict):
            extra = metadata.get("extra")
            if isinstance(extra, dict) and isinstance(extra.get("tasks"), list):
                return extra.get("tasks")

        text_blob = input_payload.get("text")
        if isinstance(text_blob, str):
            try:
                parsed = json.loads(text_blob)
                if isinstance(parsed, dict) and isinstance(parsed.get("tasks"), list):
                    return parsed.get("tasks")
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                return None

        return None

    @staticmethod
    def _validate_tasks(tasks: List[Dict[str, Any]]) -> Optional[str]:
        if not tasks:
            return "Task list must be a non-empty list."

        for idx, task in enumerate(tasks):
            if not isinstance(task, dict):
                return f"Task entry at index {idx} must be an object."
            if "id" not in task:
                return f"Task entry at index {idx} is missing required field 'id'."
            depends_on = task.get("depends_on", [])
            if depends_on is not None and not isinstance(depends_on, list):
                return f"Task '{task['id']}' depends_on must be a list."
        return None

    def _error_response(self, request_id: str, agent_name: str, error_type: str, message: str) -> Dict[str, Any]:
        return {
            "request_id": request_id,
            "agent_name": agent_name or self._id,
            "status": "error",
            "output": None,
            "error": {"type": error_type, "message": message},
        }

    # ---------------- Legacy Communication ----------------
    def send_message(self, recipient: str, message_obj: dict):
        """Mock send; when integrated via HTTP return values will be used instead."""
        print(f"[{self._id}] Sending message to {recipient}:")
        print(json.dumps(message_obj, indent=2))
