import os
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    BundlingOptions,
    aws_apigateway as apigw,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_event_sources,
    aws_iam as iam,
    aws_secretsmanager as sm,
    aws_ssm as ssm,
    aws_dynamodb as dynamodb,
    aws_logs as logs,
    aws_sqs as sqs,
)
from constructs import Construct
from cdk_nag import NagSuppressions

class UserMessengerBedrockStack(Stack):
    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "code"
        )

        # 1) DynamoDB session table
        session_table = dynamodb.Table(
            self, "SessionTable",
            partition_key=dynamodb.Attribute(name="psid", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True,
            time_to_live_attribute="ttl",  # Auto-delete sessions after 1h
        )

        # 2) SQS FIFO Queue for message deduplication and async processing
        # FIFO ensures:
        # - Deduplication: Same message_id within 5 min won't be processed twice
        # - Ordering: Messages from same user (MessageGroupId) processed in order
        message_queue = sqs.Queue(
            self, "MessageQueue",
            queue_name="meetassist-messages.fifo",  # .fifo suffix required for FIFO
            fifo=True,
            content_based_deduplication=False,  # We use explicit MessageDeduplicationId
            visibility_timeout=Duration.seconds(180),  # Should be > Lambda timeout (120s + buffer)
            retention_period=Duration.hours(4),  # Messages older than 4h are deleted
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,  # After 3 failures, move to DLQ
                queue=sqs.Queue(
                    self, "MessageDLQ",
                    queue_name="meetassist-messages-dlq.fifo",
                    fifo=True,
                    retention_period=Duration.days(7),
                )
            )
        )

        # 3) Input Parameters
        fb_app_id_param = ssm.StringParameter.from_string_parameter_name(
            self, "FbAppIdParam", string_parameter_name="/meetassist/facebook/app_id"
        )
        fb_app_secret_param = ssm.StringParameter.from_string_parameter_name(
            self, "FbAppSecretParam", string_parameter_name="/meetassist/facebook/app_secret"
        )
        fb_page_token_secret = sm.Secret.from_secret_name_v2(
            self, "FacebookPageToken", "meetassist/facebook/page_token"
        )
        fb_verify_token = sm.Secret.from_secret_name_v2(
            self, "FacebookVerifyToken", "/meetassist/facebook/verify_token"
        )
        # 4) IAM Role for Webhook Receiver (lightweight - just pushes to SQS)
        webhook_receiver_role = iam.Role(
            self, "WebhookReceiverRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )
        fb_app_secret_param.grant_read(webhook_receiver_role)
        fb_verify_token.grant_read(webhook_receiver_role)  # Grant access to verify token secret
        message_queue.grant_send_messages(webhook_receiver_role)

        # 5) IAM Role for Chat Processor (heavier - processes messages)
        processor_role = iam.Role(
            self, "ProcessorLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )
        fb_app_id_param.grant_read(processor_role)
        fb_app_secret_param.grant_read(processor_role)
        fb_page_token_secret.grant_read(processor_role)
        session_table.grant_read_write_data(processor_role)
        message_queue.grant_consume_messages(processor_role)
        
        # SES permissions for sending OTP emails
        processor_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["ses:SendEmail", "ses:SendRawEmail"],
            resources=["*"],
        ))

        # 6) Lambda Function - Webhook Receiver (lightweight, fast response)
        webhook_receiver = lambda_.Function(
            self, "WebhookReceiverFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="webhook_receiver.lambda_handler",
            code=lambda_.Code.from_asset(
                asset_path,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install --platform manylinux2014_x86_64 "
                        "--target /asset-output --implementation cp "
                        "--python-version 3.12 --only-binary=:all: "
                        "--upgrade boto3 && "
                        "cp -r . /asset-output",
                    ],
                ),
            ),
            role=webhook_receiver_role,
            timeout=Duration.seconds(10),  # Fast timeout - just push to SQS
            memory_size=256,  # Lightweight
            environment={
                "MESSAGE_QUEUE_URL": message_queue.queue_url,
                "FB_APP_SECRET_PARAM": fb_app_secret_param.parameter_name,
                "FB_VERIFY_TOKEN_SECRET": "/meetassist/facebook/verify_token",
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # 7) Lambda Function - Chat Processor (triggered by SQS)
        chat_processor = lambda_.Function(
            self, "WebhookFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="chat_handler.lambda_handler",
            code=lambda_.Code.from_asset(
                asset_path,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install --platform manylinux2014_x86_64 "
                        "--target /asset-output --implementation cp "
                        "--python-version 3.12 --only-binary=:all: "
                        "--upgrade -r requirements.txt && "
                        "cp -r . /asset-output",
                    ],
                ),
            ),
            role=processor_role,
            timeout=Duration.seconds(120),  # Increased for Bedrock retry handling
            memory_size=1024,
            environment={
                "FB_APP_ID_PARAM": fb_app_id_param.parameter_name,
                "FB_APP_SECRET_PARAM": fb_app_secret_param.parameter_name,
                "FB_PAGE_TOKEN_SECRET_ARN": fb_page_token_secret.secret_arn,
                "SESSION_TABLE_NAME": session_table.table_name,
                "TEXT2SQL_LAMBDA_NAME": "AppStack-TextToSQLFunction",
                "BEDROCK_REGION": "ap-northeast-1",  # Tokyo region for lowest latency
                "BEDROCK_EMBED_REGION": "ap-northeast-1",
                "SES_REGION": "ap-northeast-1",
                "CACHE_SIMILARITY_THRESHOLD": "0.8",
                "MAX_CONTEXT_TURNS": "3",
                "BEDROCK_MODEL_ID": "anthropic.claude-3-haiku-20240307-v1:0",  # Claude 3 Haiku - fast for general tasks
                "BEDROCK_SONNET_MODEL_ID": "anthropic.claude-3-5-sonnet-20240620-v1:0",  # Claude 3.5 Sonnet - on-demand in Tokyo
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        
        # 8) Add SQS trigger to Chat Processor
        chat_processor.add_event_source(
            lambda_event_sources.SqsEventSource(
                message_queue,
                batch_size=1,  # Process one message at a time for FIFO ordering
                report_batch_item_failures=True,  # Enable partial batch failure
            )
        )
        
        # Add Bedrock permissions - Using Claude 3 Haiku and 3.5 Sonnet in Tokyo region
        processor_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["bedrock:InvokeModel"],
            resources=[
                # Claude 3 Haiku - stable and fast for general tasks
                f"arn:aws:bedrock:ap-northeast-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
                # Claude 3.5 Sonnet - more accurate for extraction tasks, on-demand in Tokyo
                f"arn:aws:bedrock:ap-northeast-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0",
                # Amazon Titan Text Embeddings V2 (supports multilingual)
                f"arn:aws:bedrock:ap-northeast-1::foundation-model/amazon.titan-embed-text-v2:0"
            ],
        ))
        
        # Add Lambda invoke permissions for text2sql
        processor_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["lambda:InvokeFunction"],
            resources=[f"arn:aws:lambda:ap-northeast-1:*:function:AppStack-TextToSQLFunction"],
        ))

        # 9) API Gateway
        messenger_api = apigw.RestApi(
            self, "MessengerApi",
            rest_api_name="MessengerWebhookApi",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                metrics_enabled=True,
                throttling_rate_limit=10,
                throttling_burst_limit=5,
            ),
            endpoint_types=[apigw.EndpointType.REGIONAL],
        )

        # 10) API Resources - Webhook receiver handles API Gateway requests
        webhook_resource = messenger_api.root.add_resource("webhook")
        webhook_resource.add_method("POST", apigw.LambdaIntegration(webhook_receiver, proxy=True))
        webhook_resource.add_method("GET", apigw.LambdaIntegration(webhook_receiver, proxy=True))

        callback_resource = messenger_api.root.add_resource("callback")
        callback_resource.add_method("GET", apigw.LambdaIntegration(chat_processor, proxy=True))  # Callback still goes to processor

        # Outputs
        CfnOutput(self, "WebhookUrl", value=f"{messenger_api.url}webhook")
        CfnOutput(self, "SessionTableName", value=session_table.table_name, description="DynamoDB Session Table")
        CfnOutput(self, "MessageQueueUrl", value=message_queue.queue_url, description="SQS FIFO Queue URL")
        
        # Suppress cdk-nag warnings for this stack (development/testing purposes)
        NagSuppressions.add_stack_suppressions(self, [
            {"id": "AwsSolutions-IAM4", "reason": "AWS managed policies are acceptable for this Lambda function"},
            {"id": "AwsSolutions-IAM5", "reason": "Wildcard permissions needed for SES and Lambda invoke"},
            {"id": "AwsSolutions-L1", "reason": "Python 3.12 is acceptable runtime version"},
            {"id": "AwsSolutions-APIG1", "reason": "Access logging not required for development"},
            {"id": "AwsSolutions-APIG2", "reason": "Request validation handled in Lambda"},
            {"id": "AwsSolutions-APIG3", "reason": "WAF not required for development"},
            {"id": "AwsSolutions-APIG4", "reason": "Facebook webhook does not support IAM/Cognito auth"},
            {"id": "AwsSolutions-APIG6", "reason": "CloudWatch logging not required for development"},
            {"id": "AwsSolutions-COG4", "reason": "Cognito not used - Facebook handles authentication"},
            {"id": "AwsSolutions-SQS3", "reason": "DLQ is configured for the main queue"},
            {"id": "AwsSolutions-SQS4", "reason": "SSL enforcement not required for internal Lambda-to-SQS communication"},
        ])