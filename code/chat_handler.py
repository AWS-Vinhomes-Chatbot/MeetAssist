from services.authencator_service import Authenticator    
from services.messenger_service import MessengerService
from services.session_service import SessionService
from services.bedrock_service import BedrockService
import logging
import json
import boto3
import os
import re
from typing import Optional

# Initialize services
auth = Authenticator()
mess = MessengerService()
session_service = SessionService()

# Chat uses Claude 3 Haiku - stable and fast model available in Tokyo region
bedrock_service = BedrockService(
    model_id="anthropic.claude-3-haiku-20240307-v1:0",
    max_tokens=1500,
    temperature=0.7
)

# Lambda client for invoking text2sql
lambda_client = boto3.client("lambda")
TEXT2SQL_LAMBDA_NAME = os.environ.get("TEXT2SQL_LAMBDA_NAME", "text2sql-handler")
TEXT2SQL_MUTATION_LAMBDA_NAME = os.environ.get("TEXT2SQL_MUTATION_LAMBDA_NAME", TEXT2SQL_LAMBDA_NAME)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Main Lambda handler for chat messages.
    
    Triggered by:
    1. SQS FIFO Queue (from webhook_receiver) - main flow
    2. API Gateway GET (for OAuth callback only)
    
    Flow:
    1. Handle SQS events (from webhook_receiver)
    2. Handle GET callback (for OAuth)
    """
    logger.info(f"Received event: {json.dumps(event)[:1000]}...")
    
    try:
        # Check if this is an SQS event (main flow)
        if 'Records' in event:
            return handle_sqs_event(event, context)
        
        # API Gateway: Only handle GET for OAuth callback
        http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")
        path = event.get("path", "/")
        
        if http_method == "GET" and "/callback" in path:
            return auth.handle_callback(event)
        
        # All other requests should not reach here (handled by webhook_receiver)
        logger.warning(f"Unexpected event type: method={http_method}, path={path}")
        return {"statusCode": 400, "body": "Invalid request - use webhook endpoint"}
            
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}", exc_info=True)
        return {"statusCode": 500, "body": "Internal Server Error"}


def handle_sqs_event(event, context):
    """
    Handle SQS FIFO event - process messages from queue.
    
    SQS FIFO ensures:
    1. Deduplication (same message_id within 5 min window won't be processed twice)
    2. Ordering (messages from same user processed in order via MessageGroupId)
    
    Args:
        event: SQS event with Records array
        context: Lambda context
        
    Returns:
        dict with batchItemFailures for partial batch failure handling
    """
    batch_item_failures = []
    
    for record in event.get('Records', []):
        message_id = record.get('messageId')
        
        try:
            # Parse SQS message body
            body = json.loads(record.get('body', '{}'))
            messaging_event = body.get('messaging_event', {})
            original_event = body.get('original_event', {})
            
            if not messaging_event:
                logger.warning(f"Empty messaging_event in SQS message: {message_id}")
                continue
            
            # Extract psid and message
            psid = messaging_event.get('sender', {}).get('id')
            
            if not psid:
                logger.warning(f"No PSID in messaging_event: {message_id}")
                continue
            
            # Extract text or payload
            user_question = ""
            if messaging_event.get('message'):
                message = messaging_event['message']
                if message.get('quick_reply'):
                    user_question = message['quick_reply'].get('payload', '') or message.get('text', '')
                else:
                    user_question = message.get('text', '')
            elif messaging_event.get('postback'):
                user_question = messaging_event['postback'].get('payload', '')
            
            if not user_question:
                logger.warning(f"No text/payload in message for {psid}")
                continue
            
            logger.info(f"Processing SQS message for {psid}: '{user_question[:50]}...'")
            
            # Process the message
            process_chat_message(psid, user_question, original_event)
            
            logger.info(f"Successfully processed SQS message: {message_id}")
            
        except Exception as e:
            logger.error(f"Error processing SQS message {message_id}: {e}", exc_info=True)
            # Add to failures for retry
            batch_item_failures.append({
                'itemIdentifier': message_id
            })
    
    # Return partial batch failure response
    return {
        'batchItemFailures': batch_item_failures
    }


def process_chat_message(psid: str, user_question: str, original_event: dict):
    """
    Process a single chat message for an authenticated user.
    
    This is the main processing logic extracted from lambda_handler
    to be reusable for both API Gateway and SQS triggers.
    
    Args:
        psid: User's Page-Scoped ID
        user_question: User's message text
        original_event: Original webhook event (for history tracking)
    """
    # Check if this is a new user (no session) - send welcome message
    session = session_service.get_session(psid)
    is_new_user = session is None
    
    if is_new_user or user_question == "GET_STARTED":
        welcome_message = (
            "Xin chào! 👋\n\n"
            "Mình là MeetAssist, mình sẽ hỗ trợ đặt lịch hẹn với tư vấn viên hướng nghiệp "
            "và cung cấp các thông tin liên quan cho bạn.\n\n"
            "Bạn có thể hỏi mình về:\n"
            "• Lịch trống của tư vấn viên\n"
            "• Đặt lịch hẹn tư vấn\n"
            "• Thông tin về các chương trình hướng nghiệp\n\n"
            "Để bắt đầu, vui lòng nhập email của bạn để xác thực. 📧"
        )
        mess.send_text_message(psid, welcome_message)
        
        # If GET_STARTED postback, just send welcome and return
        if user_question == "GET_STARTED":
            return
        
        # For new user with real message, continue to auth flow
        # Refresh session check
        session = session_service.get_session(psid)
    
    # Check if user is authenticated
    is_authenticated = session.get("is_authenticated", False) if session else False
    
    if not is_authenticated:
        # User not authenticated - delegate to auth handler
        logger.info(f"User {psid} not authenticated, delegating to auth handler")
        auth.handle_user_authorization_event(psid, user_question)
        return
    
    # Check and reset expired session/booking flow
    was_reset, reset_message = session_service.check_and_reset_expired_session(psid)
    if was_reset:
        session_service.update_last_activity(psid)
        mess.send_text_message(psid, reset_message)
        return
    
    # Update last activity timestamp
    session_service.update_last_activity(psid)
    
    # Check if user is in booking flow
    booking_state = session_service.get_booking_state(psid)
    logger.info(f"Current booking state for {psid}: {booking_state}")
    
    # Handle confirming_restart state
    if booking_state == "confirming_restart":
        response_text = _handle_restart_confirmation(psid, user_question)
        mess.send_text_message(psid, response_text)
        session_service.add_message_to_history(
            event=original_event,
            assistant_msg=response_text,
            metadata={"flow": "booking", "booking_state": "confirming_restart"}
        )
        return
    
    # Handle active booking flow states
    if booking_state in ["selecting_slot", "selecting_appointment", "selecting_new_slot", "collecting", "confirming"]:
        response_text = _handle_booking_flow(psid, user_question, booking_state)
        mess.send_text_message(psid, response_text)
        session_service.add_message_to_history(
            event=original_event,
            assistant_msg=response_text,
            metadata={"flow": "booking", "booking_state": booking_state}
        )
        return
    
    # Check if user wants to start booking
    booking_intent = bedrock_service.detect_booking_intent(user_question)
    logger.info(f"Booking intent detection result for {psid}: {booking_intent}")
    
    if booking_intent.get("wants_booking") and booking_intent.get("confidence", 0) >= 0.6:
        logger.info(f"User {psid} wants to book: {booking_intent}")
        
        # Check for pending booking
        has_pending, pending_info = session_service.has_pending_booking(psid)
        if has_pending:
            pending_action = pending_info.get("booking_action", "create")
            action_text = {"create": "đặt lịch", "update": "cập nhật", "cancel": "hủy lịch"}.get(pending_action, "đặt lịch")
            reminder = f"⚠️ Bạn đang có một thao tác {action_text} chưa hoàn thành.\n\n"
            reminder += "Bạn muốn:\n"
            reminder += "1️⃣ **Tiếp tục** - Tiếp tục thao tác đang dở\n"
            reminder += "2️⃣ **Bắt đầu mới** - Hủy và bắt đầu lại từ đầu\n"
            
            session_service.update_appointment_info(psid, {"pending_new_intent": booking_intent})
            session_service.set_booking_state(psid, "confirming_restart")
            
            mess.send_text_message(psid, reminder)
            return
        
        response_text = _start_booking_flow(psid, user_question, booking_intent)
        mess.send_text_message(psid, response_text)
        session_service.add_message_to_history(
            event=original_event,
            assistant_msg=response_text,
            metadata={"flow": "booking", "intent": booking_intent}
        )
        return
    
    # Check cache for similar question
    cache_hit = session_service.search_cache(psid, user_question)
    
    if cache_hit:
        # Cache HIT
        logger.info(f"Cache HIT for {psid}")
        response_text = _handle_cache_hit(psid, user_question, cache_hit)
        mess.send_text_message(psid, response_text)
        session_service.add_message_to_history(
            event=original_event,
            assistant_msg=response_text,
            metadata=None
        )
    else:
        # Cache MISS - invoke text2sql
        logger.info(f"Cache MISS for {psid}, invoking text2sql")
        response_text, metadata = _handle_text2sql(psid, user_question)
        mess.send_text_message(psid, response_text)
        session_service.add_message_to_history(
            event=original_event,
            assistant_msg=response_text,
            metadata=metadata
        )


def _handle_cache_hit(psid: str, user_question: str, cache_hit: dict) -> str:
    """
    Handle cache hit - use cached metadata to generate response via Bedrock.
    
    Args:
        psid: User's PSID
        user_question: Current user question
        cache_hit: Cached turn data with metadata
        
    Returns:
        Response text from Bedrock
    """
    try:
        # Get cached metadata
        cached_metadata = cache_hit.get("metadata", {})
        sql_result = cached_metadata.get("sql_result", "")
        schema_context = cached_metadata.get("schema_context_text", "")
        
        # Get conversation context
        context = session_service.get_context_for_llm(psid)
        
        # Generate response using Bedrock
        response = bedrock_service.get_answer_from_sql_results(
            question=user_question,
            results=sql_result,
            schema=schema_context,
            context=context
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error handling cache hit: {e}")
        return "Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn."


def _handle_text2sql(psid: str, user_question: str) -> tuple:
    """
    Handle cache miss - invoke text2sql Lambda and generate response.
    
    Args:
        psid: User's PSID
        user_question: User's question
        
    Returns:
        Tuple of (response_text, metadata)
    """
    try:
        # Get conversation context for text2sql
        context = session_service.get_context_for_llm(psid)
        
        # Prepare payload for text2sql Lambda
        payload = {
            "psid": psid,
            "question": user_question,
            "context": context
        }
        
        # Invoke text2sql Lambda
        response = lambda_client.invoke(
            FunctionName=TEXT2SQL_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload)
        )
        
        # Parse response
        result = json.loads(response["Payload"].read().decode())
        logger.debug(f"Text2SQL response: {result}")
        
        if result.get("statusCode") != 200:
            logger.error(f"Text2SQL error: {result}")
            # Extract error response from Text2SQL result
            error_body = result.get("body", "{}")
            if isinstance(error_body, str):
                error_body = json.loads(error_body)
            error_response = error_body.get("response", "Xin lỗi, không thể truy vấn thông tin lúc này.")
            return error_response, {"error": True, "detail": error_body.get("error", "")}
        
        # Parse body
        body = result.get("body", "{}")
        if isinstance(body, str):
            body = json.loads(body)
        
        # Extract fields from text2sql response
        sql_result = body.get("sql_result", [])
        schema_context = body.get("schema_context_text", "")
        
        # Convert sql_result to string for Bedrock (bedrock_service handles empty results contextually)
        sql_result_str = json.dumps(sql_result, ensure_ascii=False, default=str)
        
        # Generate natural language response using Bedrock
        response_text = bedrock_service.get_answer_from_sql_results(
            question=user_question,
            results=sql_result_str,
            schema=schema_context,
            context=context
        )
        
        # Build metadata for caching - DON'T cache empty results
        # so next query will hit DB again (data might have changed)
        is_empty_result = not sql_result or (isinstance(sql_result, list) and len(sql_result) == 0)
        if is_empty_result:
            # Return None metadata to skip caching
            metadata = None
        else:
            metadata = {
                "source": "text2sql",
                "intent": "schedule_type",
                "sql_result": sql_result_str,
                "schema_context_text": schema_context
            }
        
        return response_text, metadata
        
    except Exception as e:
        logger.error(f"Error in _handle_text2sql: {e}", exc_info=True)
        return "Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn.", {"error": str(e)}


def _is_user_asking_question(message: str) -> bool:
    """
    Detect if user is asking a question (needs DB query) vs providing information.
    
    Questions:
    - "Có tư vấn viên nào chuyên về tài chính không?"
    - "Lịch trống ngày mai như thế nào?"
    - "Có chương trình gì vào cuối tuần?"
    
    Providing info:
    - "Tôi chọn Dr. A"
    - "Ngày 15/12 lúc 10h"
    - "Tên tôi là Nguyễn Văn A, SĐT 0901234567"
    
    Args:
        message: User's message
        
    Returns:
        True if user is asking a question
    """
    message_lower = message.lower().strip()
    
    # Question indicators
    question_patterns = [
        # Question words
        "có ", "có không", "có ai", "có gì", "có bao nhiêu",
        "ai ", "ai là", "ai có",
        "gì ", "là gì", "như thế nào", "thế nào",
        "khi nào", "lúc nào", "bao giờ",
        "ở đâu", "chỗ nào",
        "bao nhiêu", "mấy",
        "tại sao", "vì sao",
        "làm sao", "cách nào",
        # Query patterns
        "danh sách", "liệt kê", "cho xem", "show",
        "xem ", "kiểm tra", "check",
        "tìm ", "tìm kiếm", "search",
        "còn trống", "lịch trống", "slot trống",
        "chuyên về", "chuyên ngành", "lĩnh vực",
        "giờ nào", "ngày nào",
        # Question mark
        "?"
    ]
    
    # Providing info indicators (higher priority)
    provide_patterns = [
        "tôi chọn", "chọn ", "lấy ",
        "tên tôi", "tôi là", "tên là",
        "số điện thoại", "sđt", "phone",
        "đặt lịch với", "hẹn với",
        "ngày ", "lúc ", "vào ",  # followed by specific date/time
        "ok", "được", "đồng ý"
    ]
    
    # Check if providing info first (higher priority)
    for pattern in provide_patterns:
        if pattern in message_lower:
            # But also check if it's actually a question about these
            if "?" in message or any(q in message_lower for q in ["có không", "không có", "được không"]):
                continue  # It's actually a question
            return False
    
    # Check if asking question
    for pattern in question_patterns:
        if pattern in message_lower:
            return True
    
    # Default: if message is short and doesn't look like info, might be a question
    # If message contains names, numbers, dates - likely providing info
    has_phone = bool(re.search(r'\d{10,11}', message))
    has_date = bool(re.search(r'\d{1,2}[/\-]\d{1,2}', message))
    has_time = bool(re.search(r'\d{1,2}[hH:]\d{0,2}', message))
    
    if has_phone or has_date or has_time:
        return False
    
    return False  # Default to not a question


def _handle_booking_query(psid: str, user_question: str, current_info: dict) -> str:
    """
    Handle user's query during booking flow - query database and return helpful info.
    
    Examples:
    - "Có tư vấn viên nào chuyên về tài chính?" → Query consultants
    - "Lịch trống ngày mai?" → Query available slots
    - "Có chương trình gì tuần này?" → Query programs
    
    Args:
        psid: User's PSID
        user_question: User's question
        current_info: Current booking info (for context)
        
    Returns:
        Response with query results + prompt to continue booking
    """
    try:
        # Get conversation context
        context = session_service.get_context_for_llm(psid)
        
        # Add booking context to help with the query
        booking_context = f"""
[Đang trong quá trình đặt lịch]
- Thông tin đã có: {json.dumps({k: v for k, v in current_info.items() if v and k not in ['booking_state', 'booking_action']}, ensure_ascii=False)}
"""
        full_context = booking_context + "\n" + context if context else booking_context
        
        # Prepare payload for text2sql Lambda
        payload = {
            "psid": psid,
            "question": user_question,
            "context": full_context
        }
        
        # Invoke text2sql Lambda
        response = lambda_client.invoke(
            FunctionName=TEXT2SQL_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload)
        )
        
        # Parse response
        result = json.loads(response["Payload"].read().decode())
        
        if result.get("statusCode") == 200:
            body = result.get("body", "{}")
            if isinstance(body, str):
                body = json.loads(body)
            
            sql_result = body.get("sql_result", [])
            schema_context = body.get("schema_context_text", "")
            
            # Generate natural language response (handles empty results contextually)
            sql_result_str = json.dumps(sql_result, ensure_ascii=False, default=str)
            query_response = bedrock_service.get_answer_from_sql_results(
                question=user_question,
                results=sql_result_str,
                schema=schema_context,
                context=context
            )
            
            # Add prompt to continue booking
            missing_fields = session_service.get_missing_appointment_fields(psid)
            if missing_fields:
                # Suggest next step based on what they asked
                if "consultant" in user_question.lower() or "tư vấn viên" in user_question.lower():
                    query_response += "\n\n👉 Bạn muốn đặt lịch với tư vấn viên nào?"
                elif "lịch trống" in user_question.lower() or "slot" in user_question.lower():
                    query_response += "\n\n👉 Bạn muốn chọn khung giờ nào?"
                elif "chương trình" in user_question.lower() or "sự kiện" in user_question.lower():
                    query_response += "\n\n👉 Bạn muốn đăng ký chương trình nào?"
                else:
                    query_response += "\n\n👉 Bạn có thể tiếp tục cung cấp thông tin đặt lịch."
            
            return query_response
        else:
            # Query failed - still in booking flow
            return "Xin lỗi, mình không tìm được thông tin. Bạn có thể hỏi cách khác hoặc tiếp tục cung cấp thông tin đặt lịch."
            
    except Exception as e:
        logger.error(f"Error handling booking query: {e}", exc_info=True)
        return "Đã xảy ra lỗi khi tìm kiếm. Bạn có thể tiếp tục cung cấp thông tin đặt lịch."


def _start_booking_flow(psid: str, user_question: str, booking_intent: dict) -> str:
    """
    Start a new booking flow for the user (create, update, or cancel).
    
    Args:
        psid: User's PSID
        user_question: User's initial booking request
        booking_intent: Detected booking intent with type and action
        
    Returns:
        Response text to send to user
    """
    try:
        # Reset any previous booking info
        session_service.reset_appointment_info(psid)
        
        # Determine booking action (create, update, cancel)
        booking_action = booking_intent.get("booking_action", "create")
        
        # Set the booking action
        session_service.update_appointment_info(psid, {"booking_action": booking_action})
        
        # For CREATE: Show available slots first
        if booking_action == "create":
            session_service.set_booking_state(psid, "selecting_slot")
            return _show_available_slots(psid)
        
        # For UPDATE/CANCEL: Show user's appointments first
        if booking_action in ["update", "cancel"]:
            session_service.set_booking_state(psid, "selecting_appointment")
            return _show_user_appointments(psid, booking_action)
        
        return "Xin lỗi, không hiểu yêu cầu. Bạn muốn đặt lịch, đổi lịch hay hủy lịch?"
        
    except Exception as e:
        logger.error(f"Error starting booking flow: {e}", exc_info=True)
        return "Xin lỗi, đã xảy ra lỗi khi bắt đầu. Vui lòng thử lại."


def _show_available_slots(psid: str) -> str:
    """
    Query and show available appointment slots for CREATE flow.
    Auto-display consultants with available times in next 7 days.
    Cache slots để map thứ tự → consultant_id + date + time.
    
    Returns:
        Message listing available slots with index numbers
    """
    try:
        # Query available slots from database
        payload = {
            "psid": psid,
            "question": """Liệt kê các khung giờ tư vấn còn trống trong 7 ngày tới.
            Yêu cầu: Lấy consultantid, tên tư vấn viên, chuyên môn, ngày, giờ bắt đầu, giờ kết thúc.
            Chỉ lấy slot còn trống (isavailable = true).
            Sắp xếp theo ngày, giờ tăng dần. Giới hạn 10 kết quả.""",
            "context": ""
        }
        
        response = lambda_client.invoke(
            FunctionName=TEXT2SQL_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response["Payload"].read().decode())
        
        if result.get("statusCode") == 200:
            body = result.get("body", "{}")
            if isinstance(body, str):
                body = json.loads(body)
            
            slots = body.get("sql_result", [])
            
            if not slots:
                session_service.reset_appointment_info(psid)
                session_service.set_booking_state(psid, "idle")
                return "😔 Hiện tại không có khung giờ trống nào trong 7 ngày tới. Vui lòng thử lại sau!"
            
            # Cache slots
            session_service.cache_available_slots(psid, slots)
            
            # Format slots list
            message = "📅 **Các khung giờ còn trống:**\n\n"
            
            for i, slot in enumerate(slots[:10], 1):
                consultant = slot.get("fullname", slot.get("consultant_name", "N/A"))
                spec = slot.get("specialties", slot.get("specialization", ""))
                date = slot.get("date", slot.get("available_date", ""))
                time = slot.get("starttime", slot.get("available_time", slot.get("time", "")))
                
                spec_text = f" ({spec})" if spec else ""
                message += f"{i}️⃣ **{consultant}**{spec_text}\n"
                message += f"   📆 {date} - 🕐 {time}\n\n"
            
            message += "👉 **Vui lòng chọn số thứ tự** (1, 2, 3...)"
            
            return message
        else:
            logger.error(f"Error querying available slots: {result}")
            return "Đã xảy ra lỗi khi tìm khung giờ trống. Vui lòng thử lại."
            
    except Exception as e:
        logger.error(f"Error showing available slots: {e}", exc_info=True)
        return "Đã xảy ra lỗi. Vui lòng thử lại sau."


# NOTE: _validate_slot_still_available() đã được loại bỏ
# Lý do: Database đã có constraint UQ_Consultant_Schedule UNIQUE (ConsultantID, Date, StartTime)
# và CTE trong mutation SQL check isavailable = true trước khi book
# Nếu slot đã được đặt, DB sẽ raise exception và trả về thông báo lỗi phù hợp


def _show_user_appointments(psid: str, action: str) -> str:
    """
    Query and show user's appointments for update/cancel selection.
    KHÔNG hiển thị appointment ID, chỉ hiển thị số thứ tự.
    Cache appointments để map thứ tự → ID.
    
    Args:
        psid: User's PSID
        action: "update" or "cancel"
        
    Returns:
        Message listing user's appointments (without IDs)
    """
    try:
        # Invoke text2sql to query user's appointments
        # QUAN TRỌNG: Filter theo customerid = psid để đảm bảo user chỉ thấy lịch của chính mình
        # Lấy scheduleid và thông tin customer (name, phone) để dùng cho UPDATE/CANCEL flow
        payload = {
            "psid": psid,
            "question": f"""Lấy lịch hẹn đang pending hoặc confirmed của khách hàng có customerid là '{psid}'.
            Yêu cầu: appointmentid, scheduleid, customerid, tên khách hàng, số điện thoại, consultantid, tên tư vấn viên, ngày hẹn, giờ bắt đầu, status.
            Giới hạn 5 kết quả.""",
            "context": ""
        }
        
        response = lambda_client.invoke(
            FunctionName=TEXT2SQL_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response["Payload"].read().decode())
        
        if result.get("statusCode") == 200:
            body = result.get("body", "{}")
            if isinstance(body, str):
                body = json.loads(body)
            
            appointments = body.get("sql_result", [])
            
            if not appointments:
                session_service.reset_appointment_info(psid)
                session_service.set_booking_state(psid, "idle")
                return "Bạn chưa có lịch hẹn nào đang chờ. Bạn có muốn đặt lịch mới không?"
            
            # Cache appointments để map thứ tự → ID
            session_service.cache_user_appointments(psid, appointments)
            
            # Format appointments list - KHÔNG show appointment ID
            action_text = "hủy" if action == "cancel" else "đổi"
            message = f"📋 Danh sách lịch hẹn của bạn:\n\n"
            
            for i, apt in enumerate(appointments[:5], 1):  # Show max 5
                date = apt.get("appointmentdate", apt.get("date", "N/A"))
                time = apt.get("starttime", apt.get("time", ""))
                consultant = apt.get("consultant_name", apt.get("fullname", ""))
                status = apt.get("status", "")
                
                # Chỉ hiển thị số thứ tự, không hiển thị appointment ID
                message += f"{i}. 📅 {date}"
                if time:
                    message += f" lúc {time}"
                if consultant:
                    message += f" với {consultant}"
                if status:
                    status_emoji = "⏳" if status == "pending" else "✅" if status == "confirmed" else "📌"
                    message += f" - {status_emoji} {status}"
                message += "\n"
            
            message += f"\n👉 Vui lòng nhập **số thứ tự** (1-{min(5, len(appointments))}) của lịch hẹn bạn muốn {action_text}."
            
            return message
        else:
            return "Không thể lấy danh sách lịch hẹn. Vui lòng thử lại sau."
            
    except Exception as e:
        logger.error(f"Error showing user appointments: {e}", exc_info=True)
        return "Đã xảy ra lỗi khi lấy danh sách lịch hẹn."


def _handle_restart_confirmation(psid: str, user_message: str) -> str:
    """
    Handle user's response when asked to continue or restart booking.
    
    Args:
        psid: User's PSID
        user_message: User's response ("tiếp tục", "1", "bắt đầu mới", "2", etc.)
        
    Returns:
        Response message
    """
    try:
        message_lower = user_message.lower().strip()
        
        # Check if user wants to continue
        continue_keywords = ["tiếp tục", "tiếp", "1", "số 1", "cái 1", "continue"]
        if any(kw in message_lower for kw in continue_keywords) or message_lower == "1":
            # Continue with existing booking
            current_info = session_service.get_appointment_info(psid)
            booking_action = current_info.get("booking_action", "create")
            
            # Go back to collecting state
            session_service.set_booking_state(psid, "collecting")
            
            # Get missing fields and prompt user
            missing_fields = session_service.get_missing_appointment_fields(psid)
            if missing_fields:
                return bedrock_service.generate_booking_response(
                    current_info=current_info,
                    missing_fields=missing_fields
                )
            else:
                # All info collected, go to confirming
                session_service.set_booking_state(psid, "confirming")
                return _generate_confirmation_message(current_info)
        
        # Check if user wants to start fresh
        restart_keywords = ["bắt đầu mới", "bắt đầu lại", "mới", "2", "số 2", "cái 2", "restart", "new"]
        if any(kw in message_lower for kw in restart_keywords) or message_lower == "2":
            # Get saved new intent
            current_info = session_service.get_appointment_info(psid)
            new_intent = current_info.get("pending_new_intent", {})
            
            # Reset and start fresh
            session_service.reset_appointment_info(psid)
            
            if new_intent:
                return _start_booking_flow(psid, "", new_intent)
            else:
                session_service.set_booking_state(psid, "idle")
                return "Đã hủy thao tác trước đó. Bạn có thể bắt đầu lại bằng cách nói 'đặt lịch', 'hủy lịch', hoặc 'đổi lịch'."
        
        # User said something else - ask again
        return "Vui lòng chọn:\n1️⃣ Nhập **1** hoặc **tiếp tục** để tiếp tục thao tác đang dở\n2️⃣ Nhập **2** hoặc **bắt đầu mới** để hủy và làm lại từ đầu"
        
    except Exception as e:
        logger.error(f"Error handling restart confirmation: {e}")
        session_service.set_booking_state(psid, "idle")
        return "Đã xảy ra lỗi. Vui lòng thử lại."


def _parse_appointment_selection(user_message: str) -> Optional[int]:
    """
    Parse user's appointment selection (số thứ tự 1-10).
    
    Examples:
    - "1" → 1
    - "số 2" → 2
    - "lịch thứ 3" → 3
    - "chọn cái đầu" → 1
    
    Args:
        user_message: User's message
        
    Returns:
        Selection index (1-based) or None if not a selection
    """
    message = user_message.lower().strip()
    
    # Direct number
    if message.isdigit() and 1 <= int(message) <= 10:
        return int(message)
    
    # "số X" or "lịch X" or "cái X"
    match = re.search(r'(?:số|lịch|cái)\s*(\d+)', message)
    if match:
        num = int(match.group(1))
        if 1 <= num <= 10:
            return num
    
    # "thứ X"
    match = re.search(r'thứ\s*(\d+)', message)
    if match:
        num = int(match.group(1))
        if 1 <= num <= 10:
            return num
    
    # Common phrases
    ordinals = {
        "đầu tiên": 1, "cái đầu": 1, "lịch đầu": 1, "số một": 1,
        "thứ hai": 2, "cái thứ 2": 2, "số hai": 2,
        "thứ ba": 3, "cái thứ 3": 3, "số ba": 3
    }
    for phrase, num in ordinals.items():
        if phrase in message:
            return num
    
    # Just a number at the end or start
    match = re.search(r'\b(\d)\b', message)
    if match:
        num = int(match.group(1))
        if 1 <= num <= 10:
            return num
    
    return None


def _handle_booking_flow(psid: str, user_question: str, booking_state: str) -> str:
    """
    Handle ongoing booking flow - select slot, collect info, or confirm booking.
    
    States:
    - selecting_slot: User is choosing from available slots (CREATE)
    - collecting: Collecting customer info OR selecting appointment (UPDATE/CANCEL)
    - confirming: Waiting for user confirmation
    
    Args:
        psid: User's PSID
        user_question: User's message
        booking_state: Current booking state
        
    Returns:
        Response text to send to user
    """
    try:
        # Check if user wants to abort the current flow
        abort_keywords = ["thôi", "bỏ qua", "dừng", "không làm nữa", "quay lại", "hủy bỏ", "hủy", "cancel", "stop", "thoát", "exit"]
        msg_lower = user_question.lower().strip()
        
        # Check exact match or keyword in message
        if msg_lower in abort_keywords or any(kw in msg_lower for kw in abort_keywords):
            session_service.reset_appointment_info(psid)
            session_service.set_booking_state(psid, "idle")
            logger.info(f"User {psid} aborted booking flow with message: {user_question}")
            return "Đã hủy thao tác. Bạn có thể hỏi tôi bất cứ điều gì khác!"
        
        # Get current appointment info
        current_info = session_service.get_appointment_info(psid)
        booking_action = current_info.get("booking_action", "create")
        
        # =====================================================
        # STATE: SELECTING_SLOT (CREATE flow - chọn khung giờ)
        # =====================================================
        if booking_state == "selecting_slot":
            # Check if cache is stale (> 5 minutes) - refresh if needed
            if session_service.is_slot_cache_stale(psid, max_age_seconds=300):
                logger.info(f"Slot cache stale for {psid}, refreshing...")
                return _show_available_slots(psid)
            
            # Check if user selected a slot number
            selection = _parse_appointment_selection(user_question)
            
            if selection is not None:# khi ng dùng đã chọn số thứ tự slot
                cached_slot = session_service.get_cached_slot_by_index(psid, selection)
                
                if cached_slot:
                    # User selected a valid slot - store info from cache
                    session_service.update_appointment_info(psid, {
                        "consultant_id": cached_slot.get("consultant_id"),
                        "consultant_name": cached_slot.get("consultant_name"),
                        "appointment_date": cached_slot.get("date"),
                        "appointment_time": cached_slot.get("time"),
                        "appointment_end_time": cached_slot.get("end_time"),
                        "selected_slot_index": selection
                    })
                    
                    # Move to collecting customer info
                    session_service.set_booking_state(psid, "collecting")
                    
                    consultant = cached_slot.get("consultant_name", "")
                    date = cached_slot.get("date", "")
                    time = cached_slot.get("time", "")
                    
                    return f"✅ Bạn đã chọn:\n📆 **{date}** lúc 🕐 **{time}**\n👨‍💼 Tư vấn viên: **{consultant}**\n\n👉 Vui lòng cho biết **họ tên**, **số điện thoại** và **email** của bạn."
                else:
                    return f"❌ Không tìm thấy slot số {selection}. Vui lòng chọn lại từ danh sách (1-10)."
            
            # User didn't select a number - maybe asking a question
            if _is_user_asking_question(user_question):
                query_response = _handle_booking_query(psid, user_question, current_info)
                query_response += "\n\n👉 Bạn vẫn đang trong quá trình đặt lịch. Hãy chọn số thứ tự slot ở trên."
                return query_response
            
            # User said something unrelated
            return "Vui lòng chọn số thứ tự slot muốn đặt (1, 2, 3...) hoặc gõ 'thôi' để hủy."
        
        # =====================================================
        # STATE: SELECTING_APPOINTMENT (UPDATE/CANCEL - chọn lịch hẹn)
        # =====================================================
        if booking_state == "selecting_appointment":
            selection = _parse_appointment_selection(user_question)
            if selection is not None:
                cached_apt = session_service.get_cached_appointment_by_index(psid, selection)
                if cached_apt:
                    # Lưu appointment_id và customer info từ cache
                    # QUAN TRỌNG: Copy customer_name và phone_number để dùng cho INSERT mới khi UPDATE
                    session_service.update_appointment_info(psid, {
                        "appointment_id": cached_apt.get("appointment_id"),
                        "customer_id": cached_apt.get("customer_id"),
                        "customer_name": cached_apt.get("customer_name"),  # Tên từ lịch cũ
                        "phone_number": cached_apt.get("phone_number"),    # SĐT từ lịch cũ
                        "old_consultant_id": cached_apt.get("consultant_id"),
                        "old_date": cached_apt.get("appointment_date"),
                        "old_time": cached_apt.get("start_time"),
                        "old_consultant_name": cached_apt.get("consultant_name")
                    })
                    
                    if booking_action == "cancel":
                        # CANCEL: Go directly to confirming
                        session_service.set_booking_state(psid, "confirming")
                        updated_info = session_service.get_appointment_info(psid)
                        return _generate_confirmation_message(updated_info)
                    else:
                        # UPDATE: Show available slots for new selection
                        session_service.set_booking_state(psid, "selecting_new_slot")
                        old_info = f"📝 Bạn đã chọn lịch hẹn:\n"
                        old_info += f"   📅 Ngày: {cached_apt.get('appointment_date')}\n"
                        old_info += f"   🕐 Giờ: {cached_apt.get('start_time')}\n"
                        old_info += f"   👨‍💼 Tư vấn viên: {cached_apt.get('consultant_name')}\n\n"
                        old_info += "🔄 **Vui lòng chọn khung giờ MỚI:**\n\n"
                        
                        # Show available slots
                        slots_msg = _show_available_slots(psid)
                        return old_info + slots_msg
                else:
                    return f"❌ Không tìm thấy lịch hẹn số {selection}. Vui lòng chọn lại từ danh sách."
            
            # User didn't select a number
            return "Vui lòng chọn số thứ tự lịch hẹn muốn thao tác (1, 2, 3...) hoặc gõ 'thôi' để hủy."
        
        # =====================================================
        # STATE: SELECTING_NEW_SLOT (UPDATE - chọn slot mới)
        # =====================================================
        if booking_state == "selecting_new_slot":
            # Check if cache is stale
            if session_service.is_slot_cache_stale(psid, max_age_seconds=300):
                logger.info(f"Slot cache stale for {psid}, refreshing...")
                return _show_available_slots(psid)
            
            selection = _parse_appointment_selection(user_question)
            if selection is not None:
                cached_slot = session_service.get_cached_slot_by_index(psid, selection)
                if cached_slot:
                    # Lưu thông tin slot MỚI từ cache
                    session_service.update_appointment_info(psid, {
                        "consultant_id": cached_slot.get("consultant_id"),
                        "consultant_name": cached_slot.get("consultant_name"),
                        "appointment_date": cached_slot.get("date"),
                        "appointment_time": cached_slot.get("time"),
                        "appointment_end_time": cached_slot.get("end_time"),
                        "selected_slot_index": selection
                    })
                    
                    # Chuyển sang confirming - hỏi xác nhận
                    session_service.set_booking_state(psid, "confirming")
                    updated_info = session_service.get_appointment_info(psid)
                    return _generate_confirmation_message(updated_info)
                else:
                    return f"❌ Không tìm thấy slot số {selection}. Vui lòng chọn lại từ danh sách (1-10)."
            
            # User didn't select a number - maybe asking a question
            if _is_user_asking_question(user_question):
                query_response = _handle_booking_query(psid, user_question, current_info)
                query_response += "\n\n👉 Bạn vẫn đang chọn khung giờ mới. Hãy chọn số thứ tự slot ở trên."
                return query_response
            
            return "Vui lòng chọn số thứ tự slot mới (1, 2, 3...) hoặc gõ 'thôi' để hủy."
        
        # =====================================================
        # STATE: COLLECTING (thu thập thông tin - chỉ cho CREATE)
        # =====================================================
        if booking_state == "collecting":
            # For CREATE: Collecting customer name and phone
            # Check if user is asking a question
            if _is_user_asking_question(user_question):
                query_response = _handle_booking_query(psid, user_question, current_info)
                return query_response
            
            # Get conversation context for better extraction
            context = session_service.get_context_for_llm(psid)
            
            # Extract customer info from message
            extracted_info = bedrock_service.extract_appointment_info(
                message=user_question,
                current_info=current_info,
                context=context
            )
            
            # Update appointment info
            if extracted_info:
                session_service.update_appointment_info(psid, extracted_info)
                current_info = session_service.get_appointment_info(psid)
            
            # Check if all required info is collected
            if session_service.is_appointment_complete(psid):
                # Move to confirming state
                session_service.set_booking_state(psid, "confirming")
                return _generate_confirmation_message(current_info)
            else:
                # Still need more info
                missing_fields = session_service.get_missing_appointment_fields(psid)
                return bedrock_service.generate_booking_response(
                    current_info=current_info,
                    missing_fields=missing_fields
                )
        
        elif booking_state == "confirming":
            # Check if user confirms
            confirm_keywords = ["ok", "đồng ý", "xác nhận", "được", "yes", "có", "ừ", "đúng rồi"]
            if any(kw in user_question.lower() for kw in confirm_keywords):
                # Execute the booking action (create/update/cancel)
                return _execute_booking(psid, current_info)
            else:
                # User might want to change something
                context = session_service.get_context_for_llm(psid)
                extracted_info = bedrock_service.extract_appointment_info(
                    message=user_question,
                    current_info=current_info,
                    context=context
                )
                
                if extracted_info:
                    # Update and re-confirm
                    session_service.update_appointment_info(psid, extracted_info)
                    current_info = session_service.get_appointment_info(psid)
                    return _generate_confirmation_message(current_info)
                else:
                    # Ask again for confirmation
                    action_text = {
                        "create": "đặt lịch",
                        "update": "cập nhật lịch hẹn",
                        "cancel": "hủy lịch hẹn"
                    }.get(booking_action, "đặt lịch")
                    return f"Bạn có muốn xác nhận {action_text} với thông tin trên không? (Trả lời 'có' để xác nhận hoặc 'thôi' để hủy)"
        
        return "Xin lỗi, đã xảy ra lỗi. Vui lòng thử lại."
        
    except Exception as e:
        logger.error(f"Error handling booking flow: {e}", exc_info=True)
        return "Xin lỗi, đã xảy ra lỗi khi xử lý. Vui lòng thử lại."


def _generate_confirmation_message(appointment_info: dict) -> str:
    """
    Generate a confirmation message for the collected appointment info.
    
    Args:
        appointment_info: Current appointment info
        
    Returns:
        Confirmation message string
    """
    booking_action = appointment_info.get("booking_action", "create")
    appointment_id = appointment_info.get("appointment_id")
    
    # Different headers based on action
    if booking_action == "cancel":
        message = "📋 **Xác nhận HỦY lịch hẹn:**\n\n"
        message += f"🆔 Mã lịch hẹn: #{appointment_id}\n"
        if appointment_info.get("notes"):
            message += f"📌 Lý do hủy: {appointment_info.get('notes')}\n"
        message += "\n⚠️ Trả lời **'có'** để xác nhận HỦY hoặc **'thôi'** để giữ lại lịch hẹn."
        return message
    
    if booking_action == "update":
        message = "📋 **Xác nhận CẬP NHẬT lịch hẹn:**\n\n"
        
        # Hiển thị thông tin CŨ
        message += "❌ **Thông tin cũ:**\n"
        if appointment_info.get("old_date"):
            message += f"   📅 Ngày: {appointment_info.get('old_date')}\n"
        if appointment_info.get("old_time"):
            message += f"   🕐 Giờ: {appointment_info.get('old_time')}\n"
        if appointment_info.get("old_consultant_name"):
            message += f"   👨‍💼 Tư vấn viên: {appointment_info.get('old_consultant_name')}\n"
        
        # Hiển thị thông tin MỚI
        message += "\n✅ **Thông tin mới:**\n"
        if appointment_info.get("appointment_date"):
            message += f"   📅 Ngày: {appointment_info.get('appointment_date')}\n"
        if appointment_info.get("appointment_time"):
            message += f"   🕐 Giờ: {appointment_info.get('appointment_time')}\n"
        if appointment_info.get("consultant_name"):
            message += f"   👨‍💼 Tư vấn viên: {appointment_info.get('consultant_name')}\n"
        if appointment_info.get("notes"):
            message += f"   📌 Ghi chú: {appointment_info.get('notes')}\n"
        
        message += "\n✅ Trả lời **'có'** để xác nhận cập nhật hoặc **'thôi'** để hủy."
        return message
    
    # For create action
    message = "📋 **Xác nhận thông tin đặt lịch:**\n\n"
    message += f"👤 Tên: {appointment_info.get('customer_name', 'N/A')}\n"
    message += f"📞 SĐT: {appointment_info.get('phone_number', 'N/A')}\n"
    message += f"📧 Email: {appointment_info.get('email', 'N/A')}\n"
    message += f"📅 Ngày: {appointment_info.get('appointment_date', 'N/A')}\n"
    message += f"🕐 Giờ: {appointment_info.get('appointment_time', 'N/A')}\n"
    message += f"👨‍💼 Tư vấn viên: {appointment_info.get('consultant_name', 'N/A')}\n"
    
    if appointment_info.get("notes"):
        message += f"📌 Ghi chú: {appointment_info.get('notes')}\n"
    
    message += "\n✅ Trả lời **'có'** để xác nhận hoặc **'thôi'** để hủy."
    
    return message


def _lookup_or_create_customer(psid: str, customer_name: str, phone_number: str, email: str = None) -> Optional[dict]:
    """
    Lookup customer by phone number, create if not exists.
    
    Args:
        psid: User's PSID
        customer_name: Customer's name
        phone_number: Customer's phone number
        email: Customer's email (optional)
        
    Returns:
        Dict with customer_id or None if failed
    """
    try:
        # First, try to lookup by phone number
        lookup_payload = {
            "psid": psid,
            "question": f"Tìm khách hàng có số điện thoại {phone_number}, trả về customerid, fullname, phonenumber, email",
            "context": ""
        }
        
        response = lambda_client.invoke(
            FunctionName=TEXT2SQL_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(lookup_payload)
        )
        
        result = json.loads(response["Payload"].read().decode())
        
        if result.get("statusCode") == 200:
            body = result.get("body", "{}")
            if isinstance(body, str):
                body = json.loads(body)
            
            customers = body.get("sql_result", [])
            if customers and len(customers) > 0:
                # Customer found
                customer = customers[0]
                logger.info(f"Found existing customer: {customer}")
                return {
                    "customer_id": customer.get("customerid", customer.get("id")),
                    "fullname": customer.get("fullname"),
                    "phonenumber": customer.get("phonenumber"),
                    "email": customer.get("email"),
                    "is_new": False
                }
        
        # Customer not found - will be created during mutation
        logger.info(f"Customer not found, will create new: {customer_name}, {phone_number}")
        return {
            "customer_id": None,  # Will be created
            "fullname": customer_name,
            "phonenumber": phone_number,
            "email": email,
            "is_new": True
        }
        
    except Exception as e:
        logger.error(f"Error looking up customer: {e}")
        return None


def _lookup_consultant(psid: str, consultant_name: str) -> Optional[dict]:
    """
    Lookup consultant by name (fuzzy match).
    
    Args:
        psid: User's PSID
        consultant_name: Consultant's name (partial or full)
        
    Returns:
        Dict with consultant_id and details or None if not found
    """
    try:
        lookup_payload = {
            "psid": psid,
            "question": f"Tìm tư vấn viên có tên giống '{consultant_name}', trả về consultantid, fullname, specialization, email. Sử dụng ILIKE để tìm kiếm tên gần đúng.",
            "context": ""
        }
        
        response = lambda_client.invoke(
            FunctionName=TEXT2SQL_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(lookup_payload)
        )
        
        result = json.loads(response["Payload"].read().decode())
        
        if result.get("statusCode") == 200:
            body = result.get("body", "{}")
            if isinstance(body, str):
                body = json.loads(body)
            
            consultants = body.get("sql_result", [])
            if consultants and len(consultants) > 0:
                # Return first match
                consultant = consultants[0]
                logger.info(f"Found consultant: {consultant}")
                return {
                    "consultant_id": consultant.get("consultantid", consultant.get("id")),
                    "fullname": consultant.get("fullname"),
                    "specialization": consultant.get("specialization"),
                    "email": consultant.get("email")
                }
        
        logger.warning(f"Consultant not found: {consultant_name}")
        return None
        
    except Exception as e:
        logger.error(f"Error looking up consultant: {e}")
        return None


def _execute_booking(psid: str, appointment_info: dict) -> str:
    """
    Execute the booking action (create/update/cancel) by calling text2sql mutation Lambda.
    
    Flow for CREATE:
    - Call mutation Lambda với CTE - tự handle race condition trong SQL
    - CTE sẽ chỉ book slot nếu isavailable = true
    
    Flow for UPDATE/CANCEL:
    - Uses appointment_id and customer_id from cached selection
    
    Args:
        psid: User's PSID
        appointment_info: Complete appointment info
        
    Returns:
        Response message indicating success/failure
    """
    try:
        booking_action = appointment_info.get("booking_action", "create")
        appointment_id = appointment_info.get("appointment_id")
        
        # NOTE: Removed separate slot validation to reduce Bedrock calls
        # CTE in mutation SQL handles race condition by checking isavailable
        
        if booking_action == "create":
            consultant_id = appointment_info.get("consultant_id")
            if not consultant_id:
                return "❌ Thiếu thông tin tư vấn viên. Vui lòng chọn lại slot."
        
        # Build simple mutation request - prompt có đủ context từ appointment_info
        if booking_action == "cancel":
            mutation_request = "Hủy lịch hẹn (dùng 1 SQL với CTE)"
                
        elif booking_action == "update":
            mutation_request = "Đổi lịch hẹn (dùng 1 SQL với CTE)"
                
        else:  # create
            mutation_request = "Đặt lịch mới (dùng 1 SQL với CTE)"
        
        logger.info(f"Executing booking for {psid}: {mutation_request}")
        
        # Prepare payload for text2sql mutation Lambda
        payload = {
            "psid": psid,
            "question": mutation_request,
            "mutation": True,  # Flag to indicate this is a mutation
            "appointment_info": appointment_info
        }
        
        # Invoke text2sql Lambda with mutation flag
        response = lambda_client.invoke(
            FunctionName=TEXT2SQL_MUTATION_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload)
        )
        
        # Parse response
        result = json.loads(response["Payload"].read().decode())
        logger.info(f"Mutation response: {result}")
        
        if result.get("statusCode") == 200:
            # Success - reset booking state and appointment info
            session_service.reset_appointment_info(psid)
            session_service.set_booking_state(psid, "idle")
            logger.info(f"Booking successful for {psid}, state reset to idle")
            
            # Parse success message from body (includes formatted appointment info)
            body = result.get("body", "{}")
            if isinstance(body, str):
                body = json.loads(body)
            
            # Response already contains formatted appointment info from text2sql_handler
            success_msg = body.get("response", "Đặt lịch thành công!")
            
            # Customize success message based on action
            if booking_action == "cancel":
                return f"✅ {success_msg}\n\nLịch hẹn đã được hủy thành công."
            elif booking_action == "update":
                return f"✅ {success_msg}\n\nLịch hẹn đã được cập nhật thành công."
            else:
                return f"🎉 {success_msg}\n\nCảm ơn bạn đã sử dụng dịch vụ! Chúng tôi sẽ liên hệ với bạn sớm."
        else:
            # Error occurred
            error_body = result.get("body", "{}")
            if isinstance(error_body, str):
                error_body = json.loads(error_body)
            error_msg = error_body.get("error", error_body.get("response", "Không thể thực hiện đặt lịch"))
            logger.error(f"Booking execution failed: {error_msg}")
            return f"❌ Rất tiếc, {error_msg}. Vui lòng thử lại sau."
            
    except Exception as e:
        logger.error(f"Error executing booking: {e}", exc_info=True)
        return "❌ Đã xảy ra lỗi khi thực hiện đặt lịch. Vui lòng thử lại sau."   