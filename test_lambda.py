#!/usr/bin/env python3
"""
Test script for HyDE Lambda function
"""

import json
import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lambda_handler import lambda_handler

async def test_hyde_lambda():
    """Test the HyDE Lambda with sample data"""

    print("Testing HyDE Lambda...")

    # Test event mimicking API Gateway input
    test_event = {
        "body": {
            "query": "Find machine learning experts with Python experience in San Francisco",
            "flags": {
                "hyde_provider": "groq_llama",
                "description_provider": "groq_llama",
                "alternative_skills": False,
                "hyde_analysis_flags": {},
                "additional_context": {}
            }
        },
        "headers": {
            "Authorization": "Bearer test_token",
            "X-API-Key": "test_api_key"
        }
    }

    # Mock context
    context = {}

    try:
        # Run the lambda handler
        result = await lambda_handler(test_event, context)

        print("\n=== Lambda Response ===")
        print(f"Status Code: {result['statusCode']}")

        # Parse and pretty print the body
        body = json.loads(result['body'])
        print("\nResponse Body:")
        print(json.dumps(body, indent=2))

        return result

    except Exception as e:
        print(f"\nError running lambda: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # Run the test
    result = asyncio.run(test_hyde_lambda())

    if result and result['statusCode'] == 200:
        print("\n✅ Lambda test completed successfully!")
    else:
        print("\n❌ Lambda test failed!")
        sys.exit(1)