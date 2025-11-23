import os
import json
import logging
import boto3
import requests
import time
import hmac
import hashlib
import secrets
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError
import urllib.parse

# Logger setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS Clients
secrets_client = boto3.client("secretsmanager")
ssm_client = boto3.client("ssm")
dynamodb = boto3.resource("dynamodb")
ses_client = boto3.client("ses", region_name="ap-southeast-1")

# Environment variables
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
FB_APP_ID_PARAM = os.environ.get("FB_APP_ID_PARAM")
FB_APP_SECRET_PARAM = os.environ.get("FB_APP_SECRET_PARAM")
FB_PAGE_TOKEN_SECRET_ARN = os.environ.get("FB_PAGE_TOKEN_SECRET_ARN")
SESSION_TABLE_NAME = os.environ.get("SESSION_TABLE_NAME")
OTP_SENDER_EMAIL = "pqa1085@gmail.com"
OTP_EXPIRY_SECONDS = 300  # 5 phút

# Security Settings
MAX_OTP_ATTEMPTS = 5  # số lần thử xác thực OTP tối đa
OTP_REQUEST_COOLDOWN = 60  # Mỗi request OTP cách nhau tối thiểu 60 giây
MAX_OTP_REQUESTS_PER_HOUR = 3  # trong một giờ có tối đa 3 lần yêu cầu OTP

session_table = dynamodb.Table(SESSION_TABLE_NAME)

# Cache
_cache = {
    "fb_app_id": None,
    "fb_app_secret": None,
    "fb_page_token": None
}

# --- HELPER FUNCTIONS ---

def get_parameter_value(parameter_name: str) -> str:
    try:
        response = ssm_client.get_parameter(Name=parameter_name)
        return response["Parameter"]["Value"]
    except ClientError as e:
        logger.error(f"Error getting parameter {parameter_name}: {e}")
        raise

def generate_otp() -> str:
    """Generate cryptographically secure 6-digit OTP code."""
    # Use secrets.SystemRandom for cryptographically secure random numbers
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])

def send_otp_email(email: str, otp: str) -> bool:
    """Send OTP code via email using Amazon SES."""
    try:
        response = ses_client.send_email(
            Source=OTP_SENDER_EMAIL,
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': 'MeetAssist - Mã xác thực OTP'},
                'Body': {
                    'Text': {'Data': f'Mã OTP của bạn là: {otp}\n\nMã này có hiệu lực trong 5 phút.'},
                    'Html': {'Data': f'<h2>Mã OTP của bạn</h2><p><strong style="font-size:24px">{otp}</strong></p><p>Mã này có hiệu lực trong 5 phút.</p>'}
                }
            }
        )
        logger.info(f"OTP email sent to {email}: {response['MessageId']}")
        return True
    except ClientError as e:
        logger.error(f"Failed to send OTP email: {e}")
        return False

def get_secret_value(secret_arn: str, key: Optional[str] = None) -> str:
    try:
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

def get_fb_credentials() -> Dict[str, str]:
    if not _cache["fb_app_id"]:
        _cache["fb_app_id"] = get_parameter_value(FB_APP_ID_PARAM)
    if not _cache["fb_app_secret"]:
        _cache["fb_app_secret"] = get_parameter_value(FB_APP_SECRET_PARAM)
    if not _cache["fb_page_token"]:
        _cache["fb_page_token"] = get_secret_value(FB_PAGE_TOKEN_SECRET_ARN, "page_token")
    
    return {
        "app_id": _cache["fb_app_id"],
        "app_secret": _cache["fb_app_secret"],
        "page_token": _cache["fb_page_token"],
        "verify_token": get_secret_value(FB_PAGE_TOKEN_SECRET_ARN, "verify_token")
    }

