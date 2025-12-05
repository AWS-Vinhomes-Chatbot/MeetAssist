"""
Chat Handler - New booking flow implementation

LUỒNG MỚI:

## CREATE Flow:
1. Detect intent "create" → collecting state
2. Trong collecting: 
   - Không gọi intent detection
   - Gọi extract_appointment_info → check fields
   - Cho phép user hỏi DB để lấy thông tin (consultant, lịch trống)
   - Khi đủ: consultant_name, date, time → query lịch trống → cache → selecting_slot
3. User chọn slot → confirming → mutation

## UPDATE Flow:
1. Detect intent "update" → selecting_appointment state
2. Auto-query lịch đã đặt theo customerid → cache
3. User chọn lịch muốn đổi → lưu info cũ + customer info → collecting state
4. Thu thập consultant_name, date, time mới → selecting_new_slot
5. User chọn slot mới → confirming → mutation (cancel cũ + insert mới)

## CANCEL Flow:
1. Detect intent "cancel" → selecting_appointment state
2. Auto-query lịch đã đặt theo customerid → cache
3. User chọn lịch muốn hủy → confirming
4. User xác nhận → mutation (update status = cancelled)

STATES:
- idle: Không có booking flow
- collecting: Đang thu thập info (name, phone, email, consultant, date, time)
- selecting_appointment: Chọn lịch đã đặt (UPDATE/CANCEL)
- selecting_slot: Chọn slot trống (CREATE - sau khi có đủ consultant/date/time)
- selecting_new_slot: Chọn slot mới (UPDATE)
- confirming: Chờ xác nhận
- confirming_restart: Hỏi tiếp tục hay bắt đầu mới
"""

from services.authencator_service import Authenticator    
from services.messenger_service import MessengerService
from services.session_service import SessionService
from services.bedrock_service import BedrockService
import logging
import json
import boto3
import os
import re
from typing import Optional, Tuple

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

# Fields cần thu thập trước khi query slot
COLLECTING_FIELDS_FOR_SLOT = ["consultant_name", "appointment_date", "appointment_time"]
# Fields cần cho CREATE (customer info - thu thập sau khi chọn slot)
CUSTOMER_INFO_FIELDS = ["customer_name", "phone_number", "email"]


def lambda_handler(event, context):
    """Main Lambda handler - same as before"""
    logger.info(f"Received event: {json.dumps(event)[:1000]}...")
    
    try:
        if 'Records' in event:
            return handle_sqs_event(event, context)
        
        http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")
        path = event.get("path", "/")
        
        if http_method == "GET" and "/callback" in path:
            return auth.handle_callback(event)
        
        logger.warning(f"Unexpected event type: method={http_method}, path={path}")
        return {"statusCode": 400, "body": "Invalid request - use webhook endpoint"}
            
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}", exc_info=True)
        return {"statusCode": 500, "body": "Internal Server Error"}


def handle_sqs_event(event, context):
    """Handle SQS FIFO event - same as before"""
    batch_item_failures = []
    
    for record in event.get('Records', []):
        message_id = record.get('messageId')
        
        try:
            body = json.loads(record.get('body', '{}'))
            messaging_event = body.get('messaging_event', {})
            original_event = body.get('original_event', {})
            
            if not messaging_event:
                logger.warning(f"Empty messaging_event in SQS message: {message_id}")
                continue
            
            psid = messaging_event.get('sender', {}).get('id')
            
            if not psid:
                logger.warning(f"No PSID in messaging_event: {message_id}")
                continue
            
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
            
            process_chat_message(psid, user_question, original_event)
            
            logger.info(f"Successfully processed SQS message: {message_id}")
            
        except Exception as e:
            logger.error(f"Error processing SQS message {message_id}: {e}", exc_info=True)
            batch_item_failures.append({'itemIdentifier': message_id})
    
    return {'batchItemFailures': batch_item_failures}


def process_chat_message(psid: str, user_question: str, original_event: dict):
    """
    Main processing logic - NEW FLOW
    
    Key changes:
    1. Không gọi intent detection khi đang trong booking flow
    2. Cho phép user hỏi DB để lấy thông tin trong collecting state
    3. Query slot chỉ khi đã có đủ consultant + date + time
    """
    # Check if this is a new user
    
    
    # Check authentication
    session = session_service.get_session(psid)
    is_authenticated = session.get("is_authenticated", False) if session else False
    
    if not is_authenticated and user_question == "GET_STARTED":
        logger.info(f"User {psid} not authenticated, delegating to auth handler")
        auth.handle_user_authorization_event(psid, user_question)
        return
    
    # Check and reset expired session/booking flow
    was_reset, reset_message = session_service.check_and_reset_expired_session(psid)
    if was_reset:
        session_service.update_last_activity(psid)
        mess.send_text_message(psid, reset_message)
        return
    
    # Update last activity
    session_service.update_last_activity(psid)
    
    # Get current booking state
    booking_state = session_service.get_booking_state(psid)
    logger.info(f"Current booking state for {psid}: {booking_state}")
    
    # =====================================================
    # TRONG BOOKING FLOW - KHÔNG gọi intent detection
    # =====================================================
    if booking_state != "idle":
        response_text = _handle_booking_flow(psid, user_question, booking_state)
        mess.send_text_message(psid, response_text)
        session_service.add_message_to_history(
            event=original_event,
            assistant_msg=response_text,
            metadata={"flow": "booking", "booking_state": booking_state}
        )
        return
    
    # =====================================================
    # IDLE STATE - Check for booking intent
    # =====================================================
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
    
    # =====================================================
    # NORMAL QUERY - Cache check then Text2SQL
    # =====================================================
    cache_hit = session_service.search_cache(psid, user_question)
    
    if cache_hit:
        logger.info(f"Cache HIT for {psid}")
        response_text = _handle_cache_hit(psid, user_question, cache_hit)
    else:
        logger.info(f"Cache MISS for {psid}, invoking text2sql")
        response_text, metadata = _handle_text2sql(psid, user_question)
    
    mess.send_text_message(psid, response_text)
    session_service.add_message_to_history(
        event=original_event,
        assistant_msg=response_text,
        metadata=None if cache_hit else (metadata if 'metadata' in dir() else None)
    )


