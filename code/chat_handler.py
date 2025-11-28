from services.authencator_service import Authenticator    
from services.messenger_service import MessengerService
from services.cache_service import CacheService
from services.session_service import SessionService
from services.bedrock_service import BedrockService
import logging
import json
import boto3
import os

# Initialize services
auth = Authenticator()
mess = MessengerService()
cache = CacheService()
session_service = SessionService()
bedrock_service = BedrockService()

# Lambda client for invoking text2sql
lambda_client = boto3.client("lambda")
TEXT2SQL_LAMBDA_NAME = os.environ.get("TEXT2SQL_LAMBDA_NAME", "text2sql-handler")

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Main Lambda handler for chat messages.
    
    Flow:
    1. Verify webhook / handle callback (GET)
    2. Handle authentication (POST - unauthenticated users)
    3. For authenticated users:
       a. Check cache for similar question
       b. If cache hit: use cached metadata + bedrock to generate response
       c. If cache miss: invoke text2sql Lambda, get results, generate response
       d. Save turn to conversation_context
       e. Send response to user via Messenger
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")
        path = event.get("path", "/")
        
        # Handle GET requests (webhook verification, callback)
        if http_method == "GET":
            if "/callback" in path:
                return auth.handle_callback(event)
            else:
                return mess.handle_webhook_verification(event)
        
        # Handle POST requests
        elif http_method == "POST":
            # Step 1: Parse message first to get psid
            data = mess.parse_messenger_event(event)
            if not data.get("valid"):
                logger.error(f"Invalid messenger event: {data.get('error')}")
                return {"statusCode": 400, "body": "Invalid event"}
            
            messages = mess.extract_messages(data["data"])
            if not messages:
                logger.warning("No messages found")
                return {"statusCode": 200, "body": "No messages"}
            
            # Get first message
            msg_data = messages[0]
            psid = msg_data.get("psid")
            user_question = msg_data.get("text", "") or msg_data.get("payload", "")
            
            if not psid:
                logger.warning("Missing psid")
                return {"statusCode": 200, "body": "No valid message"}
            
            # Step 2: Check if user is authenticated
            session = session_service.get_session(psid)
            is_authenticated = session.get("is_authenticated", False) if session else False
            
            if not is_authenticated:
                # User not authenticated - delegate to auth handler
                logger.info(f"User {psid} not authenticated, delegating to auth handler")
                auth.handle_user_authorization_event(event)
                return {"statusCode": 200, "body": "Auth flow in progress"}
            
            # Step 3: User is authenticated - process chat message
            if not user_question:
                logger.warning(f"Missing question for authenticated user {psid}")
                return {"statusCode": 200, "body": "No valid message"}
            
            logger.info(f"Processing message for {psid}: '{user_question[:50]}...'")
            
            # Step 4: Check cache for similar question
            cache_hit = cache.search_cache(psid, user_question)
            
            # Step 5: Route based on cache hit/miss
            if cache_hit:
                # Cache HIT - use cached data to generate response
                logger.info(f"Cache HIT for {psid}")
                response_text = _handle_cache_hit(psid, user_question, cache_hit)
                
                # Send response to user
                mess.send_text_message(psid, response_text)
                
                # Cache hit - don't save metadata, just save turn without metadata
                session_service.add_message_to_history(
                    event=event,
                    assistant_msg=response_text,
                    metadata=None
                )
            else:
                # Cache MISS - invoke text2sql Lambda
                logger.info(f"Cache MISS for {psid}, invoking text2sql")
                response_text, metadata = _handle_text2sql(psid, user_question)
                
                # Send response to user
                mess.send_text_message(psid, response_text)
                
                # Cache miss - save turn with metadata for future cache lookups
                session_service.add_message_to_history(
                    event=event,
                    assistant_msg=response_text,
                    metadata=metadata
                )
            
            return {"statusCode": 200, "body": "OK"}
        
        else:
            return {"statusCode": 405, "body": "Method not allowed"}
            
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}", exc_info=True)
        return {"statusCode": 500, "body": "Internal Server Error"}


def _handle_cache_hit(psid: str, user_question: str, cache_hit: dict) -> str:
    """
    Handle cache hit - use cached metadata to generate response via Bedrock.
    
    Args:
        psid: User's PSID
        user_question: Current user question
        cache_hit: Cached turn data with metadata
        
    Returns:
        Response text from Bedrock
    """
    try:
        # Get cached metadata
        cached_metadata = cache_hit.get("metadata", {})
        sql_result = cached_metadata.get("sql_result", "")
        schema_context = cached_metadata.get("schema_context_text", "")
        
        # Get conversation context
        context = session_service.get_context_for_llm(psid, include_metadata=True)
        
        # Generate response using Bedrock
        response = bedrock_service.get_answer_from_sql_results(
            question=user_question,
            results=sql_result,
            schema=schema_context,
            context=context
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error handling cache hit: {e}")
        return "Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn."


def _handle_text2sql(psid: str, user_question: str) -> tuple:
    """
    Handle cache miss - invoke text2sql Lambda and generate response.
    
    Args:
        psid: User's PSID
        user_question: User's question
        
    Returns:
        Tuple of (response_text, metadata)
    """
    try:
        # Get conversation context for text2sql
        context = session_service.get_context_for_llm(psid)
        
        # Prepare payload for text2sql Lambda
        payload = {
            "psid": psid,
            "question": user_question,
            "context": context
        }
        
        # Invoke text2sql Lambda
        response = lambda_client.invoke(
            FunctionName=TEXT2SQL_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload)
        )
        
        # Parse response
        result = json.loads(response["Payload"].read().decode())
        logger.debug(f"Text2SQL response: {result}")
        
        if result.get("statusCode") != 200:
            logger.error(f"Text2SQL error: {result}")
            return "Xin lỗi, không thể truy vấn thông tin lịch hẹn lúc này.", {"error": True}
        
        # Parse body
        body = result.get("body", "{}")
        if isinstance(body, str):
            body = json.loads(body)
        
        # Extract fields from text2sql response
        sql_result = body.get("sql_result", [])
        schema_context = body.get("schema_context_text", "")
        
        # Calculate row_count from sql_result
        row_count = len(sql_result) if isinstance(sql_result, list) else 0
        
        # Convert sql_result to string for Bedrock
        sql_result_str = json.dumps(sql_result, ensure_ascii=False, default=str)
        
        # Generate natural language response using Bedrock
        response_text = bedrock_service.get_answer_from_sql_results(
            question=user_question,
            results=sql_result_str,
            schema=schema_context,
            context=context
        )
        
        # Build metadata for caching
        metadata = {
            "source": "text2sql",
            "intent": "schedule_type",
            "row_count": row_count,
            "sql_result": sql_result_str,
            "schema_context_text": schema_context
        }
        
        return response_text, metadata
        
    except Exception as e:
        logger.error(f"Error in _handle_text2sql: {e}", exc_info=True)
        return "Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn.", {"error": str(e)}