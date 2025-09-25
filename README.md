# HyDE Lambda Service

This Lambda service extracts the HyDE (Hypothetical Document Embeddings) functionality from the main logical search system. It performs query analysis and enrichment using LLM providers.

## Overview

HyDE analyzes search queries to:
- Extract location information and alternative names
- Identify skills and generate descriptions
- Extract organization details
- Determine sector information
- Generate database query details

## Structure

```
hyde/
├── lambda_handler.py          # Main Lambda entry point
├── hyde_logic.py             # Core HyDE reasoning logic
├── llm_helper.py             # LLM provider management
├── model_config.py           # Model configurations
├── auth_utils.py             # Authentication utilities
├── db.py                     # Database connections (Redis, MongoDB)
├── config.py                 # Configuration settings
├── utils.py                  # Utility functions
├── logging_config.py         # Logging setup
├── prompts/                  # Prompt templates
│   ├── logicalHyde.py
│   ├── descriptionForLocationNew.py
│   └── descriptionForKeyword.py
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables
└── test_lambda.py           # Test script
```

## Input Format

```json
{
  "query": "string",
  "flags": {
    "hyde_provider": "groq_llama",
    "description_provider": "groq_llama",
    "alternative_skills": false,
    "hyde_analysis_flags": {},
    "additional_context": {}
  },
  "headers": {
    "Authorization": "Bearer <jwt_token>",
    "X-API-Key": "<admin_api_key>"
  },
  "user_id": "string"
}
```

## Output Format

```json
{
  "statusCode": 200,
  "body": {
    "query_breakdown": {...},
    "response": {
      "regionBasedQuery": {...},
      "locationDetails": {...},
      "organisationDetails": {...},
      "sectorDetails": {...},
      "skillDetails": {...},
      "dbQueryDetails": {...}
    },
    "processing_time": 2.5,
    "hyde_analysis_time": 2.1,
    "success": true,
    "timestamp": "2024-09-22T18:30:00.000Z"
  }
}
```

## Dependencies

- **LLM Providers**: Groq, OpenAI, Gemini, DeepSeek (via LiteLLM)
- **Caching**: Redis for location/skill data
- **Configuration**: Environment variables for API keys and settings

## Testing

Run the test script:
```bash
python test_lambda.py
```

## Deployment

This Lambda is designed to be part of a 3-Lambda architecture:
1. **HyDE Service** (this Lambda) - Query analysis and enrichment
2. **Fetch & Rank Service** - Search execution and ranking
3. **Reasoning Service** - Optional additional reasoning

## Environment Variables

Required environment variables:
- `OPENAI_API_KEY`
- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`
- `REDIS_URL`
- `MONGODB_URI`
- `ADMIN_API_KEY`
- Other configuration as defined in config.py# CI/CD Test - Thu Sep 25 18:17:55 IST 2025
