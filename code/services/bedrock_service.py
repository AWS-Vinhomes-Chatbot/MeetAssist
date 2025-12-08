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
    bedrock_lite = BedrockService(model_id="anthropic.claude-haiku-4-5-20251001-v1:0")
    intent = bedrock_lite.classify_intent(message)
    
    # Lambda 2 (Inside VPC) - Use more powerful model for SQL generation
    bedrock_pro = BedrockService(model_id="anthropic.claude-3-5-sonnet-20241022-v2:0")
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

# Throttling message - shown to user when Bedrock is overloaded
THROTTLING_MESSAGE = "⏳ Hệ thống đang bận, vui lòng chờ 1 phút rồi gửi lại yêu cầu nhé!"

# Module-level singleton for Bedrock client (reuse across Lambda invocations)
_bedrock_client = None
# gọi client bedrock để các lamdba khác cũng dùng chung

def get_bedrock_client(region: str = None):
    """
    Get or create Bedrock Runtime client singleton.
    
    This is reused across Lambda invocations to improve performance.
    
    Args:
        region: AWS region (default from env or ap-northeast-1 for Tokyo)
    
    Returns:
        boto3 Bedrock Runtime client instance
    """
    global _bedrock_client
    if _bedrock_client is None:
        # Use Tokyo region for lowest latency
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
        # Use Claude 3 Haiku - stable and fast, available in Tokyo region
        self.model_id = model_id or os.environ.get(
            "BEDROCK_MODEL_ID", 
            "anthropic.claude-3-haiku-20240307-v1:0"  # Claude 3 Haiku - stable in ap-northeast-1
        )
        
        self.max_tokens = max_tokens or int(os.environ.get("BEDROCK_MAX_TOKENS", "1500"))  # Giới hạn để tránh vượt 2000 chars
        self.temperature = temperature if temperature is not None else float(os.environ.get("BEDROCK_TEMPERATURE", "0.5"))
        self.top_k = 100
        self.top_p = 0.9
        
        logger.info(f"BedrockService initialized with model: {self.model_id}, "
                   f"max_tokens: {self.max_tokens}, temperature: {self.temperature}")
        
        # Claude 3.5 Sonnet for extraction tasks (more accurate, on-demand supported)
        self.sonnet_model_id = os.environ.get(
            "BEDROCK_SONNET_MODEL_ID",
            "anthropic.claude-3-5-sonnet-20240620-v1:0"  # Claude 3.5 Sonnet - on-demand in Tokyo
        )
    
    def _invoke_bedrock(self, prompt: str, max_retries: int = 5) -> str:
        """
        Invoke Bedrock model with prompt and exponential backoff retry.
        
        Args:
            prompt: Input prompt
            max_retries: Maximum number of retry attempts for throttling errors (default 5)
            
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
        
        # All retries exhausted - return friendly message instead of raising
        logger.error(f"Bedrock throttling: max retries ({max_retries}) exhausted")
        return THROTTLING_MESSAGE
    
    def _invoke_bedrock_sonnet(self, prompt: str, max_retries: int = 5, temperature: float = 0.1) -> str:
        """
        Invoke Claude 3.5 Sonnet for extraction tasks (more accurate than Haiku).
        Uses lower temperature for more deterministic outputs.
        
        Args:
            prompt: Input prompt
            max_retries: Maximum number of retry attempts (default 5)
            temperature: Temperature for generation (default 0.1 for extraction)
            
        Returns:
            Model response text
        """
        # Prepare request body for Claude Sonnet
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,  # Extraction responses are shorter
            "temperature": temperature,  # Low temperature for accurate extraction
            "top_k": 50,
            "top_p": 0.9,
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
                response = self.bedrock_runtime.invoke_model(
                    body=body,
                    modelId=self.sonnet_model_id,
                    accept="application/json",
                    contentType="application/json"
                )
                
                response_body = json.loads(response['body'].read())
                
                if 'content' in response_body and len(response_body['content']) > 0:
                    return response_body['content'][0]['text']
                
                return ""
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code in ('ThrottlingException', 'TooManyRequestsException', 'ServiceUnavailableException'):
                    last_exception = e
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Sonnet throttling (attempt {attempt + 1}/{max_retries}), waiting {wait_time:.2f}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Error invoking Sonnet: {e}")
                    raise
            except Exception as e:
                logger.error(f"Error invoking Sonnet: {e}")
                raise
        
        # All retries exhausted - return friendly message instead of raising
        logger.error(f"Sonnet throttling: max retries ({max_retries}) exhausted")
        return THROTTLING_MESSAGE
    
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
    def generate_sql_prompt(self, question: str, schema: str, customer_id: str = None) -> str:
        """
        Generate SQL query from natural language question.
        
        Args:
            question: User's question in natural language
            schema: Database schema description (dynamically provided)
            customer_id: Optional customer ID for user-specific queries (e.g., "lịch hẹn của tôi")
            
        Returns:
            SQL prompt text for Bedrock
        """
        # Build customer context if available
        customer_context = ""
        if customer_id:
            # Ensure customer_id is treated as string (VARCHAR in DB)
            customer_id_str = str(customer_id)
            customer_context = f"""