def can_request_otp(psid: str) -> tuple[bool, str]:
    """Check if user can request new OTP (rate limiting)."""
    try:
        session = get_user_session(psid)
        if not session:
            return True, "New user"
        
        current_time = int(time.time())
        last_otp_request = session.get("last_otp_request", 0)
        otp_request_count = session.get("otp_request_count", 0)
        otp_request_window_start = session.get("otp_request_window_start", 0)
        
        # Check cooldown period
        if current_time - last_otp_request < OTP_REQUEST_COOLDOWN:
            remaining = OTP_REQUEST_COOLDOWN - (current_time - last_otp_request)
            return False, f"Vui lòng đợi {remaining} giây trước khi yêu cầu mã OTP mới."
        
        # Reset hourly counter if window expired
        if current_time - otp_request_window_start > 3600:
            return True, "New window"
        
        # Check hourly limit
        if otp_request_count >= MAX_OTP_REQUESTS_PER_HOUR:
            return False, "Bạn đã yêu cầu quá nhiều mã OTP. Vui lòng thử lại sau 1 giờ."
        
        return True, "OK"
    except Exception as e:
        logger.error(f"Rate limiting check error: {e}")
        return True, "Error - allow by default"

def store_otp(psid: str, email: str, otp: str) -> bool:
    """Store OTP in DynamoDB session table with expiry and rate limiting."""
    try:
        timestamp = int(time.time())
        expiry = timestamp + OTP_EXPIRY_SECONDS
        
        # Get existing session for rate limiting data
        session = get_user_session(psid)
        otp_request_count = 1
        otp_request_window_start = timestamp
        
        if session:# nếu đã có session rồi
            # Increment request counter within same window
            if timestamp - session.get("otp_request_window_start", 0) <= 3600:
                otp_request_count = session.get("otp_request_count", 0) + 1
                otp_request_window_start = session.get("otp_request_window_start", timestamp)
        
        session_table.put_item(
            Item={
                "psid": psid,
                "email": email,
                "otp": otp,
                "otp_expiry": expiry,
                "otp_attempts": 0,  # Counter for failed verification attempts
                "otp_used": False,  # Flag to prevent replay attacks
                "last_otp_request": timestamp,
                "otp_request_count": otp_request_count,
                "otp_request_window_start": otp_request_window_start,
                "is_authenticated": False,
                "auth_state": "awaiting_otp",
                "updated_at": timestamp
            }
        )
        return True
    except ClientError as e:
        logger.error(f"Failed to store OTP: {e}")
        return False

def verify_otp(psid: str, input_otp: str) -> Optional[str]:
    """Verify OTP code with timing attack protection and attempt limiting."""
    try:
        session = get_user_session(psid)
        if not session:
            return None
        
        stored_otp = session.get("otp")
        otp_expiry = session.get("otp_expiry")
        email = session.get("email")
        otp_attempts = session.get("otp_attempts", 0)
        otp_used = session.get("otp_used", False)
        
        if not stored_otp or not otp_expiry:
            return None
        
        # Check if OTP already used (prevent replay attack)
        if otp_used:
            logger.warning(f"OTP already used for {psid}")
            return None
        
        # Check expiry
        current_time = int(time.time())
        if current_time > otp_expiry:
            logger.warning(f"OTP expired for {psid}")
            # Invalidate expired OTP
            session_table.update_item(
                Key={"psid": psid},
                UpdateExpression="SET otp = :null, otp_expiry = :zero",
                ExpressionAttributeValues={
                    ":null": "",
                    ":zero": 0
                }
            )
            return None
        
        # Check attempt limit (brute force protection)
        if otp_attempts >= MAX_OTP_ATTEMPTS:
            logger.warning(f"Max OTP attempts exceeded for {psid}")
            # Invalidate OTP after max attempts
            session_table.update_item(
                Key={"psid": psid},
                UpdateExpression="SET otp = :null, otp_expiry = :zero, auth_state = :blocked",
                ExpressionAttributeValues={
                    ":null": "",
                    ":zero": 0,
                    ":blocked": "blocked"
                }
            )
            return None
        
        # Use constant-time comparison to prevent timing attacks
        # Convert to bytes for hmac.compare_digest
        is_valid = hmac.compare_digest(
            stored_otp.encode('utf-8'),
            input_otp.encode('utf-8')
        )
        
        if is_valid:
            # Mark OTP as used (prevent replay attack)
            session_table.update_item(
                Key={"psid": psid},
                UpdateExpression="SET otp_used = :true, otp = :null",
                ExpressionAttributeValues={
                    ":true": True,
                    ":null": ""  # Clear OTP after successful use
                }
            )
            logger.info(f"OTP verified successfully for {psid}")
            return email
        else:
            # Increment failed attempt counter
            session_table.update_item(
                Key={"psid": psid},
                UpdateExpression="SET otp_attempts = otp_attempts + :inc",
                ExpressionAttributeValues={
                    ":inc": 1
                }
            )
            remaining_attempts = MAX_OTP_ATTEMPTS - (otp_attempts + 1)
            logger.warning(f"Invalid OTP attempt for {psid}. Remaining: {remaining_attempts}")
            return None
    except Exception as e:
        logger.error(f"OTP verification error: {e}")
        return None

