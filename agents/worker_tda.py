# agents/workers/worker_tda.py
from agents.worker_base import AbstractWorkerAgent
from agents.openrouter_client import OpenRouterClient
from agents.database_client import DatabaseClient
from collections import deque, defaultdict
from dotenv import load_dotenv
import json
import logging
import os
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TaskDependencyAgent(AbstractWorkerAgent):
    """Worker that resolves task dependencies and exposes the supervisor handshake."""

    SUPPORTED_INTENTS = {"task.resolve_dependencies"}

    def __init__(self, agent_id: str, supervisor_id: str, ltm_file: str = "LTM/tda_ltm.json", db_client: Optional[DatabaseClient] = None):
        super().__init__(agent_id, supervisor_id)
        self.ltm_file = ltm_file
        self._ltm_store = self._load_ltm()
        
        # Initialize OpenRouter client for LLM-based dependency inference
        # This will raise ValueError if API key is not configured
        try:
            self.openrouter_client = OpenRouterClient()
            logger.info(f"[{agent_id}] OpenRouter client initialized successfully")
        except ValueError as e:
            # Log error but don't fail initialization - will fail on actual inference
            logger.warning(f"[{agent_id}] OpenRouter client initialization failed: {e}")
            self.openrouter_client = None
        
        # Initialize database client (optional, can be injected for testing)
        self.db_client = db_client
        if db_client:
            logger.info(f"[{agent_id}] Database client initialized")

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
        Accepts: {"tasks": [ {"id": <id>, "name": <name>, "description": <desc>}, ... ] }
        Uses LLM to infer dependencies and returns resolved dependencies with execution order.
        Returns: dict with dependencies and execution_order
        """
        tasks = task_data.get("tasks", [])
        
        if not tasks:
            return {
                "dependencies": {},
                "execution_order": []
            }
        
        # Use LLM to infer dependencies
        dependencies = self._infer_dependencies_with_llm(tasks)
        
        # Calculate execution order using simple topological sort
        execution_order = self._calculate_execution_order(dependencies)
        
        result = {
            "dependencies": dependencies,
            "execution_order": execution_order
        }
        
        return result
    
    def _infer_dependencies_with_llm(self, tasks: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Use OpenRouter LLM to infer task dependencies from descriptions.
        
        Requirements: 4.1, 4.2, 4.4, 4.5
        
        Args:
            tasks: List of task dictionaries with id, name, description fields
            
        Returns:
            Dictionary mapping task IDs to lists of dependency task IDs
            
        Raises:
            RuntimeError: If OpenRouter client is not initialized or inference fails
        """
        if self.openrouter_client is None:
            raise RuntimeError(
                "OpenRouter client not initialized. Check OPENROUTER_API_KEY environment variable."
            )
        
        # Prepare task data for LLM (only need id, name, description)
        task_data = [
            {
                "id": t["id"],
                "name": t.get("name", "Unnamed"),
                "description": t.get("description", "No description")
            }
            for t in tasks
        ]
        
        # Call OpenRouter API to infer dependencies
        try:
            logger.info(f"[{self._id}] Calling OpenRouter API to infer dependencies for {len(task_data)} tasks")
            dependencies = self.openrouter_client.infer_dependencies(task_data)
            logger.info(f"[{self._id}] Successfully inferred dependencies for {len(dependencies)} tasks")
        except RuntimeError as e:
            # Check if it's an authentication error
            if "Authentication failed" in str(e):
                logger.error(f"[{self._id}] Authentication error with OpenRouter API: {e}")
            elif "Rate limit exceeded" in str(e):
                logger.error(f"[{self._id}] Rate limit exceeded for OpenRouter API: {e}")
            else:
                logger.error(f"[{self._id}] OpenRouter API request failed: {e}")
            raise RuntimeError(f"Failed to infer dependencies: {str(e)}")
        except Exception as e:
            logger.error(f"[{self._id}] Unexpected error inferring dependencies with LLM: {e}", exc_info=True)
            raise RuntimeError(f"Failed to infer dependencies: {str(e)}")
        
        # Build complete dependency map (include tasks with no dependencies)
        complete_dependencies = {}
        for task in tasks:
            task_id = task["id"]
            complete_dependencies[task_id] = dependencies.get(task_id, [])
        
        return complete_dependencies
    
    def _calculate_execution_order(self, dependencies: Dict[str, List[str]]) -> List[str]:
        """
        Calculate execution order using simple topological sort.
        
        Args:
            dependencies: Dictionary mapping task IDs to their dependency lists
            
        Returns:
            List of task IDs in execution order
        """
        # Calculate in-degree for each task
        in_degree = {task_id: 0 for task_id in dependencies}
        
        for task_id, deps in dependencies.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[task_id] += 1
        
        # Start with tasks that have no dependencies
        queue = deque([task_id for task_id, degree in in_degree.items() if degree == 0])
        execution_order = []
        
        while queue:
            current = queue.popleft()
            execution_order.append(current)
            
            # Reduce in-degree for tasks that depend on current task
            for task_id, deps in dependencies.items():
                if current in deps:
                    in_degree[task_id] -= 1
                    if in_degree[task_id] == 0 and task_id not in execution_order:
                        queue.append(task_id)
        
        return execution_order
    
    # ---------------- Database Operations ----------------
    def retrieve_tasks_from_database(self) -> List[Dict[str, Any]]:
        """
        Retrieve all tasks from the database.
        
        Requirements: 3.1, 3.2
        
        Returns:
            List of task dictionaries from database
            
        Raises:
            RuntimeError: If database client is not initialized or query fails
        """
        if self.db_client is None:
            raise RuntimeError("Database client not initialized")
        
        try:
            logger.info(f"[{self._id}] Retrieving tasks from database")
            tasks = self.db_client.get_all_tasks()
            logger.info(f"[{self._id}] Successfully retrieved {len(tasks)} tasks from database")
            return tasks
        except Exception as e:
            logger.error(f"[{self._id}] Database query failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to retrieve tasks from database: {str(e)}")
    
    def update_tasks_in_database(self, dependencies: Dict[str, List[str]], execution_order: List[str]) -> bool:
        """
        Update tasks in database with inferred dependencies and execution order.
        
        Requirements: 6.1, 6.2
        
        Args:
            dependencies: Dictionary mapping task IDs to dependency lists
            execution_order: List of task IDs in execution order
            
        Returns:
            True if update successful, False otherwise
            
        Raises:
            RuntimeError: If database client is not initialized or update fails
        """
        if self.db_client is None:
            raise RuntimeError("Database client not initialized")
        
        # Build update payloads for each task
        task_updates = []
        for idx, task_id in enumerate(execution_order):
            update = {
                "id": task_id,
                "depends_on": dependencies.get(task_id, []),
                "execution_order": idx + 1,  # 1-indexed
                "status": "ready"
            }
            task_updates.append(update)
        
        # Update database atomically
        try:
            logger.info(f"[{self._id}] Updating {len(task_updates)} tasks in database")
            result = self.db_client.update_tasks_batch(task_updates)
            logger.info(f"[{self._id}] Successfully updated {len(task_updates)} tasks in database")
            return result
        except Exception as e:
            logger.error(f"[{self._id}] Database update failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to update tasks in database: {str(e)}")
    
    def process_task_with_database(self) -> dict:
        """
        Complete workflow: retrieve tasks from DB, infer dependencies, update DB.
        
        Requirements: 3.1, 4.1, 4.2, 6.1, 6.2
        
        Returns:
            Dictionary with dependencies and execution_order
            
        Raises:
            RuntimeError: If any step fails
        """
        logger.info(f"[{self._id}] Starting complete workflow: retrieve -> infer -> update")
        
        try:
            # Step 1: Retrieve tasks from database
            tasks = self.retrieve_tasks_from_database()
            
            if not tasks:
                logger.warning(f"[{self._id}] No tasks found in database")
                return {
                    "dependencies": {},
                    "execution_order": [],
                    "message": "No tasks found in database"
                }
            
            # Step 2: Process tasks (infer dependencies and calculate execution order)
            logger.info(f"[{self._id}] Processing {len(tasks)} tasks")
            result = self.process_task({"tasks": tasks})
            
            # Step 3: Update database with results
            self.update_tasks_in_database(result["dependencies"], result["execution_order"])
            
            logger.info(f"[{self._id}] Workflow completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"[{self._id}] Workflow failed: {e}", exc_info=True)
            raise




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

        # Check if this is a database trigger (auto-trigger from supervisor)
        trigger = input_payload.get("trigger")
        if trigger == "database_update":
            # Use database workflow: retrieve tasks, infer dependencies, update database
            try:
                logger.info(f"[{self._id}] Database trigger received, processing tasks from MongoDB")
                result = self.process_task_with_database()
            except Exception as exc:
                logger.error(f"[{self._id}] Database workflow failed: {exc}", exc_info=True)
                return self._error_response(request_id, agent_name, "runtime_error", str(exc))
        else:
            # Manual trigger with tasks provided in input
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
