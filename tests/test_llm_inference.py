# tests/test_llm_inference.py
import pytest
from unittest.mock import Mock, MagicMock, patch
from agents.worker_tda import TaskDependencyAgent
from agents.openrouter_client import OpenRouterClient


class TestLLMDependencyInference:
    """Unit tests for LLM-based dependency inference in TDA"""
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_infer_dependencies_with_llm_success(self, mock_openrouter_class):
        """Test successful LLM-based dependency inference"""
        # Setup mock OpenRouter client
        mock_client = MagicMock()
        mock_openrouter_class.return_value = mock_client
        
        # Mock LLM response
        mock_client.infer_dependencies.return_value = {
            "task-2": ["task-1"],
            "task-3": ["task-1", "task-2"]
        }
        
        # Create TDA instance
        tda = TaskDependencyAgent("tda-1", "supervisor-1")
        
        # Test tasks
        tasks = [
            {"id": "task-1", "name": "Setup", "description": "Initialize project"},
            {"id": "task-2", "name": "Build", "description": "Build the project"},
            {"id": "task-3", "name": "Deploy", "description": "Deploy to production"}
        ]
        
        # Call inference method
        dag = tda._infer_dependencies_with_llm(tasks)
        
        # Verify results
        assert dag["task-1"] == []
        assert dag["task-2"] == ["task-1"]
        assert dag["task-3"] == ["task-1", "task-2"]
        
        # Verify OpenRouter client was called correctly
        mock_client.infer_dependencies.assert_called_once()
        call_args = mock_client.infer_dependencies.call_args[0][0]
        assert len(call_args) == 3
        assert call_args[0]["id"] == "task-1"
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_infer_dependencies_with_llm_no_client(self, mock_openrouter_class):
        """Test that inference fails gracefully when OpenRouter client is not initialized"""
        # Setup mock to raise ValueError during initialization
        mock_openrouter_class.side_effect = ValueError("API key not found")
        
        # Create TDA instance (should handle initialization error)
        tda = TaskDependencyAgent("tda-1", "supervisor-1")
        
        # Verify client is None
        assert tda.openrouter_client is None
        
        # Test tasks
        tasks = [
            {"id": "task-1", "name": "Setup", "description": "Initialize project"}
        ]
        
        # Should raise RuntimeError when trying to infer
        with pytest.raises(RuntimeError, match="OpenRouter client not initialized"):
            tda._infer_dependencies_with_llm(tasks)
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_process_task_with_llm_inference(self, mock_openrouter_class):
        """Test that process_task uses LLM inference and returns dependencies and execution order"""
        import tempfile
        
        # Setup mock OpenRouter client
        mock_client = MagicMock()
        mock_openrouter_class.return_value = mock_client
        
        # Mock LLM response
        mock_client.infer_dependencies.return_value = {
            "task-2": ["task-1"]
        }
        
        # Create TDA instance with unique LTM file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            ltm_file = f.name
        
        tda = TaskDependencyAgent("tda-1", "supervisor-1", ltm_file=ltm_file)
        
        # Test tasks
        task_data = {
            "tasks": [
                {"id": "task-1", "name": "Setup", "description": "Initialize"},
                {"id": "task-2", "name": "Build", "description": "Build project"}
            ]
        }
        
        # Process tasks
        result = tda.process_task(task_data)
        
        # Verify LLM was called
        mock_client.infer_dependencies.assert_called_once()
        
        # Verify result structure
        assert "dependencies" in result
        assert "execution_order" in result
        
        # Verify dependencies
        assert result["dependencies"]["task-1"] == []
        assert result["dependencies"]["task-2"] == ["task-1"]
        
        # Verify execution order
        assert result["execution_order"] == ["task-1", "task-2"]
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_process_task_always_uses_llm(self, mock_openrouter_class):
        """Test that process_task always uses LLM inference"""
        import tempfile
        
        # Setup mock OpenRouter client
        mock_client = MagicMock()
        mock_openrouter_class.return_value = mock_client
        
        # Mock LLM response
        mock_client.infer_dependencies.return_value = {
            "task-2": ["task-1"]
        }
        
        # Create TDA instance with unique LTM file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            ltm_file = f.name
        
        tda = TaskDependencyAgent("tda-1", "supervisor-1", ltm_file=ltm_file)
        
        # Test tasks
        task_data = {
            "tasks": [
                {"id": "task-1", "name": "Setup", "description": "Initialize"},
                {"id": "task-2", "name": "Build", "description": "Build project"}
            ]
        }
        
        # Process tasks
        result = tda.process_task(task_data)
        
        # Verify LLM was called
        mock_client.infer_dependencies.assert_called_once()
        
        # Verify result structure
        assert "dependencies" in result
        assert "execution_order" in result
        assert result["execution_order"] == ["task-1", "task-2"]
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_infer_dependencies_handles_llm_error(self, mock_openrouter_class):
        """Test that inference handles LLM API errors gracefully"""
        # Setup mock OpenRouter client
        mock_client = MagicMock()
        mock_openrouter_class.return_value = mock_client
        
        # Mock LLM error
        mock_client.infer_dependencies.side_effect = RuntimeError("API request failed")
        
        # Create TDA instance
        tda = TaskDependencyAgent("tda-1", "supervisor-1")
        
        # Test tasks
        tasks = [
            {"id": "task-1", "name": "Setup", "description": "Initialize project"}
        ]
        
        # Should raise RuntimeError with appropriate message
        with pytest.raises(RuntimeError, match="Failed to infer dependencies"):
            tda._infer_dependencies_with_llm(tasks)
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_infer_dependencies_with_missing_fields(self, mock_openrouter_class):
        """Test that inference handles tasks with missing name/description fields"""
        # Setup mock OpenRouter client
        mock_client = MagicMock()
        mock_openrouter_class.return_value = mock_client
        
        # Mock LLM response
        mock_client.infer_dependencies.return_value = {}
        
        # Create TDA instance
        tda = TaskDependencyAgent("tda-1", "supervisor-1")
        
        # Test tasks with missing fields
        tasks = [
            {"id": "task-1"},  # Missing name and description
            {"id": "task-2", "name": "Build"}  # Missing description
        ]
        
        # Call inference method
        dag = tda._infer_dependencies_with_llm(tasks)
        
        # Verify it handles missing fields gracefully
        assert dag["task-1"] == []
        assert dag["task-2"] == []
        
        # Verify OpenRouter was called with default values
        call_args = mock_client.infer_dependencies.call_args[0][0]
        assert call_args[0]["name"] == "Unnamed"
        assert call_args[0]["description"] == "No description"
