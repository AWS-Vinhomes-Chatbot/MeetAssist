# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  */

import os

from aws_cdk import (
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment, 
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    aws_ec2 as ec2,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_secretsmanager as sm,
    aws_rds as rds,
    aws_glue as glue,
    aws_logs as logs,
    aws_events as events,
    aws_events_targets as targets,
    CustomResource,
    Stack,
    Duration,
    BundlingOptions,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from aws_cdk import aws_certificatemanager as acm

class AdminStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            vpc: ec2.IVpc,
            security_group: ec2.ISecurityGroup,
            history_data_bucket: s3.IBucket,
            readonly_secret: sm.ISecret,
            rds_instance: rds.IDatabaseInstance,
            **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        lambda_code_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "code"
        )
        
        frontend_asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "admin-dashboard"
        )
        
        # ==================== DOMAIN + CERTIFICATE ====================
        # ⭐ COMMENT TẠM thời - dùng khi có domain
        # DOMAIN_NAME = "admin.meetassist.ai"
        # ROOT_DOMAIN = "meetassist.ai"
        
        # hosted_zone = route53.HostedZone.from_lookup(
        #     self, "HostedZone", 
        #     domain_name=ROOT_DOMAIN
        # )
        
        # certificate = acm.DnsValidatedCertificate(
        #     self, "AdminCertificate",
        #     domain_name=DOMAIN_NAME,
        #     hosted_zone=hosted_zone,
        #     region="us-east-1",
        #     validation=acm.CertificateValidation.from_dns()
        # )
        # ==================== COGNITO USER POOL ====================
        user_pool = cognito.UserPool(
            self, "AdminUserPool",
            user_pool_name="MeetAssist-AdminPool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True
            ),
            removal_policy=RemovalPolicy.DESTROY
        )

        user_pool_domain = user_pool.add_domain(
            "CognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"meetassist-admin-{Stack.of(self).account}"
            )
        )

        # ==================== S3 + CLOUDFRONT ====================
        frontend_bucket = s3.Bucket(
            self, "AdminFrontendBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True
        )

        oai = cloudfront.OriginAccessIdentity(
            self, "AdminOAI",
            comment="OAI for Admin Dashboard"
        )
        
        frontend_bucket.add_to_resource_policy(iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[f"{frontend_bucket.bucket_arn}/*"],
            principals=[iam.CanonicalUserPrincipal(
                oai.cloud_front_origin_access_identity_s3_canonical_user_id
            )]
        ))

        distribution = cloudfront.Distribution(
            self, "AdminDistribution",
            default_root_object="index.html",
            #  BỎ domain_names và certificate khi test
            # domain_names=[DOMAIN_NAME],
            # certificate=certificate,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    frontend_bucket,
                    origin_access_identity=oai
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.CORS_WITH_PREFLIGHT,
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html"
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html"
                ),
            ]
        )
        
        #  COMMENT tạm Route53 record
        # route53.ARecord(
        #     self, "AdminAliasRecord",
        #     zone=hosted_zone,
        #     record_name="admin",
        #     target=route53.RecordTarget.from_alias(
        #         route53_targets.CloudFrontTarget(distribution)
        #     )
        # )

        # ==================== COGNITO APP CLIENT ====================
        # Tạo Cognito client SAU KHI đã có CloudFront distribution
        user_pool_client = user_pool.add_client(
            "AdminAppClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=False
                ),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE
                ],
                callback_urls=[
                    "http://localhost:3000/callback"  # Placeholder - sẽ được update bởi Custom Resource
                ],
                logout_urls=[
                    "http://localhost:3000/"
                ]
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.COGNITO
            ],
            generate_secret=False
        )

        # ==================== CUSTOM RESOURCE ====================
        # Tự động update Cognito callback URLs với CloudFront domain
        custom_resource_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "custom_resource"
        )
        
        update_cognito_lambda = lambda_.Function(
            self, "UpdateCognitoCallback",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="update_cognito_callback.handler",
            code=lambda_.Code.from_asset(custom_resource_path),
            timeout=Duration.seconds(60),
            description="Update Cognito User Pool Client callback URLs with CloudFront domain"
        )
        
        update_cognito_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cognito-idp:UpdateUserPoolClient"],
                resources=[user_pool.user_pool_arn]
            )
        )
        
        update_cognito_cr = CustomResource(
            self, "UpdateCognitoCallbackResource",
            service_token=update_cognito_lambda.function_arn,
            properties={
                "UserPoolId": user_pool.user_pool_id,
                "ClientId": user_pool_client.user_pool_client_id,
                "CloudFrontDomain": distribution.distribution_domain_name
            }
        )
        
        # Đảm bảo Custom Resource chạy SAU khi CloudFront và Cognito client đã tạo xong
        update_cognito_cr.node.add_dependency(distribution)
        update_cognito_cr.node.add_dependency(user_pool_client)
        
        s3_deployment.BucketDeployment(
            self, "DeployAdminUI",
            sources=[s3_deployment.Source.asset(frontend_asset_path)],
            destination_bucket=frontend_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
            memory_limit=1024
        )

        # ==================== ARCHIVE DATA LAMBDA ====================
        archive_lambda_role = iam.Role(
            self, "ArchiveDataRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ]
        )
        
        archive_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[readonly_secret.secret_arn]
        ))
        
        archive_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:PutObject"],
            resources=[
                f"{history_data_bucket.bucket_arn}/appointments/*",
                f"{history_data_bucket.bucket_arn}/enrollments/*",
                f"{history_data_bucket.bucket_arn}/program_attendees/*"
            ]
        ))
        
        archive_data_lambda = lambda_.Function(
            self, "ArchiveData",
            function_name="AdminStack-ArchiveData",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="archive_handler.lambda_handler",
            role=archive_lambda_role,
            code=lambda_.Code.from_asset(
                os.path.join(lambda_code_path, "archive_handler"),
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install --platform manylinux2014_x86_64 --target /asset-output " +
                        "--implementation cp --python-version 3.12 --only-binary=:all: " +
                        "--upgrade -r requirements.txt && cp -au . /asset-output"
                    ],
                ),
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[security_group],
            timeout=Duration.minutes(15),
            memory_size=1024,
            log_retention=logs.RetentionDays.ONE_WEEK,
            reserved_concurrent_executions=1,
            environment={
                "SECRET_NAME": readonly_secret.secret_name,
                "RDS_HOST": rds_instance.db_instance_endpoint_address,
                "RDS_PORT": str(rds_instance.db_instance_endpoint_port),
                "RDS_DATABASE": "postgres",
                "HISTORY_BUCKET_NAME": history_data_bucket.bucket_name,
            },
        )
        
        # ==================== EVENTBRIDGE ====================
        archive_schedule = events.Rule(
            self, "DailyArchiveSchedule",
            schedule=events.Schedule.cron(
                minute="0",
                hour="2",
                month="*",
                week_day="*",
                year="*"
            ),
            description="Daily archive RDS data to S3 at 2 AM UTC",
            enabled=True
        )
        
        archive_schedule.add_target(
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
            source_arn=archive_schedule.rule_arn
        )

        # ==================== GLUE DATABASE ====================
        glue_database = glue.CfnDatabase(
            self, "HistoryDatabase",
            catalog_id=Stack.of(self).account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name="meetassist_history",
                description="Historical data from MeetAssist RDS"
            )
        )

        # ==================== ANALYTIC LAMBDA ====================
        analytic_lambda_role = iam.Role(
            self, "AnalyticHandlerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )
        
        analytic_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "s3:GetObject",
                "s3:ListBucket",
                "s3:GetBucketLocation"
            ],
            resources=[
                history_data_bucket.bucket_arn,
                f"{history_data_bucket.bucket_arn}/*"
            ]
        ))
        
        analytic_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:PutObject", "s3:GetObject"],
            resources=[f"{history_data_bucket.bucket_arn}/athena-results/*"]
        ))
        
        analytic_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "athena:StartQueryExecution",
                "athena:GetQueryExecution",
                "athena:GetQueryResults",
                "athena:StopQueryExecution"
            ],
            resources=[
                f"arn:aws:athena:{Stack.of(self).region}:{Stack.of(self).account}:workgroup/primary"
            ]
        ))
        
        analytic_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "glue:GetDatabase",
                "glue:CreateTable",
                "glue:GetTable",
                "glue:UpdateTable"
            ],
            resources=[
                f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:catalog",
                f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:database/{glue_database.ref}",
                f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:table/{glue_database.ref}/*"
            ]
        ))

        analytic_handler_lambda = lambda_.Function(
            self, "AnalyticHandler",
            function_name="AdminStack-AnalyticHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="analytic_handler.lambda_handler",
            role=analytic_lambda_role,
            code=lambda_.Code.from_asset(lambda_code_path),
            timeout=Duration.minutes(5),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "ATHENA_DATABASE": glue_database.ref,
                "ATHENA_OUTPUT_LOCATION": f"s3://{history_data_bucket.bucket_name}/athena-results/",
                "HISTORY_BUCKET_NAME": history_data_bucket.bucket_name
            }
        )

        # ==================== ADMIN MANAGER LAMBDA ====================
        admin_lambda_role = iam.Role(
            self, "AdminManagerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ]
        )
        
        admin_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[readonly_secret.secret_arn]
        ))


        # THÊM PERMISSION WRITE VÀO RDS
        admin_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "rds-db:connect"
            ],
            resources=[
                f"arn:aws:rds-db:{Stack.of(self).region}:{Stack.of(self).account}:dbuser:*/*"
            ]
        ))

        admin_manager_lambda = lambda_.Function(
            self, "AdminManager",
            function_name="AdminStack-AdminManager",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="admin_handler.lambda_handler",
            role=admin_lambda_role,
            code=lambda_.Code.from_asset(
                lambda_code_path,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install --platform manylinux2014_x86_64 --target /asset-output " +
                        "--implementation cp --python-version 3.12 --only-binary=:all: " +
                        "--upgrade -r requirements.txt && cp -au . /asset-output"
                    ]
                ),
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[security_group],
            memory_size=1024,
            timeout=Duration.minutes(5),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "SECRET_NAME": readonly_secret.secret_name,
                "RDS_HOST": rds_instance.db_instance_endpoint_address, 
                "RDS_PORT": str(rds_instance.db_instance_endpoint_port),  
                "RDS_DATABASE": "postgres",
            }
        )
        
        # ==================== API GATEWAY ====================
        admin_api = apigw.RestApi(
            self, "AdminApi",
            rest_api_name="MeetAssistAdminApi",
            default_cors_preflight_options=apigw.CorsOptions(
                # allow_origins=[f"https://{DOMAIN_NAME}"],
                # allow_methods=["GET", "POST", "OPTIONS"],
                # allow_headers=[
                #     "Content-Type",
                #     "Authorization",
                #     "X-Amz-Date",
                #     "X-Api-Key",
                #     "X-Amz-Security-Token"
                # ],
                # allow_credentials=True,
                # max_age=Duration.hours(1)

            # ⭐ ALLOW tất cả origin khi test (SAU NÀY lock lại)
                allow_origins=["*"],  # Hoặc dùng CloudFront domain cụ thể
                
            ),
            deploy_options=apigw.StageOptions(
                throttling_rate_limit=100,
                throttling_burst_limit=200,
                logging_level=apigw.MethodLoggingLevel.INFO,
            )
        )

        authorizer = apigw.CognitoUserPoolsAuthorizer(
            self, "AdminApiAuthorizer",
            cognito_user_pools=[user_pool]
        )
        
        admin_resource = admin_api.root.add_resource("admin")
        
        #  ENDPOINT 1: POST /admin/execute-sql (AdminManager - INSERT vào RDS)
        sql_execute_resource = admin_resource.add_resource("execute-sql")
        sql_execute_resource.add_method(
            "POST",
            apigw.LambdaIntegration(admin_manager_lambda),
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer
        )
        
        #  ENDPOINT 2: POST /admin/analytics (AnalyticHandler - Query Athena)
        analytics_resource = admin_resource.add_resource("analytics")
        analytics_resource.add_method(
            "POST",
            apigw.LambdaIntegration(analytic_handler_lambda),
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer
        )
        # ==================== OUTPUTS ====================
        CfnOutput(
            self, "AdminDashboardURL",
            #  dùng CloudFront domain
            value=f"https://{distribution.distribution_domain_name}",
            description="Admin Dashboard URL"
        )

        CfnOutput(
            self, "CloudFrontDistributionDomain",
            value=distribution.distribution_domain_name,
            description="CloudFront distribution domain"
        )

        CfnOutput(
            self, "CognitoUserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID"
        )

        CfnOutput(
            self, "CognitoAppClientId",
            value=user_pool_client.user_pool_client_id,
            description="Cognito App Client ID"
        )

        CfnOutput(
            self, "CognitoDomain",
            value=user_pool_domain.domain_name,
            description="Cognito Hosted UI Domain"
        )

        CfnOutput(
            self, "AdminApiEndpoint",
            value=admin_api.url,
            description="API Gateway endpoint"
        )

        CfnOutput(
            self, "AthenaDatabase",
            value=glue_database.ref,
            description="Glue Database name for Athena"
        )

        CfnOutput(
            self, "HistoryBucketName",
            value=history_data_bucket.bucket_name,
            description="S3 bucket for historical data"
        )