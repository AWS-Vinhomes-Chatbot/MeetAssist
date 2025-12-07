# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  */

import os

from aws_cdk import (
    aws_iam as iam,
    aws_s3 as s3,
    aws_ec2 as ec2,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_secretsmanager as sm,
    aws_rds as rds,
    aws_logs as logs,
    aws_events as events,
    aws_events_targets as targets,
    aws_cognito as cognito,
    Stack,
    Duration,
    BundlingOptions,
    CfnOutput,
)
from constructs import Construct


class DashboardStack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        security_group: ec2.ISecurityGroup,
        data_stored_bucket: s3.IBucket,
        readonly_secret: sm.ISecret,
        rds_instance: rds.IDatabaseInstance,
        user_pool: cognito.IUserPool,
        consultant_user_pool: cognito.IUserPool = None,  # Consultant User Pool for account management
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, description="Admin Dashboard for managing career counseling data", **kwargs)

        lambda_code_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "code"
        )

        # ==================== ARCHIVE DATA LAMBDA ====================
        # Khi deploy lại project, index.py sẽ đọc data từ S3 và restore vào RDS
        archive_lambda_role = iam.Role(
            self,
            "ArchiveDataRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ],
        )

        archive_lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[readonly_secret.secret_arn],
            )
        )

        archive_lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
                resources=[
                    data_stored_bucket.bucket_arn,
                    f"{data_stored_bucket.bucket_arn}/*",
                ],
            )
        )

        archive_data_lambda = lambda_.Function(
            self,
            "ArchiveData",
            function_name="DashboardStack-ArchiveData",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="archive_handler.lambda_handler",
            role=archive_lambda_role,
            code=lambda_.Code.from_asset(
                lambda_code_path,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --platform manylinux2014_x86_64 --target /asset-output "
                        + "--implementation cp --python-version 3.12 --only-binary=:all: "
                        + "--upgrade -r requirements.txt && cp -r . /asset-output",
                    ],
                ),
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[security_group],
            timeout=Duration.minutes(15),
            memory_size=1024,
            log_retention=logs.RetentionDays.ONE_WEEK,
            # Removed reserved_concurrent_executions to avoid account limit issues
            environment={
                "SECRET_NAME": readonly_secret.secret_name,
                "RDS_HOST": rds_instance.db_instance_endpoint_address,
                "RDS_PORT": str(rds_instance.db_instance_endpoint_port),
                "RDS_DATABASE": "postgres",
                "BUCKET_NAME": data_stored_bucket.bucket_name,
                "DATA_PREFIX": "data",
            },
        )

        # ==================== EVENTBRIDGE SCHEDULE RULE ====================
        # Trigger ArchiveData Lambda every 5 minutes to sync RDS data to S3
        # Using schedule-based trigger instead of event-based to avoid VPC endpoint requirement
        # NOTE: Rule is DISABLED by default - enable manually when ready for production:
        #       aws events enable-rule --name MeetAssist-ArchiveSchedule
        archive_schedule_rule = events.Rule(
            self,
            "ArchiveScheduleRule",
            rule_name="MeetAssist-ArchiveSchedule",
            description="Trigger ArchiveData Lambda every 5 minutes to sync RDS data to S3",
            schedule=events.Schedule.rate(Duration.minutes(5)),
            enabled=False,  # Disabled by default - invoke manually for testing
        )

        archive_schedule_rule.add_target(
            targets.LambdaFunction(
                archive_data_lambda,
                retry_attempts=2,
                max_event_age=Duration.hours(1)
            )
        )

        archive_data_lambda.add_permission(
            "AllowEventBridgeInvoke",
            principal=iam.ServicePrincipal("events.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=archive_schedule_rule.rule_arn,
        )

        # ==================== ADMIN MANAGER LAMBDA ====================
        admin_lambda_role = iam.Role(
            self,
            "AdminManagerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ],
        )

        admin_lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[rds_instance.secret.secret_arn],
            )
        )

        admin_lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["rds-db:connect"],
                resources=[
                    f"arn:aws:rds-db:{Stack.of(self).region}:{Stack.of(self).account}:dbuser:*/*"
                ],
            )
        )

        # Cognito permissions for consultant account management
        if consultant_user_pool:
            admin_lambda_role.add_to_policy(
                iam.PolicyStatement(
                    actions=[
                        "cognito-idp:AdminCreateUser",
                        "cognito-idp:AdminSetUserPassword",
                        "cognito-idp:AdminUpdateUserAttributes",
                        "cognito-idp:AdminDisableUser",
                        "cognito-idp:AdminEnableUser",
                        "cognito-idp:AdminDeleteUser",
                        "cognito-idp:AdminGetUser",
                        "cognito-idp:ListUsers",
                    ],
                    resources=[consultant_user_pool.user_pool_arn],
                )
            )

        admin_manager_lambda = lambda_.Function(
            self,
            "AdminManager",
            function_name="DashboardStack-AdminManager",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="dashboard_handler.lambda_handler",
            role=admin_lambda_role,
            code=lambda_.Code.from_asset(
                lambda_code_path,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --platform manylinux2014_x86_64 --target /asset-output "
                        + "--implementation cp --python-version 3.12 --only-binary=:all: "
                        + "--upgrade -r requirements.txt && cp -r . /asset-output",
                    ],
                ),
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[security_group],
            memory_size=1024,
            timeout=Duration.minutes(5),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "SECRET_NAME": rds_instance.secret.secret_name,
                "RDS_HOST": rds_instance.db_instance_endpoint_address,
                "RDS_PORT": str(rds_instance.db_instance_endpoint_port),
                "RDS_DATABASE": "postgres",
                "CONSULTANT_USER_POOL_ID": consultant_user_pool.user_pool_id if consultant_user_pool else "",
            },
        )

        # ==================== API GATEWAY ====================
        admin_api = apigw.RestApi(
            self,
            "AdminApi",
            rest_api_name="MeetAssistAdminApi",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,  # Allow all origins for now
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=[
                    "Content-Type",
                    "Authorization",
                    "X-Amz-Date",
                    "X-Api-Key",
                    "X-Amz-Security-Token",
                ],
                max_age=Duration.hours(1),
            ),
            deploy_options=apigw.StageOptions(
                throttling_rate_limit=100,
                throttling_burst_limit=200,
                # Tắt logging để tránh lỗi CloudWatch Logs role
                # logging_level=apigw.MethodLoggingLevel.INFO,
            ),
        )

        # Include both Admin and Consultant User Pools in authorizer
        # so both types of users can call the API
        cognito_pools = [user_pool]
        if consultant_user_pool:
            cognito_pools.append(consultant_user_pool)
            
        authorizer = apigw.CognitoUserPoolsAuthorizer(
            self, "AdminApiAuthorizer", cognito_user_pools=cognito_pools
        )

        # ==================== EMAIL NOTIFICATION LAMBDA (OUTSIDE VPC) ====================
        # This Lambda sends email notifications via SES
        # Deployed OUTSIDE VPC to avoid NAT Gateway/VPC Endpoint costs
        # Frontend calls this after AdminManager confirms appointment
        
        email_lambda_role = iam.Role(
            self,
            "EmailNotificationRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # SES permissions
        email_lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=["*"],
            )
        )

        email_notification_lambda = lambda_.Function(
            self,
            "EmailNotification",
            function_name="DashboardStack-EmailNotification",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="notification_handler.lambda_handler",
            role=email_lambda_role,
            code=lambda_.Code.from_asset(
                lambda_code_path,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --platform manylinux2014_x86_64 --target /asset-output "
                        + "--implementation cp --python-version 3.12 --only-binary=:all: "
                        + "--upgrade -r requirements.txt && cp -r . /asset-output",
                    ],
                ),
            ),
            # NO VPC configuration - can directly access SES
            memory_size=512,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "SENDER_EMAIL": "pqa1085@gmail.com",  # Update with your verified SES email
            },
        )

        admin_resource = admin_api.root.add_resource("admin")

        # ENDPOINT 1: POST /admin/execute-sql
        sql_execute_resource = admin_resource.add_resource("execute-sql")
        sql_execute_resource.add_method(
            "POST",
            apigw.LambdaIntegration(admin_manager_lambda),
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer,
        )
        
        # ENDPOINT 2: POST /admin/send-email (Email Notification)
        # Called by frontend after appointment confirmation
        # NO authorization required - frontend already authenticated to call confirm
        send_email_resource = admin_resource.add_resource("send-email")
        send_email_resource.add_method(
            "POST",
            apigw.LambdaIntegration(email_notification_lambda),
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer,
        )

        # ==================== OUTPUTS ====================
        CfnOutput(
            self,
            "AdminApiEndpoint",
            value=admin_api.url,
            description="API Gateway endpoint for Admin Backend",
        )

        CfnOutput(
            self,
            "ArchiveLambdaName",
            value=archive_data_lambda.function_name,
            description="Archive Lambda function name (RDS -> S3 backup)",
        )

        CfnOutput(
            self,
            "ArchiveScheduleRuleOutput",
            value=archive_schedule_rule.rule_name,
            description="EventBridge Schedule Rule (every 5 minutes)",
        )

        CfnOutput(
            self,
            "AdminManagerLambdaName",
            value=admin_manager_lambda.function_name,
            description="Admin Manager Lambda function name (CRUD operations)",
        )
        
        CfnOutput(
            self,
            "EmailNotificationLambdaName",
            value=email_notification_lambda.function_name,
            description="Email Notification Lambda function name (SES - outside VPC)",
        )
        
        # Export API endpoint for other stacks to use
        self.api_endpoint = admin_api.url
