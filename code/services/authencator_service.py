import os
import json
import logging
import time
import hmac
import hashlib
import secrets
from typing import Dict, Any, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

# Logger setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)




# Hàm này có vai trò quản lý xác thực người dùng qua OTP gửi email
# quản lý lưu lượng truy cập, giới hạn số lần thử, thời gian chờ, v.v.
# check session để tạo mới session nếu chưa có





class Authenticator:
    """
    Authenticator service for handling OTP-based email authentication.
    
    Responsibilities:
    - OTP generation and verification
    - Email validation and sending
    - Rate limiting and blocking
    - Session state management
    """
    
    def __init__(self, session_table=None, ses_repo=None, message_service=None, session_service=None):
        """
        Initialize Authenticator with dependency injection.
        
        Args:
            session_table: DynamoDBRepository instance (optional, creates default if None)
            ses_repo: SESRepository instance (optional, creates default if None)
            message_service: MessengerService instance (optional, creates default if None)
            session_service: SessionService instance (optional, creates default if None)
        """
        # Dependency injection with lazy loading
        if session_table is None:
            from repositories.dynamodb_repo import DynamoDBRepository
            session_table = DynamoDBRepository()
        self.session_table = session_table
        
        if ses_repo is None:
            from repositories.ses_repo import SESRepository
            ses_repo = SESRepository()
        self.ses_repo = ses_repo
        
        if message_service is None:
            from services.messenger_service import MessengerService
            message_service = MessengerService()
        self.message_service = message_service
        
        if session_service is None:
            from services.session_service import SessionService
            session_service = SessionService(dynamodb_repo=session_table)
        self.session_service = session_service
        
        # Security settings from environment variables
        self.MAX_OTP_ATTEMPTS = int(os.environ.get("MAX_OTP_ATTEMPTS", "5"))
        self.OTP_REQUEST_COOLDOWN = int(os.environ.get("OTP_REQUEST_COOLDOWN", "15"))
        self.MAX_OTP_REQUESTS_PER_HOUR = int(os.environ.get("MAX_OTP_REQUESTS_PER_HOUR", "3"))
        self.BLOCK_DURATION_SECONDS = int(os.environ.get("BLOCK_DURATION_SECONDS", "3600"))
        self.OTP_EXPIRY_SECONDS = int(os.environ.get("OTP_EXPIRY_SECONDS", "300"))
    def generate_otp(self) -> str:
        """Generate cryptographically secure 6-digit OTP code."""
        # Use secrets.SystemRandom for cryptographically secure random numbers
        return ''.join([str(secrets.randbelow(10)) for _ in range(6)])

    def send_otp_email(self, email: str, otp: str) -> bool:
        """Send OTP code via email using Amazon SES."""
        
        return self.ses_repo.send_otp_email(email, otp)
    def can_request_otp(self, psid: str, email: str = None) -> Tuple[bool, str]:
        """Check if user can request new OTP (rate limiting)."""
        try:
            session = self.session_table.get_item(Key={"psid": psid})
            if not session:
                return True, "New user"
            
            current_time = int(time.time())
            blocked_until = session.get("blocked_until", 0)
            blocked_email = session.get("blocked_email", "")
            is_authenticated = session.get("is_authenticated", False)
            
            # Auto-reset blocked status after 1 hour for unauthenticated users
            if not is_authenticated and blocked_until > 0 and current_time >= blocked_until:
                logger.info(f"Auto-resetting block for unauthenticated user {psid}")
                self.session_table.update_item(
                    Key={"psid": psid},
                    UpdateExpression="SET blocked_until = :zero, blocked_email = :empty, otp_attempts = :zero",
                    ExpressionAttributeValues={
                        ":zero": 0,
                        ":empty": ""
                    }
                )
                blocked_until = 0
                blocked_email = ""
            
            # Check if THIS SPECIFIC EMAIL is still blocked
            if email and blocked_email and email.lower() == blocked_email.lower() and blocked_until > current_time:
                remaining_time = blocked_until - current_time
                minutes = remaining_time // 60
                seconds = remaining_time % 60
                if minutes > 0:
                    return False, f"Email này bị khóa do nhập sai quá nhiều lần. Vui lòng sử dụng email khác hoặc thử lại sau {minutes} phút {seconds} giây."
                else:
                    return False, f"Email này bị khóa do nhập sai quá nhiều lần. Vui lòng sử dụng email khác hoặc thử lại sau {seconds} giây."
            
            last_otp_request = session.get("last_otp_request", 0)
            otp_request_count = session.get("otp_request_count", 0)
            otp_request_window_start = session.get("otp_request_window_start", 0)
            
            # Check cooldown period
            if current_time - last_otp_request < self.OTP_REQUEST_COOLDOWN:
                remaining = self.OTP_REQUEST_COOLDOWN - (current_time - last_otp_request)
                return False, f"Vui lòng đợi {remaining} giây trước khi yêu cầu mã OTP mới."
            
            # Auto-reset OTP request counter if window expired (1 hour) for unauthenticated users
            if not is_authenticated and current_time - otp_request_window_start > 3600:
                logger.info(f"Auto-resetting OTP request counter for unauthenticated user {psid}")
                self.session_table.update_item(
                    Key={"psid": psid},
                    UpdateExpression="SET otp_request_count = :zero, otp_request_window_start = :current_time",
                    ExpressionAttributeValues={
                        ":zero": 0,
                        ":current_time": current_time
                    }
                )
                return True, "Counter reset - new window"
            
            # Check hourly limit
            if otp_request_count >= self.MAX_OTP_REQUESTS_PER_HOUR:
                if not is_authenticated:
                    # For unauthenticated users, show when counter will reset
                    remaining_time = 3600 - (current_time - otp_request_window_start)
                    if remaining_time > 0:
                        minutes = remaining_time // 60
                        return False, f"Bạn đã yêu cầu quá nhiều mã OTP. Vui lòng thử lại sau {minutes} phút."
                return False, "Bạn đã yêu cầu quá nhiều mã OTP. Vui lòng thử lại sau 1 giờ."
            
            return True, "OK"
        except Exception as e:
            logger.error(f"Rate limiting check error: {e}")
            return True, "Error - allow by default"

    def store_otp(self,psid: str, email: str, otp: str) -> bool:
        """Store OTP in DynamoDB session table with expiry and rate limiting."""
        try:
            timestamp = int(time.time())
            expiry = timestamp + self.OTP_EXPIRY_SECONDS
            
            # Get existing session for rate limiting data
            session = self.session_table.get_item(Key={"psid": psid})
            otp_request_count = 1
            otp_request_window_start = timestamp
            
            if session:# nếu đã có session rồi
                # Increment request counter within same window
                if timestamp - session.get("otp_request_window_start", 0) <= 3600:
                    otp_request_count = session.get("otp_request_count", 0) + 1
                    otp_request_window_start = session.get("otp_request_window_start", 0)  # Preserve original window start
                    # Nếu không có window start (trường hợp đầu tiên), dùng timestamp hiện tại
                    if otp_request_window_start == 0:
                        otp_request_window_start = timestamp
            
            self.session_table.put_item(
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

    def verify_otp(self, psid: str, input_otp: str) -> Optional[str]:
        """Verify OTP code with timing attack protection and attempt limiting."""
        try:
            session = self.session_table.get_item(Key={"psid": psid})
            if not session:
                return None
            
            stored_otp = session.get("otp")
            otp_expiry = session.get("otp_expiry")
            email = session.get("email")
            otp_attempts = session.get("otp_attempts", 0)
            otp_used = session.get("otp_used", False)
            
            if not stored_otp or not otp_expiry:
                return None # thường đã có ở bước generate_otp
            
            # Check if OTP already used (prevent replay attack)
            if otp_used:
                logger.warning(f"OTP already used for {psid}")
                return None
            
            # Check expiry
            current_time = int(time.time())
            if current_time > otp_expiry:
                logger.warning(f"OTP expired for {psid}")
                # Invalidate expired OTP
                self.session_table.update_item(
                    Key={"psid": psid},
                    UpdateExpression="SET otp = :null, otp_expiry = :zero",
                    ExpressionAttributeValues={
                        ":null": "",
                        ":zero": 0
                    }
                )
                return None
            
            # Check attempt limit (brute force protection) - should not happen if properly handled below
            if otp_attempts >= self.MAX_OTP_ATTEMPTS:
                logger.warning(f"Max OTP attempts already exceeded for {psid} - should be in awaiting_email state")
                return None
            
            # Use constant-time comparison to prevent timing attacks
            # Convert to bytes for hmac.compare_digest
            is_valid = hmac.compare_digest(
                stored_otp.encode('utf-8'),
                input_otp.encode('utf-8')
            )
            
            if is_valid:
                # Mark OTP as used (prevent replay attack)
                self.session_table.update_item(
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
                new_attempts = otp_attempts + 1
                
                # Check if this is the last attempt
                if new_attempts >= self.MAX_OTP_ATTEMPTS: 
                    # Block this email after final failed attempt
                    blocked_until = current_time + self.BLOCK_DURATION_SECONDS
                    self.session_table.update_item(
                        Key={"psid": psid},
                        UpdateExpression="SET otp_attempts = :attempts, otp = :null, otp_expiry = :zero, blocked_until = :blocked_until, blocked_email = :blocked_email, auth_state = :awaiting_email",
                        ExpressionAttributeValues={
                            ":attempts": new_attempts,
                            ":null": "",
                            ":zero": 0,
                            ":blocked_until": blocked_until,
                            ":blocked_email": email,
                            ":awaiting_email": "awaiting_email" # chỉ đổi sang awaiting_email khi vượt quá số lần thử
                        }
                    )
                    logger.info(f"Email {email} blocked for user {psid} after {new_attempts} failed attempts until {blocked_until} (Unix timestamp)")
                else:
                    # Just increment counter
                    self.session_table.update_item(
                        Key={"psid": psid},
                        UpdateExpression="SET otp_attempts = :attempts",
                        ExpressionAttributeValues={
                            ":attempts": new_attempts
                        }
                    )
                
                remaining_attempts = self.MAX_OTP_ATTEMPTS - new_attempts
                logger.warning(f"Invalid OTP attempt for {psid}. Remaining: {remaining_attempts}")
                return None
        except Exception as e:
            logger.error(f"OTP verification error: {e}")
            return None

    def get_remaining_attempts(self, psid: str) -> int:
        """Get remaining OTP verification attempts."""
        try:
            session = self.session_table.get_item(Key={"psid": psid})
            if not session:
                return self.MAX_OTP_ATTEMPTS
            otp_attempts = session.get("otp_attempts", 0)
            return max(0, self.MAX_OTP_ATTEMPTS - otp_attempts)
        except Exception:
            return self.MAX_OTP_ATTEMPTS


    



    
    def is_valid_email(self,email: str) -> bool:
        """Simple email validation."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    # --- MAIN HANDLERS ---


    def handle_callback(self,event: Dict[str, Any]) -> Dict[str, Any]:
        """Simple callback endpoint (not used for OTP flow)."""
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html"},
            "body": "<html><body><h1>MeetAssist</h1><p>Authentication handled via Messenger</p></body></html>"
        }

    def handle_user_authorization_event(self, psid: str, message_text: str) -> Dict[str, Any]:
        """
        Handle user authorization flow with OTP verification.
        
        Args:
            psid: User's Page-Scoped ID (already extracted by chat_handler)
            message_text: User's message text (already extracted by chat_handler)
        
        States:
        - None/initial: Request email
        - awaiting_email: User entering email
        - awaiting_otp: User entering OTP code
        - authenticated: User successfully authenticated
        """
        logger.info(f"Processing auth for PSID {psid}: {message_text}")
        session = self.session_table.get_item(Key={"psid": psid})    
        # Check authentication state
        if not session or not session.get("is_authenticated"):
            auth_state = session.get("auth_state") if session else None
            
            # State: Awaiting OTP input
            if auth_state == "awaiting_otp":
                # User is entering OTP
                if message_text.isdigit() and len(message_text) == 6:
                    email = self.verify_otp(psid, message_text) #check limit attempts và otp expiry 
                    if email:
                        # OTP valid - authenticate user
                        self.session_service.put_new_session(psid)
                        self.session_table.update_item(
                            Key={"psid": psid},
                            UpdateExpression="SET auth_state = :auth_state, is_authenticated = :is_authenticated",
                            ExpressionAttributeValues={
                                ":auth_state": "authenticated",
                                ":is_authenticated": True
                            }
                        )
                        self.message_service.send_text_message(psid, f"✅ Xác thực thành công! Xin chào {email}")
                        self.message_service.send_text_message(psid, "Bạn có thể bắt đầu chat với bot.")
                        return {"statusCode": 200, "body": "Authenticated"}
                        
                    else:
                        # Refresh session sau khi verify_otp để lấy state mới nhất
                        session = self.session_table.get_item(Key={"psid": psid})
                        auth_state = session.get("auth_state") if session else None  # Update auth_state
                        remaining = self.get_remaining_attempts(psid)
                        if remaining > 0:
                            self.message_service.send_text_message(psid, f"❌ Mã OTP không hợp lệ. Còn {remaining} lần thử.")
                        else:
                            # verify_otp đã chuyển auth_state sang awaiting_email
                            # auth_state đã được update ở trên, message tiếp theo sẽ vào đúng block awaiting_email
                            self.message_service.send_text_message(psid, "🔒 Email hiện tại đã bị khóa do nhập sai quá nhiều lần.\n\n✅ Bạn có thể sử dụng email khác. Vui lòng nhập địa chỉ email mới:")
                else:
                    self.message_service.send_text_message(psid, "Vui lòng nhập mã OTP 6 chữ số đã được gửi tới email của bạn.")
            
            # State: Awaiting email input
            elif auth_state == "awaiting_email":
                # User is entering email
                if self.is_valid_email(message_text):
                    # Check rate limiting and block status
                    can_request, reason = self.can_request_otp(psid, message_text)
                    if not can_request:
                        self.message_service.send_text_message(psid, f"⚠️ {reason}")
                    else:
                        otp = self.generate_otp()
                        if self.send_otp_email(message_text, otp):
                            self.store_otp(psid, message_text, otp)
                            self.message_service.send_text_message(psid, f"📧 Mã OTP đã được gửi tới {message_text}. Vui lòng kiểm tra email và nhập mã OTP (6 chữ số).\n\n⚠️ Bạn có {self.MAX_OTP_ATTEMPTS} lần thử. Mã có hiệu lực trong 5 phút.")
                        else:
                            self.message_service.send_text_message(psid, f"❌ Không thể gửi email tới {message_text}. Vui lòng kiểm tra địa chỉ email và thử lại.")
                else:
                    self.message_service.send_text_message(psid, "❌ Email không hợp lệ. Vui lòng nhập lại địa chỉ email của bạn.")
            
            # Default: New user - request email
            else:
                # Store initial state
                self.session_service.put_new_session(psid)
                self.message_service.send_text_message(psid, "👋 Xin chào! Để sử dụng MeetAssist, vui lòng nhập địa chỉ email của bạn.")
        
        return {"statusCode": 200, "body": "OK"}
