"""
Session Service - Manages user sessions and authentication state.

Responsibilities:
- Session CRUD operations
- OTP generation and verification
- Rate limiting
- Conversation history
- Cache management
"""

import os
import secrets
import time
import hmac
import logging
from typing import Dict, Any, Optional, Tuple
from botocore.exceptions import ClientError

logger = logging.getLogger()
# Static JSON template for appointment booking
APPOINTMENT_TEMPLATE = {
    "customer_name": None,
    "phone_number": None,
    "appointment_date": None,
    "appointment_time": None,
    "consultant_name": None,
    "service_type": None,
    "notes": None
}

class SessionService:
    """Service for managing user sessions."""
    
    def __init__(self, dynamodb_repo=None, messenger_service=None, cache_service=None):
        """
        Initialize SessionService.
        
        Args:
            dynamodb_repo: DynamoDBRepository instance. If None, creates default instance.
            messenger_service: MessengerService instance. If None, creates default instance.
        
        Example:
            # Use default repo (auto-creates from env vars)
            service = SessionService()
            
            # Inject custom repo (for testing)
            mock_repo = MagicMock()
            service = SessionService(dynamodb_repo=mock_repo)
            
            # Use specific table
            from repositories.dynamodb_repo import DynamoDBRepository
            repo = DynamoDBRepository(table_name="custom-table")
            service = SessionService(dynamodb_repo=repo)
        """
        # ✅ Dependency injection with lazy loading
        if dynamodb_repo is None:
            from repositories.dynamodb_repo import DynamoDBRepository
            dynamodb_repo = DynamoDBRepository()  # Uses env vars
        
        self.dynamodb_repo = dynamodb_repo
        
        if messenger_service is None:
            from services.messenger_service import MessengerService
            messenger_service = MessengerService()
        
        self.messenger_service = messenger_service
        if cache_service is None:
            from services.cache_service import CacheService
            cache_service = CacheService()
        
        self.cache_service = cache_service
        # ✅ Load context settings from environment
        self.MAX_CONTEXT_TURNS = int(os.environ.get("MAX_CONTEXT_TURNS", "3"))
    
    def get_session(self, psid: str) -> Optional[Dict[str, Any]]:
        """
        Get session by PSID.
        
        Args:
            psid: Page-Scoped ID
            
        Returns:
            Session dict or None
        """
        try:
            response = self.dynamodb_repo.get_item(Key={"psid": psid})
            return response.get("Item")
        except ClientError as e:
            logger.error(f"Error getting session for {psid}: {e}")
            return None
    
    
    
    def add_message_to_history(self, event: Dict[str, Any], assistant_msg: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add message to conversation history by extracting user message from webhook event.
        
        Args:
            event: Webhook event from Facebook Messenger
            assistant_msg: Bot's response message
            metadata: Optional metadata dict
            
        Returns:
            True if successful
        """
        try:
            # Parse webhook event using MessengerService
            parsed = self.messenger_service.parse_messenger_event(event)
            if not parsed.get("valid"):
                logger.error(f"Invalid messenger event: {parsed.get('error')}")
                return False
            
            # Extract messages from parsed data
            messages = self.messenger_service.extract_messages(parsed["data"])
            if not messages:
                logger.warning("No messages found in webhook event")
                return False
            
            # Get the first message (usually there's only one)
            msg_data = messages[0]
            psid = msg_data.get("psid")
            user_msg = msg_data.get("text", "") or msg_data.get("payload", "")
            vector =  self.cache_service.get_cache_data(psid, user_msg)
            if not psid:
                logger.error("No PSID found in message")
                return False
            
            # Get session
            session = self.get_session(psid)
            if not session:
                return False
            intent = session.get("current_intent","unknown")
            history = session.get("conversation_context", [])
            history.append({
                "user": user_msg,
                "vector": vector,
                "assistant": assistant_msg,
                "intent": intent,
                "metadata": metadata or {},
                "timestamp": msg_data.get("timestamp") or int(time.time())
            })
            
            # Keep only last MAX_CONTEXT_TURNS messages (default 3)
            if len(history) > self.MAX_CONTEXT_TURNS:
                history = history[-self.MAX_CONTEXT_TURNS:]
                logger.info(f"Trimmed context for {psid}, kept last {self.MAX_CONTEXT_TURNS} turns")
            
            self.dynamodb_repo.update_item(psid, {
                "conversation_context": history
            })
            return True
        except Exception as e:
            logger.error(f"Error adding message to history: {e}")
            return False
    
    
    def put_new_session(self, psid: str) -> bool:
        """
        Create or replace entire session.
        
        Args:
            session_data: Complete session data dict
            
        Returns:
            True if successful
        """
        try:
            session = {
                        "psid": psid,
                        "auth_state": "awaiting_email",
                        "is_authenticated": False,
                        "current_intent": "schedule_type",
                        "conversation_context": [],
                        "appointment_info": APPOINTMENT_TEMPLATE.copy(),
                        "updated_at": int(time.time())
                        }
            self.dynamodb_repo.put_item(Item=session)
            return True
        except ClientError as e:
            logger.error(f"Error putting session: {e}")
            return False
    
    
    def delete_session(self, psid: str) -> bool:
        """
        Delete session.
        
        Args:
            psid: Page-Scoped ID
            
        Returns:
            True if successful
        """
        try:
            self.dynamodb_repo.delete_item(Key={"psid": psid})
            return True
        except ClientError as e:
            logger.error(f"Error deleting session for {psid}: {e}")
            return False
    
    def query_sessions_by_email(self, email: str) -> list:
        """
        Query sessions by email (if GSI exists).
        
        Args:
            email: User email
            
        Returns:
            List of sessions
        """
        try:
            # Requires GSI on email field
            response = self.dynamodb_repo.query(
                IndexName="email-index",  # Adjust to your GSI name
                KeyConditionExpression="email = :email",
                ExpressionAttributeValues={":email": email}
            )
            return response.get("Items", [])
        except ClientError as e:
            logger.error(f"Error querying sessions by email: {e}")
            return []
    
    # ========== APPOINTMENT MANAGEMENT ==========
    
    def get_appointment_info(self, psid: str) -> Dict[str, Any]:
        """
        Get appointment booking info for user.
        
        Args:
            psid: User ID
        
        Returns:
            Dict with appointment fields (uses static template)
        """
        try:
            session = self.get_session(psid)
            if not session:
                return APPOINTMENT_TEMPLATE.copy()
            
            return session.get("appointment_info", APPOINTMENT_TEMPLATE.copy())
        
        except Exception as e:
            logger.error(f"Error getting appointment info: {e}")
            return APPOINTMENT_TEMPLATE.copy()
    
    def update_appointment_info(self, psid: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update appointment booking info.
        
        Args:
            psid: User ID
            updates: Dict with fields to update (e.g., {"customer_name": "Nguyen Van A"})
        
        Returns:
            Updated appointment info
        """
        try:
            session = self.get_session(psid)
            if not session:
                # Create new session if not exists
                self.put_session(psid)
                session = self.get_session(psid)
            
            appointment_info = session.get("appointment_info", APPOINTMENT_TEMPLATE.copy())
            
            # Update only valid fields
            for key, value in updates.items():
                if key in APPOINTMENT_TEMPLATE:
                    appointment_info[key] = value
                    logger.info(f"Updated {key} for {psid}: {value}")
            
            self.update_session(psid, {
                "appointment_info": appointment_info,
                "updated_at": int(time.time())
            })
            
            return appointment_info
        
        except Exception as e:
            logger.error(f"Error updating appointment info: {e}")
            return APPOINTMENT_TEMPLATE.copy()
    
    def get_missing_appointment_fields(self, psid: str) -> list:
        """
        Get list of missing appointment fields that need to be filled.
        
        Args:
            psid: User ID
        
        Returns:
            List of field names that are None/empty
        """
        try:
            appointment_info = self.get_appointment_info(psid)
            missing_fields = [
                field for field, value in appointment_info.items()
                if value is None or value == ""
            ]
            return missing_fields
        
        except Exception as e:
            logger.error(f"Error getting missing fields: {e}")
            return list(APPOINTMENT_TEMPLATE.keys())
    
    def reset_appointment_info(self, psid: str) -> bool:
        """
        Reset appointment info to empty template.
        
        Args:
            psid: User ID
            
        Returns:
            True if successful
        """
        try:
            session = self.get_session(psid)
            if not session:
                return False
            
            self.update_session(psid, {
                "appointment_info": APPOINTMENT_TEMPLATE.copy(),
                "updated_at": int(time.time())
            })
            logger.info(f"Reset appointment info for {psid}")
            return True
        
        except Exception as e:
            logger.error(f"Error resetting appointment info: {e}")
            return False
    
    def is_appointment_complete(self, psid: str) -> bool:
        """
        Check if all required appointment fields are filled.
        
        Args:
            psid: User ID
            
        Returns:
            True if all required fields are filled
        """
        missing = self.get_missing_appointment_fields(psid)
        # notes is optional, so exclude it from required fields
        required_missing = [f for f in missing if f != "notes"]
        return len(required_missing) == 0
    
    def get_context_for_llm(self, psid: str) -> str:
        """
        Get formatted context string for LLM prompt from session's conversation_context.
        
        Reads conversation_context from session table and formats as string with turns.
        Can include metadata for cache hit scenarios in chat_handler.
        
        Args:
            psid: User ID
            for_cache: If True, include metadata (intent, source, etc.) in context
        
        Returns:
            Formatted context string with each turn on separate lines
            
        Example output (include_metadata=False):
            Turn 1: User: Xin chào | Assistant: Chào bạn
            Turn 2: User: Lịch hẹn hôm nay | Assistant: Bạn có 2 lịch hẹn...
            
        Example output (include_metadata=True):
            Turn 1 [intent: consultation, source: bedrock]: User: Xin chào | Assistant: Chào bạn
            Turn 2 [intent: schedule_type, source: text2sql, row_count: 2]: User: Lịch hẹn hôm nay | Assistant: Bạn có 2 lịch hẹn...
        """
        try:
            # Get session from DynamoDB
            session = self.get_session(psid)
            if not session:
                logger.warning(f"No session found for {psid}")
                return ""
            
            # Get conversation_context from session
            conversation_context = session.get("conversation_context", [])
            if not conversation_context:
                return ""
            
            # Format turns as string
            context_lines = []
           
            for i, turn in enumerate(conversation_context, 1):
                user_msg = turn.get("user", "")
                assistant_msg = turn.get("assistant", "")
                context_lines.append(f"Turn {i}: User: {user_msg} | Assistant: {assistant_msg}")
            return "\n".join(context_lines)
            #  context cho LLM schedule không cần metadata 
            # vì schema bị giới hạn bởi question hiện tại user
                
            
            
        
        except Exception as e:
            logger.error(f"Error getting context for LLM: {e}")
            return ""