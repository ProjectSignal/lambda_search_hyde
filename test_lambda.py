#!/usr/bin/env python3
"""
Test script for HyDE Lambda function
"""

import json
import asyncio
import sys
import os
import uuid
import argparse
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lambda_handler import lambda_handler, SearchStatus

def create_test_search_document():
    """Create a test search document in NEW status for HyDE processing"""
    
    try:
        from db import searchOutputCollection
        
        search_id = str(uuid.uuid4())
        user_id = "6797bf304791caa516f6da9e"  # Valid ObjectId for testing
        query = "Find machine learning experts with Python experience in San Francisco"
        
        now = datetime.utcnow()
        test_doc = {
            "_id": search_id,
            "userId": user_id,
            "query": query,
            "flags": {
                "hyde_provider": "gemini",
                "description_provider": "gemini",
                "reasoning_model": "gemini",
                "alternative_skills": True,
                "reasoning": True,
                "fallback": False,
                "hyde_analysis_flags": {},
                "additional_context": {}
            },
            "status": SearchStatus.NEW,
            "createdAt": now,
            "updatedAt": now,
            "events": [
                {
                    "stage": "INIT",
                    "message": "Search initiated (test document)",
                    "timestamp": now
                }
            ],
            "metrics": {}
        }
        
        # Insert test document
        result = searchOutputCollection.insert_one(test_doc)
        if result.inserted_id:
            print(f"✅ Created test search document: {search_id}")
            return search_id, user_id, query, test_doc["flags"]
        else:
            print("❌ Failed to create test search document")
            return None, None, None, None
            
    except Exception as e:
        print(f"❌ Error creating test search document: {str(e)}")
        return None, None, None, None

def create_step_functions_event(search_id, user_id, query, flags):
    """Create Step Functions event format for HyDE Lambda"""
    return {
        "searchId": search_id,
        "userId": user_id,
        "query": query,
        "flags": flags
    }

async def test_hyde_lambda(keep_document=False):
    """Test the HyDE Lambda with Step Functions event format"""

    print("Testing HyDE Lambda...")
    print("=" * 50)

    # Step 1: Create test search document
    print("1. Creating test search document...")
    search_id, user_id, query, flags = create_test_search_document()
    
    if not search_id:
        print("❌ Cannot proceed without test search document")
        return None

    # Step 2: Create Step Functions event
    test_event = create_step_functions_event(search_id, user_id, query, flags)
    
    print("\n2. Step Functions Test Event:")
    print(json.dumps(test_event, indent=2))

    # Step 3: Mock context
    context = {}

    try:
        print("\n3. Running HyDE Lambda...")
        
        # Run the lambda handler
        result = await lambda_handler(test_event, context)

        print("\n=== Lambda Response ===")
        print(f"Status Code: {result['statusCode']}")

        # Parse and pretty print the body
        if isinstance(result['body'], str):
            body = json.loads(result['body'])
        else:
            body = result['body']
            
        print("\nResponse Body:")
        print(json.dumps(body, indent=2))

        # Step 4: Validate search document was updated
        if result['statusCode'] == 200:
            print("\n4. Validating search document update...")
            validate_search_document_update(search_id)

        return result

    except Exception as e:
        print(f"\n❌ Error running lambda: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def validate_search_document_update(search_id):
    """Validate that the search document was properly updated with HyDE analysis"""
    
    try:
        from db import searchOutputCollection
        
        doc = searchOutputCollection.find_one({"_id": search_id})
        if not doc:
            print("❌ Search document not found")
            return False
            
        print(f"   Status: {doc.get('status')}")
        
        if doc.get('status') == SearchStatus.HYDE_COMPLETE:
            print("   ✅ Status updated to HYDE_COMPLETE")
            
            hyde_analysis = doc.get('hydeAnalysis')
            if hyde_analysis:
                print("   ✅ HyDE analysis present")
                query_breakdown = hyde_analysis.get('queryBreakdown')
                response = hyde_analysis.get('response')
                processing_time = hyde_analysis.get('processingTime')
                
                print(f"   Processing time: {processing_time:.2f}s")
                
                if query_breakdown:
                    print(f"   Query breakdown keys: {list(query_breakdown.keys())}")
                if response:
                    print(f"   Response keys: {list(response.keys())}")
                    
                return True
            else:
                print("   ❌ HyDE analysis missing")
                return False
        else:
            print(f"   ❌ Unexpected status: {doc.get('status')}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error validating document: {str(e)}")
        return False

def cleanup_test_document(search_id):
    """Clean up test document after test"""
    try:
        from db import searchOutputCollection
        searchOutputCollection.delete_one({"_id": search_id})
        print(f"🧹 Cleaned up test document: {search_id}")
    except Exception as e:
        print(f"⚠️  Could not clean up test document: {str(e)}")

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test HyDE Lambda function')
    parser.add_argument('--keep', action='store_true',
                       help='Keep the test document after completion (for pipeline testing)')
    args = parser.parse_args()

    print("🚀 Starting HyDE Lambda Test")
    if args.keep:
        print("📌 Keep mode: Test document will NOT be deleted after completion")

    # Run the test
    result = asyncio.run(test_hyde_lambda(keep_document=args.keep))

    print("\n" + "=" * 50)

    if result and result['statusCode'] == 200:
        print("🎉 HyDE Lambda test completed successfully!")

        # Extract searchId from result for cleanup or reporting
        try:
            if isinstance(result['body'], str):
                body = json.loads(result['body'])
            else:
                body = result['body']
            search_id = body.get('searchId')

            if search_id:
                if args.keep:
                    print(f"✅ Test document preserved with searchId: {search_id}")
                    print(f"💡 Use this searchId for fetch testing: --search-id {search_id}")
                else:
                    cleanup_test_document(search_id)
        except:
            pass

        sys.exit(0)
    else:
        print("💥 HyDE Lambda test failed!")
        sys.exit(1)