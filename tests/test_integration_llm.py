# tests/test_integration_llm.py
"""
Integration test demonstrating LLM-based dependency inference workflow.
This test shows how the TDA uses OpenRouter to infer dependencies from task descriptions.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from agents.worker_tda import TaskDependencyAgent


class TestLLMIntegration:
    """Integration tests for LLM-based dependency inference workflow"""
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_end_to_end_llm_inference_workflow(self, mock_openrouter_class):
        """
        Test complete workflow: tasks without dependencies -> LLM inference -> dependency resolution
        
        This test validates Requirements 4.1, 4.2, 4.4, 4.5
        """
        # Setup mock OpenRouter client
        mock_client = MagicMock()
        mock_openrouter_class.return_value = mock_client
        
        # Mock LLM response that infers logical dependencies
        # Task flow: Setup -> Build -> Test -> Deploy
        mock_client.infer_dependencies.return_value = {
            "task-2": ["task-1"],  # Build depends on Setup
            "task-3": ["task-2"],  # Test depends on Build
            "task-4": ["task-3"]   # Deploy depends on Test
        }
        
        # Create TDA instance
        tda = TaskDependencyAgent("tda-1", "supervisor-1")
        
        # Input: Tasks without dependencies (as they would come from Knowledge Builder)
        task_data = {
            "tasks": [
                {
                    "id": "task-1",
                    "name": "Setup Environment",
                    "description": "Initialize the project and install dependencies"
                },
                {
                    "id": "task-2",
                    "name": "Build Application",
                    "description": "Compile and build the application code"
                },
                {
                    "id": "task-3",
                    "name": "Run Tests",
                    "description": "Execute unit and integration tests"
                },
                {
                    "id": "task-4",
                    "name": "Deploy to Production",
                    "description": "Deploy the tested application to production servers"
                }
            ]
        }
        
        # Process tasks - should trigger LLM inference
        result = tda.process_task(task_data)
        
        # Verify LLM was called with correct task data
        mock_client.infer_dependencies.assert_called_once()
        call_args = mock_client.infer_dependencies.call_args[0][0]
        assert len(call_args) == 4
        assert all("id" in task and "name" in task and "description" in task for task in call_args)
        
        # Verify result contains expected structure
        assert "dependencies" in result
        assert "execution_order" in result
        
        # Verify execution order respects inferred dependencies
        execution_order = result["execution_order"]
        assert len(execution_order) == 4
        
        # Setup should come before Build
        assert execution_order.index("task-1") < execution_order.index("task-2")
        # Build should come before Test
        assert execution_order.index("task-2") < execution_order.index("task-3")
        # Test should come before Deploy
        assert execution_order.index("task-3") < execution_order.index("task-4")
        
        # Verify dependencies contains inferred dependencies
        assert result["dependencies"]["task-1"] == []
        assert result["dependencies"]["task-2"] == ["task-1"]
        assert result["dependencies"]["task-3"] == ["task-2"]
        assert result["dependencies"]["task-4"] == ["task-3"]
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_llm_inference_with_complex_dependencies(self, mock_openrouter_class):
        """
        Test LLM inference with complex dependency graph (multiple dependencies per task)
        """
        # Setup mock OpenRouter client
        mock_client = MagicMock()
        mock_openrouter_class.return_value = mock_client
        
        # Mock LLM response with complex dependencies
        # Task-4 depends on both Task-2 and Task-3
        mock_client.infer_dependencies.return_value = {
            "task-2": ["task-1"],
            "task-3": ["task-1"],
            "task-4": ["task-2", "task-3"]
        }
        
        # Create TDA instance
        tda = TaskDependencyAgent("tda-1", "supervisor-1")
        
        # Input tasks
        task_data = {
            "tasks": [
                {"id": "task-1", "name": "Init", "description": "Initialize"},
                {"id": "task-2", "name": "Build Frontend", "description": "Build UI"},
                {"id": "task-3", "name": "Build Backend", "description": "Build API"},
                {"id": "task-4", "name": "Integration", "description": "Integrate frontend and backend"}
            ]
        }
        
        # Process tasks
        result = tda.process_task(task_data)
        
        # Verify execution order
        execution_order = result["execution_order"]
        
        # Task-1 should come first
        assert execution_order[0] == "task-1"
        
        # Task-4 should come after both Task-2 and Task-3
        task_4_index = execution_order.index("task-4")
        task_2_index = execution_order.index("task-2")
        task_3_index = execution_order.index("task-3")
        assert task_4_index > task_2_index
        assert task_4_index > task_3_index
        
        # Verify dependencies
        assert result["dependencies"]["task-2"] == ["task-1"]
        assert result["dependencies"]["task-3"] == ["task-1"]
        assert result["dependencies"]["task-4"] == ["task-2", "task-3"]
    
    @patch('agents.worker_tda.OpenRouterClient')
    def test_llm_inference_with_no_dependencies(self, mock_openrouter_class):
        """
        Test LLM inference when tasks have no dependencies
        """
        # Setup mock OpenRouter client
        mock_client = MagicMock()
        mock_openrouter_class.return_value = mock_client
        
        # Mock LLM response with no dependencies
        mock_client.infer_dependencies.return_value = {}
        
        # Create TDA instance
        tda = TaskDependencyAgent("tda-1", "supervisor-1")
        
        # Input tasks
        task_data = {
            "tasks": [
                {"id": "task-1", "name": "A", "description": "Task A"},
                {"id": "task-2", "name": "B", "description": "Task B"},
                {"id": "task-3", "name": "C", "description": "Task C"}
            ]
        }
        
        # Process tasks
        result = tda.process_task(task_data)
        
        # Verify all tasks have no dependencies
        assert result["dependencies"]["task-1"] == []
        assert result["dependencies"]["task-2"] == []
        assert result["dependencies"]["task-3"] == []
        
        # All tasks can be executed in any order (all have in-degree 0)
        assert len(result["execution_order"]) == 3
