# Vercel Deployment Setup

## Required Environment Variables

Configure these in Vercel Dashboard → Settings → Environment Variables:

### OpenRouter (Required)
```
OPENROUTER_API_KEY=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
OPENROUTER_MODEL=openai/gpt-3.5-turbo
```

### MongoDB (Required)
```
MONGODB_URI=mongodb+srv://admin:se-b_is_the_best@main.tlnnynt.mongodb.net/?appName=Main
MONGODB_DATABASE=knowledge_builder
MONGODB_COLLECTION=task
```

## Deployment Steps

1. **Add Environment Variables in Vercel**
   - Go to https://vercel.com/dashboard
   - Select your project
   - Settings → Environment Variables
   - Add all 5 variables above

2. **Push to GitHub**
   ```bash
   git add .
   git commit -m "feat: Add LLM-based dependency inference"
   git push origin main
   ```

3. **Vercel Auto-Deploys**
   - Deployment happens automatically
   - Check deployment logs for any errors

4. **Test Deployment**
   ```bash
   curl https://task-dependency-agent.vercel.app/health
   ```

## Integration with Supervisor

### Request Format
```json
{
  "request_id": "req-001",
  "agent_name": "task_dependency_agent",
  "intent": "task.resolve_dependencies",
  "input": {
    "tasks": [
      {
        "id": "task-1",
        "name": "Task Name",
        "description": "Task description"
      }
    ]
  }
}
```

### Response Format
```json
{
  "status": "success",
  "output": {
    "result": {
      "dependencies": {"task-1": []},
      "execution_order": ["task-1"]
    }
  }
}
```

## Troubleshooting

- **500 Error**: Check Vercel logs, verify env vars
- **MongoDB Error**: Whitelist 0.0.0.0/0 in MongoDB Atlas
- **OpenRouter Error**: Verify API key is valid

Your deployment will be ready once env vars are configured! ✅
