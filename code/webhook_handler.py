import os
import json
import logging
import boto3
import requests
import time

import hashlib
import secrets
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError
import urllib.parse

# Logger setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS Clients



ses_client = boto3.client("ses", region_name="ap-southeast-1")

# Environment variables
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")




session_table = dynamodb.Table(SESSION_TABLE_NAME)

# --- HELPER FUNCTIONS ---


        
        logger.info("Successfully processed all events, returning 200")
        return {"statusCode": 200, "body": "EVENT_RECEIVED"}
    except Exception as e:
        logger.error(f"Error in handle_messenger_event: {e}", exc_info=True)
        return {"statusCode": 500, "body": str(e)}

def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")
    try:
        http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")
        path = event.get("path", "/")
        
        if http_method == "GET":
            if "/callback" in path:
                return handle_callback(event)
            else:
                return handle_webhook_verification(event)
        elif http_method == "POST":
            return handle_user_authorization_event(event)
        else:
            return {"statusCode": 405, "body": "Method not allowed"}
    except Exception as e:
        logger.error(f"Error: {e}")
        return {"statusCode": 500, "body": "Internal Server Error"}