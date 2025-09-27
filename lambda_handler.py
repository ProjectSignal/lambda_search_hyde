import json
import asyncio
import os
import time
import traceback
from datetime import datetime, timezone
from dotenv import load_dotenv

from hyde_logic import HydeReasoning
from logging_config import setup_logger
from api_client import (
    create_search_document,
    get_search_document,
    update_search_document,
    SearchServiceError,
)

# Load environment variables (for local testing)
load_dotenv()

logger = setup_logger(__name__)

def get_utc_now():
    """Returns current UTC datetime in ISO format"""
    return datetime.now(timezone.utc).isoformat()



def _normalize_user_id(raw_user_id):
    if isinstance(raw_user_id, dict) and "$oid" in raw_user_id:
        raw_user_id = raw_user_id["$oid"]
    if raw_user_id is None:
        return None
    user_id_str = str(raw_user_id).strip()
    return user_id_str or None

class SearchStatus:
    """Search execution status tracking"""
    NEW = "NEW"
    HYDE_COMPLETE = "HYDE_COMPLETE"
    SEARCH_COMPLETE = "SEARCH_COMPLETE"
    RANK_AND_REASONING_COMPLETE = "RANK_AND_REASONING_COMPLETE"
    ERROR = "ERROR"

async def _run(event):
    """
    Main async execution logic for HyDE analysis.
    Uses searchOutput collection for state management.
    """
    logger.info("=== HyDE Lambda Handler ===")
    start_time = time.time()

    try:
        # Parse the input event - Step Functions passes direct objects
        search_id = event.get('searchId')
        user_id = _normalize_user_id(event.get('userId') or event.get('user_id'))
        query = event.get('query')
        flags = event.get('flags', {})

        # Validate required fields
        if not all([search_id, user_id, query]):
            error_msg = "Missing required fields: searchId, userId, and query"
            logger.warning(error_msg)
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": error_msg,
                    "success": False
                })
            }

        logger.info(f"Processing HyDE for searchId: {search_id}, query: {query}")

        # Get or create search document
        search_doc = get_search_document(search_id, user_id=user_id)
        if not search_doc:
            # Create initial search document (migration from searchInitializer)
            logger.info(f"Creating initial search document for searchId: {search_id}")
            now = datetime.now(timezone.utc)
            search_doc = {
                "_id": search_id,
                "userId": user_id,
                "query": query,
                "flags": flags,
                "status": SearchStatus.NEW,
                "createdAt": now.isoformat(),
                "updatedAt": now.isoformat(),
                "events": [
                    {
                        "stage": "INIT",
                        "message": "Search initiated",
                        "timestamp": now.isoformat()
                    }
                ],
                "metrics": {}
            }

            try:
                create_search_document(search_doc)
                logger.info(f"Created initial search document: {search_id}")
            except SearchServiceError as api_error:
                error_msg = f"Failed to create search document: {str(api_error)}"
                logger.error(error_msg)
                return {
                    "statusCode": 500,
                    "body": json.dumps({
                        "error": error_msg,
                        "success": False
                    })
                }

        # Get providers from flags or use defaults
        hyde_provider = flags.get('hyde_provider', 'groq_llama')
        description_provider = flags.get('description_provider', 'groq_llama')
        alternative_skills = flags.get('alternative_skills', False)
        hyde_analysis_flags = flags.get('hyde_analysis_flags', {})
        additional_context = flags.get('additional_context', {})

        logger.info(f"Using providers - hyde: {hyde_provider}, description: {description_provider}")

        # Initialize HyDE processor
        hyde = HydeReasoning(hyde_provider, description_provider)

        # Perform HyDE analysis (Note: analysis_flags and additional_context not yet implemented in HydeReasoning)
        hyde_start_time = time.time()
        hyde_result = await hyde.analyze_query(
            query, 
            alternative_skills=alternative_skills
        )
        
        # TODO: Extend HydeReasoning.analyze_query to accept analysis_flags and additional_context
        # For now, we store the flags in the result for future use
        if hyde_analysis_flags or additional_context:
            logger.info("hyde_analysis_flags and additional_context received but not yet implemented")
            hyde_result["flags_received"] = {
                "hyde_analysis_flags": hyde_analysis_flags,
                "additional_context": additional_context
            }
        hyde_time = time.time() - hyde_start_time

        logger.info(f"HyDE Analysis completed in {hyde_time:.2f} seconds")

        # Update searchOutput collection with HyDE results (idempotent)
        now = datetime.now(timezone.utc)
        try:
            logger.info(f"DEBUG: Calling update_search_document with search_id={search_id}, user_id={user_id}")
            update_search_document(
                search_id,
                user_id=user_id,
                set_fields={
                    "hydeAnalysis": {
                        "queryBreakdown": hyde_result.get("query_breakdown", {}),
                        "response": hyde_result.get("response", {}),
                        "processingTime": hyde_time
                    },
                    "status": SearchStatus.HYDE_COMPLETE,
                    "metrics.hydeMs": hyde_time * 1000,
                    "updatedAt": now.isoformat()
                },
                append_events=[
                    {
                        "id": f"HYDE:{search_id}",
                        "stage": "HYDE",
                        "message": "HyDE analysis completed",
                        "timestamp": now.isoformat()
                    }
                ],
                expected_statuses=[SearchStatus.NEW, SearchStatus.HYDE_COMPLETE],
            )
        except SearchServiceError as update_error:
            # Check if document already in HYDE_COMPLETE status (idempotent retry)
            existing_doc = get_search_document(search_id, user_id=user_id)
            if existing_doc and existing_doc.get("status") == SearchStatus.HYDE_COMPLETE:
                logger.info(f"Search document {search_id} already processed (idempotent retry)")
                total_time = time.time() - start_time
                return {
                    "statusCode": 200,
                    "body": json.dumps({
                        "searchId": search_id,
                        "success": True,
                        "processing_time": total_time,
                        "timestamp": get_utc_now(),
                        "note": "Already processed (idempotent)"
                    })
                }

            error_msg = f"Failed to update search document for searchId: {search_id} - {update_error}"
            logger.error(error_msg)
            return {
                "statusCode": 409,
                "body": json.dumps({
                    "error": error_msg,
                    "success": False
                })
            }

        logger.info(f"Updated search document {search_id} with HyDE results")

        # Calculate total processing time
        total_time = time.time() - start_time

        # Return lightweight response
        response = {
            "statusCode": 200,
            "body": json.dumps({
                "searchId": search_id,
                "success": True,
                "processing_time": total_time,
                "timestamp": get_utc_now()
            })
        }

        # Small delay to let any background HTTP clients cleanup naturally
        await asyncio.sleep(0.1)
        return response

    except Exception as e:
        logger.error(f"Error in HyDE Lambda: {str(e)}", exc_info=True)
        
        # Update search document with error state if we have searchId
        if 'search_id' in locals() and 'user_id' in locals() and user_id:
            try:
                now = datetime.now(timezone.utc)
                update_search_document(
                    search_id,
                    user_id=user_id,
                    set_fields={
                        "status": SearchStatus.ERROR,
                        "error": {
                            "stage": "HYDE",
                            "message": str(e),
                            "stackTrace": traceback.format_exc(),
                            "occurredAt": now.isoformat()
                        },
                        "updatedAt": now.isoformat()
                    },
                    append_events=[
                        {
                            "stage": "HYDE",
                            "message": f"Error: {str(e)}",
                            "timestamp": now.isoformat()
                        }
                    ],
                )
            except SearchServiceError as db_error:
                logger.error(f"Failed to update error state: {db_error}")

        total_time = time.time() - start_time

        # Small delay to let any background HTTP clients cleanup naturally
        await asyncio.sleep(0.1)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": f"Internal server error: {str(e)}",
                "processing_time": total_time,
                "success": False,
                "timestamp": get_utc_now()
            })
        }

