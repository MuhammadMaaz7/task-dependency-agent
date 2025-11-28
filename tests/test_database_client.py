# tests/test_database_client.py
import pytest
from unittest.mock import Mock, MagicMock, patch
from agents.database_client import DatabaseClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from datetime import datetime


class TestDatabaseClient:
    """Unit tests for DatabaseClient"""
    
    @patch('agents.database_client.MongoClient')
    def test_initialization_with_env_vars(self, mock_mongo_client):
        """Test DatabaseClient initialization with environment variables"""
        with patch.dict('os.environ', {
            'MONGODB_URI': 'mongodb+srv://test:test@cluster.mongodb.net/',
            'MONGODB_DATABASE': 'test_db',
            'MONGODB_COLLECTION': 'test_tasks'
        }):
            client = DatabaseClient()
            
            assert client.uri == 'mongodb+srv://test:test@cluster.mongodb.net/'
            assert client.database_name == 'test_db'
            assert client.collection_name == 'test_tasks'
            assert client.max_retries == 3
            assert client.initial_backoff == 1.0
    
    @patch('agents.database_client.MongoClient')
    def test_initialization_with_params(self, mock_mongo_client):
        """Test DatabaseClient initialization with constructor parameters"""
        client = DatabaseClient(
            uri='mongodb://localhost:27017',
            database_name='custom_db',
            collection_name='custom_tasks',
            max_retries=5,
            initial_backoff=2.0
        )
        
        assert client.uri == 'mongodb://localhost:27017'
        assert client.database_name == 'custom_db'
        assert client.collection_name == 'custom_tasks'
        assert client.max_retries == 5
        assert client.initial_backoff == 2.0
    
    def test_initialization_without_uri_raises_error(self):
        """Test that initialization without URI raises ValueError"""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="MongoDB URI must be provided"):
                DatabaseClient()
    
    @patch('agents.database_client.MongoClient')
    def test_get_all_tasks_success(self, mock_mongo_client):
        """Test successful retrieval of all tasks"""
        # Setup mock
        mock_collection = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
        
        # Mock task data
        mock_tasks = [
            {
                "_id": "507f1f77bcf86cd799439011",
                "id": "task-1",
                "name": "Task 1",
                "description": "Description 1",
                "deadline": datetime(2024, 12, 31),
                "status": "pending",
                "depends_on": []
            },
            {
                "_id": "507f1f77bcf86cd799439012",
                "id": "task-2",
                "name": "Task 2",
                "description": "Description 2",
                "deadline": datetime(2024, 12, 31),
                "status": "pending",
                "depends_on": ["task-1"]
            }
        ]
        mock_collection.find.return_value = mock_tasks
        
        client = DatabaseClient(uri='mongodb://localhost:27017')
        tasks = client.get_all_tasks()
        
        assert len(tasks) == 2
        assert tasks[0]["id"] == "task-1"
        assert tasks[1]["id"] == "task-2"
        assert "_id" not in tasks[0]
        assert "_id" not in tasks[1]
    
    @patch('agents.database_client.MongoClient')
    @patch('time.sleep')
    def test_get_all_tasks_retry_on_failure(self, mock_sleep, mock_mongo_client):
        """Test retry logic with exponential backoff on connection failure"""
        mock_collection = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
        
        # First two calls fail, third succeeds
        mock_collection.find.side_effect = [
            ConnectionFailure("Connection failed"),
            ConnectionFailure("Connection failed"),
            [{"id": "task-1", "name": "Task 1", "description": "Desc", 
              "deadline": datetime.now(), "status": "pending", "depends_on": []}]
        ]
        
        client = DatabaseClient(uri='mongodb://localhost:27017', initial_backoff=0.1)
        tasks = client.get_all_tasks()
        
        assert len(tasks) == 1
        assert mock_collection.find.call_count == 3
        assert mock_sleep.call_count == 2
    
    @patch('agents.database_client.MongoClient')
    def test_update_tasks_batch_success(self, mock_mongo_client):
        """Test successful batch update of tasks"""
        mock_collection = MagicMock()
        mock_session = MagicMock()
        mock_client_instance = mock_mongo_client.return_value
        mock_client_instance.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_client_instance.start_session.return_value.__enter__.return_value = mock_session
        
        # Mock successful update
        mock_update_result = MagicMock()
        mock_update_result.matched_count = 1
        mock_collection.update_one.return_value = mock_update_result
        
        client = DatabaseClient(uri='mongodb://localhost:27017')
        
        task_updates = [
            {
                "id": "task-1",
                "depends_on": ["task-0"],
                "execution_order": 1,
                "status": "ready"
            },
            {
                "id": "task-2",
                "depends_on": ["task-1"],
                "execution_order": 2,
                "status": "ready"
            }
        ]
        
        result = client.update_tasks_batch(task_updates)
        
        assert result is True
        assert mock_collection.update_one.call_count == 2
    
    @patch('agents.database_client.MongoClient')
    def test_update_tasks_batch_missing_id_raises_error(self, mock_mongo_client):
        """Test that update without task id raises ValueError"""
        mock_collection = MagicMock()
        mock_session = MagicMock()
        mock_client_instance = mock_mongo_client.return_value
        mock_client_instance.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_client_instance.start_session.return_value.__enter__.return_value = mock_session
        
        client = DatabaseClient(uri='mongodb://localhost:27017')
        
        task_updates = [
            {
                "depends_on": ["task-0"],
                "execution_order": 1
            }
        ]
        
        with pytest.raises(ValueError, match="Task update missing 'id' field"):
            client.update_tasks_batch(task_updates)
    
    @patch('agents.database_client.MongoClient')
    def test_validate_task_data_success(self, mock_mongo_client):
        """Test validation of valid task data"""
        client = DatabaseClient(uri='mongodb://localhost:27017')
        
        tasks = [
            {
                "id": "task-1",
                "name": "Task 1",
                "description": "Description",
                "deadline": datetime.now(),
                "status": "pending",
                "depends_on": []
            }
        ]
        
        error = client.validate_task_data(tasks)
        assert error is None
    
    @patch('agents.database_client.MongoClient')
    def test_validate_task_data_missing_field(self, mock_mongo_client):
        """Test validation fails for missing required field"""
        client = DatabaseClient(uri='mongodb://localhost:27017')
        
        tasks = [
            {
                "id": "task-1",
                "name": "Task 1",
                "description": "Description",
                "status": "pending",
                "depends_on": []
                # Missing deadline
            }
        ]
        
        error = client.validate_task_data(tasks)
        assert error is not None
        assert "deadline" in error
    
    @patch('agents.database_client.MongoClient')
    def test_validate_task_data_invalid_depends_on(self, mock_mongo_client):
        """Test validation fails for invalid depends_on type"""
        client = DatabaseClient(uri='mongodb://localhost:27017')
        
        tasks = [
            {
                "id": "task-1",
                "name": "Task 1",
                "description": "Description",
                "deadline": datetime.now(),
                "status": "pending",
                "depends_on": "not-a-list"  # Should be a list
            }
        ]
        
        error = client.validate_task_data(tasks)
        assert error is not None
        assert "depends_on must be a list" in error
    
    @patch('agents.database_client.MongoClient')
    def test_context_manager(self, mock_mongo_client):
        """Test DatabaseClient as context manager"""
        mock_client_instance = mock_mongo_client.return_value
        
        with DatabaseClient(uri='mongodb://localhost:27017') as client:
            assert client is not None
        
        mock_client_instance.close.assert_called_once()
