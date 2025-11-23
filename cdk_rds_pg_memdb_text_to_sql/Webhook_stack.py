import os
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    BundlingOptions,
    aws_apigateway as apigw,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_secretsmanager as sm,
    aws_ssm as ssm,
    aws_dynamodb as dynamodb,
    aws_logs as logs,
)
from constructs import Construct

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
        )

        # 2) Input Parameters
        fb_app_id_param = ssm.StringParameter.from_string_parameter_name(
            self, "FbAppIdParam", string_parameter_name="/meetassist/facebook/app_id"
        )
        fb_app_secret_param = ssm.StringParameter.from_string_parameter_name(
            self, "FbAppSecretParam", string_parameter_name="/meetassist/facebook/app_secret"
        )
        fb_page_token_secret = sm.Secret.from_secret_name_v2(
            self, "FacebookPageToken", "meetassist/facebook/page_token"
        )

        # 3) IAM Role
        lambda_role = iam.Role(
            self, "WebhookLambdaRole",
            role_name="MessengerWebhookLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )

        fb_app_id_param.grant_read(lambda_role)
        fb_app_secret_param.grant_read(lambda_role)
        fb_page_token_secret.grant_read(lambda_role)
        session_table.grant_read_write_data(lambda_role)
        
        # SES permissions for sending OTP emails
        lambda_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["ses:SendEmail", "ses:SendRawEmail"],
            resources=["*"],  # Can be restricted to specific verified email identities
        ))

        # 4) Lambda Function
        webhook_receiver = lambda_.Function(
            self, "WebhookFunction",
            function_name="MessengerWebhookHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="webhook_handler.lambda_handler",
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
            role=lambda_role,
            timeout=Duration.seconds(30),
            memory_size=1024,
            environment={
                "FB_APP_ID_PARAM": fb_app_id_param.parameter_name,
                "FB_APP_SECRET_PARAM": fb_app_secret_param.parameter_name,
                "FB_PAGE_TOKEN_SECRET_ARN": fb_page_token_secret.secret_arn,
                "SESSION_TABLE_NAME": session_table.table_name
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # 5) API Gateway
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

        # 6) API Resources
        webhook_resource = messenger_api.root.add_resource("webhook")
        webhook_resource.add_method("POST", apigw.LambdaIntegration(webhook_receiver, proxy=True))
        webhook_resource.add_method("GET", apigw.LambdaIntegration(webhook_receiver, proxy=True))

        callback_resource = messenger_api.root.add_resource("callback")
        callback_resource.add_method("GET", apigw.LambdaIntegration(webhook_receiver, proxy=True))

        # Outputs
        CfnOutput(self, "WebhookUrl", value=f"{messenger_api.url}webhook")
        CfnOutput(self, "SessionTableName", value=session_table.table_name, description="DynamoDB Session Table")