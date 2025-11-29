"""
Bedrock Service - Flexible integration with AWS Bedrock for natural language processing.

This service can be used across different Lambda functions (inside/outside VPC)
with different model IDs by passing the model_id parameter during initialization.

Responsibilities:
- Generate answers to user questions
- Format SQL query results as natural language
- Classify user intent
- Text-to-SQL generation
- Maintain conversation context

Usage:
    # Lambda 1 (Outside VPC) - Use faster/cheaper model for intent classification
    bedrock_lite = BedrockService(model_id="anthropic.claude-3-haiku-20240307-v1:0")
    intent = bedrock_lite.classify_intent(message)
    
    # Lambda 2 (Inside VPC) - Use more powerful model for SQL generation
    bedrock_pro = BedrockService(model_id="anthropic.claude-3-5-sonnet-20240620-v1:0")
    sql = bedrock_pro.generate_sql(question, schema)
"""

import os
import json
import logging 
import boto3
from typing import Dict, Any, List, Optional,Union,Tuple
import re
import json
import ast
import re
from psycopg.connection import Connection

logger = logging.getLogger()

# Module-level singleton for Bedrock client (reuse across Lambda invocations)
_bedrock_client = None
# gọi client bedrock để các lamdba khác cũng dùng chung

def get_bedrock_client(region: str = None):
    """
    Get or create Bedrock Runtime client singleton.
    
    This is reused across Lambda invocations to improve performance.
    
    Args:
        region: AWS region (default from env or ap-northeast-1)
    
    Returns:
        boto3 Bedrock Runtime client instance
    """
    global _bedrock_client
    if _bedrock_client is None:
        region = region or os.environ.get("BEDROCK_REGION", "ap-northeast-1")
        _bedrock_client = boto3.client('bedrock-runtime', region_name=region)
        logger.info(f"Created Bedrock Runtime client for region: {region}")
    return _bedrock_client


