# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  *
#  * (Giữ nguyên phần license)
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
    aws_glue as glue,
    aws_logs as logs,
    Stack,
    Duration,
    BundlingOptions,
    CfnOutput,
    RemovalPolicy
)
from cdk_nag import NagSuppressions
from constructs import Construct


class AdminStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            vpc: ec2.IVpc,
            security_group: ec2.ISecurityGroup,
            history_data_bucket: s3.IBucket,
            readonly_secret: sm.ISecret,
            **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        lambda_code_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "code"
        )
        
        frontend_asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "admin-dashboard"
        )

        # 1. Cognito User Pool cho Admin (Tạo User Pool trước)
        user_pool = cognito.UserPool(
            self, "AdminUserPool",
            user_pool_name="BookingChatbotAdminPool",
            self_sign_up_enabled=False, 
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            mfa=cognito.Mfa.OPTIONAL,
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True
            ),
            advanced_security_mode=cognito.AdvancedSecurityMode.ENFORCED,  
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,  
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # 2. S3 Bucket cho Frontend
        frontend_bucket = s3.Bucket(
            self, "AdminFrontendBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            # security
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True
        )

        # 3. CloudFront Distribution (Tạo CloudFront TRƯỚC App Client)
        oai = cloudfront.OriginAccessIdentity(
            self, "AdminOAI",
            comment="OAI for Admin Dashboard"
        )

        # Explicit bucket policy - chỉ cho phép OAI
        frontend_bucket.add_to_resource_policy(iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[f"{frontend_bucket.bucket_arn}/*"],
            principals=[iam.CanonicalUserPrincipal(oai.cloud_front_origin_access_identity_s3_canonical_user_id)]
        ))


        distribution = cloudfront.Distribution(
            self, "AdminDistribution",
            default_root_object="index.html", 
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(frontend_bucket, origin_access_identity=oai),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN
            ),
            error_responses=[ 
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(0)
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(0)
                )
            ]
        )
        
        # Deploy frontend (Placeholder, bạn sẽ đổi `sources` sau)
        s3_deployment.BucketDeployment(self, "DeployAdminUI",
            sources=[s3_deployment.Source.data("index.html", "<html><body><h1>Admin Dashboard Placeholder</h1></body></html>")],
            destination_bucket=frontend_bucket,
            distribution=distribution,
            distribution_paths=["/*"], 
        )


        # Lấy URL của CloudFront vừa tạo
        cloudfront_url = f"https://{distribution.distribution_domain_name}"
        
        # 4. Cognito App Client (Tạo SAU CloudFront)
        user_pool_client = user_pool.add_client(
            "AdminAppClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True, implicit_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                # Tự động điền URL thật, không cần placeholder
                callback_urls=[cloudfront_url, f"{cloudfront_url}/callback"], 
                logout_urls=[cloudfront_url, f"{cloudfront_url}/logout"]
            ),
            supported_identity_providers=[cognito.UserPoolClientIdentityProvider.COGNITO]
        )


        # 5A. GLUE DATABASE
        glue_database = glue.CfnDatabase(
            self, "ChatHistoryDatabase",
            catalog_id=Stack.of(self).account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name="chatbot_history",
                description="Chatbot conversation history database"
            )
        )

        # 5B. GLUE TABLE (định nghĩa schema cho S3 JSON data)
        glue_table = glue.CfnTable(
            self, "ConversationsTable",
            catalog_id=Stack.of(self).account,
            database_name=glue_database.ref,
            table_input=glue.CfnTable.TableInputProperty(
                name="conversations",
                description="Conversation history table",
                table_type="EXTERNAL_TABLE",
                storage_descriptor=glue.CfnTable.StorageDescriptorProperty(
                    columns=[
                        glue.CfnTable.ColumnProperty(name="conversation_id", type="string"),
                        glue.CfnTable.ColumnProperty(name="user_id", type="string"),
                        glue.CfnTable.ColumnProperty(name="timestamp", type="timestamp"),
                        glue.CfnTable.ColumnProperty(name="user_query", type="string"),
                        glue.CfnTable.ColumnProperty(name="sql_generated", type="string"),
                        glue.CfnTable.ColumnProperty(name="query_results", type="string"),
                        glue.CfnTable.ColumnProperty(name="response", type="string"),
                        glue.CfnTable.ColumnProperty(name="status", type="string"),
                        glue.CfnTable.ColumnProperty(name="execution_time_ms", type="int"),
                    ],
                    location=f"s3://{history_data_bucket.bucket_name}/conversations/",
                    input_format="org.apache.hadoop.mapred.TextInputFormat",
                    output_format="org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    serde_info=glue.CfnTable.SerdeInfoProperty(
                        serialization_library="org.openx.data.jsonserde.JsonSerDe",
                        parameters={
                            "paths": "conversation_id,user_id,timestamp,user_query,sql_generated,query_results,response,status,execution_time_ms"
                        }
                    )
                ),
                partition_keys=[
                    glue.CfnTable.ColumnProperty(name="year", type="string"),
                    glue.CfnTable.ColumnProperty(name="month", type="string"),
                    glue.CfnTable.ColumnProperty(name="day", type="string")
                ]
            )
        )

        # 5C. GLUE CRAWLER ROLE
        glue_crawler_role = iam.Role(
            self, "GlueCrawlerRole",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
            ]
        )
        history_data_bucket.grant_read(glue_crawler_role)

        # CloudWatch Logs permissions (cho Crawler logging)
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

        # 5D. GLUE CRAWLER (scan S3 only)
        glue_crawler = glue.CfnCrawler(
            self, "ChatHistoryCrawler",
            name="chatbot-history-crawler",
            role=glue_crawler_role.role_arn,
            database_name=glue_database.ref,
            targets=glue.CfnCrawler.TargetsProperty(
                s3_targets=[
                    glue.CfnCrawler.S3TargetProperty(
                        path=f"s3://{history_data_bucket.bucket_name}/conversations/"
                    )
                ]
            ),
            schema_change_policy=glue.CfnCrawler.SchemaChangePolicyProperty(
                update_behavior="UPDATE_IN_DATABASE",
                delete_behavior="LOG"
            )
        )

        # 5E. GLUE HANDLER LAMBDA (NGOÀI VPC - chỉ trigger Glue API)
        glue_handler_role = iam.Role(
            self, "GlueHandlerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        
        glue_handler_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:StartCrawler", "glue:GetCrawler"],
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


        # 5. Lambda 'AdminManager'
        admin_lambda_role = iam.Role(
            self, "AdminManagerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole")
            ]
        )
        
        # (Thêm các quyền IAM Policy cho S3, Athena, Glue... như cũ)
        admin_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[readonly_secret.secret_arn]
        ))
        admin_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"],
            resources=[
                history_data_bucket.bucket_arn,
                f"{history_data_bucket.bucket_arn}/conversations/*"
            ]
        ))
        # Separate permission for Athena results (write-only)
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
        admin_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:GetDatabase","glue:GetTable", "glue:GetPartitions"],
            resources=[f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:catalog",
                f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:database/{glue_database.ref}",
                f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:table/{glue_database.ref}/conversations"]
        ))
        # (Kết thúc phần quyền)

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
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "HISTORY_BUCKET_NAME": history_data_bucket.bucket_name,
                "SECRET_NAME": readonly_secret.secret_name,
                "ATHENA_DATABASE": glue_database.ref,  
                "ATHENA_OUTPUT_LOCATION": f"s3://{history_data_bucket.bucket_name}/athena-results/",  
                "GLUE_TABLE_NAME": "conversations"  
            },
        )
        
        # 6. API Gateway cho Admin
        admin_api = apigw.RestApi(
            self, "AdminApi",
            rest_api_name="BookingChatbotAdminApi",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=[cloudfront_url],  # Chỉ cho phép CloudFront domain
                allow_methods=["POST", "OPTIONS"],  # Chỉ cần POST và OPTIONS
                allow_headers=["Content-Type", "Authorization"],
                max_age=Duration.hours(1)
            )
        )

        # Cognito Authorizer
        authorizer = apigw.CognitoUserPoolsAuthorizer(self, "AdminApiAuthorizer",
            cognito_user_pools=[user_pool]
        )
        # Endpoint: POST /admin
        api_resource = admin_api.root.add_resource("admin")        
        api_resource.add_method(
            "POST",
            apigw.LambdaIntegration(admin_manager_lambda),
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer
        )
        # Endpoint: POST /crawler
        crawler_resource = admin_api.root.add_resource("crawler")
        crawler_resource.add_method(
            "POST",
            apigw.LambdaIntegration(glue_handler_lambda),
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer
        )

        # 7. Outputs
        CfnOutput(self, "CognitoUserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "CognitoAppClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, "CloudFrontURL", value=cloudfront_url) # Output ra URL thật
        CfnOutput(self, "AdminApiEndpoint", value=admin_api.url)
        CfnOutput(self, "AthenaDatabase", value=glue_database.ref, description="Glue Database name") 
        CfnOutput(self, "GlueCrawlerName", value=glue_crawler.name, description="Glue Crawler name")  
        CfnOutput(self, "HistoryBucketName", value=history_data_bucket.bucket_name, description="S3 bucket for history")  #
        
        # (NagSuppressions...)