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
    aws_glue as glue,
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
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        lambda_code_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "code"
        )

        # ==================== GLUE DATABASE (COMMENT - CHƯA CẦN) ====================
        # glue_database = glue.CfnDatabase(
        #     self,
        #     "HistoryDatabase",
        #     catalog_id=Stack.of(self).account,
        #     database_input=glue.CfnDatabase.DatabaseInputProperty(
        #         name="meetassist_history",
        #         description="Historical data from MeetAssist RDS",
        #     ),
        # )

        # ==================== ARCHIVE DATA LAMBDA (COMMENT - CHƯA CẦN TEST) ====================
        # archive_lambda_role = iam.Role(
        #     self,
        #     "ArchiveDataRole",
        #     assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        #     managed_policies=[
        #         iam.ManagedPolicy.from_aws_managed_policy_name(
        #             "service-role/AWSLambdaVPCAccessExecutionRole"
        #         )
        #     ],
        # )

        # archive_lambda_role.add_to_policy(
        #     iam.PolicyStatement(
        #         actions=["secretsmanager:GetSecretValue"],
        #         resources=[readonly_secret.secret_arn],
        #     )
        # )

        # archive_lambda_role.add_to_policy(
        #     iam.PolicyStatement(
        #         actions=["s3:PutObject"],
        #         resources=[
        #             f"{data_stored_bucket.bucket_arn}/appointments/*",
        #             f"{data_stored_bucket.bucket_arn}/enrollments/*",
        #             f"{data_stored_bucket.bucket_arn}/program_attendees/*",
        #         ],
        #     )
        # )

        # archive_data_lambda = lambda_.Function(
        #     self,
        #     "ArchiveData",
        #     function_name="DashboardStack-ArchiveData",
        #     runtime=lambda_.Runtime.PYTHON_3_12,
        #     handler="archive_handler.lambda_handler",
        #     role=archive_lambda_role,
        #     code=lambda_.Code.from_asset(
        #         os.path.join(lambda_code_path, "archive_handler"),
        #         bundling=BundlingOptions(
        #             image=lambda_.Runtime.PYTHON_3_12.bundling_image,
        #             command=[
        #                 "bash",
        #                 "-c",
        #                 "pip install --platform manylinux2014_x86_64 --target /asset-output "
        #                 + "--implementation cp --python-version 3.12 --only-binary=:all: "
        #                 + "--upgrade -r requirements.txt && cp -r . /asset-output",
        #             ],
        #         ),
        #     ),
        #     vpc=vpc,
        #     vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
        #     security_groups=[security_group],
        #     timeout=Duration.minutes(15),
        #     memory_size=1024,
        #     log_retention=logs.RetentionDays.ONE_WEEK,
        #     reserved_concurrent_executions=1,
        #     environment={
        #         "SECRET_NAME": readonly_secret.secret_name,
        #         "RDS_HOST": rds_instance.db_instance_endpoint_address,
        #         "RDS_PORT": str(rds_instance.db_instance_endpoint_port),
        #         "RDS_DATABASE": "postgres",
        #         "HISTORY_BUCKET_NAME": data_stored_bucket.bucket_name,
        #     },
        # )

        # ==================== EVENTBRIDGE (COMMENT - CHƯA CẦN TEST) ====================
        # archive_schedule = events.Rule(
        #     self,
        #     "DailyArchiveSchedule",
        #     schedule=events.Schedule.cron(
        #         minute="0", hour="2", month="*", week_day="*", year="*"
        #     ),
        #     description="Daily archive RDS data to S3 at 2 AM UTC",
        #     enabled=True,
        # )

        # archive_schedule.add_target(
        #     targets.LambdaFunction(
        #         archive_data_lambda, retry_attempts=2, max_event_age=Duration.hours(1)
        #     )
        # )

        # archive_data_lambda.add_permission(
        #     "AllowEventBridgeInvoke",
        #     principal=iam.ServicePrincipal("events.amazonaws.com"),
        #     action="lambda:InvokeFunction",
        #     source_arn=archive_schedule.rule_arn,
        # )

        # ==================== ANALYTIC LAMBDA (COMMENT - CHƯA CẦN TEST) ====================
        # analytic_lambda_role = iam.Role(
        #     self,
        #     "AnalyticHandlerRole",
        #     assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        #     managed_policies=[
        #         iam.ManagedPolicy.from_aws_managed_policy_name(
        #             "service-role/AWSLambdaBasicExecutionRole"
        #         )
        #     ],
        # )

        # analytic_lambda_role.add_to_policy(
        #     iam.PolicyStatement(
        #         actions=["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"],
        #         resources=[
        #             data_stored_bucket.bucket_arn,
        #             f"{data_stored_bucket.bucket_arn}/*",
        #         ],
        #     )
        # )

        # analytic_lambda_role.add_to_policy(
        #     iam.PolicyStatement(
        #         actions=["s3:PutObject", "s3:GetObject"],
        #         resources=[f"{data_stored_bucket.bucket_arn}/athena-results/*"],
        #     )
        # )

        # analytic_lambda_role.add_to_policy(
        #     iam.PolicyStatement(
        #         actions=[
        #             "athena:StartQueryExecution",
        #             "athena:GetQueryExecution",
        #             "athena:GetQueryResults",
        #             "athena:StopQueryExecution",
        #         ],
        #         resources=[
        #             f"arn:aws:athena:{Stack.of(self).region}:{Stack.of(self).account}:workgroup/primary"
        #         ],
        #     )
        # )

        # analytic_lambda_role.add_to_policy(
        #     iam.PolicyStatement(
        #         actions=[
        #             "glue:GetDatabase",
        #             "glue:CreateTable",
        #             "glue:GetTable",
        #             "glue:UpdateTable",
        #         ],
        #         resources=[
        #             f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:catalog",
        #             f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:database/{glue_database.ref}",
        #             f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:table/{glue_database.ref}/*",
        #         ],
        #     )
        # )

        # analytic_handler_lambda = lambda_.Function(
        #     self,
        #     "AnalyticHandler",
        #     function_name="DashboardStack-AnalyticHandler",
        #     runtime=lambda_.Runtime.PYTHON_3_12,
        #     handler="analytic_handler.lambda_handler",
        #     role=analytic_lambda_role,
        #     code=lambda_.Code.from_asset(lambda_code_path),
        #     timeout=Duration.minutes(5),
        #     log_retention=logs.RetentionDays.ONE_WEEK,
        #     environment={
        #         "ATHENA_DATABASE": glue_database.ref,
        #         "ATHENA_OUTPUT_LOCATION": f"s3://{data_stored_bucket.bucket_name}/athena-results/",
        #         "HISTORY_BUCKET_NAME": data_stored_bucket.bucket_name,
        #     },
        # )

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
            },
        )

        # ==================== API GATEWAY ====================
        admin_api = apigw.RestApi(
            self,
            "AdminApi",
            rest_api_name="MeetAssistAdminApi",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=["*"],  # Có thể lock lại sau với CloudFront domain
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=[
                    "Content-Type",
                    "Authorization",
                    "X-Amz-Date",
                    "X-Api-Key",
                    "X-Amz-Security-Token",
                ],
                allow_credentials=True,
                max_age=Duration.hours(1),
            ),
            deploy_options=apigw.StageOptions(
                throttling_rate_limit=100,
                throttling_burst_limit=200,
                # Tắt logging để tránh lỗi CloudWatch Logs role
                # logging_level=apigw.MethodLoggingLevel.INFO,
            ),
        )

        authorizer = apigw.CognitoUserPoolsAuthorizer(
            self, "AdminApiAuthorizer", cognito_user_pools=[user_pool]
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

        # ENDPOINT 2: POST /admin/analytics (COMMENT - CHƯA CẦN TEST)
        # analytics_resource = admin_resource.add_resource("analytics")
        # analytics_resource.add_method(
        #     "POST",
        #     apigw.LambdaIntegration(analytic_handler_lambda),
        #     authorization_type=apigw.AuthorizationType.COGNITO,
        #     authorizer=authorizer,
        # )

        # ==================== OUTPUTS ====================
        CfnOutput(
            self,
            "AdminApiEndpoint",
            value=admin_api.url,
            description="API Gateway endpoint for Admin Backend",
        )

        # CfnOutput(
        #     self,
        #     "AthenaDatabase",
        #     value=glue_database.ref,
        #     description="Glue Database name for Athena",
        # )

        # CfnOutput(
        #     self,
        #     "ArchiveLambdaName",
        #     value=archive_data_lambda.function_name,
        #     description="Archive Lambda function name",
        # )

        # CfnOutput(
        #     self,
        #     "AnalyticLambdaName",
        #     value=analytic_handler_lambda.function_name,
        #     description="Analytic Lambda function name",
        # )

        CfnOutput(
            self,
            "AdminManagerLambdaName",
            value=admin_manager_lambda.function_name,
            description="Admin Manager Lambda function name",
        )
