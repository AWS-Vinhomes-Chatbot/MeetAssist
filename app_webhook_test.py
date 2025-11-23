#!/usr/bin/env python3

# Test app for deploying serverless Webhook stack
# Usage: cdk deploy -a "python app_webhook_test.py" WebhookTestStack

import aws_cdk as cdk
from cdk_rds_pg_memdb_text_to_sql.Webhook_stack import UserMessengerBedrockStack

app = cdk.App()
env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "ap-southeast-1"
)

# Serverless Webhook stack - no VPC/RDS dependencies
webhook_test_stack = UserMessengerBedrockStack(
    app,
    "WebhookTestStack",
    env=env,
    description="Serverless Messenger Webhook integration with Cognito and DynamoDB"
)

app.synth()
