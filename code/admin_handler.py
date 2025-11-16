import json
import os

print("Handler loading - Đây là file placeholder cho AdminManager (TRONG VPC)")

def lambda_handler(event, context):
    """
    Đây là file placeholder cho hạ tầng CDK.
    Sau này bạn sẽ thêm logic query Athena (qua VPC Endpoint) và Postgres vào đây.
    """
    print(f"Event received: {json.dumps(event)}")

    # Trả về một thông báo thành công đơn giản
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization'
        },
        'body': json.dumps({
            "message": "AdminManager (VPC) placeholder is working!"
        })
    }