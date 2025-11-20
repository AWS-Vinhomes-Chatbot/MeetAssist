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
    aws_rds as rds,  # ✅ THÊM
    aws_glue as glue,
    aws_logs as logs,
    aws_events as events,
    aws_events_targets as targets,
    Stack,
    Duration,
    BundlingOptions,
    CfnOutput,
    RemovalPolicy
)
from cdk_nag import NagSuppressions
from constructs import Construct
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
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
        # 1. Định nghĩa domain và certificate
        DOMAIN_NAME = "admin.meetassist.ai"          # THAY BẰNG DOMAIN THỰC CỦA BẠN
        ROOT_DOMAIN = "meetassist.ai"                # domain gốc có Hosted Zone

        hosted_zone = route53.HostedZone.from_lookup(self, "HostedZone", domain_name=ROOT_DOMAIN)

        # ACM Certificate bắt buộc tạo ở us-east-1 cho CloudFront
        certificate = acm.DnsValidatedCertificate(
            self, "AdminCertificate",
            domain_name=DOMAIN_NAME,
            hosted_zone=hosted_zone,
            region="us-east-1",
            validation=acm.CertificateValidation.from_dns()
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

        # 3. CloudFront + OAI
        oai = cloudfront.OriginAccessIdentity(self, "AdminOAI", comment="OAI for Admin Dashboard")
        frontend_bucket.add_to_resource_policy(iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[f"{frontend_bucket.bucket_arn}/*"],
            principals=[iam.CanonicalUserPrincipal(oai.cloud_front_origin_access_identity_s3_canonical_user_id)]
        ))

        distribution = cloudfront.Distribution(
            self, "AdminDistribution",
            default_root_object="index.html",
            domain_names=[DOMAIN_NAME],           # ← giờ đã có biến
            certificate=certificate,              # ← giờ đã có certificate
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(frontend_bucket, origin_access_identity=oai),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.CORS_WITH_PREFLIGHT,
            ),
            additional_behaviors={
                "_next/*": cloudfront.BehaviorOptions(
                    origin=origins.S3Origin(frontend_bucket, origin_access_identity=oai),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                )
            },
            error_responses=[
                cloudfront.ErrorResponse(http_status=403, response_http_status=200, response_page_path="/index.html"),
                cloudfront.ErrorResponse(http_status=404, response_http_status=200, response_page_path="/index.html"),
            ]
        )
        
        # Route53 Alias Record
        route53.ARecord(
            self, "AdminAliasRecord",
            zone=hosted_zone,
            record_name="admin",  # tạo admin.meetassist.ai
            target=route53.RecordTarget.from_alias(targets.CloudFrontTarget(distribution))
        )
        
        # Deploy frontend (Placeholder, bạn sẽ đổi `sources` sau)
        s3_deployment.BucketDeployment(self, "DeployAdminUI",
            sources=[s3_deployment.Source.asset(frontend_asset_path)],  # ← dùng thư mục build thật
            destination_bucket=frontend_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
            memory_limit=1024
        )

        # URL chính thức của Admin Dashboard
        admin_url = f"https://{DOMAIN_NAME}"

        # 4. Cognito App Client (dùng URL thật)
        user_pool_client = user_pool.add_client(
            "AdminAppClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True, implicit_code_grant=False),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                callback_urls=[f"{admin_url}/", f"{admin_url}/callback"],
                logout_urls=[f"{admin_url}/", f"{admin_url}/logout"]
            ),
            supported_identity_providers=[cognito.UserPoolClientIdentityProvider.COGNITO],
            generate_secret=False
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
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
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

        # ❌ XÓA: Glue Table (Crawler sẽ tự tạo)

        # ==================== GLUE CRAWLER ====================
        
        glue_crawler_role = iam.Role(
            self, "GlueCrawlerRole",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
            ]
        )
        
        history_data_bucket.grant_read(glue_crawler_role)

        glue_crawler_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            resources=[
                f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:log-group:/aws-glue/crawlers:*"
            ]
        ))

        glue_crawler = glue.CfnCrawler(
            self, "HistoryCrawler",
            name="meetassist-history-crawler",
            role=glue_crawler_role.role_arn,
            database_name=glue_database.ref,
            targets=glue.CfnCrawler.TargetsProperty(
                s3_targets=[
                    # ✅ FIX: Scan đúng folders
                    glue.CfnCrawler.S3TargetProperty(
                        path=f"s3://{history_data_bucket.bucket_name}/appointments/"
                    ),
                    glue.CfnCrawler.S3TargetProperty(
                        path=f"s3://{history_data_bucket.bucket_name}/enrollments/"
                    ),
                    glue.CfnCrawler.S3TargetProperty(
                        path=f"s3://{history_data_bucket.bucket_name}/program_attendees/"
                    )
                ]
            ),
            schema_change_policy=glue.CfnCrawler.SchemaChangePolicyProperty(
                update_behavior="UPDATE_IN_DATABASE",
                delete_behavior="LOG"
            )
        )

        # ==================== GLUE HANDLER LAMBDA ====================
        
        glue_handler_role = iam.Role(
            self, "GlueHandlerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        
        glue_handler_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:StartCrawler", "glue:GetCrawler", "glue:StopCrawler"],
            resources=[
                f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:crawler/{glue_crawler.name}"
            ]
        ))

        glue_handler_lambda = lambda_.Function(
            self, "GlueHandler",
            function_name="AdminStack-GlueHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="glue_handler.lambda_handler",
            role=glue_handler_role,
            code=lambda_.Code.from_asset(lambda_code_path),
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "CRAWLER_NAME": glue_crawler.name
            }
        )

        # ==================== ADMIN MANAGER LAMBDA ====================
        
        admin_lambda_role = iam.Role(
            self, "AdminManagerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole")
            ]
        )
        
        # ✅ FIX: S3 permissions
        admin_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"],
            resources=[
                history_data_bucket.bucket_arn,
                f"{history_data_bucket.bucket_arn}/*"  
            ]
        ))
        
        admin_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:PutObject", "s3:GetObject"],
            resources=[
                f"{history_data_bucket.bucket_arn}/athena-results/*"
            ]
        ))
        
        admin_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults", "athena:StopQueryExecution"],
            resources=[f"arn:aws:athena:{Stack.of(self).region}:{Stack.of(self).account}:workgroup/primary"] 
        ))
        
        # ✅ FIX: Glue permissions
        admin_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:GetDatabase","glue:GetTable", "glue:GetPartitions"],
            resources=[
                f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:catalog",
                f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:database/{glue_database.ref}",
                f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:table/{glue_database.ref}/*" 
            ]
        ))

        admin_manager_lambda = lambda_.Function(
            self,
            "AdminManager",
            function_name="AdminStack-AdminManager",
            runtime=lambda_.Runtime.PYTHON_3_12,    
            handler="admin_handler.lambda_handler",
            role=admin_lambda_role,
            code=lambda_.Code.from_asset(
                lambda_code_path, 
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --platform manylinux2014_x86_64 --target /asset-output --implementation cp " +
                        "--python-version 3.12 --only-binary=:all: --upgrade -r requirements.txt && cp -au . " +
                        "/asset-output",
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
                "HISTORY_BUCKET_NAME": history_data_bucket.bucket_name,
                "SECRET_NAME": readonly_secret.secret_name,
                "ATHENA_DATABASE": glue_database.ref,  
                "ATHENA_OUTPUT_LOCATION": f"s3://{history_data_bucket.bucket_name}/athena-results/",
            },
        )
        
        # ==================== API GATEWAY ====================
        
        admin_api = apigw.RestApi(
            self, "AdminApi",
            rest_api_name="MeetAssistAdminApi",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=[f"https://{domain_name}"],
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization"],
                allow_credentials=True,
                max_age=Duration.hours(1)
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
        
        # Endpoint: POST /admin/query
        admin_resource = admin_api.root.add_resource("admin")
        query_resource = admin_resource.add_resource("query")
        query_resource.add_method(
            "POST",
            apigw.LambdaIntegration(admin_manager_lambda),
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer
        )
        
        # Endpoint: POST /admin/crawler
        crawler_resource = admin_resource.add_resource("crawler")
        crawler_resource.add_method(
            "POST",
            apigw.LambdaIntegration(glue_handler_lambda),
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer
        )

        # 7. Outputs
        CfnOutput(self, "AdminDashboardURL",
                  value=f"https://{domain_name}",
                  description="URL truy cập Admin Dashboard (custom domain)")

        CfnOutput(self, "CloudFrontDistributionDomain",
                  value=distribution.distribution_domain_name,
                  description="CloudFront domain (dạng d123abc.cloudfront.net)")

        CfnOutput(self, "CognitoUserPoolId",
                  value=user_pool.user_pool_id,
                  description="Cognito User Pool ID – dùng cho aws-exports.ts")

        CfnOutput(self, "CognitoAppClientId",
                  value=user_pool_client.user_pool_client_id,
                  description="Cognito App Client ID – dùng cho aws-exports.ts")

        # Tự động tạo Cognito Domain (không cần hardcode)
        cognito_domain = f"{user_pool.user_pool_name.lower().replace('_', '-')}-auth.auth.{Stack.of(self).region}.amazoncognito.com"
        CfnOutput(self, "CognitoDomain",
                  value=cognito_domain,
                  description="Cognito Hosted UI Domain – dùng cho aws-exports.ts")

        CfnOutput(self, "AdminApiEndpoint",
                  value=admin_api.url,
                  description="API Gateway endpoint cho Admin Dashboard")

        CfnOutput(self, "AthenaDatabase",
                  value=glue_database.ref,
                  description="Glue Database name")

        CfnOutput(self, "GlueCrawlerName",
                  value=glue_crawler.name,
                  description="Glue Crawler name")

        CfnOutput(self, "HistoryBucketName",
                  value=history_data_bucket.bucket_name,
                  description="S3 bucket lưu history chat")
              # (NagSuppressions...)
    
        # 8. Route 53 + Custom Domain + ACM Certificate (bắt buộc để có https://admin.yourdomain.com)

        domain_name = "admin.meetassist.ai"           
        root_domain = "meetassist.ai"                

        # Certificate phải tạo ở us-east-1 trước (dùng CloudFront)
        certificate = acm.DnsValidatedCertificate(
            self, "AdminCertificate",
            domain_name=domain_name,
            hosted_zone=route53.HostedZone.from_lookup(self, "HostedZone", domain_name=root_domain),
            region="us-east-1",        # bắt buộc cho CloudFront
            validation=acm.CertificateValidation.from_dns()
        )

        # Cập nhật CloudFront để dùng custom domain + certificate
        distribution.domain_names = [domain_name]
        distribution.certificate = certificate

        # Route53 Alias Record trỏ về CloudFront
        hosted_zone = route53.HostedZone.from_lookup(self, "Zone", domain_name=root_domain)
        
        route53.ARecord(
            self, "AdminAliasRecord",
            zone=hosted_zone,
            record_name="admin",  # tạo admin.meetassist.ai
            target=route53.RecordTarget.from_alias(targets.CloudFrontTarget(distribution))
        )

        # Cập nhật lại callback URLs của Cognito để dùng domain thật (rất quan trọng!)
        user_pool_client.node.default_child.callback_urls = [f"https://{domain_name}", f"https://{domain_name}/callback"]
        user_pool_client.node.default_child.logout_urls = [f"https://{domain_name}", f"https://{domain_name}/logout"]
        user_pool_client.node.default_child.supported_identity_providers = ["COGNITO"]

        # Cập nhật CORS của API Gateway cũng dùng domain thật
        admin_api.default_cors_preflight_options = apigw.CorsOptions(
            allow_origins=[f"https://{domain_name}"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"],
            max_age=Duration.hours(1)
        )