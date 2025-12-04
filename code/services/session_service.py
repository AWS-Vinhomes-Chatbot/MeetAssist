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
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple, List
from botocore.exceptions import ClientError
import numpy as np

logger = logging.getLogger()


def _convert_floats_to_decimal(obj: Any) -> Any:
    """
    Recursively convert all float values in a dict/list to Decimal for DynamoDB.
    DynamoDB does not support Python float type.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: _convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_floats_to_decimal(i) for i in obj]
    return obj


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
    "email": None,
    "appointment_date": None,
    "appointment_time": None,
    "appointment_end_time": None,  # Giờ kết thúc (từ ConsultantSchedule - để tham khảo)
    "consultant_name": None,
    "consultant_id": None,  # ID của tư vấn viên (từ cache)
    "customer_id": None,  # ID của khách hàng (từ cache hoặc session)
    "notes": None,
    "booking_state": "idle",  # idle, selecting_slot, selecting_appointment, selecting_new_slot, collecting, confirming, completed
    "booking_action": "create",  # create, update, cancel
    ### Fields for UPDATE/CANCEL flow
    "appointment_id": None,  # ID của lịch hẹn cần update/cancel
    # Fields cho UPDATE flow - lưu thông tin cũ để so sánh
    "old_date": None,
    "old_time": None,
    "old_consultant_id": None,
    "old_consultant_name": None,
    # Cache data
    "cached_appointments": [],  # Cache danh sách lịch hẹn của user (cho update/cancel)
    "cached_available_slots": [],  # Cache các slot trống (cho create/update)
    "slot_cache_timestamp": None,  # Timestamp khi cache slot
    "selected_slot_index": None  # Index slot user đã chọn
}

# Session timeout settings
SESSION_TIMEOUT_SECONDS = 1800  # 30 phút không hoạt động → reset session
SLOT_CACHE_TTL_SECONDS = 300    # 5 phút → refresh slot cache
BOOKING_FLOW_TIMEOUT_SECONDS = 600  # 10 phút trong booking flow → auto reset

# Required fields for CREATE - giờ cần tên, SĐT, email (slot đã chọn từ cache)
CREATE_REQUIRED_FIELDS = ["customer_name", "phone_number", "email"]

# Required fields for update/cancel (chỉ cần appointment_id)
UPDATE_REQUIRED_FIELDS = ["appointment_id"]
CANCEL_REQUIRED_FIELDS = ["appointment_id"]


def get_required_fields(booking_action: str = "create") -> List[str]:
    """
    Get required fields based on booking action.
    
    Args:
        booking_action: "create", "update", or "cancel"
        
    Returns:
        List of required field names
    """
    # For cancel, only need appointment_id
    if booking_action == "cancel":
        return CANCEL_REQUIRED_FIELDS
    
    # For update, need appointment_id plus fields being updated
    if booking_action == "update":
        return UPDATE_REQUIRED_FIELDS
    
    # For create, need full info
    return CREATE_REQUIRED_FIELDS


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
        
        # ✅ Deduplication: keep track of processed message IDs
        self.PROCESSED_MESSAGES_TTL = 300  # 5 minutes TTL for processed message IDs
        self.MAX_PROCESSED_MESSAGES = 50   # Max messages to keep per user
        
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
    
    # ========== SESSION TIMEOUT MANAGEMENT ==========
    
    def update_last_activity(self, psid: str) -> bool:
        """
        Update last activity timestamp for session.
        Should be called on every user interaction.
        
        Args:
            psid: User ID
            
        Returns:
            True if successful
        """
        try:
            from datetime import datetime
            
            self.dynamodb_repo.update_item(
                key={"psid": psid},
                updates={"last_activity": datetime.now().isoformat()}
            )
            return True
        except Exception as e:
            logger.error(f"Error updating last activity: {e}")
            return False
    
    # ========== MESSAGE DEDUPLICATION ==========
    
    def is_message_processed(self, psid: str, message_id: str) -> bool:
        """
        Check if a message has already been processed (for deduplication).
        Facebook may retry webhook calls, causing duplicate processing.
        
        Args:
            psid: User ID
            message_id: Facebook message ID (mid)
            
        Returns:
            True if message was already processed
        """
        if not message_id:
            return False
            
        try:
            import time
            
            session = self.get_session(psid)
            if not session:
                return False
            
            processed_messages = session.get("processed_messages", [])
            current_time = int(time.time())
            
            # Check if message_id exists in processed list (within TTL)
            for entry in processed_messages:
                if entry.get("mid") == message_id:
                    entry_time = entry.get("timestamp", 0)
                    if current_time - entry_time < self.PROCESSED_MESSAGES_TTL:
                        logger.info(f"Duplicate message detected for {psid}: {message_id}")
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking message deduplication: {e}")
            return False
    
    def mark_message_processed(self, psid: str, message_id: str) -> bool:
        """
        Mark a message as processed for deduplication.
        
        Args:
            psid: User ID
            message_id: Facebook message ID (mid)
            
        Returns:
            True if successful
        """
        if not message_id:
            return True  # No message_id to track
            
        try:
            import time
            
            session = self.get_session(psid)
            if not session:
                return False
            
            processed_messages = session.get("processed_messages", [])
            current_time = int(time.time())
            
            # Clean up old entries (beyond TTL)
            processed_messages = [
                entry for entry in processed_messages
                if current_time - entry.get("timestamp", 0) < self.PROCESSED_MESSAGES_TTL
            ]
            
            # Add new entry
            processed_messages.append({
                "mid": message_id,
                "timestamp": current_time
            })
            
            # Keep only the latest N entries
            if len(processed_messages) > self.MAX_PROCESSED_MESSAGES:
                processed_messages = processed_messages[-self.MAX_PROCESSED_MESSAGES:]
            
            self.dynamodb_repo.update_item(
                key={"psid": psid},
                updates={"processed_messages": processed_messages}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error marking message as processed: {e}")
            return False

    def is_session_expired(self, psid: str) -> bool:
        """
        Check if session has expired (no activity for SESSION_TIMEOUT_SECONDS).
        
        Args:
            psid: User ID
            
        Returns:
            True if session expired
        """
        try:
            from datetime import datetime
            
            session = self.get_session(psid)
            if not session:
                return True
            
            last_activity = session.get("last_activity")
            if not last_activity:
                return False  # No timestamp = legacy session, don't expire
            
            last_time = datetime.fromisoformat(last_activity)
            age = (datetime.now() - last_time).total_seconds()
            
            return age > SESSION_TIMEOUT_SECONDS
            
        except Exception as e:
            logger.error(f"Error checking session expiry: {e}")
            return False
    
    def is_booking_flow_expired(self, psid: str) -> bool:
        """
        Check if booking flow has expired (started but not completed within timeout).
        
        Args:
            psid: User ID
            
        Returns:
            True if booking flow expired
        """
        try:
            from datetime import datetime
            
            appointment_info = self.get_appointment_info(psid)
            booking_state = appointment_info.get("booking_state", "idle")
            
            # Only check timeout for active booking flows
            if booking_state == "idle":
                return False
            
            # Check slot_cache_timestamp as proxy for when booking started
            timestamp_str = appointment_info.get("slot_cache_timestamp")
            if not timestamp_str:
                return False
            
            start_time = datetime.fromisoformat(timestamp_str)
            age = (datetime.now() - start_time).total_seconds()
            
            return age > BOOKING_FLOW_TIMEOUT_SECONDS
            
        except Exception as e:
            logger.error(f"Error checking booking flow expiry: {e}")
            return False
    
    def check_and_reset_expired_session(self, psid: str) -> Tuple[bool, str]:
        """
        Check if session or booking flow expired and reset if needed.
        
        Args:
            psid: User ID
            
        Returns:
            Tuple of (was_reset, message)
        """
        try:
            # Check session expiry
            if self.is_session_expired(psid):
                self.reset_session(psid)
                logger.info(f"Session expired for {psid}, reset")
                return True, "Phiên làm việc đã hết hạn do không hoạt động. Bạn có thể bắt đầu lại!"
            
            # Check booking flow expiry
            if self.is_booking_flow_expired(psid):
                self.reset_appointment_info(psid)
                self.set_booking_state(psid, "idle")
                logger.info(f"Booking flow expired for {psid}, reset")
                return True, "Thao tác đặt lịch đã hết thời gian. Bạn có thể bắt đầu lại bằng cách nói 'đặt lịch'."
            
            return False, ""
            
        except Exception as e:
            logger.error(f"Error checking session expiry: {e}")
            return False, ""
    
    def reset_session(self, psid: str) -> bool:
        """
        Fully reset session - clear conversation context and appointment info.
        
        Args:
            psid: User ID
            
        Returns:
            True if successful
        """
        try:
            from datetime import datetime
            
            self.dynamodb_repo.update_item(
                key={"psid": psid},
                updates={
                    "conversation_context": [],
                    "appointment_info": APPOINTMENT_TEMPLATE.copy(),
                    "current_intent": "unknown",
                    "last_activity": datetime.now().isoformat()
                }
            )
            logger.info(f"Session fully reset for {psid}")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting session: {e}")
            return False
    
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
                
                # Skip turns without sql_result in metadata (empty results shouldn't be cached)
                turn_metadata = turn.get("metadata", {})
                if not turn_metadata or not turn_metadata.get("sql_result"):
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
                        "metadata": turn_metadata,
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
                "metadata": _convert_floats_to_decimal(metadata) if metadata else {},
                "timestamp": int(msg_data.get("timestamp") or int(time.time()))
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
            
            self.dynamodb_repo.update_item(
                key={"psid": psid},
                updates={
                    "appointment_info": appointment_info,
                    "updated_at": int(time.time())
                }
            )
            
            return appointment_info
        
        except Exception as e:
            logger.error(f"Error updating appointment info: {e}")
            return APPOINTMENT_TEMPLATE.copy()
    
    def get_missing_appointment_fields(self, psid: str) -> list:
        """
        Get list of missing REQUIRED appointment fields based on booking_action.
        
        Args:
            psid: User ID
        
        Returns:
            List of required field names that are None/empty
        """
        try:
            appointment_info = self.get_appointment_info(psid)
            booking_action = appointment_info.get("booking_action", "create")
            
            # Get required fields based on action
            required_fields = get_required_fields(booking_action)
            
            # Find missing required fields
            missing_fields = [
                field for field in required_fields
                if appointment_info.get(field) is None or appointment_info.get(field) == ""
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
            
            self.dynamodb_repo.update_item(
                key={"psid": psid},
                updates={
                    "appointment_info": APPOINTMENT_TEMPLATE.copy(),
                    "updated_at": int(time.time())
                }
            )
            logger.info(f"Reset appointment info for {psid}")
            return True
        
        except Exception as e:
            logger.error(f"Error resetting appointment info: {e}")
            return False
    
    def is_appointment_complete(self, psid: str) -> bool:
        """
        Check if all required appointment fields are filled.
        
        Required: customer_name, phone_number, appointment_date, 
                  appointment_time, consultant_name
        notes is always optional.
        
        Args:
            psid: User ID
            
        Returns:
            True if all required fields are filled
        """
        missing = self.get_missing_appointment_fields(psid)
        return len(missing) == 0
    
    def set_booking_state(self, psid: str, state: str) -> bool:
        """
        Set the booking state for a user's appointment flow.
        
        Valid states:
        - "idle": No active booking
        - "selecting_slot": CREATE - choosing available slot
        - "selecting_appointment": UPDATE/CANCEL - choosing which appointment to modify
        - "selecting_new_slot": UPDATE - choosing new slot after selecting appointment
        - "collecting": Collecting additional info (name, phone for CREATE)
        - "confirming": Waiting for user confirmation
        - "confirming_restart": Asking if user wants to continue or restart
        - "completed": Booking finished
        
        Args:
            psid: User ID
            state: New booking state
            
        Returns:
            True if successful
        """
        valid_states = ["idle", "selecting_slot", "selecting_appointment", "selecting_new_slot", "collecting", "confirming", "confirming_restart", "completed"]
        if state not in valid_states:
            logger.error(f"Invalid booking state: {state}")
            return False
        
        return self.update_appointment_info(psid, {"booking_state": state})
    
    def get_booking_state(self, psid: str) -> str:
        """
        Get current booking state for a user.
        
        Args:
            psid: User ID
            
        Returns:
            Current booking state ("idle", "collecting", "confirming", "completed")
        """
        appointment_info = self.get_appointment_info(psid)
        return appointment_info.get("booking_state", "idle")
    
    def cache_user_appointments(self, psid: str, appointments: list) -> bool:
        """
        Cache user's appointments list for selection (update/cancel flow).
        Maps index (1, 2, 3...) to appointment details including hidden ID.
        
        Args:
            psid: User ID
            appointments: List of appointment dicts from DB query
            
        Returns:
            True if successful
        """
        try:
            # Store appointments with index mapping
            # Handle various column name formats from PostgreSQL (lowercase) or aliases
            cached = []
            for i, apt in enumerate(appointments[:10], 1):  # Max 10 appointments
                cached.append({
                    "index": i,
                    "appointment_id": apt.get("appointmentid", apt.get("appointment_id", apt.get("id"))),
                    "customer_id": apt.get("customerid", apt.get("customer_id")),
                    "customer_name": apt.get("customer_name", apt.get("fullname")),  # Tên khách hàng
                    "phone_number": apt.get("phone_number", apt.get("phonenumber")),  # SĐT
                    "consultant_id": apt.get("consultantid", apt.get("consultant_id")),
                    "appointment_date": apt.get("date", apt.get("appointmentdate", apt.get("appointment_date"))),
                    "start_time": apt.get("time", apt.get("starttime", apt.get("start_time"))),
                    "end_time": apt.get("endtime", apt.get("end_time")),
                    "consultant_name": apt.get("consultant_name", apt.get("fullname", apt.get("name"))),
                    "status": apt.get("status"),
                    "notes": apt.get("description", apt.get("notes", apt.get("note")))
                })
            
            self.update_appointment_info(psid, {"cached_appointments": cached})
            logger.info(f"Cached {len(cached)} appointments for {psid}")
            return True
            
        except Exception as e:
            logger.error(f"Error caching appointments: {e}")
            return False
    
    def get_cached_appointment_by_index(self, psid: str, index: int) -> Optional[Dict]:
        """
        Get cached appointment by user's selection index (1, 2, 3...).
        
        Args:
            psid: User ID
            index: User's selection (1-based)
            
        Returns:
            Appointment dict or None if not found
        """
        try:
            appointment_info = self.get_appointment_info(psid)
            cached = appointment_info.get("cached_appointments", [])
            
            for apt in cached:
                if apt.get("index") == index:
                    return apt
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting cached appointment: {e}")
            return None
    
    def has_pending_booking(self, psid: str) -> Tuple[bool, Dict]:
        """
        Check if user has an unfinished booking flow.
        
        Args:
            psid: User ID
            
        Returns:
            Tuple of (has_pending, appointment_info)
        """
        try:
            appointment_info = self.get_appointment_info(psid)
            booking_state = appointment_info.get("booking_state", "idle")
            
            if booking_state in ["selecting_slot", "selecting_appointment", "selecting_new_slot", "collecting", "confirming"]:
                return True, appointment_info
            
            return False, {}
            
        except Exception as e:
            logger.error(f"Error checking pending booking: {e}")
            return False, {}
    
    def cache_available_slots(self, psid: str, slots: list) -> bool:
        """
        Cache available appointment slots for CREATE flow.
        Maps index (1, 2, 3...) to slot details (consultant, date, time).
        
        Args:
            psid: User ID
            slots: List of available slot dicts from DB query
            
        Returns:
            True if successful
        """
        try:
            from datetime import datetime
            
            cached = []
            for i, slot in enumerate(slots[:10], 1):  # Max 10 slots
                # Handle various column name formats from PostgreSQL (lowercase) or aliases
                cached.append({
                    "index": i,
                    "consultant_id": slot.get("consultantid", slot.get("consultant_id")),
                    "consultant_name": slot.get("fullname", slot.get("consultant_name", slot.get("name"))),
                    "specialization": slot.get("specialties", slot.get("specialization", slot.get("specialty"))),
                    "date": slot.get("date", slot.get("available_date")),
                    "time": slot.get("starttime", slot.get("start_time", slot.get("time", slot.get("available_time")))),
                    "end_time": slot.get("endtime", slot.get("end_time")),
                    "email": slot.get("email")
                })
            
            self.update_appointment_info(psid, {
                "cached_available_slots": cached,
                "slot_cache_timestamp": datetime.now().isoformat()
            })
            logger.info(f"Cached {len(cached)} available slots for {psid}")
            return True
            
        except Exception as e:
            logger.error(f"Error caching available slots: {e}")
            return False
    
    def get_cached_slot_by_index(self, psid: str, index: int) -> Optional[Dict]:
        """
        Get cached available slot by user's selection index (1, 2, 3...).
        
        Args:
            psid: User ID
            index: User's selection (1-based)
            
        Returns:
            Slot dict or None if not found
        """
        try:
            appointment_info = self.get_appointment_info(psid)
            cached = appointment_info.get("cached_available_slots", [])
            
            for slot in cached:
                if slot.get("index") == index:
                    return slot
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting cached slot: {e}")
            return None
    
    def is_slot_cache_stale(self, psid: str, max_age_seconds: int = 300) -> bool:
        """
        Check if cached slots are stale (older than max_age_seconds).
        Default 5 minutes for safety.
        
        Args:
            psid: User ID
            max_age_seconds: Maximum cache age in seconds (default 300 = 5 min)
            
        Returns:
            True if cache is stale or doesn't exist
        """
        try:
            from datetime import datetime
            
            appointment_info = self.get_appointment_info(psid)
            timestamp_str = appointment_info.get("slot_cache_timestamp")
            
            if not timestamp_str:
                return True
            
            cache_time = datetime.fromisoformat(timestamp_str)
            age = (datetime.now() - cache_time).total_seconds()
            
            return age > max_age_seconds
            
        except Exception as e:
            logger.error(f"Error checking slot cache staleness: {e}")
            return True
    
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