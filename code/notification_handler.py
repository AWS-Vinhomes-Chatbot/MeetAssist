"""
Email Notification Lambda Handler

This Lambda function is deployed OUTSIDE VPC to send email notifications via SES.
Called from frontend after AdminManager confirms appointment.

NO VPC configuration needed - can directly access SES without NAT Gateway or VPC Endpoint.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any

from repositories.ses_repo import SESRepository
from util.lambda_logger import create_logger

# Setup
lambda_function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "NotificationHandler")
logger = create_logger(lambda_function_name)

# Environment variables
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "pqa1085@gmail.com")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Handle email notification requests from frontend
    
    Expected request body:
    {
        "action": "send_confirmation_email",
        "appointment_id": 123,
        "customer_email": "customer@example.com",
        "customer_name": "Nguyen Van A",
        "consultant_name": "Tran Thi B",
        "date": "2025-12-15",
        "time": "14:00",
        "duration": 60,
        "meeting_url": "https://meet.google.com/xxx",
        "description": "Career counseling session"
    }
    """
    logger.info(f"Event received: {json.dumps(event)}")
    
    try:
        # Parse request body
        body = event.get('body', {})
        if isinstance(body, str):
            body = json.loads(body)
        
        action = body.get('action')
        
        if not action:
            return error_response("Missing 'action' in request body", 400)
        
        # Route to appropriate method
        if action == 'send_confirmation_email':
            return send_confirmation_email(body)
        elif action == 'send_cancellation_email':
            return send_cancellation_email(body)
        else:
            return error_response(f"Unknown action: {action}", 400)
            
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return error_response(f"Internal server error: {str(e)}", 500)


