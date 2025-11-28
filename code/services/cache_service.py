"""
Cache Service - Manages conversation context with embedding-based caching.

Responsibilities:
- Search for similar questions across all user sessions using vector similarity
- If cache hit: return cached response
- If no cache hit: embed current turn and store in conversation_context
- Vector and metadata stored in conversation_context turns (managed by session_service)
- Provide context for LLM responses
"""
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger()




class CacheService:
    """
    Service for caching conversation with embedding-based similarity search.
    
    Features:
    - Search for cached responses across all user sessions using vector similarity
    - If cache hit: return cached response (no need to call LLM/RAG/SQL)
    - If no cache hit: embed current turn and add to conversation_context
    - Vector and metadata stored directly in conversation_context turns
    - Turn limit managed by session_service.add_message_to_history()
    """
    
    def __init__(
        self, 
        dynamodb_repo=None,
        embed_service=None,
        session_service=None,
        similarity_threshold: float = None
    ):
        """
        Initialize CacheService.
        
        Args:
            dynamodb_repo: DynamoDB repository instance
            embed_service: Embedding service instance (for vector search)
            session_service: Session service instance (for managing turns)
            similarity_threshold: Min cosine similarity for cache hit (default 0.8)
        """
        # Dependency injection with lazy loading
        if dynamodb_repo is None:
            from repositories.dynamodb_repo import DynamoDBRepository
            dynamodb_repo = DynamoDBRepository()
        
        if embed_service is None:
            from services.embed import EmbeddingService
            embed_service = EmbeddingService()
        if session_service is None:
            from services.session_service import SessionService
            session_service = SessionService()
            
        self.dynamodb_repo = dynamodb_repo
        self.embed_service = embed_service
        self.session_service = session_service
        self.similarity_threshold = similarity_threshold or float(os.environ.get("CACHE_SIMILARITY_THRESHOLD", "0.8"))
        
        logger.info(f"CacheService initialized: similarity_threshold={self.similarity_threshold}")
    
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
        Search for similar questions in the user's own conversation_context.
        
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
            session = self.session_service.get_session(psid)
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
                
                # Parse vector if stored as string
                if isinstance(cached_vector, str):
                    cached_vector = json.loads(cached_vector)
                
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
    
    def get_cache_data(self, psid: str, user_msg: str) -> Optional[List[float]]:
        """
        Get vector embedding for a user message for caching purposes.
        
        Args:
            psid: User's PSID
            user_msg: User's message to embed
            
        Returns:
            Vector embedding list or None if failed
        """
        try:
            # Get current session (ensure it exists)
            session = self.session_service.get_session(psid)
            if not session:
                logger.warning(f"Session not found for {psid}, creating new")
                self.session_service.put_session(psid)
            
            # Embed the user question
            try:
                vector = self.embed_service.get_embedding(user_msg)
                return vector
            except Exception as e:
                logger.warning(f"Failed to embed question: {e}")
                return None
            
        except Exception as e:
            logger.error(f"Error getting cache data: {e}")
            return None
    
    
    
    
    