def get_remaining_attempts(psid: str) -> int:
    """Get remaining OTP verification attempts."""
    try:
        session = get_user_session(psid)
        if not session:
            return MAX_OTP_ATTEMPTS
        otp_attempts = session.get("otp_attempts", 0)
        return max(0, MAX_OTP_ATTEMPTS - otp_attempts)
    except Exception:
        return MAX_OTP_ATTEMPTS

def verify_facebook_signature(payload: str, signature: str) -> bool:
    try:
        app_secret = get_fb_credentials()["app_secret"]
        expected = hmac.new(app_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
    except Exception:
        return False

def get_user_session(psid: str) -> Optional[Dict[str, Any]]:
    try:
        return session_table.get_item(Key={"psid": psid}).get("Item")
    except ClientError: return None

def create_or_update_session(psid: str, user_data: Dict[str, Any]) -> bool:
    try:
        timestamp = int(time.time())
        item = {
            "psid": psid,
            "email": user_data.get("email"),
            "name": user_data.get("name", user_data.get("email", "User")),
            "updated_at": timestamp,
            "is_authenticated": user_data.get("is_authenticated", True),
            "auth_state": "authenticated"
        }
        session_table.put_item(Item=item)
        return True
    except ClientError as e:
        logger.error(f"DB Error: {e}")
        return False

def send_messenger_message(psid: str, message_text: str) -> bool:
    try:
        page_token = get_fb_credentials()["page_token"]
        url = "https://graph.facebook.com/v18.0/me/messages"
        payload = {"recipient": {"id": psid}, "message": {"text": message_text}}
        logger.info(f"Sending message to PSID {psid}: {message_text[:50]}...")
        
        resp = requests.post(
            url, 
            json=payload,
            params={"access_token": page_token},
            timeout=10
        )
        
        logger.info(f"Facebook API response: Status={resp.status_code}, Body={resp.text}")
        
        if resp.status_code != 200:
            logger.error(f"Failed to send message: {resp.status_code} - {resp.text}")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Send msg error: {e}", exc_info=True)
        return False

def is_valid_email(email: str) -> bool:
    """Simple email validation."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# --- MAIN HANDLERS ---

def handle_webhook_verification(event):
    params = event.get("queryStringParameters") or {}
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == get_fb_credentials()["verify_token"]:
        return {"statusCode": 200, "body": params.get("hub.challenge")}
    return {"statusCode": 403, "body": "Forbidden"}

def handle_callback(event: Dict[str, Any]) -> Dict[str, Any]:
    """Simple callback endpoint (not used for OTP flow)."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": "<html><body><h1>MeetAssist</h1><p>Authentication handled via Messenger</p></body></html>"
    }

