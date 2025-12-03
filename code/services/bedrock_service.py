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
import time
import random
from botocore.exceptions import ClientError
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
        self.temperature = temperature if temperature is not None else float(os.environ.get("BEDROCK_TEMPERATURE", "0.5"))
        self.top_k = 250
        self.top_p = 0.9
        
        logger.info(f"BedrockService initialized with model: {self.model_id}, "
                   f"max_tokens: {self.max_tokens}, temperature: {self.temperature}")
    
    def _invoke_bedrock(self, prompt: str, max_retries: int = 3) -> str:
        """
        Invoke Bedrock model with prompt and exponential backoff retry.
        
        Args:
            prompt: Input prompt
            max_retries: Maximum number of retry attempts for throttling errors (default 3 to avoid Lambda timeout)
            
        Returns:
            Model response text
        """
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
        
        last_exception = None
        for attempt in range(max_retries):
            try:
                # Invoke model
                response = self.bedrock_runtime.invoke_model(
                    body=body,
                    modelId=self.model_id,
                    accept="application/json",
                    contentType="application/json"
                )
                
                # Parse response
                response_body = json.loads(response['body'].read())
                
                # Lấy nội dung phản hồi từ Bedrock 
                if 'content' in response_body and len(response_body['content']) > 0:
                    return response_body['content'][0]['text']
                
                return "Không thể tạo phản hồi."
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code in ('ThrottlingException', 'TooManyRequestsException', 'ServiceUnavailableException'):
                    last_exception = e
                    # Exponential backoff with jitter: 1s, 2s, 4s, 8s, 16s + random jitter
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Bedrock throttling (attempt {attempt + 1}/{max_retries}), waiting {wait_time:.2f}s...")
                    time.sleep(wait_time)
                else:
                    # Non-throttling error, raise immediately
                    logger.error(f"Error invoking Bedrock: {e}")
                    raise
            except Exception as e:
                logger.error(f"Error invoking Bedrock: {e}")
                raise
        
        # All retries exhausted
        logger.error(f"Bedrock throttling: max retries ({max_retries}) exhausted")
        raise last_exception
    
    # def get_qa_answer(self, question: str, context: str = "", rag_content: str = "") -> str:
    #     """Create Q&A prompt with context."""
    #     base_prompt = f"""Bạn là một chuyên gia tư vấn định hướng nghề nghiệp thân thiện. Hãy trả lời câu hỏi bằng tiếng Việt."""
    #     if context:
    #         base_prompt += f"""Lịch sử hội thoại:{context}"""
    #     if rag_content:
    #         base_prompt += f"Kiến thức chuyên ngành {rag_content}"
    #     base_prompt += f"""Câu hỏi mới: {question}
    #                         Trả lời:"""
    #     response = self._invoke_bedrock(base_prompt)
    #     return response
    def generate_sql_prompt(self, question: str, schema: str) -> str:
        """
        Generate SQL query from natural language question.
        
        Args:
            question: User's question in natural language
            schema: Database schema description (dynamically provided)
            
        Returns:
            SQL prompt text for Bedrock
        """
        sql_prompt_text = f"""Bạn là chuyên gia SQL PostgreSQL bảo mật. Tạo query SELECT an toàn từ yêu cầu người dùng.

## QUY TẮC (bắt buộc):
- CHỈ SELECT, KHÔNG INSERT/UPDATE/DELETE → nếu yêu cầu thay đổi dữ liệu: trả <error>Không hỗ trợ thay đổi dữ liệu</error>
- Dùng `%s` cho TẤT CẢ tham số từ USER INPUT (psycopg3), KHÔNG nối chuỗi
- Tên bảng/cột: lowercase, không ngoặc kép, CHÍNH XÁC như schema, không viết tắt
- So sánh Tiếng Việt: dùng `LOWER(col) = LOWER(%s)` hoặc `ILIKE %s` cho fuzzy search
- JOIN: kiểm tra khóa ngoại tồn tại trong schema trước

## QUY TẮC CỘT ENUM/GIÁ TRỊ CỐ ĐỊNH (RẤT QUAN TRỌNG):
- Các cột có giá trị cố định (enum) như: status, type, role, category, priority, isdisabled
- KHÔNG dùng %s placeholder cho các cột này → dùng giá trị cố định trực tiếp trong SQL
- Giá trị phổ biến:
  * status: 'upcoming', 'completed', 'cancelled', 'pending', 'active', 'inactive'
  * isdisabled: true, false (boolean, không cần quotes)
  * type/role: string cố định theo schema
- Chỉ dùng %s cho dữ liệu DO USER NHẬP: tên, ngày, số lượng, ID cụ thể từ câu hỏi

## QUY TẮC AGGREGATE & GROUP BY:
- Các hàm tổng hợp: COUNT(*), COUNT(col), SUM(col), AVG(col), MAX(col), MIN(col)
- HAVING: dùng để filter kết quả SAU aggregate (không dùng WHERE cho aggregate)
- GROUP BY BẮT BUỘC: mọi cột trong SELECT mà KHÔNG nằm trong hàm aggregate PHẢI có trong GROUP BY
- ORDER BY với aggregate: có thể ORDER BY theo alias (VD: ORDER BY total DESC)
- Khi đếm distinct: dùng COUNT(DISTINCT col)

## FEW-SHOT EXAMPLES:

### Ví dụ 1 - Query đơn giản:
Schema: customer(customerid, fullname, phonenumber, dateofbirth)
Question: Lấy tên khách hàng có id là 123
<reasoning>Cần cột fullname từ bảng customer, filter theo customerid. 1 placeholder cho id.</reasoning>
<sql>SELECT fullname FROM customer WHERE customerid = %s</sql>
<params>[123]</params>
<validation>1 placeholder = 1 param ✓ | bảng customer, cột fullname, customerid tồn tại ✓</validation>

### Ví dụ 2 - Tìm kiếm Tiếng Việt:
Schema: consultant(consultantid, fullname, specialties)
Question: Tìm tư vấn viên tên có chứa "Nguyễn"
<reasoning>Fuzzy search tên Tiếng Việt → dùng ILIKE với LOWER. Thêm % cho pattern matching.</reasoning>
<sql>SELECT consultantid, fullname, specialties FROM consultant WHERE LOWER(fullname) ILIKE LOWER(%s)</sql>
<params>["%Nguyễn%"]</params>
<validation>1 placeholder = 1 param ✓ | bảng consultant, các cột tồn tại ✓</validation>

### Ví dụ 3 - CỘT ENUM - KHÔNG dùng placeholder:
Schema: communityprogram(programid, programname, date, status, isdisabled)
Question: Các chương trình sắp diễn ra
<reasoning>status là cột ENUM → dùng giá trị cố định 'upcoming', KHÔNG dùng %s. isdisabled là boolean.</reasoning>
<sql>SELECT programid, programname, date FROM communityprogram WHERE isdisabled = false AND status = 'upcoming' ORDER BY date ASC</sql>
<params>[]</params>
<validation>0 placeholder = 0 param ✓ | status dùng giá trị cố định ✓ | isdisabled là boolean không quotes ✓</validation>

### Ví dụ 4 - JOIN và GROUP BY:
Schema: appointment(appointmentid, consultantid, status), consultant(consultantid, fullname)
Question: Đếm số cuộc hẹn theo từng tư vấn viên
<reasoning>Cần JOIN appointment với consultant qua consultantid. GROUP BY fullname, COUNT appointmentid.</reasoning>
<sql>SELECT c.fullname, COUNT(a.appointmentid) as total FROM appointment a JOIN consultant c ON a.consultantid = c.consultantid GROUP BY c.fullname</sql>
<params>[]</params>
<validation>0 placeholder = 0 param ✓ | FK consultantid tồn tại ✓ | GROUP BY đúng ✓</validation>

### Ví dụ 5 - KẾT HỢP: Enum cố định + Tham số user:
Schema: appointment(appointmentid, consultantid, customerid, status, scheduledtime), consultant(consultantid, fullname)
Question: Lịch hẹn đã hoàn thành của tư vấn viên Nguyễn Văn A
<reasoning>status='completed' là ENUM → giá trị cố định. Tên "Nguyễn Văn A" là user input → dùng %s.</reasoning>
<sql>SELECT a.appointmentid, a.scheduledtime, c.fullname FROM appointment a JOIN consultant c ON a.consultantid = c.consultantid WHERE a.status = 'completed' AND LOWER(c.fullname) ILIKE LOWER(%s) ORDER BY a.scheduledtime DESC</sql>
<params>["%Nguyễn Văn A%"]</params>
<validation>1 placeholder = 1 param ✓ | status cố định ✓ | tên user input dùng %s ✓</validation>

### Ví dụ 6 - Aggregate với điều kiện status:
Schema: appointment(appointmentid, consultantid, customerid, duration_minutes, status, createdat), consultant(consultantid, fullname)
Question: Tổng thời gian tư vấn của tất cả tư vấn viên trong tháng này
<reasoning>SUM(duration_minutes), status='completed' là ENUM cố định. Không có user input → params trống.</reasoning>
<sql>SELECT c.fullname, SUM(a.duration_minutes) as total_minutes, COUNT(a.appointmentid) as total_appointments FROM appointment a JOIN consultant c ON a.consultantid = c.consultantid WHERE a.status = 'completed' AND EXTRACT(MONTH FROM a.createdat) = EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(YEAR FROM a.createdat) = EXTRACT(YEAR FROM CURRENT_DATE) GROUP BY c.fullname ORDER BY total_minutes DESC</sql>
<params>[]</params>
<validation>0 placeholder = 0 param ✓ | status cố định ✓ | không có user input ✓</validation>


### Ví dụ 8 - GROUP BY với HAVING:
Schema: consultant(consultantid, fullname), appointment(appointmentid, consultantid, status, createdat)
Question: Tư vấn viên nào có hơn 10 cuộc hẹn hoàn thành?
<reasoning>COUNT appointment với status='completed' (ENUM cố định), HAVING > 10. Số 10 có thể từ user → dùng %s.</reasoning>
<sql>SELECT c.fullname, COUNT(a.appointmentid) as appointment_count FROM consultant c LEFT JOIN appointment a ON c.consultantid = a.consultantid WHERE a.status = 'completed' GROUP BY c.consultantid, c.fullname HAVING COUNT(a.appointmentid) > %s ORDER BY appointment_count DESC</sql>
<params>[10]</params>
<validation>1 placeholder = 1 param ✓ | status cố định ✓ | số lượng từ user dùng %s ✓</validation>


---

## SCHEMA HIỆN TẠI:
{schema}

## YÊU CẦU NGƯỜI DÙNG:
{question}

## THỰC HIỆN (Chain of Thought):
1. Đọc schema → liệt kê bảng/cột liên quan
2. Xác định cột ENUM (status, isdisabled, isavailable, type, role) → dùng giá trị cố định
3. Xác định tham số từ USER INPUT (tên, số, ngày cụ thể) → dùng %s
4. Viết SQL, kiểm tra syntax PostgreSQL
5. Nếu schema không có bảng/cột cần thiết → trả <error>Schema không có thông tin này</error>

## OUTPUT FORMAT (bắt buộc theo thứ tự):
<reasoning>Phân tích ngắn gọn: liệt kê cột enum (giá trị cố định) và user input (dùng %s)</reasoning>
<sql>Query SQL ở đây</sql>
<params>[danh sách tham số theo thứ tự %s - CHỈ chứa user input, KHÔNG chứa giá trị enum]</params>
<validation>1. Số %s = số params | 2. Cột enum dùng giá trị cố định | 3. User input dùng %s | 4. Bảng/cột tồn tại</validation>
"""  # nosec

        return sql_prompt_text

    def extract_appointment_info(self, message: str, current_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Extract appointment-related information from user message using Bedrock.
        
        This function analyzes the user's message to identify and extract:
        - customer_name: Tên khách hàng
        - phone_number: Số điện thoại
        - appointment_date: Ngày hẹn (YYYY-MM-DD format)
        - appointment_time: Giờ hẹn (HH:MM format)
        - consultant_name: Tên tư vấn viên
        - notes: Ghi chú
        - appointment_id: Mã lịch hẹn (cho update/cancel)
        
        Args:
            message: User's message to extract information from
            current_info: Current appointment info dictionary (to merge with)
            
        Returns:
            Dictionary with extracted fields (only non-empty values)
        """
        if current_info is None:
            current_info = {}
        
        booking_action = current_info.get("booking_action", "create")
            
        prompt = f"""Bạn là trợ lý AI chuyên trích xuất thông tin đặt lịch từ tin nhắn người dùng.

## HÀNH ĐỘNG HIỆN TẠI: {booking_action.upper()}

## NHIỆM VỤ:
Phân tích tin nhắn và trích xuất các thông tin sau (nếu có):

1. **appointment_id**: Mã lịch hẹn (số, VD: 123, #456, lịch số 789)
   - Trích xuất nếu user đề cập đến mã/số lịch hẹn cụ thể
2. **customer_name**: Tên khách hàng (họ và tên đầy đủ)
3. **phone_number**: Số điện thoại (format: 10-11 số, có thể có dấu + hoặc 84)
4. **appointment_date**: Ngày hẹn (chuyển về format YYYY-MM-DD)
   - Hôm nay: dùng ngày hiện tại (2025-12-01)
   - Ngày mai: dùng ngày hiện tại + 1
   - Thứ X: tính ngày cụ thể trong tuần này hoặc tuần sau
5. **appointment_time**: Giờ hẹn (chuyển về format HH:MM, 24h)
   - "9 giờ sáng" → "09:00"
   - "2 giờ chiều" → "14:00"
   - "8h30" → "08:30"
6. **consultant_name**: Tên tư vấn viên (nếu có đề cập)
7. **notes**: Ghi chú thêm (lý do hẹn, lý do hủy, yêu cầu đặc biệt, v.v.)

## THÔNG TIN HIỆN TẠI (đã thu thập):
{json.dumps(current_info, ensure_ascii=False, indent=2)}

## TIN NHẮN NGƯỜI DÙNG:
"{message}"

## QUY TẮC:
- CHỈ trích xuất thông tin được đề cập rõ ràng trong tin nhắn
- KHÔNG đoán hoặc bịa thông tin không có
- Nếu không tìm thấy thông tin nào → trả về {{}}
- Phone number: chỉ trích xuất nếu có đủ 10-11 số
- Ngày tháng: cố gắng chuyển về YYYY-MM-DD, nếu không rõ năm thì dùng 2025
- appointment_id: trích xuất số từ "lịch hẹn số 123", "#123", "mã 123"

## OUTPUT FORMAT (JSON thuần túy, không có text khác):
{{
    "customer_name": "Nguyễn Văn A",
    "phone_number": "0901234567",
    "appointment_date": "2025-06-15",
    "appointment_time": "14:00",
    "consultant_name": "Dr. Trần B",
    "notes": "Tư vấn về tài chính"
}}

Lưu ý: CHỈ trả về các field có thông tin, không trả field với giá trị null/empty."""

        try:
            response_text = self._invoke_bedrock(prompt)
            
            # Clean up response to extract JSON
            response_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            # Try to extract JSON from response
            extracted_info = json.loads(response_text)
            
            # Filter out empty/null values
            cleaned_info = {k: v for k, v in extracted_info.items() if v and str(v).strip()}
            
            logger.info(f"Extracted appointment info: {cleaned_info}")
            return cleaned_info
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from Bedrock response: {e}. Response: {response_text}")
            return {}
        except Exception as e:
            logger.error(f"Error extracting appointment info: {e}")
            return {}
    
    def generate_booking_response(self, current_info: Dict[str, Any], missing_fields: List[str]) -> str:
        """
        Generate a natural language response to ask for missing appointment information.
        
        Args:
            current_info: Current appointment info collected so far
            missing_fields: List of field names still needed
            
        Returns:
            Natural language prompt to ask for missing information
        """
        booking_action = current_info.get("booking_action", "create") if current_info else "create"
        
        field_descriptions = {
            "customer_name": "tên của bạn",
            "phone_number": "số điện thoại liên hệ",
            "appointment_date": "ngày bạn muốn đặt lịch",
            "appointment_time": "giờ bạn muốn hẹn",
            "consultant_name": "tên tư vấn viên bạn muốn gặp",
            "notes": "ghi chú hoặc lý do hẹn (tùy chọn)",
            "appointment_id": "mã lịch hẹn cần thay đổi"
        }
        
        # Suggestions for querying info
        query_suggestions = {
            "consultant_name": "💡 Bạn có thể hỏi: 'Có tư vấn viên nào chuyên về [lĩnh vực]?' hoặc 'Cho xem danh sách tư vấn viên'",
            "appointment_date": "💡 Bạn có thể hỏi: 'Lịch trống ngày nào?' hoặc 'Tư vấn viên X có rảnh khi nào?'",
            "appointment_time": "💡 Bạn có thể hỏi: 'Có slot nào trống ngày X?' hoặc 'Giờ nào còn trống?'"
        }
        
        # Handle different booking actions
        if booking_action == "cancel":
            if "appointment_id" in missing_fields:
                return "Bạn muốn hủy lịch hẹn nào?\n\n💡 Bạn có thể hỏi: 'Cho xem lịch hẹn của tôi' để xem danh sách, hoặc cho mình biết mã lịch hẹn cần hủy."
            return "Xác nhận hủy lịch hẹn? Trả lời 'có' để xác nhận hoặc 'thôi' để hủy thao tác."
        
        if booking_action == "update":
            if "appointment_id" in missing_fields:
                return "Bạn muốn đổi lịch hẹn nào?\n\n💡 Bạn có thể hỏi: 'Cho xem lịch hẹn của tôi' để xem danh sách, hoặc cho mình biết mã lịch cần đổi."
            return "Bạn muốn thay đổi thông tin gì? (ngày, giờ, tư vấn viên, hoặc ghi chú)"
        
        # Collect descriptions for missing required fields
        missing_descriptions = []
        first_missing_field = None
        for field in missing_fields:
            if field in field_descriptions and field != "notes":  # notes is optional
                missing_descriptions.append(field_descriptions[field])
                if first_missing_field is None:
                    first_missing_field = field
        
        if not missing_descriptions:
            return "Thông tin đặt lịch đã đầy đủ! Bạn có muốn xác nhận đặt lịch không?"
        
        # Build response with query suggestion
        if len(missing_descriptions) == 1:
            response = f"Vui lòng cho mình biết {missing_descriptions[0]} ạ?"
        elif len(missing_descriptions) == 2:
            response = f"Vui lòng cho mình biết {missing_descriptions[0]} và {missing_descriptions[1]} ạ?"
        else:
            fields_str = ", ".join(missing_descriptions[:-1]) + f" và {missing_descriptions[-1]}"
            response = f"Để hoàn tất đặt lịch, mình cần thêm: {fields_str}."
        
        # Add query suggestion for the first missing field
        if first_missing_field and first_missing_field in query_suggestions:
            response += f"\n\n{query_suggestions[first_missing_field]}"
        
        return response
    
    def detect_booking_intent(self, message: str) -> Dict[str, Any]:
        """
        Detect if user wants to make/update/cancel a booking/appointment.
        
        Args:
            message: User's message
            
        Returns:
            Dict with:
                - wants_booking: bool - True if user wants to interact with booking
                - booking_action: str - "create", "update", "cancel" or None
                - booking_type: str - "consultation" or "event" or None
                - confidence: float - 0.0 to 1.0
        """
        prompt = f"""Bạn là hệ thống phân loại ý định đặt lịch RẤT CHÍNH XÁC.

## NHIỆM VỤ:
Xác định xem người dùng có THỰC SỰ muốn thực hiện hành động đặt/sửa/hủy lịch hay không.

## ⚠️ QUAN TRỌNG - PHÂN BIỆT RÕ:

### ❌ KHÔNG PHẢI ĐẶT LỊCH (wants_booking = false):
- Hỏi thông tin: "có tư vấn viên nào?", "ai là tư vấn viên?", "bên bạn có những ai?"
- Hỏi về dịch vụ: "có dịch vụ gì?", "giá bao nhiêu?", "làm việc mấy giờ?"
- Hỏi về lịch trống: "lịch trống ngày nào?", "có slot nào không?", "khi nào rảnh?"
- Xem lịch: "xem lịch hẹn của tôi", "tôi có lịch gì?", "kiểm tra lịch"
- Tán gẫu, chào hỏi, cảm ơn

### ✅ ĐẶT LỊCH MỚI (wants_booking = true, booking_action = "create"):
- Phải có từ khóa RÕ RÀNG: "đặt lịch", "book lịch", "đăng ký", "xin đặt", "muốn đặt"
- Ví dụ: "tôi muốn đặt lịch", "cho tôi đặt lịch hẹn", "đăng ký tư vấn"

### ✅ CẬP NHẬT LỊCH (wants_booking = true, booking_action = "update"):
- "đổi lịch", "dời lịch", "thay đổi lịch hẹn", "sửa lịch"
- "chuyển sang ngày khác", "đổi giờ hẹn"

### ✅ HỦY LỊCH (wants_booking = true, booking_action = "cancel"):
- "hủy lịch", "cancel lịch", "không đến được", "hủy cuộc hẹn"

## TIN NHẮN CẦN PHÂN LOẠI:
"{message}"

## QUY TẮC:
- Nếu KHÔNG CHẮC CHẮN → wants_booking = false
- Chỉ trả true khi có từ khóa đặt/sửa/hủy lịch RÕ RÀNG
- Hỏi thông tin ≠ đặt lịch

## OUTPUT (JSON thuần túy, không giải thích):
{{
    "wants_booking": true/false,
    "booking_action": "create" hoặc "update" hoặc "cancel" hoặc null,
    "booking_type": "consultation" hoặc "event" hoặc null,
    "confidence": 0.0-1.0
}}"""

        try:
            response_text = self._invoke_bedrock(prompt)
            
            # Clean up response
            response_text = response_text.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(response_text)
            logger.info(f"Booking intent detection: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error detecting booking intent: {e}")
            return {"wants_booking": False, "booking_type": None, "confidence": 0.0}

    def generate_appointment_mutation_prompt(self, question: str, schema: str, customer_id: str = None, appointment_info: Dict[str, Any] = None) -> str:
        """
        Generate SQL cho CREATE/UPDATE/CANCEL appointment.
        Logic đơn giản:
        - CREATE: Upsert customer + INSERT appointment (status='pending')
        - UPDATE: UPDATE appointment cũ (status='cancelled') + INSERT appointment mới (status='pending')  
        - CANCEL: UPDATE appointment (status='cancelled')
        """
        allowed_tables = ["appointment", "customer"]
        booking_action = appointment_info.get('booking_action', 'create') if appointment_info else 'create'
        
        # Build appointment info string
        info_str = ""
        if appointment_info:
            actual_customer_id = customer_id or appointment_info.get('customer_id', 'N/A')
            info_str = f"""
## THÔNG TIN TỪ CACHE (dùng trực tiếp làm params):

| Thông tin | Giá trị | Cột trong DB |
|-----------|---------|--------------|
| customer_id | {actual_customer_id} | customerid (VARCHAR) |
| customer_name | {appointment_info.get('customer_name', 'N/A')} | fullname |
| phone_number | {appointment_info.get('phone_number', 'N/A')} | phonenumber |
| consultant_id | {appointment_info.get('consultant_id', 'N/A')} | consultantid (INT) |
| appointment_date | {appointment_info.get('appointment_date', 'N/A')} | date (DATE) |
| appointment_time | {appointment_info.get('appointment_time', 'N/A')} | time (TIME) |
"""
            if booking_action in ['update', 'cancel']:
                info_str += f"""
### THÔNG TIN LỊCH CẦN HỦY/ĐỔI:
- appointment_id cũ: {appointment_info.get('appointment_id', 'N/A')}
- customer_id (để verify ownership): {actual_customer_id}
"""

        prompt = f"""Tạo SQL PostgreSQL cho thao tác lịch hẹn.

## BẢNG ĐƯỢC PHÉP: {', '.join(allowed_tables)}

## QUY TẮC:
1. KHÔNG DELETE - chỉ UPDATE status thành 'cancelled'
2. Dùng %s cho params, KHÔNG nối chuỗi
3. UPDATE appointment phải có WHERE appointmentid = %s AND customerid = %s (bảo mật)
4. RETURNING để xác nhận

## SCHEMA (chỉ các bảng liên quan):
{schema}
{info_str}

## MẪU SQL THEO ACTION:

### CREATE (Đặt lịch mới):
Bước 1: Upsert customer (tạo mới nếu chưa có, cập nhật thông tin nếu có)
Bước 2: INSERT appointment với status='pending'
```sql
WITH upsert_customer AS (
    INSERT INTO customer (customerid, fullname, phonenumber) 
    VALUES (%s, %s, %s)
    ON CONFLICT (customerid) DO UPDATE SET 
        fullname = COALESCE(EXCLUDED.fullname, customer.fullname),
        phonenumber = COALESCE(EXCLUDED.phonenumber, customer.phonenumber)
    RETURNING customerid
)
INSERT INTO appointment (customerid, consultantid, date, time, status)
SELECT %s, %s, %s, %s, 'pending'
FROM upsert_customer
RETURNING appointmentid
```
params: [customer_id, customer_name, phone_number, customer_id, consultant_id, date, time]

### UPDATE (Đổi lịch):
Bước 1: UPDATE appointment cũ → status='cancelled'
Bước 2: INSERT appointment mới với status='pending'
⚠️ WHERE phải có customerid để verify ownership!
```sql
WITH cancel_old AS (
    UPDATE appointment SET status = 'cancelled', updatedat = CURRENT_TIMESTAMP
    WHERE appointmentid = %s AND customerid = %s
    RETURNING customerid, consultantid
)
INSERT INTO appointment (customerid, consultantid, date, time, status)
SELECT customerid, %s, %s, %s, 'pending'
FROM cancel_old
RETURNING appointmentid
```
params: [old_appointment_id, customer_id, new_consultant_id, new_date, new_time]

### CANCEL (Hủy lịch):
UPDATE appointment → status='cancelled'
⚠️ WHERE phải có customerid để verify ownership!
```sql
UPDATE appointment SET status = 'cancelled', updatedat = CURRENT_TIMESTAMP
WHERE appointmentid = %s AND customerid = %s
RETURNING appointmentid
```
params: [appointment_id, customer_id]

## YÊU CẦU:
{question}

## OUTPUT:
<operation>{booking_action.upper()}</operation>
<sql>SQL query</sql>
<params>[GIÁ TRỊ CỤ THỂ từ bảng cache ở trên, theo đúng thứ tự %s]</params>
"""
        return prompt

    def get_mutation_sql_from_bedrock(
        self, 
        query: str, 
        schema: str, 
        customer_id: str,
        appointment_info: Dict[str, Any] = None,
        allowed_tables: List[str] = None
    ) -> Union[Tuple[str, List, str], Dict[str, Any]]:
        """
        Generate single CTE-based SQL for appointment mutations.
        
        Returns single SQL that handles all operations in one transaction.
        """
        if not customer_id:
            return {
                "statusCode": 401,
                "body": {"response": "Yêu cầu xác thực để thực hiện thao tác này."},
                "headers": {"Content-Type": "application/json"}
            }
        
        # Generate the prompt with appointment info
        mutation_prompt = self.generate_appointment_mutation_prompt(query, schema, customer_id, appointment_info)
        logger.debug(f"Mutation prompt: {mutation_prompt[:300]}...")
        
        # Call Bedrock
        text_content = self._invoke_bedrock(mutation_prompt)
        logger.info(f"Mutation response (first 500 chars): {text_content[:500]}...")

        # Extract operation type
        operation_regex = re.compile(r"<operation>(.*?)</operation>", re.DOTALL)
        operation_match = operation_regex.findall(text_content)
        operation = operation_match[0].strip().upper() if operation_match else "UNKNOWN"

        # Extract SQL
        sql_regex = re.compile(r"<sql>(.*?)</sql>", re.DOTALL)
        sql_statements = sql_regex.findall(text_content)

        # Extract parameters
        params_regex = re.compile(r"<params>(.*?)</params>", re.DOTALL)
        params_match = params_regex.findall(text_content)

        if not sql_statements:
            # Check for error tag
            error_regex = re.compile(r"<error>(.*?)</error>", re.DOTALL)
            error_match = error_regex.findall(text_content)
            if error_match:
                return {
                    "statusCode": 400,
                    "body": {"response": error_match[0].strip()},
                    "headers": {"Content-Type": "application/json"}
                }
            return {
                "statusCode": 500,
                "body": {"response": "Không thể tạo SQL cho yêu cầu này."},
                "headers": {"Content-Type": "application/json"}
            }

        sql_query = sql_statements[0].strip()
        
        # Clean SQL: remove double quotes, lowercase identifiers
        sql_query = re.sub(r'"([a-zA-Z_][a-zA-Z0-9_]*)"', lambda m: m.group(1).lower(), sql_query)

        # CRITICAL: Block DELETE statements - always use soft delete (UPDATE status)
        sql_upper = sql_query.upper().strip()
        if sql_upper.startswith("DELETE") or "DELETE FROM" in sql_upper:
            logger.error(f"DELETE statement blocked! Use UPDATE status='cancelled' instead. SQL: {sql_query}")
            return {
                "statusCode": 403,
                "body": {"response": "Không được phép dùng DELETE. Để hủy lịch hẹn, hệ thống sẽ cập nhật trạng thái thành 'cancelled'."},
                "headers": {"Content-Type": "application/json"}
            }

        # Security validation: ensure WHERE clause exists for UPDATE/CANCEL
        if operation in ["UPDATE", "CANCEL"]:
            if "WHERE" not in sql_query.upper():
                logger.error(f"UPDATE without WHERE clause detected: {sql_query}")
                return {
                    "statusCode": 400,
                    "body": {"response": "Lỗi bảo mật: UPDATE phải có điều kiện WHERE."},
                    "headers": {"Content-Type": "application/json"}
                }
            # Ensure appointmentid is in WHERE clause
            sql_lower = sql_query.lower()
            if "appointmentid" not in sql_lower:
                logger.error(f"UPDATE without appointmentid in WHERE: {sql_query}")
                return {
                    "statusCode": 400,
                    "body": {"response": "Lỗi bảo mật: Phải có appointmentid trong điều kiện WHERE."},
                    "headers": {"Content-Type": "application/json"}
                }
            
            # CRITICAL: For UPDATE/CANCEL on appointment table, must have customerid in WHERE
            # This ensures user can only modify their own appointments
            if "update appointment" in sql_lower:
                if "customerid" not in sql_lower:
                    logger.error(f"UPDATE appointment without customerid in WHERE: {sql_query}")
                    return {
                        "statusCode": 400,
                        "body": {"response": "Lỗi bảo mật: UPDATE appointment phải có customerid trong điều kiện WHERE."},
                        "headers": {"Content-Type": "application/json"}
                    }

        # Parse parameters
        params = []
        if params_match:
            try:
                raw_params = params_match[0].strip()
                if raw_params not in ['[]', '']:
                    params = ast.literal_eval(raw_params)
                    if not isinstance(params, list):
                        params = [params]
            except Exception as e:
                logger.error(f"Error parsing mutation parameters: {e}")
                return {
                    "statusCode": 500,
                    "body": {"response": "Lỗi xử lý tham số."},
                    "headers": {"Content-Type": "application/json"}
                }

        # Validate placeholder count
        placeholder_count = sql_query.count('%s')
        if placeholder_count != len(params):
            logger.warning(f"Placeholder mismatch: {placeholder_count} vs {len(params)}")
            return {
                "statusCode": 500,
                "body": {"response": f"Lỗi: SQL có {placeholder_count} placeholder nhưng có {len(params)} tham số."},
                "headers": {"Content-Type": "application/json"}
            }

        logger.info(f"Generated mutation - Operation: {operation}")
        logger.info(f"SQL: {sql_query}")
        logger.info(f"Params: {params}")

        return sql_query, params, operation

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

        # Log raw response for debugging
        logger.info(f"Raw Bedrock response (first 500 chars): {text_content[:500]}...")

        # Clean SQL: remove double quotes around identifiers and convert to lowercase
        # PostgreSQL treats unquoted identifiers as lowercase
        cleaned_sql_statements = []
        for sql in sql_statements:
            # Remove double quotes around identifiers (table/column names)
            # Pattern: "identifier" -> identifier (lowercase)
            cleaned_sql = re.sub(r'"([a-zA-Z_][a-zA-Z0-9_]*)"', lambda m: m.group(1).lower(), sql)
            cleaned_sql_statements.append(cleaned_sql)
        sql_statements = cleaned_sql_statements

        logger.info(f"Extracted SQL: {sql_statements}")
        logger.info(f"Raw params string: {params_match}")

        # Check if SQL was successfully generated
        if not sql_statements:
            return {"statusCode": 500,
                    "body": {"response": "Unable to generate SQL for the provided prompt, please try again."},
                    "headers": {"Content-Type": "application/json"}}

        # Parse parameters if available, otherwise return empty list
        params = []
        if params_match:
            try:
                raw_params = params_match[0].strip()
                # Handle empty array case
                if raw_params in ['[]', '']:
                    params = []
                else:
                    # Safely evaluate the parameter list (should be a Python list literal)
                    params = ast.literal_eval(raw_params)
                    # Ensure it's a list
                    if not isinstance(params, list):
                        params = [params]
            except Exception as e:
                logger.error(f"Error parsing parameters: {e}")
                logger.error(f"Raw parameters string: {params_match[0]}")
                # Continue with empty params rather than failing

        # Validate: count %s placeholders and compare with params
        sql_query = sql_statements[0]
        placeholder_count = sql_query.count('%s')
        params_count = len(params)
        
        if placeholder_count != params_count:
            logger.warning(f"Placeholder mismatch! SQL has {placeholder_count} placeholders but got {params_count} params")
            logger.warning(f"SQL: {sql_query}")
            logger.warning(f"Params: {params}")
            
            # If no params but has placeholders, this is a serious error
            if params_count == 0 and placeholder_count > 0:
                return {"statusCode": 500,
                        "body": {"response": f"Lỗi: SQL có {placeholder_count} placeholder nhưng không có tham số. Vui lòng thử lại."},
                        "headers": {"Content-Type": "application/json"}}

        logger.info(f"Final SQL: {sql_query}")
        logger.info(f"Final params: {params}")
        
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
            
        