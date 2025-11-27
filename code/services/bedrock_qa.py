"""
Bedrock Q&A Service - Integration with AWS Bedrock for natural language processing.

Responsibilities:
- Generate answers to user questions
- Format SQL query results as natural language
- Maintain conversation context
"""

import json
import logging
import boto3
from typing import Dict, Any, List, Optional

logger = logging.getLogger()


class BedrockQAService:
    """Service for interacting with AWS Bedrock models."""
    
    def __init__(self, model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"):
        """
        Initialize Bedrock Q&A service.
        
        Args:
            model_id: Bedrock model identifier
        """
        self.bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
        self.model_id = model_id
        self.max_tokens = 2048
        self.temperature = 0.7
    
    async def get_answer(self, question: str, session: Any = None) -> str:
        """
        Get answer to user's question using Bedrock.
        
        Args:
            question: User's question
            session: Current session (for context)
            
        Returns:
            Answer string
        """
        try:
            # Build context from session history if available
            context = self._build_context(session)
            
            # Create prompt
            prompt = self._create_qa_prompt(question, context)
            
            # Call Bedrock
            response = self._invoke_bedrock(prompt)
            
            return response
            
        except Exception as e:
            logger.error(f"Error in BedrockQAService.get_answer: {e}")
            raise
    
    async def format_query_results(self, question: str, sql: str, results: List[Dict]) -> str:
        """
        Format SQL query results as natural language response.
        
        Args:
            question: Original user question
            sql: SQL query that was executed
            results: Query results (list of dicts)
            
        Returns:
            Formatted natural language response
        """
        try:
            if not results:
                return "Không tìm thấy kết quả nào cho câu hỏi của bạn."
            
            # Create formatting prompt
            prompt = f"""Bạn là trợ lý AI. Hãy trả lời câu hỏi dưới đây dựa trên kết quả truy vấn SQL.

Câu hỏi: {question}

SQL đã thực thi:
```sql
{sql}
```

Kết quả ({len(results)} hàng):
{json.dumps(results[:10], ensure_ascii=False, indent=2)}

Hãy trả lời bằng tiếng Việt, ngắn gọn, dễ hiểu. Nếu có nhiều kết quả, hãy tóm tắt hoặc liệt kê."""

            response = self._invoke_bedrock(prompt)
            return response
            
        except Exception as e:
            logger.error(f"Error formatting query results: {e}")
            # Fallback: return raw results
            return self._format_results_simple(results)
    
    async def classify_intent(self, message: str) -> Dict[str, Any]:
        """
        Classify user intent using Bedrock.
        
        Args:
            message: User's message
            
        Returns:
            Dict with intent classification
        """
        try:
            prompt = f"""Phân loại câu hỏi sau vào một trong các loại:
- "sql_query": Câu hỏi cần truy vấn database (ví dụ: "có bao nhiêu user", "danh sách orders")
- "direct_answer": Câu hỏi thông tin chung, hướng dẫn, giải thích
- "greeting": Lời chào, xin chào
- "other": Các loại khác

Câu hỏi: "{message}"

Trả lời chỉ một từ: sql_query, direct_answer, greeting, hoặc other"""

            response = self._invoke_bedrock(prompt)
            intent_type = response.strip().lower()
            
            return {
                "type": intent_type if intent_type in ["sql_query", "direct_answer", "greeting"] else "other",
                "confidence": 0.8  # Placeholder
            }
            
        except Exception as e:
            logger.error(f"Error classifying intent: {e}")
            return {"type": "other", "confidence": 0.0}
    
    def _invoke_bedrock(self, prompt: str) -> str:
        """
        Invoke Bedrock model with prompt.
        
        Args:
            prompt: Input prompt
            
        Returns:
            Model response text
        """
        try:
            # Prepare request body for Claude
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
            
            # Invoke model
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=body
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            
            # Extract text from Claude response
            if 'content' in response_body and len(response_body['content']) > 0:
                return response_body['content'][0]['text']
            
            return "Không thể tạo phản hồi."
            
        except Exception as e:
            logger.error(f"Error invoking Bedrock: {e}")
            raise
    
    def _build_context(self, session: Any) -> str:
        """Build conversation context from session history."""
        if not session or not hasattr(session, 'conversation_history'):
            return ""
        
        # Get last N messages for context
        history = session.conversation_history[-5:] if session.conversation_history else []
        
        context_lines = []
        for msg in history:
            context_lines.append(f"User: {msg['user']}")
            context_lines.append(f"Assistant: {msg['assistant']}")
        
        return "\n".join(context_lines)
    
    def _create_qa_prompt(self, question: str, context: str = "") -> str:
        """Create Q&A prompt with context."""
        base_prompt = f"""Bạn là trợ lý AI thông minh, thân thiện. Hãy trả lời câu hỏi bằng tiếng Việt.

"""
        if context:
            base_prompt += f"""Lịch sử hội thoại:
{context}

"""
        
        base_prompt += f"""Câu hỏi mới: {question}

Trả lời:"""
        
        return base_prompt
    
    def _format_results_simple(self, results: List[Dict]) -> str:
        """Simple formatting for query results."""
        if not results:
            return "Không có kết quả."
        
        # Format first 5 results
        lines = [f"Tìm thấy {len(results)} kết quả:\n"]
        for i, row in enumerate(results[:5], 1):
            row_str = ", ".join([f"{k}: {v}" for k, v in row.items()])
            lines.append(f"{i}. {row_str}")
        
        if len(results) > 5:
            lines.append(f"\n... và {len(results) - 5} kết quả khác.")
        
        return "\n".join(lines)
