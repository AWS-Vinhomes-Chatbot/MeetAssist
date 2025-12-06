"""
Lambda to sync Consultants to Cognito User Pool (OUTSIDE VPC)

This Lambda runs outside VPC to access Cognito directly.
It fetches consultant list via API Gateway and creates Cognito users.

Triggered by:
- Manual invocation from Admin Dashboard
- API Gateway endpoint
"""

import json
import os
import secrets
import string
import boto3
from botocore.exceptions import ClientError

# Initialize clients
cognito = boto3.client('cognito-idp')

# Environment variables
CONSULTANT_USER_POOL_ID = os.environ.get('CONSULTANT_USER_POOL_ID')
API_ENDPOINT = os.environ.get('API_ENDPOINT')
DEFAULT_PASSWORD_LENGTH = 12


def generate_temp_password(length: int = DEFAULT_PASSWORD_LENGTH) -> str:
    """Generate a secure temporary password meeting Cognito requirements."""
    # Ensure password has required character types
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*"
    
    # Ensure at least one of each required type
    password = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    
    # Fill remaining length with random chars
    all_chars = lowercase + uppercase + digits + symbols
    password.extend(secrets.choice(all_chars) for _ in range(length - 4))
    
    # Shuffle the password
    password_list = list(password)
    secrets.SystemRandom().shuffle(password_list)
    
    return ''.join(password_list)


