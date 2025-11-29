"""
Session Service - Manages user sessions, authentication state, and conversation caching.

Responsibilities:
- Session CRUD operations
- OTP generation and verification
- Rate limiting
- Conversation history
- Cache management with embedding-based similarity search
"""

import os
import json
import secrets
import time
import hmac
import logging
from typing import Dict, Any, Optional, Tuple, List
from botocore.exceptions import ClientError
import numpy as np

logger = logging.getLogger()


def _vector_to_string(vector: List[float]) -> str:
    """
    Convert vector (list of floats) to JSON string for DynamoDB storage.
    DynamoDB does not support Python float type, so we store as string.
    """
    if vector is None:
        return None
    return json.dumps(vector)


def _string_to_vector(vector_str: str) -> List[float]:
    """
    Convert JSON string back to vector (list of floats) for computation.
    """
    if vector_str is None:
        return None
    if isinstance(vector_str, list):
        # Already a list, just ensure floats
        return [float(x) for x in vector_str]
    return json.loads(vector_str)


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
    """Service for managing user sessions and conversation caching."""
    
    def __init__(self, dynamodb_repo=None, messenger_service=None, embed_service=None, similarity_threshold: float = None):
        """
        Initialize SessionService with integrated caching.
        
        Args:
            dynamodb_repo: DynamoDBRepository instance. If None, creates default instance.
            messenger_service: MessengerService instance. If None, creates default instance.
            embed_service: EmbeddingService instance for vector search. If None, uses singleton.
            similarity_threshold: Min cosine similarity for cache hit (default 0.8)
        
        Example:
            # Use default instances (auto-creates from env vars)
            service = SessionService()
            
            # Inject custom repo (for testing)
            mock_repo = MagicMock()
            service = SessionService(dynamodb_repo=mock_repo)
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
        
        # Embedding service for cache similarity search
        if embed_service is None:
            from services.embed import EmbeddingService
            embed_service = EmbeddingService()  # Uses singleton client
        self.embed_service = embed_service
        
        # Cache settings
        self.similarity_threshold = similarity_threshold or float(os.environ.get("CACHE_SIMILARITY_THRESHOLD", "0.8"))
        
        # ✅ Load context settings from environment
        self.MAX_CONTEXT_TURNS = int(os.environ.get("MAX_CONTEXT_TURNS", "3"))
        
        logger.info(f"SessionService initialized: similarity_threshold={self.similarity_threshold}")
    
    def get_session(self, psid: str) -> Optional[Dict[str, Any]]:
        """
        Get session by PSID.
        
        Args:
            psid: Page-Scoped ID
            
        Returns:
            Session dict or None
        """
        try:
            response = self.dynamodb_repo.get_item(key={"psid": psid})
            return response
        except ClientError as e:
            logger.error(f"Error getting session for {psid}: {e}")
            return None
    
    # ========== CACHE METHODS (integrated from CacheService) ==========
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
        
        Returns:
            Cosine similarity score (0 to 1)
        """
        try:
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            
            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            return max(0.0, min(1.0, float(similarity)))
        
        except Exception as e:
            logger.error(f"Error calculating cosine similarity: {e}")
            return 0.0
    
    def search_cache(self, psid: str, user_question: str) -> Optional[Dict[str, Any]]:
        """
        Search for similar questions in the user's conversation_context.
        
        Flow:
        1. Get session by psid
        2. Embed the user question
        3. Compare with cached turn vectors in conversation_context
        4. Return best match if similarity >= threshold
        
        Args:
            psid: User's PSID to search in their session
            user_question: Question to search for
            
        Returns:
            Cached turn data if hit, None if no cache hit
        """
        try:
            # Get session by psid
            session = self.get_session(psid)
            if not session:
                logger.info(f"No session found for {psid}, cache miss")
                return None
            
            conversation_context = session.get("conversation_context", [])
            if not conversation_context:
                logger.info(f"No conversation_context for {psid}, cache miss")
                return None
            
            # Embed current question
            query_vector = self.embed_service.get_embedding(user_question)
            
            best_match = None
            best_score = 0.0
            
            for turn in conversation_context:
                # Skip turns without vector embedding
                cached_vector = turn.get("vector")
                if not cached_vector:
                    continue
                
                # Convert string back to vector for computation
                cached_vector = _string_to_vector(cached_vector)
                
                # Calculate similarity
                similarity = self._cosine_similarity(query_vector, cached_vector)
                
                if similarity >= self.similarity_threshold and similarity > best_score:
                    best_score = similarity
                    best_match = {
                        "user": turn.get("user"),
                        "assistant": turn.get("assistant"),
                        "metadata": turn.get("metadata", {}),
                        "vector_score": round(similarity, 3)
                    }
            
            if best_match:
                logger.info(f"Cache HIT for {psid}: '{user_question[:50]}...' with score {best_score:.3f}")
                return best_match
            else:
                logger.info(f"Cache MISS for {psid}: '{user_question[:50]}...'")
                return None
                
        except Exception as e:
            logger.error(f"Error searching cache for {psid}: {e}")
            return None
    
    def get_embedding_vector(self, user_msg: str) -> Optional[List[float]]:
        """
        Get vector embedding for a user message.
        
        Args:
            user_msg: User's message to embed
            
        Returns:
            Vector embedding list or None if failed
        """
        try:
            return self.embed_service.get_embedding(user_msg)
        except Exception as e:
            logger.warning(f"Failed to embed question: {e}")
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
            vector = self.get_embedding_vector(user_msg)
            if not psid:
                logger.error("No PSID found in message")
                return False
            
            # Get session
            session = self.get_session(psid)
            if not session:
                return False
            intent = session.get("current_intent","unknown")
            history = session.get("conversation_context", [])
            
            # Ensure all existing vectors are stored as strings (fix legacy data)
            for turn in history:
                if turn.get("vector") and isinstance(turn["vector"], list):
                    turn["vector"] = _vector_to_string(turn["vector"])
            
            history.append({
                "user": user_msg,
                "vector": _vector_to_string(vector),  # Store as JSON string
                "assistant": assistant_msg,
                "intent": intent,
                "metadata": metadata or {},
                "timestamp": msg_data.get("timestamp") or int(time.time())
            })
            
            # Keep only last MAX_CONTEXT_TURNS messages (default 3)
            if len(history) > self.MAX_CONTEXT_TURNS:
                history = history[-self.MAX_CONTEXT_TURNS:]
                logger.info(f"Trimmed context for {psid}, kept last {self.MAX_CONTEXT_TURNS} turns")
            
            self.dynamodb_repo.update_item(key={"psid": psid}, updates={
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
            self.dynamodb_repo.put_item(item=session)
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
            self.dynamodb_repo.delete_item(key={"psid": psid})
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
            from boto3.dynamodb.conditions import Key
            response = self.dynamodb_repo.query(
                key_condition_expression=Key("email").eq(email),
                expression_attribute_values={
                    ":email": email
                }
            )
            return response or []
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
        
        Args:
            psid: User ID
        
        Returns:
            Formatted context string with each turn on separate lines
            
        Example output:
            Turn 1: User: Xin chào | Assistant: Chào bạn
            Turn 2: User: Lịch hẹn hôm nay | Assistant: Bạn có 2 lịch hẹn...
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
        
        except Exception as e:
            logger.error(f"Error getting context for LLM: {e}")
            return ""