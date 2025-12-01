"""
Custom Resource Lambda to generate config.json for frontend.
Reads API endpoint from SSM Parameter Store and uploads config to S3.
"""

import json
import boto3
import cfnresponse


def handler(event, context):
    """
    CloudFormation Custom Resource handler.
    Creates config.json with Cognito + API Gateway configuration.
    """
    try:
        print(f"Event: {json.dumps(event)}")
        
        if event['RequestType'] == 'Delete':
            print("Delete request - no action needed")
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            return
        
        props = event['ResourceProperties']
        ssm = boto3.client('ssm')
        s3 = boto3.client('s3')
        
        # Read API endpoint from SSM Parameter Store
        # May not exist on first deployment
        try:
            ssm_param = props['SsmApiEndpoint']
            print(f"Reading SSM parameter: {ssm_param}")
            api_endpoint = ssm.get_parameter(Name=ssm_param)['Parameter']['Value']
            # Remove trailing slash for consistency
            api_endpoint = api_endpoint.rstrip('/')
            print(f"API endpoint from SSM: {api_endpoint}")
        except ssm.exceptions.ParameterNotFound:
            print("SSM parameter not found - using placeholder")
            api_endpoint = "https://placeholder.execute-api.ap-southeast-1.amazonaws.com/prod"
        except Exception as e:
            print(f"Error reading SSM: {e}")
            api_endpoint = "https://placeholder.execute-api.ap-southeast-1.amazonaws.com/prod"
        
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
        
        # Return config as output data
        response_data = {
            "ConfigJson": json.dumps(config),
            "S3Location": f"s3://{bucket_name}/config.json"
        }
        
        cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
        
    except Exception as e:
        error_msg = f"Error generating config.json: {str(e)}"
        print(error_msg)
        import traceback
        print(traceback.format_exc())
        cfnresponse.send(event, context, cfnresponse.FAILED, {"Error": error_msg})