## THÔNG TIN USER HIỆN TẠI (ĐÃ XÁC THỰC):
- customer_id: "{customer_id_str}" (VARCHAR/string, KHÔNG phải số)
- Khi user hỏi "của tôi", "của mình", "lịch hẹn tôi", "cuộc hẹn của tôi" → dùng customerid = %s với param ["{customer_id_str}"]
- Đây là thông tin đã xác thực, KHÔNG cần hỏi lại user
- QUAN TRỌNG: customerid là VARCHAR, params phải là STRING có quotes, VD: ["{customer_id_str}"] KHÔNG PHẢI [{customer_id_str}]

"""
        
        sql_prompt_text = f"""Bạn là chuyên gia SQL PostgreSQL bảo mật. Tạo query SELECT an toàn từ yêu cầu người dùng.
{customer_context}
## QUY TẮC (bắt buộc):
- CHỈ SELECT, KHÔNG INSERT/UPDATE/DELETE → nếu yêu cầu thay đổi dữ liệu: trả <error>Không hỗ trợ thay đổi dữ liệu</error>
- Dùng `%s` cho TẤT CẢ tham số từ USER INPUT (psycopg3), KHÔNG nối chuỗi
- Tên bảng/cột: lowercase, không ngoặc kép, CHÍNH XÁC như schema, không viết tắt
- So sánh Tiếng Việt: dùng `unaccent(LOWER(col)) ILIKE unaccent(LOWER(%s))` để hỗ trợ cả có dấu và không dấu
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

## QUY TẮC NGÀY/THỜI GIAN (RẤT QUAN TRỌNG):
- Ngày tương đối: dùng hàm PostgreSQL TRỰC TIẾP trong SQL, KHÔNG dùng placeholder %s
  * "hôm nay", "today" → CURRENT_DATE
  * "ngày mai", "tomorrow" → CURRENT_DATE + INTERVAL '1 day'
  * "hôm qua", "yesterday" → CURRENT_DATE - INTERVAL '1 day'  
  * "tuần này" → date >= date_trunc('week', CURRENT_DATE)
  * "tháng này" → EXTRACT(MONTH FROM col) = EXTRACT(MONTH FROM CURRENT_DATE)
  * "năm nay" → EXTRACT(YEAR FROM col) = EXTRACT(YEAR FROM CURRENT_DATE)
- Ngày cụ thể từ user (VD: "ngày 15/12/2025") → dùng %s với format 'YYYY-MM-DD'
- So sánh DATE với TIMESTAMP: dùng col::date hoặc DATE(col)

## QUY TẮC BẢO MẬT & QUYỀN TRUY CẬP (CRITICAL):
### 1. LỊCH HẸN CỦA CUSTOMER (bảng appointment):
- **BẮT BUỘC**: Khi query appointment liên quan đến customer cụ thể, PHẢI có WHERE customerid = %s::VARCHAR
- Ví dụ câu hỏi: "lịch hẹn của tôi", "cuộc hẹn của mình", "appointment của customer X"
- **KHÔNG** cho phép query tất cả appointment mà không filter theo customerid (trừ khi hỏi thống kê tổng quát)
- **CHỈ** customer được xem appointment của chính họ (dùng customer_id từ THÔNG TIN USER HIỆN TẠI)

### 2. LỊCH TƯ VẤN VIÊN (bảng consultantschedule):
- **BẮT BUỘC**: CHỈ query lịch HIỆN TẠI và TƯƠNG LAI, KHÔNG query quá khứ
- **LOGIC THỜI GIAN**:
  * Ngày tương lai (date > CURRENT_DATE): Lấy TẤT CẢ slots, KHÔNG cần kiểm tra starttime
  * Hôm nay (date = CURRENT_DATE): Chỉ lấy slots có starttime >= CURRENT_TIME
  * Kết hợp: `(date > CURRENT_DATE) OR (date = CURRENT_DATE AND starttime >= CURRENT_TIME)`
- Ví dụ: "lịch trống của tư vấn viên", "slot còn trống", "lịch rảnh" → áp dụng logic trên
- **LÝ DO**: Bảo mật thông tin cá nhân, lịch quá khứ không còn ý nghĩa cho đặt lịch

### 3. XỬ LÝ VI PHẠM:
- Nếu user hỏi appointment của customer mà không có customer_id context → trả <error>Cần đăng nhập để xem lịch hẹn cá nhân</error>
- Nếu user cố query consultantschedule quá khứ → tự động thêm date >= CURRENT_DATE, KHÔNG trả lỗi

## FEW-SHOT EXAMPLES:

### Ví dụ 1 - Query đơn giản:
Schema: customer(customerid, fullname, phonenumber, dateofbirth)
Question: Lấy tên khách hàng có id là 123
<reasoning>Cần cột fullname từ bảng customer, filter theo customerid (VARCHAR). Cast param về VARCHAR.</reasoning>
<sql>SELECT fullname FROM customer WHERE customerid = %s::VARCHAR</sql>
<params>["123"]</params>
<validation>1 placeholder = 1 param ✓ | bảng customer, cột fullname, customerid tồn tại ✓ | param cast to VARCHAR ✓</validation>