def handle_messenger_event(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        headers = event.get("headers") or {}
        signature = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
        body = event.get("body", "")
        
        if signature and not verify_facebook_signature(body, signature):
            logger.warning("Invalid Facebook signature")
            return {"statusCode": 403, "body": json.dumps({"error": "Invalid signature"})}
        
        if event.get("isBase64Encoded"):
            import base64
            body = base64.b64decode(body).decode()
        
        data = json.loads(body) if isinstance(body, str) else body
        logger.info(f"Processing {len(data.get('entry', []))} entries")
        
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                psid = messaging_event.get("sender", {}).get("id")
                if not psid: 
                    logger.warning("No PSID found")
                    continue
                
                logger.info(f"Processing message from PSID: {psid}")
                session = get_user_session(psid)
                
                if messaging_event.get("message"):
                    message_text = messaging_event["message"].get("text", "").strip()
                    logger.info(f"Message text: {message_text}")
                    
                    # Check authentication state
                    if not session or not session.get("is_authenticated"):
                        auth_state = session.get("auth_state") if session else None
                        
                        # State: Awaiting OTP input
                        if auth_state == "awaiting_otp":
                            # User is entering OTP
                            if message_text.isdigit() and len(message_text) == 6:
                                # Check if account is blocked
                                remaining = get_remaining_attempts(psid)
                                if remaining == 0:
                                    send_messenger_message(psid, "🔒 Tài khoản của bạn đã bị khóa do nhập sai mã OTP quá nhiều lần. Vui lòng nhập email để nhận mã mới.")
                                else:
                                    email = verify_otp(psid, message_text)
                                    if email:
                                        # OTP valid - authenticate user
                                        create_or_update_session(psid, {
                                            "email": email,
                                            "name": email.split('@')[0],
                                            "is_authenticated": True
                                        })
                                        send_messenger_message(psid, f"✅ Xác thực thành công! Xin chào {email}")
                                        send_messenger_message(psid, "Bạn có thể bắt đầu chat với bot.")
                                    else:
                                        remaining = get_remaining_attempts(psid)
                                        if remaining > 0:
                                            send_messenger_message(psid, f"❌ Mã OTP không hợp lệ. Còn {remaining} lần thử.")
                                        else:
                                            send_messenger_message(psid, "🔒 Mã OTP đã bị khóa do nhập sai quá nhiều lần. Vui lòng nhập email để nhận mã mới.")
                            else:
                                send_messenger_message(psid, "Vui lòng nhập mã OTP 6 chữ số đã được gửi tới email của bạn.")
                        
                        # State: Awaiting email input
                        elif auth_state == "awaiting_email":
                            # User is entering email
                            if is_valid_email(message_text):
                                # Check rate limiting
                                can_request, reason = can_request_otp(psid)
                                if not can_request:
                                    send_messenger_message(psid, f"⚠️ {reason}")
                                else:
                                    otp = generate_otp()
                                    if send_otp_email(message_text, otp):
                                        store_otp(psid, message_text, otp)
                                        send_messenger_message(psid, f"📧 Mã OTP đã được gửi tới {message_text}. Vui lòng kiểm tra email và nhập mã OTP (6 chữ số).\n\n⚠️ Bạn có {MAX_OTP_ATTEMPTS} lần thử. Mã có hiệu lực trong 5 phút.")
                                    else:
                                        send_messenger_message(psid, f"❌ Không thể gửi email tới {message_text}. Vui lòng kiểm tra địa chỉ email và thử lại.")
                            else:
                                send_messenger_message(psid, "❌ Email không hợp lệ. Vui lòng nhập lại địa chỉ email của bạn.")
                        
                        # Default: New user - request email
                        else:
                            # Store initial state
                            session_table.put_item(
                                Item={
                                    "psid": psid,
                                    "auth_state": "awaiting_email",
                                    "is_authenticated": False,
                                    "updated_at": int(time.time())
                                }
                            )
                            send_messenger_message(psid, "👋 Xin chào! Để sử dụng MeetAssist, vui lòng nhập địa chỉ email của bạn.")
                    
                    else:
                        # User is authenticated - process normal message
                        logger.info(f"User authenticated: {session.get('name')}")
                        user_name = session.get('name', 'bạn')
                        send_messenger_message(psid, f"Chào {user_name}! Bạn nói: {message_text}")
                        # TODO: Add your bot logic here
        
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
            return handle_messenger_event(event)
        else:
            return {"statusCode": 405, "body": "Method not allowed"}
    except Exception as e:
        logger.error(f"Error: {e}")
        return {"statusCode": 500, "body": "Internal Server Error"}