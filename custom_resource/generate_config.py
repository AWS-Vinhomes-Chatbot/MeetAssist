"""
Custom Resource Lambda to generate config.json for frontend (sử dụng với cr.Provider)
Nhận API endpoint trực tiếp từ properties, upload config lên S3.

Khi dùng cr.Provider, Lambda chỉ cần return dict,
Provider sẽ tự động xử lý việc gửi response về CloudFormation.
"""

import json
import boto3


def handler(event, context):
    """
    CloudFormation Custom Resource handler (với cr.Provider)
    Creates config.json with Cognito + API Gateway configuration.
    
    Khi dùng cr.Provider:
    - Không cần gọi cfnresponse.send()
    - Chỉ cần return dict với PhysicalResourceId và Data
    - Nếu throw exception, Provider sẽ tự động báo FAILED
    
    Returns:
        Dict với PhysicalResourceId và Data
    """
    print(f"Event: {json.dumps(event)}")
    
    if event['RequestType'] == 'Delete':
        print("Delete request - no action needed")
        return {
            "PhysicalResourceId": "config-generator",
            "Data": {"Message": "Delete completed"}
        }
    
    props = event['ResourceProperties']
    s3 = boto3.client('s3')
    
    # API endpoint được truyền trực tiếp từ CDK
    api_endpoint = props.get('ApiEndpoint', 'https://placeholder.execute-api.ap-southeast-1.amazonaws.com/prod')
    api_endpoint = api_endpoint.rstrip('/')
    print(f"API endpoint: {api_endpoint}")
    
    # Build config object
    config = {
        "region": props['Region'],
        "cognitoUserPoolId": props['CognitoUserPoolId'],
        "cognitoClientId": props['CognitoClientId'],
        "cognitoDomain": props['CognitoDomain'],
        "cloudFrontUrl": props['CloudFrontUrl'],
        "apiEndpoint": api_endpoint
    }
    
    print(f"Generated config: {json.dumps(config, indent=2)}")
    
    # Upload config.json to S3 bucket
    bucket_name = props['BucketName']
    print(f"Uploading config.json to s3://{bucket_name}/config.json")
    
    s3.put_object(
        Bucket=bucket_name,
        Key='config.json',
        Body=json.dumps(config, indent=2),
        ContentType='application/json',
        CacheControl='no-cache, no-store, must-revalidate'
    )
    
    print("config.json uploaded successfully")
    
    # Chỉ cần return dict - Provider sẽ tự động gửi SUCCESS về CloudFormation
    return {
        "PhysicalResourceId": "config-generator",
        "Data": {
            "ConfigJson": json.dumps(config),
            "S3Location": f"s3://{bucket_name}/config.json"
        }
    }