def send_confirmation_email(data: Dict) -> Dict:
    """
    Send appointment confirmation email to customer
    
    Args:
        data: Request data containing appointment details
        
    Returns:
        API Gateway response dict
    """
    try:
        # Validate required fields
        required_fields = ['customer_email', 'customer_name', 'consultant_name', 'date', 'time']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return error_response(f"Missing required fields: {', '.join(missing_fields)}", 400)
        
        # Extract data
        customer_email = data['customer_email']
        customer_name = data['customer_name']
        consultant_name = data['consultant_name']
        appointment_date = data['date']
        appointment_time = data['time']
        duration = data.get('duration', 60)
        meeting_url = data.get('meeting_url', '')
        description = data.get('description', '')
        
        # Format date for display
        try:
            date_obj = datetime.strptime(appointment_date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d/%m/%Y')
            weekday = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật'][date_obj.weekday()]
        except (ValueError, IndexError):
            formatted_date = appointment_date
            weekday = ''
        
        # Build email subject
        subject = f"Xác nhận lịch hẹn tư vấn - {formatted_date}"
        
        # Build email body (HTML)
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                }}
                .header {{
                    background-color: #007bff;
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                .content {{
                    padding: 20px;
                    background-color: #f9f9f9;
                }}
                .appointment-details {{
                    background-color: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .detail-row {{
                    margin: 10px 0;
                    padding: 10px;
                    border-left: 4px solid #007bff;
                }}
                .detail-label {{
                    font-weight: bold;
                    color: #555;
                }}
                .meeting-link {{
                    display: inline-block;
                    background-color: #28a745;
                    color: white;
                    padding: 12px 24px;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    padding: 20px;
                    color: #666;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>✅ Lịch Hẹn Đã Được Xác Nhận</h1>
            </div>
            
            <div class="content">
                <p>Xin chào <strong>{customer_name}</strong>,</p>
                
                <p>Lịch hẹn tư vấn của bạn đã được xác nhận thành công!</p>
                
                <div class="appointment-details">
                    <h2 style="color: #007bff; margin-top: 0;">Thông Tin Lịch Hẹn</h2>
                    
                    <div class="detail-row">
                        <div class="detail-label">📅 Ngày:</div>
                        <div>{weekday}, {formatted_date}</div>
                    </div>
                    
                    <div class="detail-row">
                        <div class="detail-label">🕐 Giờ:</div>
                        <div>{appointment_time}</div>
                    </div>
                    
                    <div class="detail-row">
                        <div class="detail-label">⏱️ Thời lượng:</div>
                        <div>{duration} phút</div>
                    </div>
                    
                    <div class="detail-row">
                        <div class="detail-label">👤 Tư vấn viên:</div>
                        <div>{consultant_name}</div>
                    </div>
                    
                    {f'''
                    <div class="detail-row">
                        <div class="detail-label">📝 Nội dung:</div>
                        <div>{description}</div>
                    </div>
                    ''' if description else ''}
                </div>
                
                {f'''
                <div style="text-align: center;">
                    <a href="{meeting_url}" class="meeting-link">
                        🎥 Tham Gia Cuộc Họp
                    </a>
                </div>
                ''' if meeting_url else ''}
                
                <p><strong>Lưu ý:</strong></p>
                <ul>
                    <li>Vui lòng tham gia đúng giờ để không làm chậm trễ buổi tư vấn</li>
                    <li>Chuẩn bị sẵn các câu hỏi bạn muốn trao đổi</li>
                    <li>Nếu cần thay đổi lịch hẹn, vui lòng liên hệ trước ít nhất 24 giờ</li>
                </ul>
                
                <p>Nếu bạn có bất kỳ câu hỏi nào, đừng ngần ngại liên hệ với chúng tôi.</p>
                
                <p>Trân trọng,<br>
                <strong>Đội ngũ MeetAssist</strong></p>
            </div>
            
            <div class="footer">
                <p>Email này được gửi tự động, vui lòng không trả lời.</p>
                <p>© 2025 MeetAssist - Career Counseling Platform</p>
            </div>
        </body>
        </html>
        """
        
        # Initialize SES repository and send email
        ses_repo = SESRepository(sender_email=SENDER_EMAIL)
        success = ses_repo.send_notification_email(
            recipient=customer_email,
            subject=subject,
            body=html_body
        )
        
        if success:
            logger.info(f"Confirmation email sent successfully to {customer_email}")
            return success_response({
                "success": True,
                "message": f"Email sent to {customer_email}"
            })
        else:
            logger.error(f"Failed to send email to {customer_email}")
            return error_response("Failed to send email", 500)
            
    except Exception as e:
        logger.error(f"Error sending confirmation email: {str(e)}", exc_info=True)
        return error_response(f"Failed to send email: {str(e)}", 500)


def send_cancellation_email(data: Dict) -> Dict:
    """
    Send appointment cancellation email to customer
    
    Args:
        data: Request data containing appointment details
        
    Returns:
        API Gateway response dict
    """
    try:
        # Validate required fields
        required_fields = ['customer_email', 'customer_name', 'consultant_name', 'date', 'time']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return error_response(f"Missing required fields: {', '.join(missing_fields)}", 400)
        
        # Extract data
        customer_email = data['customer_email']
        customer_name = data['customer_name']
        consultant_name = data['consultant_name']
        appointment_date = data['date']
        appointment_time = data['time']
        duration = data.get('duration', 60)
        cancellation_reason = data.get('cancellation_reason', '')
        description = data.get('description', '')
        
        # Format date for display
        try:
            date_obj = datetime.strptime(appointment_date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d/%m/%Y')
            weekday = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật'][date_obj.weekday()]
        except (ValueError, IndexError):
            formatted_date = appointment_date
            weekday = ''
        
        # Build email subject
        subject = f"Thông báo hủy lịch hẹn - {formatted_date}"
        
        # Build email body (HTML)
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                }}
                .header {{
                    background-color: #dc3545;
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                .content {{
                    padding: 20px;
                    background-color: #f9f9f9;
                }}
                .appointment-details {{
                    background-color: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .detail-row {{
                    margin: 10px 0;
                    padding: 10px;
                    border-left: 4px solid #dc3545;
                }}
                .detail-label {{
                    font-weight: bold;
                    color: #555;
                }}
                .reason-box {{
                    background-color: #fff3cd;
                    border: 1px solid #ffc107;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    padding: 20px;
                    color: #666;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>❌ Lịch Hẹn Đã Bị Hủy</h1>
            </div>
            
            <div class="content">
                <p>Xin chào <strong>{customer_name}</strong>,</p>
                
                <p>Rất tiếc phải thông báo rằng lịch hẹn tư vấn của bạn đã bị hủy bởi tư vấn viên.</p>
                
                <div class="appointment-details">
                    <h2 style="color: #dc3545; margin-top: 0;">Thông Tin Lịch Hẹn Đã Hủy</h2>
                    
                    <div class="detail-row">
                        <div class="detail-label">📅 Ngày:</div>
                        <div>{weekday}, {formatted_date}</div>
                    </div>
                    
                    <div class="detail-row">
                        <div class="detail-label">🕐 Giờ:</div>
                        <div>{appointment_time}</div>
                    </div>
                    
                    <div class="detail-row">
                        <div class="detail-label">⏱️ Thời lượng:</div>
                        <div>{duration} phút</div>
                    </div>
                    
                    <div class="detail-row">
                        <div class="detail-label">👤 Tư vấn viên:</div>
                        <div>{consultant_name}</div>
                    </div>
                    
                    {f'''
                    <div class="detail-row">
                        <div class="detail-label">📝 Nội dung:</div>
                        <div>{description}</div>
                    </div>
                    ''' if description else ''}
                </div>
                
                {f'''
                <div class="reason-box">
                    <h3 style="margin-top: 0; color: #856404;">📋 Lý do hủy:</h3>
                    <p style="margin: 0;">{cancellation_reason}</p>
                </div>
                ''' if cancellation_reason else ''}
                
                <p>Chúng tôi rất tiếc về sự bất tiện này. Nếu bạn vẫn muốn đặt lịch tư vấn, vui lòng liên hệ với chúng tôi để được hỗ trợ.</p>
                
                <p>Trân trọng,<br>
                <strong>Đội ngũ MeetAssist</strong></p>
            </div>
            
            <div class="footer">
                <p>Email này được gửi tự động, vui lòng không trả lời.</p>
                <p>© 2025 MeetAssist - Career Counseling Platform</p>
            </div>
        </body>
        </html>
        """
        
        # Initialize SES repository and send email
        ses_repo = SESRepository(sender_email=SENDER_EMAIL)
        success = ses_repo.send_notification_email(
            recipient=customer_email,
            subject=subject,
            body=html_body
        )
        
        if success:
            logger.info(f"Cancellation email sent successfully to {customer_email}")
            return success_response({
                "success": True,
                "message": f"Cancellation email sent to {customer_email}"
            })
        else:
            logger.error(f"Failed to send cancellation email to {customer_email}")
            return error_response("Failed to send email", 500)
            
    except Exception as e:
        logger.error(f"Error sending cancellation email: {str(e)}", exc_info=True)
        return error_response(f"Failed to send email: {str(e)}", 500)


def success_response(data: Dict, status_code: int = 200) -> Dict:
    """Build success response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'POST,OPTIONS',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(data, default=str)
    }


def error_response(message: str, status_code: int = 500) -> Dict:
    """Build error response"""
    logger.error(f"Error response ({status_code}): {message}")
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'POST,OPTIONS',
            'Content-Type': 'application/json'
        },
        'body': json.dumps({'error': message})
    }
