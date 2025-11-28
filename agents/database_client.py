# agents/database_client.py
import os
import time
from typing import List, Dict, Any, Optional
from pymongo import MongoClient
from pymongo.errors import (
    ConnectionFailure,
    OperationFailure,
    ServerSelectionTimeoutError,
    PyMongoError
)
from datetime import datetime, timezone


class DatabaseClient:
    """
    Database client for MongoDB Atlas with support for:
    - Querying all tasks
    - Atomic transaction support for batch updates
    - Retry logic with exponential backoff
    
    Requirements: 3.1, 3.2, 3.5, 6.2, 6.5
    """
    
    def __init__(
        self,
        uri: Optional[str] = None,
        database_name: Optional[str] = None,
        collection_name: Optional[str] = None,
        max_retries: int = 3,
        initial_backoff: float = 1.0
    ):
        """
        Initialize the database client.
        
        Args:
            uri: MongoDB connection URI (defaults to MONGODB_URI env var)
            database_name: Database name (defaults to MONGODB_DATABASE env var)
            collection_name: Collection name (defaults to MONGODB_COLLECTION env var)
            max_retries: Maximum number of retry attempts (default: 3)
            initial_backoff: Initial backoff time in seconds (default: 1.0)
        """
        self.uri = uri or os.getenv("MONGODB_URI")
        self.database_name = database_name or os.getenv("MONGODB_DATABASE", "task_dependency_db")
        self.collection_name = collection_name or os.getenv("MONGODB_COLLECTION", "tasks")
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        
        if not self.uri:
            raise ValueError("MongoDB URI must be provided via constructor or MONGODB_URI environment variable")
        
        # Initialize MongoDB client
        self.client = MongoClient(
            self.uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000
        )
        self.db = self.client[self.database_name]
        self.collection = self.db[self.collection_name]
    
    def _retry_with_backoff(self, operation, operation_name: str):
        """
        Execute an operation with exponential backoff retry logic.
        
        Requirements: 3.5 - Retry up to three times with exponential backoff
        
        Args:
            operation: Callable to execute
            operation_name: Name of the operation for logging
            
        Returns:
            Result of the operation
            
        Raises:
            Exception: If all retry attempts fail
        """
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return operation()
            except (ConnectionFailure, ServerSelectionTimeoutError, OperationFailure) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    backoff_time = self.initial_backoff * (2 ** attempt)
                    print(f"[DatabaseClient] {operation_name} failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                    print(f"[DatabaseClient] Retrying in {backoff_time} seconds...")
                    time.sleep(backoff_time)
                else:
                    print(f"[DatabaseClient] {operation_name} failed after {self.max_retries} attempts: {e}")
        
        raise last_exception
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """
        Retrieve all tasks from the database.
        
        Requirements:
        - 3.1: Query database for all task records
        - 3.2: Return all tasks with required fields
        - 3.5: Retry up to three times with exponential backoff
        
        Returns:
            List of task dictionaries with fields: id, name, description, 
            deadline, status, depends_on
            
        Raises:
            Exception: If database query fails after all retries
        """
        def query_operation():
            # Query all tasks from the collection
            tasks = list(self.collection.find({}))
            
            # Convert MongoDB documents to standardized format
            result = []
            for task in tasks:
                # Map database fields to standard fields
                standardized_task = {
                    "id": task.get("task_id") or task.get("id") or str(task.get("_id", "")),
                    "name": task.get("task_name") or task.get("name", "Unnamed Task"),
                    "description": task.get("task_description") or task.get("description", "No description"),
                    "deadline": task.get("task_deadline") or task.get("deadline", ""),
                    "status": task.get("task_status") or task.get("status", "pending"),
                    "depends_on": task.get("depends_on") or []
                }
                
                # Ensure depends_on is a list
                if standardized_task["depends_on"] is None:
                    standardized_task["depends_on"] = []
                elif not isinstance(standardized_task["depends_on"], list):
                    standardized_task["depends_on"] = []
                
                result.append(standardized_task)
            
            return result
        
        return self._retry_with_backoff(query_operation, "get_all_tasks")
    
    def update_tasks_batch(self, task_updates: List[Dict[str, Any]]) -> bool:
        """
        Update multiple tasks atomically in a single transaction.
        
        Requirements:
        - 6.2: Write depends_on array and execution order to each task record
        - 6.5: Commit transaction atomically to ensure consistency
        
        Args:
            task_updates: List of task update dictionaries. Each should contain:
                - id: Task identifier
                - depends_on: Array of task IDs (optional)
                - execution_order: Integer position (optional)
                - status: Task status (optional)
                - cycle_info: Cycle information (optional)
                
        Returns:
            True if all updates succeeded, False otherwise
            
        Raises:
            Exception: If transaction fails after all retries
        """
        def update_operation():
            # Start a session for transaction support
            with self.client.start_session() as session:
                with session.start_transaction():
                    for task_update in task_updates:
                        task_id = task_update.get("id")
                        if not task_id:
                            raise ValueError("Task update missing 'id' field")
                        
                        # Build update document
                        update_doc = {}
                        
                        if "depends_on" in task_update:
                            update_doc["depends_on"] = task_update["depends_on"]
                        
                        if "execution_order" in task_update:
                            update_doc["execution_order"] = task_update["execution_order"]
                        
                        if "status" in task_update:
                            # Update both status and task_status for compatibility
                            update_doc["status"] = task_update["status"]
                            update_doc["task_status"] = task_update["status"]
                        
                        if "cycle_info" in task_update:
                            update_doc["cycle_info"] = task_update["cycle_info"]
                        
                        # Add updated timestamp
                        update_doc["updated_at"] = datetime.now(timezone.utc)
                        
                        # Update the task - try both task_id and id fields
                        result = self.collection.update_one(
                            {"$or": [{"task_id": task_id}, {"id": task_id}]},
                            {"$set": update_doc},
                            session=session
                        )
                        
                        if result.matched_count == 0:
                            raise ValueError(f"Task with id '{task_id}' not found in database")
                    
                    # Transaction commits automatically when exiting the context
                    return True
        
        return self._retry_with_backoff(update_operation, "update_tasks_batch")
    
    def validate_task_data(self, tasks: List[Dict[str, Any]]) -> Optional[str]:
        """
        Validate that task data contains all required fields.
        
        Requirements: 3.3 - Validate returned data structure contains all required fields
        
        Args:
            tasks: List of task dictionaries to validate
            
        Returns:
            None if valid, error message string if invalid
        """
        if not isinstance(tasks, list):
            return "Tasks must be a list"
        
        required_fields = ["id", "name", "description", "deadline", "status", "depends_on"]
        
        for idx, task in enumerate(tasks):
            if not isinstance(task, dict):
                return f"Task at index {idx} must be a dictionary"
            
            for field in required_fields:
                if field not in task:
                    task_id = task.get("id", f"index {idx}")
                    return f"Task {task_id} missing required field: {field}"
            
            # Validate depends_on is a list
            if not isinstance(task.get("depends_on"), list):
                return f"Task {task['id']} depends_on must be a list"
        
        return None
    
    def close(self):
        """Close the database connection."""
        if self.client:
            self.client.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