def lambda_handler(event, context):
    """
    AWS Lambda handler for HyDE analysis service - synchronous wrapper for async execution.
    Uses searchOutput collection for state management.

    Input:
    {
        "searchId": "uuid-string",
        "userId": "user-id-string",
        "query": "search query string",
        "flags": {
            "hyde_provider": "groq_llama",
            "description_provider": "groq_llama",
            "alternative_skills": false,
            "hyde_analysis_flags": {...},
            "additional_context": {...}
        }
    }

    Output:
    {
        "statusCode": 200,
        "body": {
            "searchId": "uuid-string",
            "success": true,
            "processing_time": float
        }
    }
    """
    return asyncio.run(_run(event))

# For local testing
if __name__ == "__main__":
    import asyncio
    import uuid

    # Test event with new format
    test_event = {
        "searchId": str(uuid.uuid4()),
        "userId": "test_user_123", 
        "query": "Find experts in machine learning with Python experience",
        "flags": {
            "hyde_provider": "groq_llama",
            "description_provider": "groq_llama",
            "alternative_skills": False,
            "hyde_analysis_flags": {},
            "additional_context": {}
        }
    }

    # Create initial search document for testing
    try:
        now = datetime.now(timezone.utc)
        create_search_document({
            "_id": test_event["searchId"],
            "userId": test_event["userId"],
            "query": test_event["query"],
            "flags": test_event["flags"],
            "status": SearchStatus.NEW,
            "createdAt": now.isoformat(),
            "updatedAt": now.isoformat(),
            "events": [],
            "metrics": {}
        })
        print(f"Created test search document: {test_event['searchId']}")
    except SearchServiceError as e:
        print(f"Warning: Could not create test document: {e}")

    # Run the handler
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
