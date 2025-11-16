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
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # 2. S3 Bucket cho Frontend
        frontend_bucket = s3.Bucket(
            self, "AdminFrontendBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True
        )

        # 3. CloudFront Distribution (Tạo CloudFront TRƯỚC App Client)
        oai = cloudfront.OriginAccessIdentity(self, "AdminOAI")
        frontend_bucket.grant_read(oai)

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
            actions=["s3:GetObject", "s3:ListBucket", "s3:PutObject"],
            resources=[
                history_data_bucket.bucket_arn,
                history_data_bucket.bucket_arn + "/*"
            ]
        ))
        admin_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"],
            resources=["*"] 
        ))
        admin_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:GetDatabase", "glue:GetTables", "glue:GetTable", "glue:GetPartition", "glue:GetPartitions"],
            resources=["*"]
        ))
        # (Kết thúc phần quyền)

        admin_manager_lambda = lambda_.Function(
            self,
            "AdminManagerFunction",
            function_name="AdminStack-AdminManagerFunction",
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
                "SECRET_NAME": readonly_secret.secret_name
            },
        )
        
        # 6. API Gateway cho Admin
        admin_api = apigw.RestApi(
            self, "AdminApi",
            rest_api_name="BookingChatbotAdminApi",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS, 
                allow_methods=apigw.Cors.ALL_METHODS
            )
        )
        
        authorizer = apigw.CognitoUserPoolsAuthorizer(self, "AdminApiAuthorizer",
            cognito_user_pools=[user_pool]
        )

        api_resource = admin_api.root.add_resource("admin")
        
        api_resource.add_method(
            "POST",
            apigw.LambdaIntegration(admin_manager_lambda),
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer
        )

        # 7. Outputs
        CfnOutput(self, "CognitoUserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "CognitoAppClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, "CloudFrontURL", value=cloudfront_url) # Output ra URL thật
        CfnOutput(self, "AdminApiEndpoint", value=admin_api.url)
        
        # (NagSuppressions...)