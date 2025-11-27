"""
Webhook Handler - Lambda entry point for Facebook Messenger webhook.

This is a lightweight routing layer that:
1. Receives webhook events from Facebook
2. Routes to MessengerHandler for verification/validation
3. Routes to Orchestrator for message processing
4. Returns responses to API Gateway
"""

import json
import logging
from handlers.messenger_handler import MessengerHandler
from services.messenger_service import MessengerService
from orchestrator import ChatOrchestrator

# Logger setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize handlers and services
messenger_service = MessengerService()
messenger_handler = MessengerHandler(messenger_service)
chat_orchestrator = ChatOrchestrator()


def lambda_handler(event, context):
    """
    Lambda entry point for Facebook Messenger webhook.
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")
        path = event.get("path", "/")
        
        # Route based on HTTP method and path
        if http_method == "GET":
            # Webhook verification from Facebook
            return handle_webhook_verification(event)
        
        elif http_method == "POST":
            # Webhook events from Facebook
            return handle_webhook_event(event)
        
        else:
            return {
                "statusCode": 405,
                "body": json.dumps({"error": "Method not allowed"})
            }
    
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal Server Error"})
        }


def handle_webhook_verification(event: dict) -> dict:
    """
    Handle webhook verification (GET request from Facebook).
    
    Args:
        event: API Gateway event
        
    Returns:
        Verification response
    """
    logger.info("Handling webhook verification")
    return messenger_handler.verify_webhook(event)


def handle_webhook_event(event: dict) -> dict:
    """
    Handle webhook event (POST request from Facebook).
    
    Args:
        event: API Gateway event
        
    Returns:
        Event processing response
    """
    try:
        # Step 1: Parse and validate webhook event
        parsed_event = messenger_handler.parse_webhook_event(event)
        
        if not parsed_event.get("valid"):
            logger.warning(f"Invalid webhook event: {parsed_event.get('error')}")
            return {
                "statusCode": 403,
                "body": json.dumps({"error": "Invalid signature or malformed request"})
            }
        
        # Step 2: Extract messages from webhook data
        messages = messenger_handler.extract_messages(parsed_event["data"])
        
        if not messages:
            logger.info("No messages to process")
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "No messages to process"})
            }
        
        # Step 3: Process each message
        for msg in messages:
            process_message(msg)
        
        # Step 4: Return success to Facebook immediately
        # (Facebook requires 200 response within 20 seconds)
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "EVENT_RECEIVED"})
        }
    
    except Exception as e:
        logger.error(f"Error handling webhook event: {e}", exc_info=True)
        # Still return 200 to Facebook to avoid retries
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "ERROR_OCCURRED"})
        }


def process_message(message: dict):
    """
    Process individual message event.
    
    This function orchestrates the chat flow by:
    1. Extracting message details
    2. Calling ChatOrchestrator
    3. Sending response back to user
    
    Args:
        message: Message event dict with type, psid, text, etc.
    """
    try:
        psid = message.get("psid")
        message_type = message.get("type")
        
        logger.info(f"Processing {message_type} from PSID: {psid}")
        
        # Route based on message type
        if message_type == "message":
            # Regular text message
            process_text_message(psid, message.get("text"))
        
        elif message_type == "postback":
            # Button postback
            process_postback(psid, message.get("payload"))
        
        elif message_type == "quick_reply":
            # Quick reply button
            process_quick_reply(psid, message.get("payload"))
        
        else:
            logger.warning(f"Unknown message type: {message_type}")
    
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)


def process_text_message(psid: str, text: str):
    """
    Process text message from user.
    
    Args:
        psid: Facebook Page-Scoped ID
        text: Message text
    """
    try:
        # Show typing indicator
        messenger_handler.send_typing_indicator(psid, on=True)
        
        # Call orchestrator to process message
        # Note: Using sync call here, but orchestrator methods are async
        # For proper async execution, consider using asyncio.run() or async Lambda
        import asyncio
        response = asyncio.run(chat_orchestrator.process_message(psid, text))
        
        # Turn off typing indicator
        messenger_handler.send_typing_indicator(psid, on=False)
        
        # Send response to user
        if response.get("success"):
            messenger_handler.send_message(psid, response.get("message"))
        else:
            error_message = response.get("message", "Xin lỗi, đã có lỗi xảy ra.")
            messenger_handler.send_message(psid, error_message)
    
    except Exception as e:
        logger.error(f"Error in process_text_message: {e}", exc_info=True)
        # Send generic error message to user
        try:
            messenger_handler.send_message(psid, "Xin lỗi, tôi gặp sự cố. Vui lòng thử lại sau.")
        except:
            pass


def process_postback(psid: str, payload: str):
    """
    Process button postback from user.
    
    Args:
        psid: Facebook Page-Scoped ID
        payload: Postback payload
    """
    try:
        import asyncio
        response = asyncio.run(chat_orchestrator.handle_postback(psid, payload))
        
        if response.get("success"):
            messenger_handler.send_message(psid, response.get("message"))
    
    except Exception as e:
        logger.error(f"Error in process_postback: {e}", exc_info=True)


def process_quick_reply(psid: str, payload: str):
    """
    Process quick reply button from user.
    
    Quick replies are treated similar to postbacks.
    
    Args:
        psid: Facebook Page-Scoped ID
        payload: Quick reply payload
    """
    try:
        # Quick replies can be handled like postbacks
        process_postback(psid, payload)
    
    except Exception as e:
        logger.error(f"Error in process_quick_reply: {e}", exc_info=True)
