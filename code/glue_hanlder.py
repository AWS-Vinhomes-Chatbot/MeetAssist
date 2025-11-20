import json
import os
import boto3
from typing import Dict, Any

glue = boto3.client('glue')
CRAWLER_NAME = os.environ.get('CRAWLER_NAME', '')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Trigger Glue Crawler để scan S3 và update Glue Data Catalog
    
    Request: POST /crawler
    Response: {"message": "...", "crawler": "..."}
    """
    print(f"Event: {json.dumps(event)}")
    print(f"Crawler name: {CRAWLER_NAME}")
    
    # TODO: Implement logic sau
    # 1. Check crawler state (READY/RUNNING/STOPPING)
    # 2. If READY -> start crawler
    # 3. If RUNNING -> return status
    
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json'
        },
        'body': json.dumps({
            'message': 'Glue Handler placeholder - logic chưa implement',
            'crawler': CRAWLER_NAME
        })
    }