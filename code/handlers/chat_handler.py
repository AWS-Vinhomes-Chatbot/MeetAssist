"""
Chat Handler - Processes authenticated user messages.

Flow:
1. Classify intent (SQL query vs Direct answer)
2. Route to appropriate service
3. Generate and return response
"""

import logging
from typing import Dict, Any

logger = logging.getLogger()


class ChatHandler:
    """Handles chat messages from authenticated users."""
    
    def __init__(self, bedrock_qa, intent_classifier, text_to_sql, session_service):
        """
        Initialize ChatHandler.
        
        Args:
            bedrock_qa: Bedrock Q&A service
            intent_classifier: Intent classification service
            text_to_sql: Text-to-SQL service
            session_service: Session management service
        """
        self.bedrock_qa = bedrock_qa
        self.intent_classifier = intent_classifier
        self.text_to_sql = text_to_sql
        self.session_service = session_service
    
    async def handle(self, psid: str, message_text: str, session: Any) -> Dict[str, Any]:
        """
        Process chat message and generate response.
        
        Flow:
        1. Classify intent → "sql_query" or "direct_answer"
        2. If SQL: Use Text-to-SQL + Execute query
        3. If Direct: Use Bedrock Q&A or DynamoDB cache
        
        Args:
            psid: User ID
            message_text: User's question/message
            session: Current session
            
        Returns:
            Dict with response message
        """
        try:
            # Step 1: Classify intent
            intent = await self.intent_classifier.classify(message_text)
            logger.info(f"Intent classified as: {intent['type']}")
            
            # Step 2: Route to appropriate service
            if intent['type'] == 'sql_query':
                response = await self._handle_sql_query(psid, message_text, session)
            elif intent['type'] == 'direct_answer':
                response = await self._handle_direct_answer(psid, message_text, session)
            else:
                # Fallback to Bedrock Q&A
                response = await self._handle_general_question(psid, message_text, session)
            
            # Step 3: Update session with conversation history
            await self.session_service.add_message_to_history(psid, message_text, response['message'])
            
            return response
            
        except Exception as e:
            logger.error(f"Error in ChatHandler.handle: {e}", exc_info=True)
            return {
                "success": False,
                "message": "Xin lỗi, tôi gặp lỗi khi xử lý câu hỏi của bạn. Vui lòng thử lại."
            }
    
    async def _handle_sql_query(self, psid: str, question: str, session: Any) -> Dict[str, Any]:
        """
        Handle questions that require SQL query execution.
        
        Args:
            psid: User ID
            question: User's question
            session: Current session
            
        Returns:
            Dict with query results formatted as natural language
        """
        try:
            # Generate SQL from natural language
            sql_result = await self.text_to_sql.generate_sql(question)
            
            if not sql_result['success']:
                return {
                    "success": False,
                    "message": "Xin lỗi, tôi không thể tạo truy vấn SQL cho câu hỏi này."
                }
            
            sql_query = sql_result['sql']
            logger.info(f"Generated SQL: {sql_query}")
            
            # Execute SQL query
            query_result = await self.text_to_sql.execute_sql(sql_query)
            
            if not query_result['success']:
                return {
                    "success": False,
                    "message": "Xin lỗi, có lỗi khi thực thi truy vấn."
                }
            
            # Format results as natural language using Bedrock
            formatted_response = await self.bedrock_qa.format_query_results(
                question=question,
                sql=sql_query,
                results=query_result['data']
            )
            
            return {
                "success": True,
                "message": formatted_response,
                "metadata": {
                    "type": "sql_query",
                    "sql": sql_query,
                    "row_count": len(query_result['data'])
                }
            }
            
        except Exception as e:
            logger.error(f"Error in _handle_sql_query: {e}")
            return {
                "success": False,
                "message": "Đã xảy ra lỗi khi truy vấn dữ liệu."
            }
    
    async def _handle_direct_answer(self, psid: str, question: str, session: Any) -> Dict[str, Any]:
        """
        Handle questions that can be answered directly without SQL.
        
        First check DynamoDB cache, then fall back to Bedrock Q&A.
        
        Args:
            psid: User ID
            question: User's question
            session: Current session
            
        Returns:
            Dict with direct answer
        """
        try:
            # Check cache first (DynamoDB FAQ table)
            cached_answer = await self.session_service.get_cached_answer(question)
            
            if cached_answer:
                logger.info(f"Cache hit for question: {question}")
                return {
                    "success": True,
                    "message": cached_answer,
                    "metadata": {"source": "cache"}
                }
            
            # Cache miss - use Bedrock Q&A
            answer = await self.bedrock_qa.get_answer(question, session)
            
            # Cache the answer for future use
            await self.session_service.cache_answer(question, answer)
            
            return {
                "success": True,
                "message": answer,
                "metadata": {"source": "bedrock"}
            }
            
        except Exception as e:
            logger.error(f"Error in _handle_direct_answer: {e}")
            return {
                "success": False,
                "message": "Xin lỗi, tôi không thể trả lời câu hỏi này lúc này."
            }
    
    async def _handle_general_question(self, psid: str, question: str, session: Any) -> Dict[str, Any]:
        """
        Handle general questions using Bedrock Q&A.
        
        Args:
            psid: User ID
            question: User's question
            session: Current session
            
        Returns:
            Dict with answer
        """
        try:
            answer = await self.bedrock_qa.get_answer(question, session)
            
            return {
                "success": True,
                "message": answer,
                "metadata": {"type": "general"}
            }
            
        except Exception as e:
            logger.error(f"Error in _handle_general_question: {e}")
            return {
                "success": False,
                "message": "Xin lỗi, tôi không hiểu câu hỏi của bạn. Bạn có thể diễn đạt lại không?"
            }
    
    async def handle_postback(self, psid: str, payload: str, session: Any) -> Dict[str, Any]:
        """Handle chat-related postbacks (quick replies, buttons)."""
        # Handle various postback types
        if payload == "CHAT_HELP":
            return {
                "success": True,
                "message": "Tôi có thể giúp bạn:\n- Truy vấn dữ liệu\n- Trả lời câu hỏi\n- Phân tích thông tin"
            }
        
        return {"success": False, "message": "Unknown postback"}