### Ví dụ 2 - Tìm kiếm Tiếng Việt (CÓ DẤU & KHÔNG DẤU):
Schema: consultant(consultantid, fullname, specialties)
Question: Tìm tư vấn viên tên có chứa "Nguyễn"
<reasoning>Fuzzy search tên Tiếng Việt → dùng unaccent() để bỏ dấu khi so sánh, hỗ trợ cả input có dấu và không dấu.</reasoning>
<sql>SELECT consultantid, fullname, specialties FROM consultant WHERE unaccent(LOWER(fullname)) ILIKE unaccent(LOWER(%s))</sql>
<params>["%Nguyễn%"]</params>
<validation>1 placeholder = 1 param ✓ | unaccent() xử lý tiếng Việt ✓</validation>

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
<reasoning>status='completed' là ENUM → giá trị cố định. Tên "Nguyễn Văn A" là user input → dùng %s với unaccent().</reasoning>
<sql>SELECT a.appointmentid, a.scheduledtime, c.fullname FROM appointment a JOIN consultant c ON a.consultantid = c.consultantid WHERE a.status = 'completed' AND unaccent(LOWER(c.fullname)) ILIKE unaccent(LOWER(%s)) ORDER BY a.scheduledtime DESC</sql>
<params>["%Nguyễn Văn A%"]</params>
<validation>1 placeholder = 1 param ✓ | status cố định ✓ | tên dùng unaccent() ✓</validation>

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

### Ví dụ 9 - QUERY DỮ LIỆU CỦA USER HIỆN TẠI:
Schema: appointment(appointmentid, customerid, consultantid, date, time, status), consultant(consultantid, fullname), customer(customerid, fullname)
THÔNG TIN USER HIỆN TẠI: customer_id = "fb_12345"
Question: Cho xem lịch hẹn của tôi
<reasoning>User hỏi "của tôi" → dùng customer_id từ context. Filter appointment theo customerid, cast param về VARCHAR.</reasoning>
<sql>SELECT a.appointmentid, a.date, a.time, a.status, c.fullname as consultant_name FROM appointment a JOIN consultant c ON a.consultantid = c.consultantid WHERE a.customerid = %s::VARCHAR ORDER BY a.date DESC, a.time DESC</sql>
<params>["fb_12345"]</params>
<validation>1 placeholder = 1 param ✓ | customer_id từ context ✓ | param cast to VARCHAR ✓</validation>

### Ví dụ 10 - QUERY "CỦA TÔI" KẾT HỢP ĐIỀU KIỆN:
Schema: appointment(appointmentid, customerid, consultantid, date, time, status)
THÔNG TIN USER HIỆN TẠI: customer_id = "fb_67890"
Question: Lịch hẹn sắp tới của mình tuần này
<reasoning>"của mình" → dùng customer_id. "sắp tới" → status='upcoming'. "tuần này" → date trong tuần hiện tại.</reasoning>
<sql>SELECT appointmentid, date, time FROM appointment WHERE customerid = %s::VARCHAR AND status = 'upcoming' AND date >= date_trunc('week', CURRENT_DATE) AND date < date_trunc('week', CURRENT_DATE) + INTERVAL '7 days' ORDER BY date ASC, time ASC</sql>
<params>["fb_67890"]</params>
<validation>1 placeholder = 1 param ✓ | status cố định ✓ | customer_id từ context ✓ | param cast to VARCHAR ✓</validation>

### Ví dụ 11 - LỊCH TƯ VẤN VIÊN (TẤT CẢ LỊCH TRỐNG):
Schema: consultantschedule(scheduleid, consultantid, date, starttime, endtime, isavailable), consultant(consultantid, fullname)
Question: Lịch trống của tư vấn viên Nguyễn Văn A
<reasoning>Query consultantschedule → BẮT BUỘC (date > CURRENT_DATE) OR (date = CURRENT_DATE AND starttime >= CURRENT_TIME). Tên tư vấn viên dùng unaccent(), isavailable=true.</reasoning>
<sql>SELECT cs.scheduleid, cs.date, cs.starttime, cs.endtime FROM consultantschedule cs JOIN consultant c ON cs.consultantid = c.consultantid WHERE unaccent(LOWER(c.fullname)) ILIKE unaccent(LOWER(%s)) AND cs.isavailable = true AND (cs.date > CURRENT_DATE OR (cs.date = CURRENT_DATE AND cs.starttime >= CURRENT_TIME)) ORDER BY cs.date ASC, cs.starttime ASC</sql>
<params>["%Nguyễn Văn A%"]</params>
<validation>1 placeholder = 1 param ✓ | date > CURRENT_DATE OR (date = CURRENT_DATE AND starttime >= CURRENT_TIME) bắt buộc ✓ | isavailable là boolean ✓</validation>

