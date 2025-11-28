"""OpenRouter API client for LLM-based dependency inference."""

import json
import os
from typing import Dict, List, Optional
import urllib.request
import urllib.error


class OpenRouterClient:
    """Client for interacting with OpenRouter API to infer task dependencies."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, timeout: int = 30):
        """
        Initialize OpenRouter client.
        
        Args:
            api_key: OpenRouter API key. If None, reads from OPENROUTER_API_KEY env var.
            model: Model to use for inference. If None, reads from OPENROUTER_MODEL env var.
            timeout: Request timeout in seconds.
        
        Raises:
            ValueError: If API key is not provided and not found in environment.
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.model = model or os.getenv("OPENROUTER_MODEL", "openai/gpt-4")
        self.timeout = timeout
        self.base_url = "https://openrouter.ai/api/v1"
    
    def infer_dependencies(self, tasks: List[Dict]) -> Dict[str, List[str]]:
        """
        Infer task dependencies using LLM analysis.
        
        Args:
            tasks: List of task dictionaries with 'id', 'name', and 'description' fields.
        
        Returns:
            Dictionary mapping task IDs to lists of dependency task IDs.
            Format: {"task-id": ["dependency-id-1", "dependency-id-2"], ...}
        
        Raises:
            ValueError: If tasks list is empty or malformed.
            RuntimeError: If API request fails.
        """
        if not tasks:
            raise ValueError("Tasks list cannot be empty")
        
        # Validate task structure
        for task in tasks:
            if not isinstance(task, dict):
                raise ValueError("Each task must be a dictionary")
            if "id" not in task:
                raise ValueError("Each task must have an 'id' field")
        
        # Construct prompt
        prompt = self._build_prompt(tasks)
        
        # Make API request
        try:
            response = self._make_request(prompt)
            dependencies = self._parse_response(response, tasks)
            return dependencies
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else ""
            if e.code == 401:
                raise RuntimeError(
                    f"Authentication failed. Check your OpenRouter API key. Error: {error_body}"
                )
            elif e.code == 429:
                raise RuntimeError(
                    f"Rate limit exceeded. Please retry later. Error: {error_body}"
                )
            else:
                raise RuntimeError(
                    f"OpenRouter API request failed with status {e.code}: {error_body}"
                )
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error connecting to OpenRouter API: {e.reason}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error during API request: {str(e)}")
    
    def _build_prompt(self, tasks: List[Dict]) -> str:
        """
        Build LLM prompt for dependency inference.
        
        Args:
            tasks: List of task dictionaries.
        
        Returns:
            Formatted prompt string with task information.
        """
        task_descriptions = []
        for task in tasks:
            task_id = task["id"]
            task_name = task.get("name", "Unnamed")
            task_desc = task.get("description", "No description")
            task_descriptions.append(f"- ID: {task_id}\n  Name: {task_name}\n  Description: {task_desc}")
        
        tasks_text = "\n\n".join(task_descriptions)
        
        prompt = f"""Analyze these tasks and identify which tasks depend on others. A task depends on another if it requires the other task's output or completion.

Tasks:
{tasks_text}

Return a JSON object with this exact structure:
{{
  "dependencies": {{
    "task-id": ["dependency-id-1", "dependency-id-2"],
    ...
  }}
}}

Only include task IDs that have dependencies. Only use task IDs from the provided list. If a task has no dependencies, omit it from the response."""
        
        return prompt
    
    def _make_request(self, prompt: str) -> Dict:
        """
        Make HTTP request to OpenRouter API.
        
        Args:
            prompt: User prompt for dependency analysis.
        
        Returns:
            Parsed JSON response from API.
        
        Raises:
            urllib.error.HTTPError: If HTTP request fails.
            RuntimeError: If response parsing fails.
        """
        url = f"{self.base_url}/chat/completions"
        
        system_message = (
            "You are a task dependency analyzer. Given a list of tasks with descriptions, "
            "identify which tasks depend on others. A task depends on another if it requires "
            "the other task's output or completion. Return results in strict JSON format. "
            "Only use task IDs from the provided list."
        )
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/tda-workflow",  # Optional but recommended
            "X-Title": "Task Dependency Agent"  # Optional but recommended
        }
        
        data = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(url, data=data, headers=headers, method='POST')
        
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            response_data = response.read().decode('utf-8')
            return json.loads(response_data)
    
    def _parse_response(self, response: Dict, tasks: List[Dict]) -> Dict[str, List[str]]:
        """
        Parse OpenRouter API response to extract dependencies.
        
        Args:
            response: Raw API response dictionary.
            tasks: Original task list for validation.
        
        Returns:
            Dictionary mapping task IDs to dependency lists.
        
        Raises:
            RuntimeError: If response format is invalid or cannot be parsed.
        """
        try:
            # Extract content from response
            choices = response.get("choices", [])
            if not choices:
                raise RuntimeError("API response contains no choices")
            
            message = choices[0].get("message", {})
            content = message.get("content", "")
            
            if not content:
                raise RuntimeError("API response message content is empty")
            
            # Parse JSON from content
            # Try to extract JSON if it's wrapped in markdown code blocks
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            parsed = json.loads(content)
            
            # Extract dependencies
            dependencies = parsed.get("dependencies", {})
            if not isinstance(dependencies, dict):
                raise RuntimeError("Dependencies field must be a dictionary")
            
            # Validate that all referenced task IDs exist
            valid_task_ids = {task["id"] for task in tasks}
            for task_id, deps in dependencies.items():
                if task_id not in valid_task_ids:
                    raise RuntimeError(f"Invalid task ID in dependencies: {task_id}")
                if not isinstance(deps, list):
                    raise RuntimeError(f"Dependencies for task {task_id} must be a list")
                for dep_id in deps:
                    if dep_id not in valid_task_ids:
                        raise RuntimeError(
                            f"Invalid dependency ID '{dep_id}' for task '{task_id}'"
                        )
            
            return dependencies
            
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse JSON from API response: {str(e)}")
        except KeyError as e:
            raise RuntimeError(f"Missing expected field in API response: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Error parsing API response: {str(e)}")
