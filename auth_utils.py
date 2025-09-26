# /Users/kushthakker/personal/brace/finalBackend/auth_utils.py

from quart import request, jsonify
from bson import ObjectId
from api_client import get_user_document, SearchServiceError
from config import ADMIN_API_KEY
from logging_config import setup_logger
from quart_jwt_extended import verify_jwt_in_request, get_jwt_identity

logger = setup_logger(__name__)


async def authenticate_request(return_data=False, require_user_id=True):
    """
    Authenticate the request using JWT or Admin API Key (dual authentication system).
    
    Args:
        return_data (bool): Whether to return JSON data to avoid double-reading request body
        require_user_id (bool): Whether to require user_id (default True)
        
    Returns:
        - If return_data=False: Tuple(bool, str, response, status_code): (is_admin, user_id, error_response, status_code)
        - If return_data=True: Tuple(bool, str, response, status_code, data): (is_admin, user_id, error_response, status_code, request_data)
    """
    # Check for Admin API Key in headers first
    admin_api_key = request.headers.get("X-API-Key")
    if admin_api_key:
        if admin_api_key != ADMIN_API_KEY:
            error_response = jsonify(message="Invalid Admin API Key.")
            if return_data:
                return False, None, error_response, 401, None
            return False, None, error_response, 401

        # If user_id is not required (system-level endpoints), skip user validation
        if not require_user_id:
            if return_data:
                data = await request.get_json()
                return True, None, None, None, data
            return True, None, None, None

        # Get user_id from request body for admin authentication
        data = await request.get_json()
        user_id = data.get("user_id")
        if not user_id:
            error_response = jsonify(message="Missing 'user_id' in request body.")
            if return_data:
                return False, None, error_response, 400, None
            return False, None, error_response, 400
        
        # Validate if the user_id exists in the database
        try:
            user_doc = get_user_document(user_id)
        except SearchServiceError as exc:
            logger.error("User lookup via API failed: %s", exc)
            error_response = jsonify(message="Upstream user lookup failed")
            if return_data:
                return False, None, error_response, 502, None
            return False, None, error_response, 502

        if not user_doc:
            error_response = jsonify(message="Invalid 'user_id' provided.")
            if return_data:
                return False, None, error_response, 404, None
            return False, None, error_response, 404
        
        # Success case for admin API key
        if return_data:
            return True, user_id, None, None, data
        return True, user_id, None, None

    # Fallback to JWT authentication
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.error("Missing or invalid Authorization header format")
            error_response = jsonify(message="Missing or invalid Authorization header. Provide either X-API-Key or Bearer token.")
            if return_data:
                return False, None, error_response, 401, None
            return False, None, error_response, 401

        # Verify the JWT token
        await verify_jwt_in_request()
        identity = get_jwt_identity()
        logger.info(f"Raw identity from token: {identity}")

        # Handle the case where identity might be a string representation of ObjectId
        if isinstance(identity, str):
            try:
                # Verify if it's a valid ObjectId
                user_id = str(ObjectId(identity))
                
                # If user_id is not required, we still return the user_id from JWT but mark as non-admin
                if not require_user_id:
                    if return_data:
                        data = await request.get_json()
                        return False, user_id, None, None, data
                    return False, user_id, None, None
                
                # Success case for JWT
                if return_data:
                    data = await request.get_json()
                    return False, user_id, None, None, data
                return False, user_id, None, None
            except Exception as e:
                logger.error(f"Invalid ObjectId format: {str(e)}")
                error_response = jsonify(message="Invalid user ID format")
                if return_data:
                    return False, None, error_response, 401, None
                return False, None, error_response, 401

        error_response = jsonify(message="Invalid JWT Token format")
        if return_data:
            return False, None, error_response, 401, None
        return False, None, error_response, 401

    except Exception as e:
        logger.error(f"JWT Authentication failed: {str(e)}")
        error_response = jsonify(message=f"Authentication failed: {str(e)}")
        if return_data:
            return False, None, error_response, 401, None
        return False, None, error_response, 401