### Ví dụ 11b - LỊCH TRỐNG NGÀY MAI (NGÀY CỤ THỂ TRONG TƯƠNG LAI):
Schema: consultantschedule(scheduleid, consultantid, date, starttime, endtime, isavailable), consultant(consultantid, fullname)
Question: Lịch trống ngày mai
<reasoning>Query consultantschedule ngày mai (date = CURRENT_DATE + 1 day) → Lấy TẤT CẢ slots trong ngày, KHÔNG cần kiểm tra starttime vì là ngày tương lai.</reasoning>
<sql>SELECT cs.scheduleid, cs.date, cs.starttime, cs.endtime, c.fullname FROM consultantschedule cs JOIN consultant c ON cs.consultantid = c.consultantid WHERE cs.date = CURRENT_DATE + INTERVAL '1 day' AND cs.isavailable = true ORDER BY cs.starttime ASC</sql>
<params>[]</params>
<validation>0 placeholder = 0 param ✓ | date = CURRENT_DATE + INTERVAL '1 day' (ngày mai) ✓ | KHÔNG có starttime >= CURRENT_TIME vì là ngày tương lai ✓</validation>

### Ví dụ 12 - VI PHẠM BẢO MẬT (KHÔNG CÓ CUSTOMER_ID):
Schema: appointment(appointmentid, customerid, consultantid, date, time, status)
THÔNG TIN USER HIỆN TẠI: KHÔNG CÓ (chưa đăng nhập)
Question: Cho xem lịch hẹn của tôi
<reasoning>User hỏi "của tôi" nhưng không có customer_id trong context → vi phạm bảo mật.</reasoning>
<error>Cần đăng nhập để xem lịch hẹn cá nhân</error>


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

    def extract_appointment_info(self, message: str, current_info: Dict[str, Any] = None, context: str = "") -> Dict[str, Any]:
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
            context: Conversation context/history for better understanding
            
        Returns:
            Dictionary with extracted fields (only non-empty values)
        """
        if current_info is None:
            current_info = {}
        
        # ========== STEP 0: SIMPLE PATTERN MATCHING (FAST, NO LLM) ==========
        # Handle simple cases without calling Bedrock
        import re
        message_stripped = message.strip()
        
        # Phone number: 10-11 digits starting with 0
        phone_pattern = r'^0\d{9,10}$'
        if re.match(phone_pattern, message_stripped):
            logger.info(f"Pattern match: phone_number = {message_stripped}")
            return {"phone_number": message_stripped}
        
        # Email: contains @ and .
        email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if re.match(email_pattern, message_stripped, re.IGNORECASE):
            logger.info(f"Pattern match: email = {message_stripped}")
            return {"email": message_stripped.lower()}
        
        # Vietnamese name: 2-5 words, each capitalized, no special chars
        # Examples: "Nguyễn Văn A", "Phan Quốc Anh", "Lê Thị Mai"
        name_pattern = r'^[A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ][a-zàáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]*(\s+[A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ][a-zàáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]*){1,4}$'
        if re.match(name_pattern, message_stripped) and len(message_stripped.split()) >= 2:
            # Check if it's likely a customer name (not consultant)
            # If user is in collecting_customer state, it's customer_name
            if current_info.get("booking_state") == "collecting_customer" or \
               (current_info.get("consultant_name") and not current_info.get("customer_name")):
                logger.info(f"Pattern match: customer_name = {message_stripped}")
                return {"customer_name": message_stripped}
        
        booking_action = current_info.get("booking_action", "create")
        
        # ========== STEP 1: LLM EXTRACTION FOR COMPLEX CASES ==========
        # Build context section
        context_section = ""
        if context:
            context_section = f"""
## LỊCH SỬ HỘI THOẠI (ĐỌC KỸ ĐỂ HIỂU CONTEXT):
{context}
"""
        
        # Get current date dynamically
        from datetime import datetime, timedelta
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        tomorrow_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        day_after_str = (today + timedelta(days=2)).strftime("%Y-%m-%d")
            
        prompt = f"""Bạn là trợ lý AI phân loại và trích xuất thông tin đặt lịch.

## CONTEXT:
{context_section}
## THÔNG TIN ĐÃ THU THẬP:
{json.dumps(current_info, ensure_ascii=False, indent=2)}

## TIN NHẮN HIỆN TẠI CỦA USER:
"{message}"

## BƯỚC 1: PHÂN LOẠI Ý ĐỊNH

### is_query = TRUE khi user muốn BOT TRA CỨU/LẤY THÔNG TIN TỪ HỆ THỐNG:
- Hỏi danh sách: "cho tôi tên...", "liệt kê...", "cho xem...", "xem danh sách..."
- Yêu cầu xem: "cho tôi lại...", "cho mình...", "đưa cho tôi...", "gửi lại..."
- Hỏi thông tin: "có ai...", "ai rảnh...", "lịch trống...", "còn slot không"
- Hỏi cụ thể: "tư vấn viên nào...", "ngày nào...", "giờ nào..."
- Hỏi điều kiện: "có không?", "được không?", "như thế nào?"
- QUAN TRỌNG: "cho tôi X đi", "cho tôi lại X", "đưa X cho tôi" = YÊU CẦU XEM → is_query=true

