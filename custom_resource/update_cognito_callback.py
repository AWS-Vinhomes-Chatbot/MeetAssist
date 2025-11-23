# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  */

"""
Custom Resource Lambda Handler
Updates Cognito User Pool Client callback URLs with CloudFront domain
"""

import json
import boto3
import urllib3
from typing import Dict, Any

cognito = boto3.client('cognito-idp')
http = urllib3.PoolManager()


def send_cfn_response(event: Dict[str, Any], context: Any, status: str, data: Dict = None) -> None:
    """Send response back to CloudFormation"""
    response_body = json.dumps({
        'Status': status,
        'Reason': f'See CloudWatch Log Stream: {context.log_stream_name}',
        'PhysicalResourceId': context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': data or {}
    })
    
    try:
        http.request(
            'PUT',
            event['ResponseURL'],
            body=response_body,
            headers={'Content-Type': 'application/json'}
        )
        print(f"✅ Successfully sent {status} response to CloudFormation")
    except Exception as e:
        print(f"❌ Failed to send response to CloudFormation: {str(e)}")


def handler(event: Dict[str, Any], context: Any) -> None:
    """
    Lambda handler for Custom Resource
    
    Automatically updates Cognito User Pool Client with CloudFront callback URLs
    after CloudFront distribution is created
    """
    print(f"Event: {json.dumps(event, indent=2)}")
    
    try:
        request_type = event['RequestType']
        
        if request_type in ['Create', 'Update']:
            # Extract properties
            props = event['ResourceProperties']
            user_pool_id = props['UserPoolId']
            client_id = props['ClientId']
            cloudfront_domain = props['CloudFrontDomain']
            
            print(f"Updating Cognito User Pool Client:")
            print(f"  User Pool ID: {user_pool_id}")
            print(f"  Client ID: {client_id}")
            print(f"  CloudFront Domain: {cloudfront_domain}")
            
            # Update Cognito User Pool Client
            response = cognito.update_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=client_id,
                CallbackURLs=[
                    f"https://{cloudfront_domain}/callback",
                    "http://localhost:5173/callback"  # Local development
                ],
                LogoutURLs=[
                    f"https://{cloudfront_domain}",
                    "http://localhost:5173"
                ],
                AllowedOAuthFlows=['code'],
                AllowedOAuthScopes=['openid', 'email', 'profile'],
                AllowedOAuthFlowsUserPoolClient=True,
                SupportedIdentityProviders=['COGNITO']
            )
            
            print(f"✅ Successfully updated Cognito User Pool Client")
            print(f"   Callback URLs: https://{cloudfront_domain}/, https://{cloudfront_domain}/callback")
            print(f"   Logout URLs: https://{cloudfront_domain}/, https://{cloudfront_domain}/logout")
            
            send_cfn_response(event, context, 'SUCCESS', {
                'CloudFrontDomain': cloudfront_domain,
                'Message': 'Cognito callback URLs updated successfully'
            })
            
        elif request_type == 'Delete':
            # No action needed on delete - Cognito will be deleted by CloudFormation
            print("Delete request - no action required")
            send_cfn_response(event, context, 'SUCCESS', {
                'Message': 'Delete completed - no action taken'
            })
        else:
            raise ValueError(f"Unsupported request type: {request_type}")
            
    except Exception as e:
        error_msg = f"❌ Error processing request: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        send_cfn_response(event, context, 'FAILED')
