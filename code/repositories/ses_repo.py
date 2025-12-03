"""
SES Repository - Handles email sending via Amazon SES.

Separates email operations from business logic.
Uses singleton pattern for SES client to optimize Lambda performance.
"""

import os
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

# Module-level singleton for Lambda container reuse
_ses_client = None


def get_ses_client(region: str = None):
    """
    Get or create SES client singleton.
    
    Args:
        region: AWS region (default from SES_REGION env or ap-northeast-1)
    
    Returns:
        boto3 SES client instance
    """
    global _ses_client
    if _ses_client is None:
        # Use SES_REGION for explicit SES region, fallback to AWS_REGION or Tokyo
        region = region or os.environ.get("SES_REGION") or os.environ.get("AWS_REGION", "ap-northeast-1")
        _ses_client = boto3.client("ses", region_name=region)
        logger.info(f"Created SES client for region: {region}")
    return _ses_client


class SESRepository:
    """Repository for Amazon SES operations."""
    
    def __init__(self, sender_email: str = None, ses_client=None):
        """
        Initialize SES repository.
        
        Args:
            sender_email: Sender email address (default from OTP_SENDER_EMAIL env var)
            ses_client: Optional SES client (for testing, otherwise uses singleton)
        
        Usage:
            # Production (auto-creates singleton):
            repo = SESRepository()
            
            # Custom sender:
            repo = SESRepository(sender_email="custom@example.com")
            
            # Testing with mock:
            mock_client = Mock()
            repo = SESRepository(ses_client=mock_client)
        """
        # Use singleton client or injected client (for testing)
        self.ses_client = ses_client if ses_client is not None else get_ses_client()
        self.sender_email = sender_email or os.environ.get("OTP_SENDER_EMAIL", "pqa1085@gmail.com")
        
        if not self.sender_email:
            raise ValueError("Sender email must be provided or set in OTP_SENDER_EMAIL environment variable")
    
    def send_otp_email(self, recipient: str, otp: str) -> bool:
        """
        Send OTP code via email.
        
        Args:
            recipient: Recipient email address
            otp: 6-digit OTP code
            
        Returns:
            True if sent successfully
        """
        try:
            response = self.ses_client.send_email(
                Source=self.sender_email,
                Destination={'ToAddresses': [recipient]},
                Message={
                    'Subject': {
                        'Data': 'MeetAssist - Mã xác thực OTP',
                        'Charset': 'UTF-8'
                    },
                    'Body': {
                        'Text': {
                            'Data': f'Mã OTP của bạn là: {otp}\n\nMã này có hiệu lực trong 5 phút.',
                            'Charset': 'UTF-8'
                        },
                        'Html': {
                            'Data': f'''
                                <html>
                                <head></head>
                                <body>
                                    <h2>Mã OTP của bạn</h2>
                                    <p><strong style="font-size:24px; color:#007bff;">{otp}</strong></p>
                                    <p>Mã này có hiệu lực trong 5 phút.</p>
                                    <hr>
                                    <p style="color:#666; font-size:12px;">
                                        Nếu bạn không yêu cầu mã này, vui lòng bỏ qua email này.
                                    </p>
                                </body>
                                </html>
                            ''',
                            'Charset': 'UTF-8'
                        }
                    }
                }
            )
            
            message_id = response.get('MessageId')
            logger.info(f"OTP email sent to {recipient}: {message_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to send OTP email to {recipient}: {e}")
            return False
    
    def send_notification_email(self, recipient: str, subject: str, body: str) -> bool:
        """
        Send generic notification email.
        
        Args:
            recipient: Recipient email address
            subject: Email subject
            body: Email body (HTML)
            
        Returns:
            True if sent successfully
        """
        try:
            response = self.ses_client.send_email(
                Source=self.sender_email,
                Destination={'ToAddresses': [recipient]},
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {
                        'Html': {'Data': body, 'Charset': 'UTF-8'}
                    }
                }
            )
            
            logger.info(f"Notification email sent to {recipient}: {response['MessageId']}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to send notification email: {e}")
            return False