### is_query = FALSE khi user CUNG CẤP THÔNG TIN ĐẶT LỊCH:
- Trả lời trực tiếp: "tên tôi là...", "SĐT: 0912...", "email@..."
- Cung cấp dữ liệu: chỉ số điện thoại, chỉ tên, chỉ ngày/giờ
- Chọn/xác nhận: "chọn số 2", "đặt với anh Hùng", "9h sáng mai"
- Ra quyết định đặt lịch: "tôi muốn đặt với...", "chọn ngày...", "lấy giờ..."

## BƯỚC 2: TÓM TẮT Ý ĐỊNH TRƯỚC KHI TRÍCH XUẤT

**QUAN TRỌNG**: Khi is_query=false, PHẢI viết user_intent_summary MÔ TẢ QUYẾT ĐỊNH ĐẶT LỊCH CỦA USER:
- User muốn đặt với ai? (consultant)
- User chọn ngày nào? (date)
- User chọn giờ nào? (time)
- User cung cấp thông tin gì về bản thân? (name, phone, email)

Ví dụ summary tốt: "User quyết định đặt lịch với tư vấn viên Hùng vào ngày mai lúc 9h sáng"

## BƯỚC 3: TRÍCH XUẤT THÔNG TIN TỪ SUMMARY (chỉ khi is_query=false)

Dựa vào user_intent_summary, trích xuất các field:
- customer_name: Tên khách hàng (HỌ VÀ TÊN người đặt lịch)
- phone_number: SĐT (10-11 số, bắt đầu bằng 0)
- email: Email (có dấu @)
- appointment_date: Ngày hẹn (YYYY-MM-DD). Hôm nay={today_str}, Ngày mai={tomorrow_str}, Ngày kia={day_after_str}
- appointment_time: Giờ hẹn (HH:MM 24h). "9h"→"09:00", "2h chiều"→"14:00"
- consultant_name: Tên TƯ VẤN VIÊN (người được đặt lịch với)
- appointment_id: Mã lịch hẹn cần sửa/hủy

## QUY TẮC:
1. "đặt lịch VỚI X", "hẹn với X", "gặp X" → X là consultant_name
2. Bot hỏi "họ tên, SĐT, email" + user trả lời → thông tin customer
3. Tin nhắn CHỈ chứa số 10-11 chữ số → phone_number
4. KHÔNG TỰ BỊA THÔNG TIN - chỉ trích xuất từ message
5. KHI KHÔNG CHẮC CHẮN → ưu tiên is_query=true

## OUTPUT FORMAT - CHỈ JSON:
{{
  "user_intent_summary": "Mô tả chi tiết quyết định/yêu cầu của user",
  "is_query": boolean,
  ...extracted_fields (nếu is_query=false, trích xuất từ summary)
}}

## VÍ DỤ:

### Ví dụ is_query=true (user HỎI thông tin):
- "cho tôi tên các tư vấn viên đi" → {{"user_intent_summary": "User yêu cầu xem danh sách tên các tư vấn viên", "is_query": true}}
- "cho tôi lại tên các tư vấn viên" → {{"user_intent_summary": "User yêu cầu xem lại danh sách tư vấn viên", "is_query": true}}
- "Lịch trống ngày mai thế nào?" → {{"user_intent_summary": "User muốn xem lịch trống vào ngày mai", "is_query": true}}
- "Anh Hùng còn slot nào không?" → {{"user_intent_summary": "User hỏi các slot trống của tư vấn viên tên Hùng", "is_query": true}}