def create_cognito_user(email: str, consultant_id: int, send_invite: bool = True) -> dict:
    """
    Create a Cognito user for consultant.
    
    Args:
        email: Consultant's email (used as username)
        consultant_id: Consultant ID from database
        send_invite: Whether to send email invitation
        
    Returns:
        Dict with success status and user info
    """
    try:
        # Check if user already exists
        try:
            existing = cognito.admin_get_user(
                UserPoolId=CONSULTANT_USER_POOL_ID,
                Username=email
            )
            # User exists, update consultant_id attribute if needed
            cognito.admin_update_user_attributes(
                UserPoolId=CONSULTANT_USER_POOL_ID,
                Username=email,
                UserAttributes=[
                    {'Name': 'custom:consultant_id', 'Value': str(consultant_id)}
                ]
            )
            return {
                'success': True,
                'message': f'User {email} already exists, updated consultant_id',
                'user_status': existing.get('UserStatus'),
                'action': 'updated'
            }
        except cognito.exceptions.UserNotFoundException:
            pass  # User doesn't exist, create new
        
        # Generate temporary password
        temp_password = generate_temp_password()
        
        # Create user with email as username
        message_action = 'SUPPRESS' if not send_invite else None
        
        create_params = {
            'UserPoolId': CONSULTANT_USER_POOL_ID,
            'Username': email,
            'UserAttributes': [
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'},
                {'Name': 'custom:consultant_id', 'Value': str(consultant_id)}
            ],
            'TemporaryPassword': temp_password,
            'DesiredDeliveryMediums': ['EMAIL'] if send_invite else []
        }
        
        if not send_invite:
            create_params['MessageAction'] = 'SUPPRESS'
        
        response = cognito.admin_create_user(**create_params)
        
        return {
            'success': True,
            'message': f'User {email} created successfully',
            'user_status': response['User']['UserStatus'],
            'temp_password': temp_password if not send_invite else None,
            'action': 'created'
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        return {
            'success': False,
            'error': f'{error_code}: {error_msg}',
            'email': email
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'email': email
        }


def delete_cognito_user(email: str) -> dict:
    """Delete a Cognito user."""
    try:
        cognito.admin_delete_user(
            UserPoolId=CONSULTANT_USER_POOL_ID,
            Username=email
        )
        return {'success': True, 'message': f'User {email} deleted'}
    except cognito.exceptions.UserNotFoundException:
        return {'success': True, 'message': f'User {email} not found (already deleted)'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def disable_cognito_user(email: str) -> dict:
    """Disable a Cognito user (when consultant is disabled in DB)."""
    try:
        cognito.admin_disable_user(
            UserPoolId=CONSULTANT_USER_POOL_ID,
            Username=email
        )
        return {'success': True, 'message': f'User {email} disabled'}
    except cognito.exceptions.UserNotFoundException:
        return {'success': False, 'error': f'User {email} not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def enable_cognito_user(email: str) -> dict:
    """Enable a Cognito user."""
    try:
        cognito.admin_enable_user(
            UserPoolId=CONSULTANT_USER_POOL_ID,
            Username=email
        )
        return {'success': True, 'message': f'User {email} enabled'}
    except cognito.exceptions.UserNotFoundException:
        return {'success': False, 'error': f'User {email} not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def reset_user_password(email: str, send_invite: bool = True) -> dict:
    """Reset user password and optionally send new invite."""
    try:
        temp_password = generate_temp_password()
        
        cognito.admin_set_user_password(
            UserPoolId=CONSULTANT_USER_POOL_ID,
            Username=email,
            Password=temp_password,
            Permanent=False  # User must change on next login
        )
        
        return {
            'success': True,
            'message': f'Password reset for {email}',
            'temp_password': temp_password if not send_invite else None
        }
    except cognito.exceptions.UserNotFoundException:
        return {'success': False, 'error': f'User {email} not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def list_cognito_users() -> dict:
    """List all users in Consultant User Pool."""
    try:
        users = []
        pagination_token = None
        
        while True:
            params = {
                'UserPoolId': CONSULTANT_USER_POOL_ID,
                'Limit': 60
            }
            if pagination_token:
                params['PaginationToken'] = pagination_token
                
            response = cognito.list_users(**params)
            
            for user in response.get('Users', []):
                attrs = {attr['Name']: attr['Value'] for attr in user.get('Attributes', [])}
                users.append({
                    'username': user['Username'],
                    'email': attrs.get('email'),
                    'consultant_id': attrs.get('custom:consultant_id'),
                    'status': user['UserStatus'],
                    'enabled': user['Enabled'],
                    'created': user['UserCreateDate'].isoformat() if user.get('UserCreateDate') else None
                })
            
            pagination_token = response.get('PaginationToken')
            if not pagination_token:
                break
        
        return {'success': True, 'users': users, 'count': len(users)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def lambda_handler(event, context):
    """
    Lambda handler for Consultant Cognito management.
    
    Supported actions:
    - create_user: Create single Cognito user
    - delete_user: Delete Cognito user
    - disable_user: Disable Cognito user
    - enable_user: Enable Cognito user
    - reset_password: Reset user password
    - list_users: List all Cognito users
    - sync_consultant: Sync single consultant (create/update)
    
    Request body:
    {
        "action": "create_user",
        "email": "consultant@example.com",
        "consultant_id": 123,
        "send_invite": true
    }
    """
    print(f"Event: {json.dumps(event)}")
    
    # Parse request
    body = event.get('body', {})
    if isinstance(body, str):
        body = json.loads(body)
    
    action = body.get('action')
    
    if not action:
        return response(400, {'error': "Missing 'action' in request"})
    
    if not CONSULTANT_USER_POOL_ID:
        return response(500, {'error': 'CONSULTANT_USER_POOL_ID not configured'})
    
    # Route actions
    try:
        if action == 'create_user' or action == 'sync_consultant':
            email = body.get('email')
            consultant_id = body.get('consultant_id')
            send_invite = body.get('send_invite', True)
            
            if not email or not consultant_id:
                return response(400, {'error': 'Missing email or consultant_id'})
            
            result = create_cognito_user(email, consultant_id, send_invite)
            return response(200 if result['success'] else 400, result)
        
        elif action == 'delete_user':
            email = body.get('email')
            if not email:
                return response(400, {'error': 'Missing email'})
            
            result = delete_cognito_user(email)
            return response(200 if result['success'] else 400, result)
        
        elif action == 'disable_user':
            email = body.get('email')
            if not email:
                return response(400, {'error': 'Missing email'})
            
            result = disable_cognito_user(email)
            return response(200 if result['success'] else 400, result)
        
        elif action == 'enable_user':
            email = body.get('email')
            if not email:
                return response(400, {'error': 'Missing email'})
            
            result = enable_cognito_user(email)
            return response(200 if result['success'] else 400, result)
        
        elif action == 'reset_password':
            email = body.get('email')
            send_invite = body.get('send_invite', False)
            if not email:
                return response(400, {'error': 'Missing email'})
            
            result = reset_user_password(email, send_invite)
            return response(200 if result['success'] else 400, result)
        
        elif action == 'list_users':
            result = list_cognito_users()
            return response(200 if result['success'] else 500, result)
        
        else:
            return response(400, {'error': f'Unknown action: {action}'})
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return response(500, {'error': str(e)})


def response(status_code: int, body: dict) -> dict:
    """Build API Gateway response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'POST,OPTIONS'
        },
        'body': json.dumps(body, default=str)
    }