class BedrockService:
    """
    Flexible Bedrock service that can be used with different models.
    
    Use Cases:
    - Lambda outside VPC: Fast intent classification with Haiku
    - Lambda inside VPC: Complex SQL generation with Sonnet
    """
    
    def __init__(
        self, 
        model_id: str = None,
        bedrock_client = None,
        max_tokens: int = None,
        temperature: float = None
    ):
        """
        Initialize Bedrock service with flexible configuration.
        
        Args:
            model_id: Bedrock model identifier (default from env or Haiku)
            bedrock_client: Optional client (for testing, otherwise uses singleton)
            max_tokens: Maximum tokens in response (default from env or 2048)
            temperature: Model temperature 0.0-1.0 (default from env or 0.7)
        
        Examples:
            # Default configuration (Haiku)
            service = BedrockService()
            
            # Custom model for SQL generation
            service = BedrockService(
                model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
                max_tokens=4096,
                temperature=0.3
            )
            
            # From environment variables
            service = BedrockService(
                model_id=os.environ.get("BEDROCK_MODEL_ID"),
                max_tokens=int(os.environ.get("BEDROCK_MAX_TOKENS", "2048"))
            )
            
            # For testing with mock
            mock_client = Mock()
            service = BedrockService(bedrock_client=mock_client)
        """
        # Use singleton client or injected client (for testing)
        self.bedrock_runtime = bedrock_client if bedrock_client is not None else get_bedrock_client()
        
        # Model configuration with environment variable fallbacks
        self.model_id = model_id or os.environ.get(
            "BEDROCK_MODEL_ID", 
            "anthropic.claude-3-haiku-20240307-v1:0"
        )
        
        self.max_tokens = max_tokens or int(os.environ.get("BEDROCK_MAX_TOKENS", "2048"))
        self.temperature = temperature if temperature is not None else float(os.environ.get("BEDROCK_TEMPERATURE", "0.7"))
        self.top_k = 250
        self.top_p = 0.9
        
        logger.info(f"BedrockService initialized with model: {self.model_id}, "
                   f"max_tokens: {self.max_tokens}, temperature: {self.temperature}")
    
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
                "top_k": self.top_k,
                "top_p": self.top_p,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
            
            # Invoke model
            response = self.bedrock_runtime.invoke_model(
            body=body,
            modelId=self.model_id,
            accept="application/json",
            contentType="application/json")
            
            # Parse response
            response_body = json.loads(response['body'].read())
            
            # Lấy nội dung phản hồi từ Bedrock 
            if 'content' in response_body and len(response_body['content']) > 0:
                return response_body['content'][0]['text']
            
            return "Không thể tạo phản hồi."
            
        except Exception as e:
            logger.error(f"Error invoking Bedrock: {e}")
            raise
    
    def classify_intent(self, message: str) -> Dict[str, Any]:
        """
        Classify user intent using Bedrock.
        
        Args:
            message: User's message
            
        Returns:
            Dict with intent classification
        """
        try:
            # 1. Cải thiện Prompt để ép kiểu JSON
            prompt = f"""Bạn là một hệ thống phân loại ý định (Intent Classifier). 
        Nhiệm vụ: Phân loại câu hỏi người dùng vào một trong các nhãn sau và đánh giá độ tự tin (confidence score từ 0.0 đến 1.0).

        Danh sách nhãn:
        - "schedule_type": Câu hỏi cần truy vấn database lịch hẹn (Ví dụ: Lịch trống, tư vấn viên rảnh, đặt lịch, lĩnh vực/dịch vụ liên quan đến tư vấn viên).
        - "consultation": Câu hỏi thông tin chung, hướng dẫn, giải thích, tư vấn, tán gẫu.

        Câu hỏi của người dùng: "{message}"

        YÊU CẦU OUTPUT: Chỉ trả về định dạng JSON hợp lệ.
        Format mẫu:
        {{
            "type": "schedule_type",
            "confidence": 0.95
        }}
        """

            # Gọi Bedrock (giả sử hàm này trả về string nội dung text)
            response_text = self._invoke_bedrock(prompt)
            
            # 2. Xử lý an toàn để lấy JSON (Phòng khi bot trả về text thừa)
            # Tìm đoạn text bắt đầu bằng { và kết thúc bằng }
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                
                # Lấy giá trị từ JSON
                intent_type = result.get("type", "consultation").lower()
                confidence = result.get("confidence", 0.0)
                
                # (Tùy chọn) Logic: Nếu confidence thấp quá thì coi là không hiểu
                if confidence < 0.5:
                    intent_type = "consultation" # Hoặc "fallback"
                    
                return {
                    "type": intent_type,
                    "confidence": confidence
                }
            else:
                # Trường hợp model không trả về JSON
                logger.warning(f"Model response format invalid: {response_text}")
                return {"type": "consultation", "confidence": 0.0}

        except json.JSONDecodeError:
            logger.error("Failed to parse JSON from model response")
            return {"type": "consultation", "confidence": 0.0}

        except Exception as e:
            logger.error(f"Error classifying intent: {e}")
            return {"type": "consultation", "confidence": 0.0}
    
    
    
    
    
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
    
    def get_qa_answer(self, question: str, context: str = "", rag_content: str = "") -> str:
        """Create Q&A prompt with context."""
        base_prompt = f"""Bạn là một chuyên gia tư vấn định hướng nghề nghiệp thân thiện. Hãy trả lời câu hỏi bằng tiếng Việt."""
        if context:
            base_prompt += f"""Lịch sử hội thoại:{context}"""
        if rag_content:
            base_prompt += f"Kiến thức chuyên ngành {rag_content}"
        base_prompt += f"""Câu hỏi mới: {question}
                            Trả lời:"""
        response = self._invoke_bedrock(base_prompt)
        return response
    def generate_sql_prompt(self, question: str, schema: str) -> str:
        """
        Generate SQL query from natural language question.
        
        Args:
            question: User's question in natural language
            schema: Database schema description
            
        Returns:
            SQL query string
            
        Example:
            schema = '''
            Table: appointments
            - id (bigint, primary key)
            - patient_name (varchar)
            - doctor_id (bigint)
            - appointment_date (date)
            '''
            
            sql = bedrock.generate_sql(
                "Có bao nhiêu lịch hẹn vào ngày mai?",
                schema
            )
        """
        sql_prompt_text = f"""
        Hãy viết một câu lệnh SQL cho tác vụ sau đây, với tư cách là một quản trị viên CSDL chuyên nghiệp và có ý thức bảo mật cao.

        ## Hướng dẫn chung:
        - Chỉ cho phép INSERT, UPDATE, DELETE trên các bảng/cột liên quan đến lịch hẹn (ví dụ: bảng appointment với cột như appointmentid, status, date, customerid, consultantid, v.v. – dựa trên schema).
        - Ví dụ: INSERT để đặt lịch mới, DELETE để hủy lịch, UPDATE để thay đổi thông tin lịch (như ngày giờ, trạng thái).
        - Đối với tất cả các bảng/cột khác (không liên quan đến lịch hẹn), CHỈ cho phép SELECT. Từ chối INSERT/UPDATE/DELETE trên chúng. 
        - Không bao giờ truy vấn tất cả các cột (`SELECT *`) từ một bảng; chỉ yêu cầu các cột có liên quan đến câu hỏi.

        ## Yêu cầu bảo mật:
        - Sử dụng placeholder `%s` cho các tham số (tương thích với psycopg3).
        - Không bao giờ nối chuỗi đầu vào của người dùng trực tiếp vào câu truy vấn.
        - Đặt tất cả đầu vào của người dùng làm tham số, bao gồm:
          * Các cụm từ tìm kiếm/bộ lọc (ví dụ: tên tư vấn viên, trạng thái cuộc hẹn).
          * Tên cột cho `ORDER BY`.
          * Giá trị `LIMIT`/`OFFSET`.
        - XÁC MINH RẰNG tất cả các bảng và cột đều tồn tại trong schema được cung cấp trước khi tham chiếu chúng.
        - Khi so sánh văn bản (string) Tiếng Việt, hãy luôn dùng hàm `LOWER()` hoặc `UPPER()` để chuẩn hóa (ví dụ: `LOWER(column_name) = LOWER(%s)`).

        ## Hướng dẫn Cú pháp PostgreSQL (Rất quan trọng):
        - Chỉ sử dụng cú pháp tương thích với PostgreSQL.
        - **QUAN TRỌNG VỀ TÊN BẢNG VÀ CỘT**: Sử dụng tên bảng và cột CHÍNH XÁC như trong schema được cung cấp (thường là lowercase).
          * KHÔNG dùng dấu ngoặc kép cho tên bảng/cột lowercase.
          * Ví dụ đúng: `SELECT fullname FROM account WHERE accountid = %s`
          * Ví dụ đúng: `SELECT date, time, status FROM appointment WHERE consultantid = %s`
          * Ví dụ SAI: `SELECT "FullName" FROM "Account"` (sai vì dùng ngoặc kép và chữ hoa)
        - Đối với các phép tính ngày tháng và tuổi (ví dụ: tính tuổi của tư vấn viên):
          * Dùng `AGE(end_date, start_date)` để lấy khoảng thời gian.
          * Dùng `DATE_PART('year', AGE(timestamp))` để lấy tuổi (ví dụ: `DATE_PART('year', AGE(a.dateofbirth))` để lấy tuổi của Account).
        - Đối với các phép tính tổng hợp và `GROUP BY`:
          * Quy tắc quan trọng: Mọi cột trong `SELECT` không nằm trong hàm tổng hợp (aggregate function) BẮT BUỘC phải nằm trong mệnh đề `GROUP BY`.
          * Khi dùng `CASE` với `GROUP BY`, hãy dùng CTE (subquery) để đặt bí danh (alias) cho biểu thức `CASE`, sau đó `GROUP BY` theo bí danh đó.
          * Ví dụ (đếm số lượng cuộc hẹn theo trạng thái):
            ```sql
            WITH appointments_with_status AS (
              SELECT 
                  CASE 
                      WHEN status = 'completed' THEN 'Đã hoàn thành'
                      WHEN status = 'pending' THEN 'Đang chờ'
                      WHEN status = 'rejected' THEN 'Đã từ chối'
                      ELSE 'Khác'
                  END AS trang_thai,
                  appointmentid
              FROM appointment
            )
            SELECT 
                trang_thai, 
                COUNT(appointmentid) as so_luong
            FROM appointments_with_status
            GROUP BY trang_thai
            ```

        ## Định dạng phản hồi:
        Đầu tiên: Phân tích kỹ schema được cung cấp để xác định tất cả các bảng và cột có sẵn.
        Sử dụng tên bảng/cột CHÍNH XÁC như trong schema (không thay đổi chữ hoa/thường).
        Không tham chiếu bất kỳ bảng hoặc cột nào không tồn tại trong schema này.
        Thứ hai: Xem xét các định dạng dữ liệu thực tế và phân biệt chữ hoa/thường trong các giá trị CSDL.

        Vui lòng phản hồi với:
        1. <sql>Câu truy vấn SQL của bạn ở đây</sql>
        2. <params>[param1, param2, ...]</params>
        3. <validation>Một xác thực ngắn gọn xác nhận rằng placeholder khớp với tham số và tất cả các bảng/cột đều tồn tại</validation>

        Đây là tác vụ:
        <task>
        Bạn là một chuyên gia SQL tập trung vào bảo mật. Một CSDL PostgreSQL được tạo với các bảng và cột sau:
        {schema}

        Viết một câu truy vấn SQL có tham số (dùng `%s`) trả về kết quả tốt nhất dựa trên yêu cầu sau của người dùng:
        {question}

        Hãy kiểm tra kỹ công việc của bạn để đảm bảo:
        1. MỌI bảng và cột bạn tham chiếu ĐỀU TỒN TẠI trong schema ở trên và sử dụng ĐÚNG tên (lowercase, không dấu ngoặc kép).
        2. Số lượng placeholder `%s` KHỚP CHÍNH XÁC với số lượng tham số bạn cung cấp.
        3. Không có lỗ hổng SQL injection.
        4. Xử lý đúng việc so sánh chuỗi Tiếng Việt (dùng `LOWER` hoặc `UPPER`).
        </task>
        """  # nosec

        return  sql_prompt_text
    def get_sql_from_bedrock(self, query: str, schema: str) -> Union[Tuple[str, List], Dict[str, Any]]:
        """Generate SQL from a natural language query using Bedrock.

        Args:
            query (str): The natural language query.
            schema (str): The database schema.

        Returns:
            Union[Tuple[str, List], Dict[str, Any]]: The generated SQL statement and parameters or an error response dictionary.

        Raises:
            Exception: If there is an error generating SQL from the query.
        """
        # Generate the prompt for Bedrock
        sql_prompt = self.generate_sql_prompt(query, schema)
        logger.debug(f"SQL prompt: {sql_prompt[:200]}...")
        
        # Call Bedrock to generate SQL
        text_content = self._invoke_bedrock(sql_prompt)

        # Extract SQL from the AI's response
        sql_regex = re.compile(r"<sql>(.*?)</sql>", re.DOTALL)
        sql_statements = sql_regex.findall(text_content)

        # Extract parameters
        params_regex = re.compile(r"<params>(.*?)</params>", re.DOTALL)
        params_match = params_regex.findall(text_content)

        logger.debug(f"SQL statements: {sql_statements}")
        logger.debug(f"Params match: {params_match}")

        # Check if SQL was successfully generated
        if not sql_statements:
            return {"statusCode": 500,
                    "body": {"response": "Unable to generate SQL for the provided prompt, please try again."},
                    "headers": {"Content-Type": "application/json"}}

        # Parse parameters if available, otherwise return empty list
        params = []
        if params_match:
            try:
                # Safely evaluate the parameter list (should be a Python list literal)
                params = ast.literal_eval(params_match[0])
            except Exception as e:
                logger.error(f"Error parsing parameters: {e}")
                logger.error(f"Raw parameters string: {params_match[0]}")
                # Continue with empty params rather than failing

        # Return the SQL and parameters
        return sql_statements[0], params
    def execute_sql(self, conn: Connection, sql_data) -> Tuple[List[Tuple], List[str]]:
        """Execute SQL statements on a given database connection.

        Args:
            conn (connection): The database connection.
            sql_data: Either a SQL string or a tuple of (SQL, parameters)

        Returns:
            Tuple[List[Tuple], List[str]]: The results of the SQL execution and column names.

        Raises:
            Exception: If there is an error executing the SQL statements.
        """
        sql = sql_data
        params = []

        # Check if we have parameters
        if isinstance(sql_data, tuple) and len(sql_data) == 2:
            sql, params = sql_data

        logger.info(f"Executing SQL: {sql}")
        logger.debug(f"With parameters: {params}")

        cursor = conn.cursor()
        cursor.execute(sql, params)

        # Fetch results if available
        results = []
        column_names = []

        if cursor.description:  # Check if the query returned any rows
            results = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]

        logger.info(f"Query returned {len(results)} rows")
        logger.debug(f"Column names: {column_names}")
        return results, column_names
    
    def get_answer_from_sql_results(
        self, 
        question: str, 
        results: str, 
        schema: str = "",
        context: str = ""
    ) -> str:
        """
        Format SQL query results as natural language response using Bedrock.
        
        Args:
            question: Original user question
            results: Query results as list of tuples from execute_sql
            column_names: List of column names from execute_sql
            schema: Database schema description (optional, for context)
            
        Returns:
            Formatted natural language response
            
        Example:
            results = [("Nguyễn Văn A", "2025-11-28", "pending")]
            column_names = ["FullName", "AppointmentDate", "Status"]
            answer = bedrock.get_answer_from_sql_results(
                question="Ai có lịch hẹn hôm nay?",
                results=results,
                column_names=column_names
            )
        """
        if not results:
            return "Không tìm thấy kết quả nào cho câu hỏi của bạn."
        
        # Format results as readable table for LLM
        
        
        # Create formatting prompt
        prompt = f"""Bạn là một chuyên viên tư vấn đặt lịch hẹn thân thiện.
                Kết quả truy vấn từ hệ thống:{results}
                Thông tin schema: {schema}
                Câu hỏi của khách hàng: {question}"""
        if context:
            prompt += f"""Lịch sử hội thoại:{context}"""
        prompt += f"""
                Hãy trả lời câu hỏi dựa trên kết quả trên theo phong cách tư vấn viên:
                - Trả lời bằng tiếng Việt tự nhiên, thân thiện
                - KHÔNG đề cập đến SQL, database, schema hay bất kỳ khía cạnh kỹ thuật nào
                - Tóm tắt thông tin quan trọng một cách rõ ràng
                - Nếu có nhiều kết quả, liệt kê ngắn gọn
                Trả lời:"""

        response = self._invoke_bedrock(prompt)
        return response
            
        