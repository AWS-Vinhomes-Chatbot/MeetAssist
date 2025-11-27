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


class SessionService:
    """Service for managing user sessions."""
    
    def __init__(self, dynamodb_repo=None):
        """
        Initialize SessionService.
        
        Args:
            dynamodb_repo: DynamoDBRepository instance. If None, creates default instance.
        
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
        
        # ✅ Load security settings from environment
        self.MAX_OTP_ATTEMPTS = int(os.environ.get("MAX_OTP_ATTEMPTS", "5"))
        self.OTP_REQUEST_COOLDOWN = int(os.environ.get("OTP_REQUEST_COOLDOWN", "60"))
        self.MAX_OTP_REQUESTS_PER_HOUR = int(os.environ.get("MAX_OTP_REQUESTS_PER_HOUR", "3"))
        self.BLOCK_DURATION_SECONDS = int(os.environ.get("BLOCK_DURATION_SECONDS", "3600"))
        self.OTP_EXPIRY_SECONDS = int(os.environ.get("OTP_EXPIRY_SECONDS", "300"))
    
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
    
    
    
    def add_message_to_history(self, psid: str, user_msg: str, assistant_msg: str) -> bool:
        """Add message to conversation history."""
        try:
            session = self.get_session(psid)
            if not session:
                return False
            
            history = session.get("conversation_history", [])
            history.append({
                "user": user_msg,
                "assistant": assistant_msg,
                "timestamp": int(time.time())
            })
            
            # Keep only last 20 messages
            if len(history) > 20:
                history = history[-20:]
            
            self.update_session(psid, {
                "conversation_history": history
            })
            return True
        except Exception as e:
            logger.error(f"Error adding message to history: {e}")
            return False
    
    def get_cached_answer(self, question: str) -> Optional[str]:
        """Get cached answer from DynamoDB FAQ table."""
        try:
            # Implement cache lookup logic
            # This would query a separate FAQ/Cache table
            return None  # Placeholder
        except Exception as e:
            logger.error(f"Error getting cached answer: {e}")
            return None
    
    def cache_answer(self, question: str, answer: str) -> bool:
        """Cache answer in DynamoDB."""
        try:
            # Implement cache storage logic
            return True  # Placeholder
        except Exception as e:
            logger.error(f"Error caching answer: {e}")
            return False
    
    def put_session(self, session_data: Dict[str, Any]) -> bool:
        """
        Create or replace entire session.
        
        Args:
            session_data: Complete session data dict
            
        Returns:
            True if successful
        """
        try:
            self.dynamodb_repo.put_item(Item=session_data)
            return True
        except ClientError as e:
            logger.error(f"Error putting session: {e}")
            return False
    
    def update_session(self, psid: str, updates: Dict[str, Any]) -> bool:
        """
        Update specific fields in session.
        
        Args:
            psid: Page-Scoped ID
            updates: Dict of fields to update
            
        Returns:
            True if successful
        """
        try:
            # Build update expression
            update_expr = "SET " + ", ".join([f"#{k} = :{k}" for k in updates.keys()])
            
            # Build expression attribute names (handle reserved keywords)
            expr_names = {f"#{k}": k for k in updates.keys()}
            
            # Build expression attribute values
            expr_values = {f":{k}": v for k, v in updates.items()}
            
            self.dynamodb_repo.update_item(
                Key={"psid": psid},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values
            )
            return True
            
        except ClientError as e:
            logger.error(f"Error updating session for {psid}: {e}")
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