def _start_booking_flow(psid: str, user_question: str, booking_intent: dict) -> str:
    """
    Start booking flow based on intent.
    
    NEW LOGIC:
    - CREATE: Go to collecting state immediately (not selecting_slot first)
    - UPDATE/CANCEL: Go to selecting_appointment state, auto-query user's appointments
    """
    try:
        session_service.reset_appointment_info(psid)
        
        booking_action = booking_intent.get("booking_action", "create")
        session_service.update_appointment_info(psid, {"booking_action": booking_action})
        
        if booking_action == "create":
            # CREATE: Đi thẳng vào collecting, thu thập consultant + date + time trước
            session_service.set_booking_state(psid, "collecting")
            
            # Extract any info from initial message
            context = session_service.get_context_for_llm(psid)
            extracted = bedrock_service.extract_appointment_info(
                message=user_question,
                current_info={"booking_action": "create"},
                context=context
            )
            
            if extracted:
                session_service.update_appointment_info(psid, extracted)
            
            # Generate prompt for collecting info
            return _generate_collecting_prompt(psid)
        
        elif booking_action in ["update", "cancel"]:
            # UPDATE/CANCEL: Query user's appointments first
            session_service.set_booking_state(psid, "selecting_appointment")
            return _show_user_appointments(psid, booking_action)
        
        return "Xin lỗi, không hiểu yêu cầu. Bạn muốn đặt lịch, đổi lịch hay hủy lịch?"
        
    except Exception as e:
        logger.error(f"Error starting booking flow: {e}", exc_info=True)
        return "Xin lỗi, đã xảy ra lỗi. Vui lòng thử lại."


def _generate_collecting_prompt(psid: str) -> str:
    """
    Generate prompt based on what info is still needed.
    
    For CREATE:
    - First, need: consultant_name, date, time (to query available slots)
    - After selecting slot: need customer_name, phone, email
    """
    current_info = session_service.get_appointment_info(psid)
    booking_action = current_info.get("booking_action", "create")
    
    # Check if we have consultant + date + time
    has_slot_criteria = all([
        current_info.get("consultant_name"),
        current_info.get("appointment_date"),
        current_info.get("appointment_time")
    ])
    
    if has_slot_criteria:
        # Đã có đủ info để query slot - chuyển sang selecting_slot
        return _query_and_show_available_slots(psid, current_info)
    
    # Build prompt asking for missing slot criteria
    missing = []
    if not current_info.get("consultant_name"):
        missing.append("tư vấn viên bạn muốn gặp")
    if not current_info.get("appointment_date"):
        missing.append("ngày bạn muốn hẹn")
    if not current_info.get("appointment_time"):
        missing.append("giờ bạn muốn hẹn")
    
    # Differentiate between CREATE and UPDATE flow
    if booking_action == "update":
        # UPDATE flow - user đang đổi lịch cũ
        if len(missing) == 3:
            return (
                "🔄 **Đổi lịch hẹn - Thông tin lịch MỚI**\n\n"
                "Vui lòng cho mình biết lịch MỚI:\n"
                "• Tên tư vấn viên mới (hoặc giữ nguyên)\n"
                "• Ngày mới bạn muốn hẹn\n"
                "• Giờ mới bạn muốn hẹn\n\n"
                "💡 Bạn có thể hỏi:\n"
                "• 'Cho tôi danh sách tư vấn viên'\n"
                "• 'Lịch trống ngày mai như thế nào?'\n"
                "• 'Anh/chị X còn slot nào trống?'"
            )
        
        # Có một số info rồi - UPDATE flow
        prompt = "🔄 **Thông tin lịch MỚI:**\n"
        if current_info.get("consultant_name"):
            prompt += f"✅ Tư vấn viên mới: {current_info['consultant_name']}\n"
        if current_info.get("appointment_date"):
            prompt += f"✅ Ngày mới: {current_info['appointment_date']}\n"
        if current_info.get("appointment_time"):
            prompt += f"✅ Giờ mới: {current_info['appointment_time']}\n"
        
        prompt += "\n👉 Vui lòng cho mình biết thêm: " + ", ".join(missing)
        prompt += "\n💡 Hoặc hỏi: 'Cho xem danh sách tư vấn viên', 'Lịch trống của X?'"
        
        return prompt
    
    # CREATE flow
    if len(missing) == 3:
        return (
            "📅 **Đặt lịch hẹn tư vấn**\n\n"
            "Để đặt lịch, vui lòng cho mình biết:\n"
            "• Tên tư vấn viên (hoặc lĩnh vực tư vấn)\n"
            "• Ngày bạn muốn hẹn\n"
            "• Giờ bạn muốn hẹn\n\n"
            "💡 Bạn có thể hỏi:\n"
            "• 'Có tư vấn viên nào chuyên về tài chính?'\n"
            "• 'Lịch trống ngày mai như thế nào?'\n"
            "• 'Cho xem danh sách tư vấn viên'"
        )
    
    # Có một số info rồi - CREATE flow
    prompt = "📝 **Thông tin đặt lịch:**\n"
    if current_info.get("consultant_name"):
        prompt += f"✅ Tư vấn viên: {current_info['consultant_name']}\n"
    if current_info.get("appointment_date"):
        prompt += f"✅ Ngày: {current_info['appointment_date']}\n"
    if current_info.get("appointment_time"):
        prompt += f"✅ Giờ: {current_info['appointment_time']}\n"
    
    prompt += "\n👉 Vui lòng cho mình biết thêm: " + ", ".join(missing)
    
    return prompt


