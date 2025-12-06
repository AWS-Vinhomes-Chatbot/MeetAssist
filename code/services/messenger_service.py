"""
Messenger Service - Handles Facebook Messenger API calls.

Responsibilities:
- Send messages via Graph API
- Send typing indicators
- Send quick replies, buttons, templates
- Manage send API errors and retries

Note: Webhook verification and signature validation is handled by webhook_receiver.py
"""

import os
import json
import logging
import requests
from typing import Dict, Any, List, Optional
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

# Cache for credentials to avoid repeated AWS API calls
_credentials_cache = {
    "page_token": None
}


class MessengerService:
    """Service for Facebook Messenger Graph API operations."""
    
    def __init__(self, page_token: str = None):
        """
        Initialize MessengerService.
        
        Args:
            page_token: Facebook Page Access Token (optional, will fetch from Secrets Manager if not provided)
        """
        self.page_token = page_token
        self.graph_api_version = "v18.0"
        self.graph_api_url = f"https://graph.facebook.com/{self.graph_api_version}/me/messages"
        self.timeout = 10  # seconds
    
    def send_text_message(self, psid: str, text: str) -> bool:
        """
        Send simple text message.
        
        Args:
            psid: Facebook Page-Scoped ID
            text: Message text (will be truncated if > 2000 chars)
            
        Returns:
            True if sent successfully
        """
        try:
            # Facebook Messenger limit is 2000 characters
            MAX_MESSAGE_LENGTH = 2000
            if len(text) > MAX_MESSAGE_LENGTH:
                logger.warning(f"Message too long ({len(text)} chars), truncating to {MAX_MESSAGE_LENGTH}")
                text = text[:MAX_MESSAGE_LENGTH - 3] + "..."
            
            payload = {
                "recipient": {"id": psid},
                "message": {"text": text}
            }
            
            return self._send_api_request(payload)
            
        except Exception as e:
            logger.error(f"Error sending text message to {psid}: {e}")
            return False
    
    def send_quick_replies(self, psid: str, text: str, quick_replies: List[Dict]) -> bool:
        """
        Send message with quick reply buttons.
        
        Args:
            psid: Facebook Page-Scoped ID
            text: Message text
            quick_replies: List of quick replies, e.g.:
                [
                    {"content_type": "text", "title": "Yes", "payload": "YES"},
                    {"content_type": "text", "title": "No", "payload": "NO"}
                ]
            
        Returns:
            True if sent successfully
        """
        try:
            payload = {
                "recipient": {"id": psid},
                "message": {
                    "text": text,
                    "quick_replies": quick_replies
                }
            }
            
            return self._send_api_request(payload)
            
        except Exception as e:
            logger.error(f"Error sending quick replies to {psid}: {e}")
            return False
    
    def send_button_template(self, psid: str, text: str, buttons: List[Dict]) -> bool:
        """
        Send button template message.
        
        Args:
            psid: Facebook Page-Scoped ID
            text: Template text
            buttons: List of buttons, e.g.:
                [
                    {"type": "postback", "title": "Option 1", "payload": "OPTION_1"},
                    {"type": "web_url", "title": "Visit", "url": "https://example.com"}
                ]
            
        Returns:
            True if sent successfully
        """
        try:
            payload = {
                "recipient": {"id": psid},
                "message": {
                    "attachment": {
                        "type": "template",
                        "payload": {
                            "template_type": "button",
                            "text": text,
                            "buttons": buttons
                        }
                    }
                }
            }
            
            return self._send_api_request(payload)
            
        except Exception as e:
            logger.error(f"Error sending button template to {psid}: {e}")
            return False
    
    def send_typing_indicator(self, psid: str, on: bool = True) -> bool:
        """
        Send typing indicator (on/off).
        
        Args:
            psid: Facebook Page-Scoped ID
            on: True for typing_on, False for typing_off
            
        Returns:
            True if sent successfully
        """
        try:
            payload = {
                "recipient": {"id": psid},
                "sender_action": "typing_on" if on else "typing_off"
            }
            
            return self._send_api_request(payload)
            
        except Exception as e:
            logger.error(f"Error sending typing indicator to {psid}: {e}")
            return False
    
    def _send_api_request(self, payload: Dict[str, Any]) -> bool:
        """
        Core method to send request to Messenger Graph API.
        
        Args:
            payload: Request payload dict
            
        Returns:
            True if successful (status 200)
        """
        try:
            # Get page token (from cache or fetch from AWS)
            page_token = self.page_token or self._get_page_token()
            
            logger.info(f"Sending API request to PSID {payload.get('recipient', {}).get('id')}")
            
            response = requests.post(
                self.graph_api_url,
                json=payload,
                params={"access_token": page_token},
                timeout=self.timeout
            )
            
            logger.info(f"Facebook API response: Status={response.status_code}, Body={response.text}")
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Facebook API error: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("Facebook API request timeout")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook API request error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in _send_api_request: {e}")
            return False
    
    def _get_page_token(self) -> str:
        """Get Facebook Page Token from cache or Secrets Manager."""
        if _credentials_cache["page_token"]:
            return _credentials_cache["page_token"]
        
        FB_PAGE_TOKEN_SECRET_ARN = os.environ.get("FB_PAGE_TOKEN_SECRET_ARN")
        token = self.get_secret_value(FB_PAGE_TOKEN_SECRET_ARN, "page_token")
        _credentials_cache["page_token"] = token
        return token
    
    def get_parameter_value(self, parameter_name: str) -> str:
        try:
            ssm_client = boto3.client("ssm")
            response = ssm_client.get_parameter(Name=parameter_name)
            return response["Parameter"]["Value"]
        except ClientError as e:
            logger.error(f"Error getting parameter {parameter_name}: {e}")
            raise


    def get_secret_value(self, secret_arn: str, key: Optional[str] = None) -> str:
        """Get secret value from AWS Secrets Manager."""
        try:
            secrets_client = boto3.client("secretsmanager")
            response = secrets_client.get_secret_value(SecretId=secret_arn)
            secret_string = response.get("SecretString")
            if secret_string:
                if key:
                    return json.loads(secret_string).get(key)
                return secret_string
            return None
        except ClientError as e:
            logger.error(f"Error getting secret {secret_arn}: {e}")
            raise

    def parse_messenger_event(self, event: dict) -> dict:
        """
        Parse and validate webhook event from Facebook.
        
        Returns dict with:
        - valid: bool (True if signature valid)
        - data: dict (parsed webhook data)
        - error: str (error message if invalid)
        """
        try:
            headers = event.get("headers") or {}
            body = event.get("body", "")
            
            # Decode base64 if needed
            if event.get("isBase64Encoded"):
                import base64
                body = base64.b64decode(body).decode()
            
            # Parse JSON
            data = json.loads(body) if isinstance(body, str) else body
            logger.info(f"Webhook event parsed: {data.get('object', 'unknown')} with {len(data.get('entry', []))} entries")
            
            return {
                "valid": True,
                "data": data
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {
                "valid": False,
                "error": f"Invalid JSON: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error parsing webhook event: {e}")
            return {
                "valid": False,
                "error": f"Parse error: {str(e)}"
            }

    def extract_messages(self, webhook_data: dict) -> List[Dict[str, Any]]:
        """
        Extract messages from parsed webhook data.
        
        Supports multiple event types:
        - message: Regular text messages
        - postback: Button clicks
        - quick_reply: Quick reply button clicks
        
        Args:
            webhook_data: Parsed webhook data from parse_messenger_event
            
        Returns:
            List of message dicts with:
            - type: "message" | "postback" | "quick_reply"
            - psid: Page-scoped user ID
            - text: Message text (for message type)
            - payload: Payload string (for postback/quick_reply)
            - timestamp: Message timestamp
        """
        messages = []
        
        try:
            for entry in webhook_data.get("entry", []):
                for messaging_event in entry.get("messaging", []):
                    psid = messaging_event.get("sender", {}).get("id")
                    
                    if not psid:
                        logger.warning("No PSID found in messaging event")
                        continue
                    
                    timestamp = messaging_event.get("timestamp")
                    
                    # Handle regular text message
                    if messaging_event.get("message"):
                        message = messaging_event["message"]
                        
                        # Check for quick_reply (takes precedence)
                        if message.get("quick_reply"):
                            messages.append({
                                "type": "quick_reply",
                                "psid": psid,
                                "mid": message.get("mid"),  # Message ID for deduplication
                                "payload": message["quick_reply"].get("payload", ""),
                                "text": message.get("text", ""),
                                "timestamp": timestamp
                            })
                        # Regular text message
                        elif message.get("text"):
                            messages.append({
                                "type": "message",
                                "psid": psid,
                                "mid": message.get("mid"),  # Message ID for deduplication
                                "text": message["text"].strip(),
                                "timestamp": timestamp
                            })
                    # Handle postback (button clicks)
                    elif messaging_event.get("postback"):
                        postback = messaging_event["postback"]
                        messages.append({
                            "type": "postback",
                            "psid": psid,
                            "mid": postback.get("mid"),  # Message ID for deduplication
                            "payload": postback.get("payload", ""),
                            "title": postback.get("title", ""),
                            "timestamp": timestamp
                        })
                    
                    
                    # # Handle read confirmation (skip)
                    # elif messaging_event.get("read"):
                    #     logger.debug(f"Read confirmation from {psid}")
                    #     # Skip read events
                    #     continue
                    
                    else:
                        logger.warning(f"Unknown messaging event type from {psid}: {list(messaging_event.keys())}")
            
            logger.info(f"Extracted {len(messages)} message(s) from webhook")
            return messages
            
        except Exception as e:
            logger.error(f"Error extracting messages: {e}")
            return []