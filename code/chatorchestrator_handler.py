"""
Chat Orchestrator - Central routing and coordination for all chat interactions.

This module handles:
1. Authentication flow (OTP)
2. Intent classification (SQL query vs Direct answer)
3. Routing to appropriate service (Bedrock Q&A, Text-to-SQL, DynamoDB cache)
4. Response generation and delivery
"""

import logging
from typing import Dict, Any, Optional
from handlers.auth_handler import AuthHandler
from handlers.chat_handler import ChatHandler
from services.session_service import SessionService
from services.bedrock_qa import BedrockQAService
from services.intent_classifier import IntentClassifier
from services.text_to_sql import TextToSQLService
from repositories.dynamodb_repo import DynamoDBRepository
from repositories.ses_repo import SESRepository

logger = logging.getLogger()


class ChatOrchestrator:
    """
    Orchestrates the entire chat flow from authentication to response generation.
    
    This class acts as the central coordinator, deciding which handler/service
    to invoke based on user state and message content.
    """
    
    def __init__(self):
        """Initialize all services and handlers."""
        # Repositories (Data Access Layer)
        self.dynamodb_repo = DynamoDBRepository()
        self.ses_repo = SESRepository()
        
        # Services (Business Logic)
        self.session_service = SessionService(self.dynamodb_repo)
        self.bedrock_qa = BedrockQAService()
        self.intent_classifier = IntentClassifier()
        self.text_to_sql = TextToSQLService()
        
        # Handlers (Request Processing)
        self.auth_handler = AuthHandler(
            session_service=self.session_service,
            ses_repo=self.ses_repo
        )
        self.chat_handler = ChatHandler(
            bedrock_qa=self.bedrock_qa,
            intent_classifier=self.intent_classifier,
            text_to_sql=self.text_to_sql,
            session_service=self.session_service
        )
    
    async def process_message(self, psid: str, message_text: str) -> Dict[str, Any]:
        """
        Main entry point for processing user messages.
        
        Flow:
        1. Get user session
        2. Check authentication state
        3. If not authenticated → AuthHandler
        4. If authenticated → ChatHandler
        
        Args:
            psid: Facebook Page-Scoped ID
            message_text: User's message text
            
        Returns:
            Dict containing response message and metadata
        """
        try:
            # Step 1: Get current session state
            session = await self.session_service.get_session(psid)
            
            # Step 2: Route based on authentication state
            if not session or not session.is_authenticated:
                # Handle authentication flow (OTP)
                return await self.auth_handler.handle(psid, message_text, session)
            else:
                # Handle authenticated chat
                return await self.chat_handler.handle(psid, message_text, session)
                
        except Exception as e:
            logger.error(f"Error in ChatOrchestrator.process_message: {e}", exc_info=True)
            return {
                "success": False,
                "message": "Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại sau.",
                "error": str(e)
            }
    
    async def handle_postback(self, psid: str, payload: str) -> Dict[str, Any]:
        """
        Handle Facebook Messenger postback events (button clicks, quick replies).
        
        Args:
            psid: Facebook Page-Scoped ID
            payload: Postback payload
            
        Returns:
            Dict containing response
        """
        try:
            session = await self.session_service.get_session(psid)
            
            # Route postbacks to appropriate handler
            if payload.startswith("AUTH_"):
                return await self.auth_handler.handle_postback(psid, payload, session)
            else:
                return await self.chat_handler.handle_postback(psid, payload, session)
                
        except Exception as e:
            logger.error(f"Error handling postback: {e}")
            return {"success": False, "message": "Lỗi xử lý postback"}
