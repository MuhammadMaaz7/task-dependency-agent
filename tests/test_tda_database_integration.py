# tests/test_tda_database_integration.py
"""
Tests for TDA database integration functionality.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from agents.worker_tda import TaskDependencyAgent
from agents.database_client import DatabaseClient
from datetime import datetime


class TestTDADatabaseIntegration:
    """Tests for TDA database operations"""
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_retrieve_tasks_from_database(self, mock_openrouter_class):
        """Test retrieving tasks from database"""
        # Setup mocks
        mock_openrouter = MagicMock()
        mock_openrouter_class.return_value = mock_openrouter
        
        mock_db_client = MagicMock(spec=DatabaseClient)
        mock_db_client.get_all_tasks.return_value = [
            {
                "id": "task-1",
                "name": "Setup",
                "description": "Initialize project",
                "deadline": datetime(2024, 12, 31),
                "status": "pending",
                "depends_on": []
            },
            {
                "id": "task-2",
                "name": "Build",
                "description": "Build application",
                "deadline": datetime(2024, 12, 31),
                "status": "pending",
                "depends_on": []
            }
        ]
        
        # Create TDA with database client
        tda = TaskDependencyAgent("tda-1", "supervisor-1", db_client=mock_db_client)
        
        # Retrieve tasks
        tasks = tda.retrieve_tasks_from_database()
        
        # Verify
        assert len(tasks) == 2
        assert tasks[0]["id"] == "task-1"
        assert tasks[1]["id"] == "task-2"
        mock_db_client.get_all_tasks.assert_called_once()
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_retrieve_tasks_without_db_client(self, mock_openrouter_class):
        """Test that retrieving tasks fails without database client"""
        mock_openrouter = MagicMock()
        mock_openrouter_class.return_value = mock_openrouter
        
        # Create TDA without database client
        tda = TaskDependencyAgent("tda-1", "supervisor-1")
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Database client not initialized"):
            tda.retrieve_tasks_from_database()
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_update_tasks_in_database(self, mock_openrouter_class):
        """Test updating tasks in database with dependencies and execution order"""
        # Setup mocks
        mock_openrouter = MagicMock()
        mock_openrouter_class.return_value = mock_openrouter
        
        mock_db_client = MagicMock(spec=DatabaseClient)
        mock_db_client.update_tasks_batch.return_value = True
        
        # Create TDA with database client
        tda = TaskDependencyAgent("tda-1", "supervisor-1", db_client=mock_db_client)
        
        # Test data
        dependencies = {
            "task-1": [],
            "task-2": ["task-1"],
            "task-3": ["task-2"]
        }
        execution_order = ["task-1", "task-2", "task-3"]
        
        # Update tasks
        result = tda.update_tasks_in_database(dependencies, execution_order)
        
        # Verify
        assert result is True
        mock_db_client.update_tasks_batch.assert_called_once()
        
        # Verify update payload structure
        call_args = mock_db_client.update_tasks_batch.call_args[0][0]
        assert len(call_args) == 3
        assert call_args[0]["id"] == "task-1"
        assert call_args[0]["depends_on"] == []
        assert call_args[0]["execution_order"] == 1
        assert call_args[0]["status"] == "ready"
        
        assert call_args[1]["id"] == "task-2"
        assert call_args[1]["depends_on"] == ["task-1"]
        assert call_args[1]["execution_order"] == 2
        
        assert call_args[2]["id"] == "task-3"
        assert call_args[2]["depends_on"] == ["task-2"]
        assert call_args[2]["execution_order"] == 3
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_update_tasks_without_db_client(self, mock_openrouter_class):
        """Test that updating tasks fails without database client"""
        mock_openrouter = MagicMock()
        mock_openrouter_class.return_value = mock_openrouter
        
        # Create TDA without database client
        tda = TaskDependencyAgent("tda-1", "supervisor-1")
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Database client not initialized"):
            tda.update_tasks_in_database({}, [])
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_process_task_with_database_complete_workflow(self, mock_openrouter_class):
        """Test complete workflow: retrieve -> infer -> update"""
        # Setup mocks
        mock_openrouter = MagicMock()
        mock_openrouter_class.return_value = mock_openrouter
        
        # Mock LLM response
        mock_openrouter.infer_dependencies.return_value = {
            "task-2": ["task-1"],
            "task-3": ["task-2"]
        }
        
        # Mock database client
        mock_db_client = MagicMock(spec=DatabaseClient)
        mock_db_client.get_all_tasks.return_value = [
            {
                "id": "task-1",
                "name": "Setup",
                "description": "Initialize project",
                "deadline": datetime(2024, 12, 31),
                "status": "pending",
                "depends_on": []
            },
            {
                "id": "task-2",
                "name": "Build",
                "description": "Build application",
                "deadline": datetime(2024, 12, 31),
                "status": "pending",
                "depends_on": []
            },
            {
                "id": "task-3",
                "name": "Deploy",
                "description": "Deploy to production",
                "deadline": datetime(2024, 12, 31),
                "status": "pending",
                "depends_on": []
            }
        ]
        mock_db_client.update_tasks_batch.return_value = True
        
        # Create TDA with database client and unique LTM file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            ltm_file = f.name
        
        tda = TaskDependencyAgent("tda-1", "supervisor-1", ltm_file=ltm_file, db_client=mock_db_client)
        
        # Execute complete workflow
        result = tda.process_task_with_database()
        
        # Verify database operations were called
        mock_db_client.get_all_tasks.assert_called_once()
        mock_db_client.update_tasks_batch.assert_called_once()
        
        # Verify LLM was called
        mock_openrouter.infer_dependencies.assert_called_once()
        
        # Verify result structure
        assert "dependencies" in result
        assert "execution_order" in result
        
        # Verify dependencies
        assert result["dependencies"]["task-1"] == []
        assert result["dependencies"]["task-2"] == ["task-1"]
        assert result["dependencies"]["task-3"] == ["task-2"]
        
        # Verify execution order
        assert result["execution_order"] == ["task-1", "task-2", "task-3"]
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_process_task_with_database_no_tasks(self, mock_openrouter_class):
        """Test workflow when database has no tasks"""
        # Setup mocks
        mock_openrouter = MagicMock()
        mock_openrouter_class.return_value = mock_openrouter
        
        mock_db_client = MagicMock(spec=DatabaseClient)
        mock_db_client.get_all_tasks.return_value = []
        
        # Create TDA with database client
        tda = TaskDependencyAgent("tda-1", "supervisor-1", db_client=mock_db_client)
        
        # Execute workflow
        result = tda.process_task_with_database()
        
        # Verify
        assert result["dependencies"] == {}
        assert result["execution_order"] == []
        assert "message" in result
        
        # Database update should not be called
        mock_db_client.update_tasks_batch.assert_not_called()
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_database_retrieval_error_handling(self, mock_openrouter_class):
        """Test error handling when database retrieval fails"""
        # Setup mocks
        mock_openrouter = MagicMock()
        mock_openrouter_class.return_value = mock_openrouter
        
        mock_db_client = MagicMock(spec=DatabaseClient)
        mock_db_client.get_all_tasks.side_effect = Exception("Database connection failed")
        
        # Create TDA with database client
        tda = TaskDependencyAgent("tda-1", "supervisor-1", db_client=mock_db_client)
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Failed to retrieve tasks from database"):
            tda.retrieve_tasks_from_database()
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_database_update_error_handling(self, mock_openrouter_class):
        """Test error handling when database update fails"""
        # Setup mocks
        mock_openrouter = MagicMock()
        mock_openrouter_class.return_value = mock_openrouter
        
        mock_db_client = MagicMock(spec=DatabaseClient)
        mock_db_client.update_tasks_batch.side_effect = Exception("Database update failed")
        
        # Create TDA with database client
        tda = TaskDependencyAgent("tda-1", "supervisor-1", db_client=mock_db_client)
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Failed to update tasks in database"):
            tda.update_tasks_in_database({}, [])
