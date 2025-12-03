"""
Webhook Receiver - Lightweight Lambda to receive Facebook webhooks and push to SQS.

This Lambda:
1. Handles webhook verification (GET)
2. Receives webhook events (POST)
3. Pushes messages to SQS FIFO queue
4. Returns 200 immediately (prevents Facebook timeout & retry)

The actual message processing is done by chat_handler triggered by SQS.
"""

import os
import json
import logging
import hashlib
import hmac
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# SQS client
sqs_client = boto3.client('sqs')
QUEUE_URL = os.environ.get('MESSAGE_QUEUE_URL', '')

# SSM/Secrets for Facebook verification
ssm_client = boto3.client('ssm')
secrets_client = boto3.client('secretsmanager')

# Cache credentials
_credentials_cache = {}


def get_verify_token():
    """Get Facebook verify token from SSM."""
    if 'verify_token' not in _credentials_cache:
        param_name = os.environ.get('FB_APP_ID_PARAM', '/meetassist/facebook/app_id')
        # Verify token is typically a simple string you set in Facebook App settings
        # For simplicity, we'll use a fixed value or env var
        _credentials_cache['verify_token'] = os.environ.get('FB_VERIFY_TOKEN', 'meetassist_verify_token')
    return _credentials_cache['verify_token']


def get_app_secret():
    """Get Facebook app secret for signature verification."""
    if 'app_secret' not in _credentials_cache:
        try:
            param_name = os.environ.get('FB_APP_SECRET_PARAM', '/meetassist/facebook/app_secret')
            response = ssm_client.get_parameter(Name=param_name, WithDecryption=True)
            _credentials_cache['app_secret'] = response['Parameter']['Value']
        except Exception as e:
            logger.error(f"Error getting app secret: {e}")
            _credentials_cache['app_secret'] = ''
    return _credentials_cache['app_secret']


def verify_signature(payload: str, signature: str) -> bool:
    """Verify Facebook webhook signature."""
    if not signature:
        return False
    
    app_secret = get_app_secret()
    if not app_secret:
        logger.warning("No app secret configured, skipping signature verification")
        return True  # Skip verification if no secret configured
    
    try:
        # Facebook sends signature as "sha256=<hash>"
        if signature.startswith('sha256='):
            expected_signature = signature[7:]
            computed_signature = hmac.new(
                app_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected_signature, computed_signature)
        elif signature.startswith('sha1='):
            expected_signature = signature[5:]
            computed_signature = hmac.new(
                app_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha1
            ).hexdigest()
            return hmac.compare_digest(expected_signature, computed_signature)
    except Exception as e:
        logger.error(f"Error verifying signature: {e}")
    
    return False


def lambda_handler(event, context):
    """
    Main handler - receives webhook and pushes to SQS.
    
    GET: Webhook verification
    POST: Push message to SQS FIFO queue
    """
    logger.info(f"Received event: {json.dumps(event)[:500]}...")
    
    http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method')
    
    # Handle GET - Webhook verification
    if http_method == 'GET':
        return handle_verification(event)
    
    # Handle POST - Push to SQS
    elif http_method == 'POST':
        return handle_webhook(event)
    
    return {
        'statusCode': 405,
        'body': 'Method not allowed'
    }


def handle_verification(event):
    """Handle Facebook webhook verification (GET request)."""
    query_params = event.get('queryStringParameters') or {}
    
    mode = query_params.get('hub.mode')
    token = query_params.get('hub.verify_token')
    challenge = query_params.get('hub.challenge')
    
    verify_token = get_verify_token()
    
    if mode == 'subscribe' and token == verify_token:
        logger.info("Webhook verified successfully")
        return {
            'statusCode': 200,
            'body': challenge
        }
    else:
        logger.warning(f"Webhook verification failed. Mode: {mode}, Token match: {token == verify_token}")
        return {
            'statusCode': 403,
            'body': 'Verification failed'
        }


def handle_webhook(event):
    """Handle incoming webhook - push to SQS FIFO queue."""
    try:
        body = event.get('body', '')
        
        # Verify signature
        signature = event.get('headers', {}).get('X-Hub-Signature-256') or \
                   event.get('headers', {}).get('x-hub-signature-256')
        
        if not verify_signature(body, signature):
            logger.warning("Invalid webhook signature")
            # Still return 200 to prevent Facebook from retrying
            return {'statusCode': 200, 'body': 'OK'}
        
        # Parse body
        try:
            data = json.loads(body) if isinstance(body, str) else body
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook body")
            return {'statusCode': 200, 'body': 'OK'}
        
        # Only process page events
        if data.get('object') != 'page':
            logger.info(f"Ignoring non-page event: {data.get('object')}")
            return {'statusCode': 200, 'body': 'OK'}
        
        # Extract messages and push to SQS
        messages_sent = 0
        for entry in data.get('entry', []):
            for messaging_event in entry.get('messaging', []):
                # Get message ID for deduplication
                message_id = None
                if messaging_event.get('message'):
                    message_id = messaging_event['message'].get('mid')
                elif messaging_event.get('postback'):
                    # Postbacks don't have mid, generate from timestamp + sender
                    sender_id = messaging_event.get('sender', {}).get('id', '')
                    timestamp = messaging_event.get('timestamp', '')
                    message_id = f"postback_{sender_id}_{timestamp}"
                
                if not message_id:
                    # Generate fallback ID
                    sender_id = messaging_event.get('sender', {}).get('id', 'unknown')
                    timestamp = messaging_event.get('timestamp', '')
                    message_id = f"msg_{sender_id}_{timestamp}"
                
                # Get sender for message group (ensures ordering per user)
                sender_id = messaging_event.get('sender', {}).get('id', 'default')
                
                # Push to SQS FIFO
                try:
                    # Build minimal event for auth handling (reduce SQS message size)
                    minimal_event = {
                        'body': body,  # Original webhook body
                        'httpMethod': 'POST',
                        'headers': event.get('headers', {}),
                    }
                    
                    sqs_response = sqs_client.send_message(
                        QueueUrl=QUEUE_URL,
                        MessageBody=json.dumps({
                            'messaging_event': messaging_event,
                            'entry_time': entry.get('time'),
                            'page_id': entry.get('id'),
                            'original_event': minimal_event  # Minimal event for auth
                        }),
                        MessageDeduplicationId=message_id,  # Deduplication in 5-minute window
                        MessageGroupId=sender_id  # Group by user for FIFO ordering
                    )
                    messages_sent += 1
                    logger.info(f"Sent message to SQS: {message_id}, MessageId: {sqs_response.get('MessageId')}")
                except ClientError as e:
                    logger.error(f"Failed to send message to SQS: {e}")
        
        logger.info(f"Pushed {messages_sent} message(s) to SQS")
        
        # Return 200 immediately - processing happens async via SQS
        return {
            'statusCode': 200,
            'body': 'OK'
        }
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}", exc_info=True)
        # Still return 200 to prevent Facebook from retrying
        return {
            'statusCode': 200,
            'body': 'OK'
        }