### Ví dụ is_query=false (user CUNG CẤP thông tin đặt lịch):
- "đặt với anh Hùng ngày mai 9h" → {{"user_intent_summary": "User quyết định đặt lịch với tư vấn viên Hùng vào ngày mai ({tomorrow_str}) lúc 9h sáng", "is_query": false, "consultant_name": "Hùng", "appointment_date": "{tomorrow_str}", "appointment_time": "09:00"}}
- "0379729847" → {{"user_intent_summary": "User cung cấp số điện thoại 0379729847", "is_query": false, "phone_number": "0379729847"}}
- "Tôi là Nguyễn Văn A, email abc@gmail.com" → {{"user_intent_summary": "User cung cấp họ tên Nguyễn Văn A và email abc@gmail.com", "is_query": false, "customer_name": "Nguyễn Văn A", "email": "abc@gmail.com"}}
- "chọn ngày 10/12 lúc 14h" → {{"user_intent_summary": "User chọn ngày 10/12/2025 lúc 14h để đặt lịch", "is_query": false, "appointment_date": "2025-12-10", "appointment_time": "14:00"}}"""

        try:
            # Use Claude 3 Sonnet for more accurate extraction
            response_text = self._invoke_bedrock_sonnet(prompt, temperature=0.2)
            logger.info(f"Sonnet extraction response: {response_text[:500] if response_text else 'EMPTY'}")
            
            # Clean up response to extract JSON
            response_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                parts = response_text.split("```")
                if len(parts) >= 2:
                    response_text = parts[1].strip()
            
            # If response contains text before JSON, extract JSON using improved regex
            if not response_text.startswith("{"):
                import re
                # Find the first { and find matching } by counting braces
                start_idx = response_text.find("{")
                if start_idx != -1:
                    brace_count = 0
                    end_idx = start_idx
                    for i, char in enumerate(response_text[start_idx:], start=start_idx):
                        if char == "{":
                            brace_count += 1
                        elif char == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i
                                break
                    if end_idx > start_idx:
                        response_text = response_text[start_idx:end_idx + 1]
                        logger.info(f"Extracted JSON from mixed response: {response_text[:200]}")
                    else:
                        logger.warning(f"Failed to find matching braces in: {response_text[:200]}")
                        return {}
                else:
                    logger.warning(f"No JSON found in response: {response_text[:200]}")
                    return {}
            
            # Try to extract JSON from response
            extracted_info = json.loads(response_text)
            
            # Log the user intent summary for debugging
            if "user_intent_summary" in extracted_info:
                logger.info(f"📝 User Intent: {extracted_info['user_intent_summary']}")
            
            # Filter out empty/null values but KEEP is_query and user_intent_summary
            cleaned_info = {}
            for k, v in extracted_info.items():
                if k == "is_query":
                    # Always keep is_query as boolean
                    cleaned_info["is_query"] = bool(v)
                elif k == "user_intent_summary":
                    # Always keep the summary for context
                    cleaned_info["user_intent_summary"] = str(v) if v else ""
                elif v and str(v).strip():
                    cleaned_info[k] = v
            
            logger.info(f"Extracted appointment info: {cleaned_info}")
            return cleaned_info
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from Bedrock response: {e}. Response: {response_text[:200] if response_text else 'EMPTY'}")
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
            "email": "email để nhận thông báo",
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
        Uses Claude AI for intent classification with structured prompt.
        
        Args:
            message: User's message
            
        Returns:
            Dict with:
                - wants_booking: bool - True if user wants to interact with booking
                - booking_action: str - "create", "update", "cancel" or None
                - matched_keywords: list - keywords found in message
                - confidence: float - 0.0 to 1.0
        """
        prompt = f"""
SYSTEM: Bạn là hệ thống phân loại ý định đặt lịch (booking intent classifier).
NHIỆM VỤ: Phân tích message và trả về JSON.
QUY TẮC CỐT LÕI:
1. MẶC ĐỊNH: wants_booking = false. Chỉ true khi có từ khóa hành động rõ ràng (Tạo/Sửa/Hủy).
2. KHÔNG PHẢI ĐẶT LỊCH: Hỏi lịch trống (availability), hỏi giá, kiểm tra lịch đã đặt, chào hỏi, cung cấp sđt khơi khơi -> false.
3. OUTPUT: Chỉ trả về JSON, không giải thích.

TỪ KHÓA (Keywords):
- CREATE: "đặt lịch", "book", "đặt hẹn", "đăng ký", "schedule", "xin đặt".
- UPDATE: "đổi lịch", "dời lịch", "sửa lịch", "reschedule", "thay đổi".
- CANCEL: "hủy lịch", "cancel", "bỏ lịch", "hủy hẹn".

JSON SCHEMA:
{{
  "wants_booking": boolean,
  "booking_action": "create" | "update" | "cancel" | null,
  "matched_keywords": [string],
  "confidence": float (0.0-1.0)
}}

VÍ DỤ (Few-shot learning):
Input: "Chiều mai cho tôi đặt lịch massage." -> {{"wants_booking": true, "booking_action": "create", "matched_keywords": ["đặt lịch"], "confidence": 0.95}}
Input: "Tuần sau còn slot trống không?" -> {{"wants_booking": false, "booking_action": null, "matched_keywords": ["slot"], "confidence": 0.1}}
Input: "Tôi muốn dời lịch hẹn sang thứ 2." -> {{"wants_booking": true, "booking_action": "update", "matched_keywords": ["dời lịch"], "confidence": 0.9}}
Input: "Giá dịch vụ bao nhiêu?" -> {{"wants_booking": false, "booking_action": null, "matched_keywords": [], "confidence": 0.05}}
Input: "Hủy giúp tôi cái hẹn hôm nay." -> {{"wants_booking": true, "booking_action": "cancel", "matched_keywords": ["hủy"], "confidence": 0.95}}

USER MESSAGE: "{message}"
"""
        
        try:
            # Use Claude Haiku for fast intent classification
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 256,
                "temperature": 0.2,  # Deterministic for classification
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            
            response = self.bedrock_runtime.invoke_model(
                modelId="anthropic.claude-3-haiku-20240307-v1:0",
                body=json.dumps(body)
            )
            
            response_body = json.loads(response["body"].read())
            response_text = response_body["content"][0]["text"].strip()
            
            logger.info(f"Intent classification raw response: {response_text}")
            
            # Parse JSON response
            # Handle case where response might have markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            intent_result = json.loads(response_text)
            
            # Validate required fields
            if "wants_booking" not in intent_result:
                intent_result["wants_booking"] = False
            if "booking_action" not in intent_result:
                intent_result["booking_action"] = None
            if "confidence" not in intent_result:
                intent_result["confidence"] = 0.5
            if "matched_keywords" not in intent_result:
                intent_result["matched_keywords"] = []
                
            logger.info(f"Intent classification result: {intent_result}")
            return intent_result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse intent JSON: {e}, response: {response_text}")
            # Fallback to no booking intent
            return {
                "wants_booking": False,
                "booking_action": None,
                "matched_keywords": [],
                "confidence": 0.0
            }
        except Exception as e:
            logger.error(f"Intent classification error: {e}")
            # Fallback to no booking intent on error
            return {
                "wants_booking": False,
                "booking_action": None,
                "matched_keywords": [],
                "confidence": 0.0
            }

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
| email | {appointment_info.get('email', 'N/A')} | email |
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
3. UPDATE appointment phải có WHERE appointmentid = %s AND customerid = %s::VARCHAR (cast tham số về VARCHAR)
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
    INSERT INTO customer (customerid, fullname, phonenumber, email) 
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (customerid) DO UPDATE SET 
        fullname = COALESCE(EXCLUDED.fullname, customer.fullname),
        phonenumber = COALESCE(EXCLUDED.phonenumber, customer.phonenumber),
        email = COALESCE(EXCLUDED.email, customer.email)
    RETURNING customerid
)
INSERT INTO appointment (customerid, consultantid, date, time, status)
SELECT %s, %s, %s, %s, 'pending'
FROM upsert_customer
RETURNING appointmentid
```
params: [customer_id, customer_name, phone_number, email, customer_id, consultant_id, date, time]

### UPDATE (Đổi lịch):
Bước 1: UPDATE appointment cũ → status='cancelled'
Bước 2: INSERT appointment mới với status='pending'
⚠️ WHERE phải có customerid để verify ownership!
```sql
WITH cancel_old AS (
    UPDATE appointment SET status = 'cancelled', updatedat = CURRENT_TIMESTAMP
    WHERE appointmentid = %s AND customerid = %s::VARCHAR
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
WHERE appointmentid = %s AND customerid = %s::VARCHAR
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

    def get_sql_from_bedrock(self, query: str, schema: str, customer_id: str = None) -> Union[Tuple[str, List], Dict[str, Any]]:
        """Generate SQL from a natural language query using Bedrock.

        Args:
            query (str): The natural language query.
            schema (str): The database schema.
            customer_id (str): Optional customer ID for user-specific queries (e.g., "lịch hẹn của tôi").

        Returns:
            Union[Tuple[str, List], Dict[str, Any]]: The generated SQL statement and parameters or an error response dictionary.

        Raises:
            Exception: If there is an error generating SQL from the query.
        """
        # Generate the prompt for Bedrock (with customer_id if available)
        sql_prompt = self.generate_sql_prompt(query, schema, customer_id)
        logger.debug(f"SQL prompt: {sql_prompt[:200]}...")
        
        # Call Bedrock to generate SQL
        text_content = self._invoke_bedrock(sql_prompt)

        # Check if Bedrock returned throttling message
        if text_content == THROTTLING_MESSAGE:
            return {"statusCode": 503,
                    "body": {"response": THROTTLING_MESSAGE},
                    "headers": {"Content-Type": "application/json"}}

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
                    "body": {"response": " Xin lỗi bạn, tôi không thể tìm kiếm thông tin liên quan đến yêu cầu của bạn."},
                    "headers": {"Content-Type": "application/json"}}

        # SECURITY CHECK: Block INSERT/UPDATE/DELETE mutations
        # Text2SQL Lambda should ONLY generate SELECT queries
        # Mutations are handled separately via _handle_mutation in text2sql_handler.py
        # sql_upper = sql_statements[0].upper().strip()
        # mutation_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE"]
        
        # for keyword in mutation_keywords:
        #     if sql_upper.startswith(keyword) or f" {keyword} " in sql_upper or f"\n{keyword} " in sql_upper:
        #         logger.warning(f"BLOCKED mutation query: {sql_statements[0][:200]}...")
        #         return {"statusCode": 400,
        #                 "body": {"response": "Tôi chỉ có thể trả lời câu hỏi về thông tin. Để đặt/sửa/hủy lịch hẹn, vui lòng nói 'đặt lịch', 'đổi lịch' hoặc 'hủy lịch'."},
        #                 "headers": {"Content-Type": "application/json"}}

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
                    
                    # CRITICAL: Convert customer_id to string if it matches
                    # customerid column is VARCHAR, not integer
                    if customer_id is not None:
                        customer_id_int = int(customer_id) if str(customer_id).isdigit() else None
                        params = [
                            str(p) if (p == customer_id or p == customer_id_int) else p
                            for p in params
                        ]
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
        # Check if results are empty (handles string "[]", empty list, None, etc.)
        is_empty = False
        if not results:
            is_empty = True
        elif isinstance(results, str):
            try:
                parsed = json.loads(results)
                if not parsed or (isinstance(parsed, list) and len(parsed) == 0):
                    is_empty = True
            except:
                if results.strip() in ['[]', 'null', 'None', '']:
                    is_empty = True
        elif isinstance(results, list) and len(results) == 0:
            is_empty = True
        
        # Create formatting prompt - different prompt for empty vs non-empty results
        if is_empty:
            prompt = f"""Bạn là một chuyên viên tư vấn đặt lịch hẹn thân thiện.
                Câu hỏi của khách hàng: {question}
                Thông tin schema: {schema}
                Kết quả truy vấn: KHÔNG TÌM THẤY DỮ LIỆU PHÙ HỢP
                """
            if context:
                prompt += f"""Lịch sử hội thoại:{context}"""
            prompt += f"""
                Hãy trả lời câu hỏi khách hàng một cách thân thiện rằng KHÔNG TÌM THẤY thông tin họ yêu cầu.
                Quan trọng:
                - Dựa vào lịch sử hội thoại chỉ để hiểu ngữ cảnh câu hỏi của khách hàng không dùng để trả lời (ví dụ: "Hiện tại chưa có lịch hẹn nào của [tên] vào [ngày]")
                - Câu trả lời tập trung vào câu hỏi của khách hàng
                - KHÔNG bịa đặt hay đoán thông tin
                - KHÔNG nói có dữ liệu khi không có
                - Có thể gợi ý khách hỏi theo cách khác hoặc thử thời gian/ngày khác
                - KHÔNG đề cập đến SQL, database, schema hay bất kỳ khía cạnh kỹ thuật nào
                Trả lời:"""
        else:
            # Build context hint for understanding user message
            context_hint = ""
            if context:
                context_hint = f"""
## NGỮ CẢNH (chỉ để hiểu câu hỏi, KHÔNG dùng để trả lời):
{context}
---
"""
            prompt = f"""Bạn là một chuyên viên tư vấn đặt lịch hẹn thân thiện.
{context_hint}
## CÂU HỎI HIỆN TẠI CỦA KHÁCH HÀNG:
"{question}"

## KẾT QUẢ TRUY VẤN (DỮ LIỆU DUY NHẤT ĐỂ TRẢ LỜI):
{results}

## QUY TẮC:
1. **CHỈ trả lời dựa trên KẾT QUẢ TRUY VẤN** - đây là dữ liệu chính xác 
2. Ngữ cảnh chỉ giúp hiểu user muốn gì, KHÔNG dùng thông tin từ ngữ cảnh để trả lời
3. Trả lời bằng tiếng Việt tự nhiên, thân thiện, đúng trọng tâm câu hỏi
4. KHÔNG đề cập đến SQL, database, schema hay bất kỳ khía cạnh kỹ thuật nào
5. Liệt kê đầy đủ thông tin từ kết quả nếu có nhiều rows
6. **QUAN TRỌNG: Câu trả lời PHẢI NGẮN GỌN, TỐI ĐA 1500 ký tự**

Trả lời:"""

        response = self._invoke_bedrock(prompt)
        return response
    
    def generate_natural_error_response(
        self,
        user_intent: str,
        error_context: str,
        suggestions: List[str] = None
    ) -> str:
        """
        Generate natural language error response using Bedrock when SQL query fails.
        
        Args:
            user_intent: What user was trying to do (e.g., "tìm lịch trống", "xem lịch hẹn")
            error_context: Context about the error (e.g., "Không tìm thấy tư vấn viên 'Nguyễn Văn A'")
            suggestions: List of suggested actions for user
            
        Returns:
            Natural language error message
        """
        suggestions_text = ""
        if suggestions:
            suggestions_text = "\n\nGợi ý cho user:\n" + "\n".join([f"- {s}" for s in suggestions])
        
        prompt = f"""Bạn là trợ lý đặt lịch hẹn thân thiện MeetAssist.

## TÌNH HUỐNG:
User đang cố: {user_intent}
Nhưng gặp lỗi: {error_context}
{suggestions_text}

## YÊU CẦU:
1. Bạn đóng vai trò như một tư vấn viên hỗ trợ đặt lịch chuyên nghiệp hãy tạo câu trả lời TỰ NHIÊN, THÂN THIỆN bằng tiếng Việt
2. Giải thích lỗi một cách DỄ HIỂU (không dùng thuật ngữ kỹ thuật)
3. An ủi user và đưa ra gợi ý hữu ích
4. Giữ câu trả lời NGẮN GỌN (tối đa 200 ký tự)
5. Dùng emoji phù hợp để thân thiện hơn

Trả lời:"""
        
        try:
            response = self._invoke_bedrock(prompt)
            return response
        except Exception as e:
            logger.error(f"Error generating natural error response: {e}")
            # Fallback nếu Bedrock cũng fail
            return f"😔 Xin lỗi, {user_intent} không thành công. {suggestions[0] if suggestions else 'Vui lòng thử lại.'}"
            
        