def _query_and_show_available_slots(psid: str, current_info: dict) -> str:
    """
    Query available slots based on available criteria (consultant, date, time).
    Flexible query - uses whatever info is available, not requiring all 3.
    """
    try:
        consultant = current_info.get("consultant_name", "")
        date = current_info.get("appointment_date", "")
        time = current_info.get("appointment_time", "")
        
        # Build flexible query based on available criteria
        conditions = []
        if consultant:
            conditions.append(f'tư vấn viên tên "{consultant}"')
        if date:
            conditions.append(f'ngày {date}')
        if time:
            conditions.append(f'khoảng giờ {time}')
        
        if not conditions:
            # No criteria - get any available slots
            query = """Tìm các khung giờ tư vấn còn trống.
            Yêu cầu: consultantid, fullname, specialties, date, starttime, endtime, isavailable.
            Chỉ lấy slot còn trống (isavailable = true). Sắp xếp theo ngày và giờ. """
        else:
            # Build query with available conditions using OR logic for flexible matching
            criteria_text = " hoặc ".join(conditions)
            query = f"""Tìm các khung giờ tư vấn còn trống thỏa mãn một trong các điều kiện sau: {criteria_text}.
            Yêu cầu: consultantid, fullname, specialties, date, starttime, endtime, isavailable.
            Chỉ lấy slot còn trống (isavailable = true). 
            Ưu tiên: khớp nhiều điều kiện hơn xếp trước. Sắp xếp theo ngày và giờ."""
        
        payload = {
            "psid": psid,
            "question": query,
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
                # Không tìm thấy slot - vẫn ở collecting, đề xuất thử khác
                criteria_msg = []
                if consultant:
                    criteria_msg.append(f"tư vấn viên {consultant}")
                if date:
                    criteria_msg.append(f"ngày {date}")
                if time:
                    criteria_msg.append(f"lúc {time}")
                
                criteria_str = ", ".join(criteria_msg) if criteria_msg else "tiêu chí đã cho"
                
                return (
                    f"😔 Không tìm thấy lịch trống với {criteria_str}.\n\n"
                    "Bạn có thể thử:\n"
                    "• Chọn ngày khác\n"
                    "• Chọn giờ khác\n"
                    "• Chọn tư vấn viên khác\n"
                    "• Hỏi 'Lịch trống của [tên tư vấn viên]?'\n"
                    "• Hỏi 'Có tư vấn viên nào rảnh ngày [ngày]?'"
                )
            
            # Cache slots and switch to selecting_slot
            session_service.cache_available_slots(psid, slots)
            session_service.set_booking_state(psid, "selecting_slot")
            
            # Format slots list - show header based on criteria
            if consultant:
                message = f"📅 **Lịch trống của {consultant}:**\n\n"
            elif date:
                message = f"📅 **Lịch trống ngày {date}:**\n\n"
            else:
                message = "📅 **Các lịch trống tìm được:**\n\n"
            
            for i, slot in enumerate(slots[:5], 1):
                slot_consultant = slot.get("fullname", slot.get("consultant_name", ""))
                slot_date = slot.get("date", slot.get("available_date", ""))
                slot_time = slot.get("starttime", slot.get("start_time", slot.get("time", "")))
                slot_end = slot.get("endtime", slot.get("end_time", ""))
                spec = slot.get("specialties", slot.get("specialization", ""))
                
                message += f"{i}️⃣ 👨‍💼 {slot_consultant} | 📆 {slot_date} | 🕐 {slot_time}"
                if slot_end:
                    message += f" - {slot_end}"
                message += "\n"
            
            message += "\n👉 **Vui lòng chọn số thứ tự** (1, 2, 3...)"
            
            return message
        else:
            logger.error(f"Error querying slots: {result}")
            return "Đã xảy ra lỗi khi tìm lịch trống. Vui lòng thử lại."
            
    except Exception as e:
        logger.error(f"Error querying available slots: {e}", exc_info=True)
        return "Đã xảy ra lỗi. Vui lòng thử lại."


def _show_user_appointments(psid: str, action: str) -> str:
    """
    Query and show user's appointments for UPDATE/CANCEL.
    """
    try:
        payload = {
            "psid": psid,
            "question": f"""Lấy lịch hẹn đang pending hoặc confirmed của khách hàng có customerid là '{psid}'.
            Yêu cầu: appointmentid, customerid, fullname as customer_name, phonenumber as phone_number, 
            consultantid, tên tư vấn viên, ngày hẹn, giờ bắt đầu, status.
            Sắp xếp theo ngày giảm dần. Giới hạn 5 kết quả.""",
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
            
            # Cache appointments
            session_service.cache_user_appointments(psid, appointments)
            
            # Format list
            action_text = "hủy" if action == "cancel" else "đổi"
            message = f"📋 **Lịch hẹn của bạn:**\n\n"
            
            for i, apt in enumerate(appointments[:5], 1):
                date = apt.get("appointmentdate", apt.get("date", "N/A"))
                time = apt.get("starttime", apt.get("time", ""))
                consultant = apt.get("consultant_name", apt.get("fullname", ""))
                status = apt.get("status", "")
                
                message += f"{i}. 📅 {date}"
                if time:
                    message += f" lúc {time}"
                if consultant:
                    message += f" với {consultant}"
                if status:
                    status_emoji = "⏳" if status == "pending" else "✅" if status == "confirmed" else "📌"
                    message += f" - {status_emoji} {status}"
                message += "\n"
            
            message += f"\n👉 Nhập **số thứ tự** (1-{min(5, len(appointments))}) của lịch hẹn bạn muốn {action_text}."
            
            return message
        else:
            return "Không thể lấy danh sách lịch hẹn. Vui lòng thử lại sau."
            
    except Exception as e:
        logger.error(f"Error showing user appointments: {e}", exc_info=True)
        return "Đã xảy ra lỗi khi lấy danh sách lịch hẹn."


def _handle_booking_flow(psid: str, user_question: str, booking_state: str) -> str:
    """
    Handle ongoing booking flow.
    
    KHÔNG gọi intent detection trong booking flow.
    """
    try:
        # Check abort keywords
        abort_keywords = ["thôi", "bỏ qua", "dừng", "không làm nữa", "quay lại", "hủy bỏ", "cancel", "stop", "thoát", "exit", "hủy"]
        msg_lower = user_question.lower().strip()
        
        if msg_lower in abort_keywords or any(kw in msg_lower for kw in abort_keywords):
            session_service.reset_appointment_info(psid)
            session_service.set_booking_state(psid, "idle")
            logger.info(f"User {psid} aborted booking flow")
            return "Quá trình đặt lịch đã bị hủy. Bạn có thể hỏi tôi bất cứ điều gì khác!"
        
        current_info = session_service.get_appointment_info(psid)
        booking_action = current_info.get("booking_action", "create")
        
        # =====================================================
        # STATE: CONFIRMING_RESTART
        # =====================================================
        if booking_state == "confirming_restart":
            return _handle_restart_confirmation(psid, user_question)
        
        # =====================================================
        # STATE: SELECTING_APPOINTMENT (UPDATE/CANCEL)
        # =====================================================
        if booking_state == "selecting_appointment":
            selection = _parse_selection(user_question)
            
            if selection is not None:
                cached_apt = session_service.get_cached_appointment_by_index(psid, selection)
                
                if cached_apt:
                    # Save appointment info
                    # lưu thông id lịch cũ để dùng cho update/cancel
                    session_service.update_appointment_info(psid, {
                        "appointment_id": cached_apt.get("appointment_id"),
                        "customer_id": cached_apt.get("customer_id"),
                        "customer_name": cached_apt.get("customer_name"),
                        "phone_number": cached_apt.get("phone_number"),
                        "old_consultant_id": cached_apt.get("consultant_id"),
                        "old_consultant_name": cached_apt.get("consultant_name"),
                        "old_date": cached_apt.get("appointment_date"),
                        "old_time": cached_apt.get("start_time")
                    })
                    
                    if booking_action == "cancel":
                        # CANCEL: Go to confirming
                        session_service.set_booking_state(psid, "confirming")
                        return _generate_confirmation_message(session_service.get_appointment_info(psid))
                    else:
                        # UPDATE: Go to collecting for new slot info
                        session_service.set_booking_state(psid, "collecting")
                        return (
                            f"📝 **Bạn đã chọn lịch:**\n"
                            f"📅 {cached_apt.get('appointment_date')} lúc {cached_apt.get('start_time')}\n"
                            f"👨‍💼 {cached_apt.get('consultant_name')}\n\n"
                            "🔄 **Vui lòng cho biết thông tin lịch MỚI:**\n"
                            "• Tư vấn viên mới (hoặc giữ nguyên)\n"
                            "• Ngày mới\n"
                            "• Giờ mới\n\n"
                            "💡 Bạn có thể hỏi 'Lịch trống của [tên]?' để xem lịch trống."
                        )
                else:
                    return f"❌ Không tìm thấy lịch hẹn số {selection}. Vui lòng chọn lại."
            
            # Not a selection - check if user is asking a question 
            context = session_service.get_context_for_llm(psid)
            extracted = bedrock_service.extract_appointment_info(
                message=user_question,
                current_info=current_info,
                context=context
            )
            if extracted.get("is_query"):
                return _handle_query_in_booking(psid, user_question)
            
            return "Vui lòng chọn số thứ tự lịch hẹn (1, 2, 3...) hoặc gõ 'thôi' để hủy." #thoát khỏi state selecting_appointment
        
        # =====================================================
        # STATE: SELECTING_SLOT (CREATE - after collecting slot criteria)
        # =====================================================
        if booking_state == "selecting_slot":
            # Check if cache is stale
            if session_service.is_slot_cache_stale(psid, max_age_seconds=300):
                logger.info(f"Slot cache stale for {psid}, returning to collecting")
                session_service.set_booking_state(psid, "collecting")
                return _generate_collecting_prompt(psid)
            
            selection = _parse_selection(user_question)
            
            if selection is not None:
                cached_slot = session_service.get_cached_slot_by_index(psid, selection)
                
                if cached_slot:
                    # Save slot info
                    session_service.update_appointment_info(psid, {
                        "consultant_id": cached_slot.get("consultant_id"),
                        "consultant_name": cached_slot.get("consultant_name"),
                        "appointment_date": cached_slot.get("date"),
                        "appointment_time": cached_slot.get("time"),
                        "appointment_end_time": cached_slot.get("end_time"),
                        "selected_slot_index": selection
                    })
                    
                    # Now collect customer info
                    # Check if we already have customer info
                    updated_info = session_service.get_appointment_info(psid)
                    has_customer_info = all([
                        updated_info.get("customer_name"),
                        updated_info.get("phone_number"),
                        updated_info.get("email")
                    ])
                    
                    if has_customer_info:
                        # Go to confirming
                        session_service.set_booking_state(psid, "confirming")
                        return _generate_confirmation_message(updated_info)
                    else:
                        # Stay in selecting_slot but ask for customer info
                        session_service.set_booking_state(psid, "collecting_customer")
                        return (
                            f"✅ **Bạn đã chọn:**\n"
                            f"📆 {cached_slot.get('date')} lúc 🕐 {cached_slot.get('time')}\n"
                            f"👨‍💼 Tư vấn viên: {cached_slot.get('consultant_name')}\n\n"
                            "👉 Vui lòng cho biết **họ tên**, **số điện thoại** và **email** của bạn."
                        )
                else:
                    return f"❌ Không tìm thấy slot số {selection}. Vui lòng chọn lại."
            
            # Not a selection - check if user is asking a question
            context = session_service.get_context_for_llm(psid)
            extracted = bedrock_service.extract_appointment_info(
                message=user_question,
                current_info=current_info,
                context=context
            )
            if extracted.get("is_query"):
                return _handle_query_in_booking(psid, user_question) + "\n\n👉 Hãy chọn số thứ tự slot ở trên."
            
            return "Vui lòng chọn số thứ tự slot (1, 2, 3...) hoặc gõ 'thôi' để hủy."
        
        # =====================================================
        # STATE: SELECTING_NEW_SLOT (UPDATE)
        # =====================================================
        if booking_state == "selecting_new_slot":
            if session_service.is_slot_cache_stale(psid, max_age_seconds=300):
                session_service.set_booking_state(psid, "collecting")
                return _generate_collecting_prompt(psid)
            
            selection = _parse_selection(user_question)
            
            if selection is not None:
                cached_slot = session_service.get_cached_slot_by_index(psid, selection)
                
                if cached_slot:
                    session_service.update_appointment_info(psid, {
                        "consultant_id": cached_slot.get("consultant_id"),
                        "consultant_name": cached_slot.get("consultant_name"),
                        "appointment_date": cached_slot.get("date"),
                        "appointment_time": cached_slot.get("time"),
                        "appointment_end_time": cached_slot.get("end_time"),
                        "selected_slot_index": selection
                    })
                    
                    session_service.set_booking_state(psid, "confirming")
                    return _generate_confirmation_message(session_service.get_appointment_info(psid))
                else:
                    return f"❌ Không tìm thấy slot số {selection}. Vui lòng chọn lại."
            
            # Check if user is asking a question
            context = session_service.get_context_for_llm(psid)
            extracted = bedrock_service.extract_appointment_info(
                message=user_question,
                current_info=current_info,
                context=context
            )
            if extracted.get("is_query"):
                return _handle_query_in_booking(psid, user_question) + "\n\n👉 Hãy chọn số thứ tự slot mới."
            
            return "Vui lòng chọn số thứ tự slot mới (1, 2, 3...) hoặc gõ 'thôi' để hủy."
        
        # =====================================================
        # STATE: COLLECTING (CREATE or UPDATE)
        # =====================================================
        if booking_state == "collecting":
            # Extract info from message (also checks if it's a query)
            context = session_service.get_context_for_llm(psid)
            extracted = bedrock_service.extract_appointment_info(
                message=user_question,
                current_info=current_info,
                context=context
            )
            
            # Check if user is asking a question
            if extracted.get("is_query"):
                query_response = _handle_query_in_booking(psid, user_question)
                
                # Add reminder based on booking action and missing info
                missing = []
                if not current_info.get("consultant_name"):
                    missing.append("tư vấn viên")
                if not current_info.get("appointment_date"):
                    missing.append("ngày")
                if not current_info.get("appointment_time"):
                    missing.append("giờ")
                
                if missing:
                    if booking_action == "update":
                        reminder = f"\n\n👉 Hãy cho mình biết thông tin lịch MỚI: {', '.join(missing)}"
                    else:
                        reminder = f"\n\n👉 Hãy cho mình biết: {', '.join(missing)} để đặt lịch"
                    return query_response + reminder
                
                return query_response
            
            # Remove is_query and user_intent_summary from extracted before updating
            extracted.pop("is_query", None)
            extracted.pop("user_intent_summary", None)
            
            if extracted:
                session_service.update_appointment_info(psid, extracted)
                current_info = session_service.get_appointment_info(psid)
            
            # Check if we have enough info for slot query
            has_slot_criteria = all([
                current_info.get("consultant_name"),
                current_info.get("appointment_date"),
                current_info.get("appointment_time")
            ])
            
            if has_slot_criteria:
                if booking_action == "update":
                    # For UPDATE: query and show new slots
                    return _query_and_show_available_slots_for_update(psid, current_info)
                else:
                    # For CREATE: query slots
                    return _query_and_show_available_slots(psid, current_info)
            
            # Still need more info
            return _generate_collecting_prompt(psid)
        
        # =====================================================
        # STATE: COLLECTING_CUSTOMER (after selecting slot)
        # =====================================================
        if booking_state == "collecting_customer":
            # Extract customer info
            context = session_service.get_context_for_llm(psid)
            extracted = bedrock_service.extract_appointment_info(
                message=user_question,
                current_info=current_info,
                context=context
            )
            
            # Check if user is asking a question
            if extracted.get("is_query"):
                query_response = _handle_query_in_booking(psid, user_question)
                return query_response + "\n\n👉 Vui lòng cung cấp họ tên, số điện thoại và email của bạn."
            
            # Remove is_query and user_intent_summary before updating
            extracted.pop("is_query", None)
            extracted.pop("user_intent_summary", None)
            
            if extracted:
                session_service.update_appointment_info(psid, extracted)
                current_info = session_service.get_appointment_info(psid)
            
            # Check if all customer info collected
            has_customer_info = all([
                current_info.get("customer_name"),
                current_info.get("phone_number"),
                current_info.get("email")
            ])
            
            if has_customer_info:
                session_service.set_booking_state(psid, "confirming")
                return _generate_confirmation_message(current_info)
            
            # Still need more customer info
            missing = []
            if not current_info.get("customer_name"):
                missing.append("họ tên")
            if not current_info.get("phone_number"):
                missing.append("số điện thoại")
            if not current_info.get("email"):
                missing.append("email")
            
            return f"Vui lòng cho mình biết thêm: {', '.join(missing)}"
        
        # =====================================================
        # STATE: CONFIRMING
        # =====================================================
        if booking_state == "confirming":
            confirm_keywords = ["ok", "đồng ý", "xác nhận", "được", "yes", "có", "ừ", "đúng rồi", "confirm"]
            
            if any(kw in msg_lower for kw in confirm_keywords):
                return _execute_booking(psid, current_info)
            
            # Maybe user wants to change something
            context = session_service.get_context_for_llm(psid)
            extracted = bedrock_service.extract_appointment_info(
                message=user_question,
                current_info=current_info,
                context=context
            )
            
            # Check if user is asking a question
            if extracted.get("is_query"):
                query_response = _handle_query_in_booking(psid, user_question)
                action_text = {"create": "đặt lịch", "update": "cập nhật", "cancel": "hủy lịch"}.get(booking_action, "đặt lịch")
                return query_response + f"\n\n👉 Trả lời **'có'** để xác nhận {action_text} hoặc **'thôi'** để hủy."
            
            # Remove is_query and user_intent_summary before updating
            extracted.pop("is_query", None)
            extracted.pop("user_intent_summary", None)
            
            if extracted:
                session_service.update_appointment_info(psid, extracted)
                return _generate_confirmation_message(session_service.get_appointment_info(psid))
            
            action_text = {"create": "đặt lịch", "update": "cập nhật", "cancel": "hủy lịch"}.get(booking_action, "đặt lịch")
            return f"Trả lời **'có'** để xác nhận {action_text} hoặc **'thôi'** để hủy."
        
        return "Xin lỗi, đã xảy ra lỗi. Vui lòng thử lại."
        
    except Exception as e:
        logger.error(f"Error handling booking flow: {e}", exc_info=True)
        return "Xin lỗi, đã xảy ra lỗi. Vui lòng thử lại."


def _query_and_show_available_slots_for_update(psid: str, current_info: dict) -> str:
    """Query slots for UPDATE flow and transition to selecting_new_slot"""
    result = _query_and_show_available_slots(psid, current_info)
    
    # If successful (contains slot list), change state
    if "Vui lòng chọn số thứ tự" in result:
        session_service.set_booking_state(psid, "selecting_new_slot")
    
    return result


def _handle_query_in_booking(psid: str, user_question: str) -> str:
    """
    Handle user's question during booking flow (query DB for info).
    """
    try:
        context = session_service.get_context_for_llm(psid)
        current_info = session_service.get_appointment_info(psid)
        
        booking_context = f"[Đang đặt lịch - info hiện tại: {json.dumps({k:v for k,v in current_info.items() if v and k not in ['booking_state','booking_action','cached_appointments','cached_available_slots']}, ensure_ascii=False)}]"
        
        payload = {
            "psid": psid,
            "question": user_question,
            "context": booking_context + "\n" + context if context else booking_context
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
            
            sql_result = body.get("sql_result", [])
            schema_context = body.get("schema_context_text", "")
            sql_result_str = json.dumps(sql_result, ensure_ascii=False, default=str)
            
            query_response = bedrock_service.get_answer_from_sql_results(
                question=user_question,
                results=sql_result_str,
                schema=schema_context,
                context=context
            )
            
            return query_response
        else:
            return "Xin lỗi, không tìm được thông tin. Bạn có thể hỏi cách khác."
            
    except Exception as e:
        logger.error(f"Error handling booking query: {e}")
        return "Đã xảy ra lỗi khi tìm kiếm."


def _handle_restart_confirmation(psid: str, user_message: str) -> str:
    """Handle restart confirmation"""
    message_lower = user_message.lower().strip()
    
    continue_keywords = ["tiếp tục", "tiếp", "1", "số 1", "continue"]
    if any(kw in message_lower for kw in continue_keywords) or message_lower == "1":
        current_info = session_service.get_appointment_info(psid)
        booking_action = current_info.get("booking_action", "create")
        
        session_service.set_booking_state(psid, "collecting")
        return _generate_collecting_prompt(psid)
    
    restart_keywords = ["bắt đầu mới", "bắt đầu lại", "mới", "2", "số 2", "restart", "new"]
    if any(kw in message_lower for kw in restart_keywords) or message_lower == "2":
        current_info = session_service.get_appointment_info(psid)
        new_intent = current_info.get("pending_new_intent", {})
        
        session_service.reset_appointment_info(psid)
        
        if new_intent:
            return _start_booking_flow(psid, "", new_intent)
        else:
            session_service.set_booking_state(psid, "idle")
            return "Đã hủy. Bạn có thể nói 'đặt lịch', 'hủy lịch', hoặc 'đổi lịch' để bắt đầu lại."
    
    return "Nhập **1** để tiếp tục hoặc **2** để bắt đầu lại."


def _parse_selection(user_message: str) -> Optional[int]:
    """Parse user's selection number (1-10)"""
    message = user_message.lower().strip()
    
    if message.isdigit() and 1 <= int(message) <= 10:
        return int(message)
    
    import re
    match = re.search(r'(?:số|lịch|cái|slot)\s*(\d+)', message)
    if match:
        num = int(match.group(1))
        if 1 <= num <= 10:
            return num
    
    match = re.search(r'\b(\d)\b', message)
    if match:
        num = int(match.group(1))
        if 1 <= num <= 10:
            return num
    
    return None


# _is_question removed - replaced by is_query field from extract_appointment_info


def _generate_confirmation_message(appointment_info: dict) -> str:
    """Generate confirmation message"""
    booking_action = appointment_info.get("booking_action", "create")
    
    if booking_action == "cancel":
        message = "📋 **Xác nhận HỦY lịch hẹn:**\n\n"
        message += f"📅 Ngày: {appointment_info.get('old_date', 'N/A')}\n"
        message += f"🕐 Giờ: {appointment_info.get('old_time', 'N/A')}\n"
        message += f"👨‍💼 Tư vấn viên: {appointment_info.get('old_consultant_name', 'N/A')}\n"
        message += "\n⚠️ Trả lời **'có'** để xác nhận HỦY hoặc **'thôi'** để giữ lại."
        return message
    
    if booking_action == "update":
        message = "📋 **Xác nhận ĐỔI lịch hẹn:**\n\n"
        message += "❌ **Lịch cũ:**\n"
        message += f"   📅 {appointment_info.get('old_date')}\n"
        message += f"   🕐 {appointment_info.get('old_time')}\n"
        message += f"   👨‍💼 {appointment_info.get('old_consultant_name')}\n"
        message += "\n✅ **Lịch mới:**\n"
        message += f"   📅 {appointment_info.get('appointment_date')}\n"
        message += f"   🕐 {appointment_info.get('appointment_time')}\n"
        message += f"   👨‍💼 {appointment_info.get('consultant_name')}\n"
        message += "\nTrả lời **'có'** để xác nhận hoặc **'thôi'** để hủy."
        return message
    
    # CREATE
    message = "📋 **Xác nhận đặt lịch:**\n\n"
    message += f"👤 Tên: {appointment_info.get('customer_name', 'N/A')}\n"
    message += f"📞 SĐT: {appointment_info.get('phone_number', 'N/A')}\n"
    message += f"📧 Email: {appointment_info.get('email', 'N/A')}\n"
    message += f"📅 Ngày: {appointment_info.get('appointment_date', 'N/A')}\n"
    message += f"🕐 Giờ: {appointment_info.get('appointment_time', 'N/A')}\n"
    message += f"👨‍💼 Tư vấn viên: {appointment_info.get('consultant_name', 'N/A')}\n"
    message += "\n✅ Trả lời **'có'** để xác nhận hoặc **'thôi'** để hủy."
    
    return message


def _execute_booking(psid: str, appointment_info: dict) -> str:
    """Execute booking mutation"""
    try:
        booking_action = appointment_info.get("booking_action", "create")
        
        if booking_action == "cancel":
            mutation_request = "Hủy lịch hẹn"
        elif booking_action == "update":
            mutation_request = "Đổi lịch hẹn"
        else:
            mutation_request = "Đặt lịch mới"
        
        logger.info(f"Executing booking for {psid}: {mutation_request}")
        
        payload = {
            "psid": psid,
            "question": mutation_request,
            "mutation": True,
            "appointment_info": appointment_info
        }
        
        response = lambda_client.invoke(
            FunctionName=TEXT2SQL_MUTATION_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response["Payload"].read().decode())
        logger.info(f"Mutation response: {result}")
        
        if result.get("statusCode") == 200:
            session_service.reset_appointment_info(psid)
            session_service.set_booking_state(psid, "idle")
            
            body = result.get("body", "{}")
            if isinstance(body, str):
                body = json.loads(body)
            
            success_msg = body.get("response", "Thành công!")
            
            if booking_action == "cancel":
                return f"✅ {success_msg}\n\nLịch hẹn đã được hủy thành công."
            elif booking_action == "update":
                return f"✅ {success_msg}\n\nLịch hẹn đã được cập nhật thành công."
            else:
                return f"🎉 {success_msg}\n\nCảm ơn bạn đã sử dụng dịch vụ!"
        else:
            error_body = result.get("body", "{}")
            if isinstance(error_body, str):
                error_body = json.loads(error_body)
            error_msg = error_body.get("error", error_body.get("response", "Không thể thực hiện"))
            logger.error(f"Booking failed: {error_msg}")
            return f"❌ {error_msg}. Vui lòng thử lại."
            
    except Exception as e:
        logger.error(f"Error executing booking: {e}", exc_info=True)
        return "❌ Đã xảy ra lỗi. Vui lòng thử lại."


def _handle_cache_hit(psid: str, user_question: str, cache_hit: dict) -> str:
    """Handle cache hit"""
    try:
        cached_metadata = cache_hit.get("metadata", {})
        sql_result = cached_metadata.get("sql_result", "")
        schema_context = cached_metadata.get("schema_context_text", "")
        context = session_service.get_context_for_llm(psid)
        
        response = bedrock_service.get_answer_from_sql_results(
            question=user_question,
            results=sql_result,
            schema=schema_context,
            context=context
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error handling cache hit: {e}")
        return "Xin lỗi, đã xảy ra lỗi."


def _handle_text2sql(psid: str, user_question: str) -> tuple:
    """Handle cache miss - invoke text2sql"""
    try:
        context = session_service.get_context_for_llm(psid)
        
        payload = {
            "psid": psid,
            "question": user_question,
            "context": context
        }
        
        response = lambda_client.invoke(
            FunctionName=TEXT2SQL_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response["Payload"].read().decode())
        
        if result.get("statusCode") != 200:
            error_body = result.get("body", "{}")
            if isinstance(error_body, str):
                error_body = json.loads(error_body)
            return error_body.get("response", "Xin lỗi, không thể xử lý yêu cầu."), {"error": True}
        
        body = result.get("body", "{}")
        if isinstance(body, str):
            body = json.loads(body)
        
        sql_result = body.get("sql_result", [])
        schema_context = body.get("schema_context_text", "")
        sql_result_str = json.dumps(sql_result, ensure_ascii=False, default=str)
        
        response_text = bedrock_service.get_answer_from_sql_results(
            question=user_question,
            results=sql_result_str,
            schema=schema_context,
            context=context
        )
        
        is_empty = not sql_result or (isinstance(sql_result, list) and len(sql_result) == 0)
        if is_empty:
            return response_text, None
        
        return response_text, {
            "source": "text2sql",
            "sql_result": sql_result_str,
            "schema_context_text": schema_context
        }
        
    except Exception as e:
        logger.error(f"Error in _handle_text2sql: {e}", exc_info=True)
        return "Xin lỗi, đã xảy ra lỗi.", {"error": str(e)}
