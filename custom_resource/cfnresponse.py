# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from __future__ import print_function
import urllib3
import json

SUCCESS = "SUCCESS"
FAILED = "FAILED"

http = urllib3.PoolManager()


def send(event, context, responseStatus, responseData, physicalResourceId=None, noEcho=False, reason=None):
    """
    Send a response to CloudFormation for a Custom Resource.
    
    Args:
        event: Lambda event from CloudFormation
        context: Lambda context object
        responseStatus: SUCCESS or FAILED
        responseData: Dictionary of data to return
        physicalResourceId: Optional physical resource ID
        noEcho: Whether to mask outputs in CloudFormation logs
        reason: Optional reason for failure
    """
    responseUrl = event['ResponseURL']

    print(f"Event: {json.dumps(event)}")

    responseBody = {
        'Status': responseStatus,
        'Reason': reason or f'See the details in CloudWatch Log Stream: {context.log_stream_name}',
        'PhysicalResourceId': physicalResourceId or context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'NoEcho': noEcho,
        'Data': responseData
    }

    json_responseBody = json.dumps(responseBody)

    print(f"Response body:\n{json_responseBody}")

    headers = {
        'content-type': '',
        'content-length': str(len(json_responseBody))
    }

    try:
        response = http.request('PUT', responseUrl, headers=headers, body=json_responseBody)
        print(f"Status code: {response.status}")
        print(f"S3 Request id: {response.headers.get('x-amz-request-id', 'N/A')}")
        print(f"S3 Request id 2 / host id: {response.headers.get('x-amz-id-2', 'N/A')}")
    except Exception as e:
        print(f"send(..) failed executing http.request(..):{e}")
